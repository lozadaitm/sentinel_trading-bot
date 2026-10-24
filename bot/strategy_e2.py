"""SessionEngine: motor e2 «tres patas» (Experimento 2).

Tres operaciones de calendario sobre XAUUSD, en hora del servidor:
  - Big One   : compra a las 01:00, salida 10:00.
  - Momentum  : a las 15:00 si |ret 01:00->15:00| > umbral y s = +-2; salida 21:00.
  - NFP       : T+60 min en la direccion open(T-15) -> precio; salida 96 velas M15 de mercado.

Cada entrada abre una escalera de 3 tercios iguales (T1 por hora; T2 y T3 con
objetivo +2/+3 ATR15 gestionado por el motor). Sin stop loss: la unica
proteccion es el CANDADO (orden opuesta por el volumen abierto) a -1 ATR_D.
A la hora de salida se cierran juntos tercios y candado aunque el neto sea
negativo (decision D1 del usuario). Sin Healer, Profit Banking ni recovery.

Diseno: docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md.
Reglas puras: bot/sessions.py. Persistencia: bot/e2_state.py.

Robustez ante caidas: antes de mandar las ordenes se persiste la pata en estado
'opening' con todo lo calculado; si el proceso muere entre el envio y el
guardado, al reiniciar se adoptan los tercios vivos por comentario en vez de
reabrir (nunca se duplica una entrada).
"""

import math
import os
import shutil

import MetaTrader5 as mt5
import pandas as pd

from . import config, news, sessions
from .e2_state import E2State

DEFAULTS = {
    "e2_risk_pct": 0.08,
    "e2_lock_atrd_mult": 1.0,
    "e2_tp_atr15_mults": (2.0, 3.0),
    "e2_mom_threshold_pct": 0.232,
    "e2_bigone_weight_nontrend": 0.5,
    "e2_bigone_event_weight": 0.5,
    "e2_entry_grace_s": 60,
    "e2_nfp_hold_bars": 96,
    "e2_legs": "bigone,mom,nfp",
}

# Nombre de cada pata en comentarios MT5 y logs.
LEG_NAMES = {"bigone": "BigOne", "mom": "MomUS", "nfp": "NFP"}
LEG_ORDER = ("bigone", "mom", "nfp")

# Eventos que hacen «dia de evento» para la Big One (x0,5 adicional).
BIGONE_EVENT_WORDS = ("Non-Farm", "CPI", "Federal Funds Rate")
NFP_EVENT_NAME = "Non-Farm Employment Change"

STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instances",
    f"e2_state_{config.USER_ID}.json")

ERR_EVERY_S = 60          # un ERROR repetido sale como mucho una vez por minuto
PRUNE_KEEP_DAYS = 10      # patas closed/skipped que se conservan en el archivo
DAY = 86400
OK_RC = (mt5.TRADE_RETCODE_DONE,)


def _is_weekday(day):
    return (day + 3) % 7 < 5


class SessionEngine:
    """Motor e2. Misma forma que M5Engine: on_tick() por tick, close_all(reason)."""

    def __init__(self, broker, logger, state_path=None):
        self.b = broker
        self.log = logger
        self.cfg = {}
        self.hud = {}
        self.is_active = False
        self.close_only = False
        self.user_email = None
        self.initial_balance = None
        self.last_flow_ticket = None
        self.baseline_applied_at = None

        self.state = E2State(state_path or STATE_PATH)
        self.news = news.NewsGuard(config.NEWS_CALENDAR_PATH, logger)
        self.tick = None
        self.now = 0
        self._loaded = False
        self._dirty = False
        self._err_next = {}       # clave -> epoch a partir del cual se puede repetir el ERROR
        self._pruned_day = None

    # ==============================================================
    # Parametros / seams
    # ==============================================================
    def _p(self, key):
        return self.cfg.get(key, DEFAULTS[key])

    def _legs_enabled(self):
        return {x.strip().lower() for x in str(self._p("e2_legs")).split(",") if x.strip()}

    def _fetch_tick(self):
        return mt5.symbol_info_tick(config.SYMBOL)

    def _now(self):
        """Epoch de servidor del ultimo tick."""
        return int(self.tick.time)

    def _rates(self, timeframe, n):
        rates = mt5.copy_rates_from_pos(config.SYMBOL, timeframe, 0, n)
        if rates is None or len(rates) == 0:
            return None
        return pd.DataFrame(rates)   # 'time' queda en epoch de servidor (int)

    def _rates_d1(self, n):
        return self._rates(mt5.TIMEFRAME_D1, n)

    def _rates_m15(self, n):
        return self._rates(mt5.TIMEFRAME_M15, n)

    def _events(self):
        """Eventos USD de importancia HIGH del calendario del NewsGuard."""
        self.news._load(self.now)
        return [e for e in self.news._events
                if e.get("currency") == "USD" and e.get("importance") == "high"]

    # ==============================================================
    # Estado
    # ==============================================================
    def init_history_cursor(self):
        """Compat con main.setup(): carga el estado persistido y nada mas."""
        self._load_state()

    def _load_state(self):
        self._loaded = True
        self.state.load()
        if self.state.load_error:
            bak = self.state.path + ".bak"
            try:
                shutil.copyfile(self.state.path, bak)
                where = f"copia en {bak}"
            except OSError as e:
                where = f"no se pudo copiar a .bak ({e})"
            self.log.write("ERROR", f"E2: archivo de estado ilegible ({self.state.load_error}); "
                                    f"{where}. Se sigue con estado vacio.")

    def _persist(self):
        if not self._dirty:
            return
        try:
            self.state.save()
            self._dirty = False
        except OSError as e:
            self._err("save", f"E2: no se pudo guardar el estado ({e}); "
                              f"se conserva en memoria y se reintenta.")

    def _err(self, key, msg, price=0.0, lots=0.0, ticket=0):
        """ERROR con throttle por clave (una vez por minuto)."""
        if self.now < self._err_next.get(key, 0):
            return
        self._err_next[key] = self.now + ERR_EVERY_S
        self.log.write("ERROR", msg, price, lots, self.b.account_balance(), ticket=ticket)

    def _ok(self, res):
        return self.b.shadow or (res is not None and getattr(res, "retcode", None) in OK_RC)

    # ==============================================================
    # Tick
    # ==============================================================
    def on_tick(self):
        if not self._loaded:
            self._load_state()
        tick = self._fetch_tick()
        if tick is None:
            return
        self.tick = tick
        self.now = int(self._now())
        day = self.now // DAY
        try:
            self._manage(tick)
            if self.is_active and not self.close_only:
                self._entries(tick, day)
            if self._pruned_day != day:
                self._pruned_day = day
                n = len(self.state.legs)
                self.state.prune(day - PRUNE_KEEP_DAYS)
                self._dirty |= len(self.state.legs) != n
        finally:
            self._persist()
        self._update_hud(day)

    # ==============================================================
    # Gestion de las patas vivas
    # ==============================================================
    def _manage(self, tick):
        pending = [e for e in self.state.legs.values()
                   if e.get("status") in ("opening", "open", "locked")]
        if not pending:
            return
        pos = self.b.positions_checked()
        if pos is None:
            self._err("pos", "E2: lectura de posiciones fallida; gestion pospuesta al proximo tick.")
            return
        by_ticket = {p.ticket: p for p in pos}
        for e in pending:
            if e["status"] == "opening":
                self._adopt_opening(e, pos)
                if e["status"] != "open":
                    continue
            if self.now >= e["exit_epoch"]:
                self._close_leg(e, by_ticket, "salida por hora")
                continue
            live = self._live_thirds(e, by_ticket)
            if e["status"] == "open":
                if not live:
                    self._finish(e, "sin tercios vivos")
                    continue
                if self._lock_hit(e, tick):
                    self._open_lock(e, live, pos)
                    continue
                self._check_targets(e, tick, by_ticket)
            elif not live and not self._lock_live(e, by_ticket):
                self._finish(e, "sin posiciones vivas")

    def _live_thirds(self, e, by_ticket):
        """Posiciones vivas de los tercios aun no cerrados. Los que desaparecieron
        fuera del motor (cierre manual) se apuntan como cerrados."""
        live = []
        for i, t in enumerate(e["thirds"]):
            if t is None or t in e["closed_thirds"]:
                continue
            if t in by_ticket:
                live.append(by_ticket[t])
            else:
                e["closed_thirds"].append(t)
                self._dirty = True
                self.log.write("SYSTEM", f"E2 {LEG_NAMES[e['leg']]} T{i + 1}: el ticket #{t} ya no "
                                         f"existe en MT5 (cerrado fuera del motor).", ticket=t)
        return live

    def _lock_live(self, e, by_ticket):
        t = e.get("lock_ticket")
        return bool(t) and not e.get("lock_closed") and t in by_ticket

    @staticmethod
    def _lock_hit(e, tick):
        if e["side"] == "buy":
            return tick.bid <= e["lock_price"]
        return tick.ask >= e["lock_price"]

    def _open_lock(self, e, live, pos):
        name = LEG_NAMES[e["leg"]]
        comment = f"E2 Lock {name}"
        vol = round(sum(p.volume for p in live), 2)
        # Un candado que ya entro (p.ej. el broker confirmo tarde) se adopta, no se duplica.
        own = {t for t in e["thirds"] if t}
        orphan = next((p for p in pos if p.comment == comment and p.ticket not in own
                       and int(p.time) >= int(e["entry_epoch"])), None)
        if orphan is not None:
            res_ticket = orphan.ticket
        else:
            otype = mt5.ORDER_TYPE_SELL if e["side"] == "buy" else mt5.ORDER_TYPE_BUY
            res = self.b.market_order(otype, vol, comment, sl=0.0, tp=0.0)
            if not self._ok(res):
                rc = getattr(res, "retcode", "sin respuesta del broker")
                self._err(f"lock:{e['leg']}",
                          f"Candado {name} FALLIDO (retcode {rc}) por {vol:.2f} lotes. "
                          f"Entrada DESNUDA; se reintenta en cada tick.",
                          e["lock_price"], vol)
                return
            res_ticket = getattr(res, "order", 0) or None
        e["lock_ticket"] = res_ticket
        e["lock_closed"] = False
        e["status"] = "locked"
        e["locked_at"] = self.now
        self._dirty = True
        self.log.write("CANDADO", f"Candado {name} {'adoptado' if orphan else 'abierto'}: "
                                  f"{vol:.2f} lotes opuestos a {e['side']}; precio gatillo "
                                  f"{e['lock_price']:.2f}. Perdida congelada hasta la salida.",
                       e["lock_price"], vol, self.b.account_balance(), ticket=res_ticket or 0)

    def _check_targets(self, e, tick, by_ticket):
        name = LEG_NAMES[e["leg"]]
        for i in (1, 2):
            t = e["thirds"][i]
            tp = e["tp"][i]
            if t is None or tp is None or t in e["closed_thirds"] or t not in by_ticket:
                continue
            hit = tick.bid >= tp if e["side"] == "buy" else tick.ask <= tp
            if not hit:
                continue
            p = by_ticket[t]
            money = p.profit + p.swap
            res = self.b.close_position(p, f"E2 TP {name} T{i + 1}")
            if not self._ok(res):
                self._err(f"tp:{t}", f"E2 {name} T{i + 1}: cierre por objetivo RECHAZADO "
                                     f"(retcode {getattr(res, 'retcode', None)}); se reintenta.",
                          tp, p.volume, ticket=t)
                continue
            e["closed_thirds"].append(t)
            e["pnl"] = e.get("pnl", 0.0) + money
            self._dirty = True
            self.log.write("CIERRE", f"E2 {name} T{i + 1} objetivo {tp:.2f} alcanzado. "
                                     f"PnL: {money:.2f}", tp, p.volume,
                           self.b.account_balance(), ticket=t)

    def _close_leg(self, e, by_ticket, reason):
        """Cierra tercios abiertos y candado. closed solo cuando no queda nada vivo."""
        name = LEG_NAMES[e["leg"]]
        all_done = True
        targets = [(t, "third") for t in e["thirds"] if t and t not in e["closed_thirds"]]
        if e.get("lock_ticket") and not e.get("lock_closed"):
            targets.append((e["lock_ticket"], "lock"))
        for t, kind in targets:
            p = by_ticket.get(t)
            if p is not None:
                money = p.profit + p.swap
                res = self.b.close_position(p, f"E2 Salida {name}")
                if not self._ok(res):
                    all_done = False
                    self._err(f"close:{t}", f"E2 {name}: cierre de #{t} RECHAZADO (retcode "
                                            f"{getattr(res, 'retcode', None)}); se reintenta.",
                              p.price_current, p.volume, ticket=t)
                    continue
                e["pnl"] = e.get("pnl", 0.0) + money
                self.log.write("CIERRE", f"E2 {name} #{t} cerrado ({reason}). PnL: {money:.2f}",
                               p.price_current, p.volume, self.b.account_balance(), ticket=t)
            if kind == "lock":
                e["lock_closed"] = True
            else:
                e["closed_thirds"].append(t)
            self._dirty = True
        if all_done:
            self._finish(e, reason)

    def _finish(self, e, reason):
        e["status"] = "closed"
        e["closed_at"] = self.now
        self._dirty = True
        self.log.write("CIERRE", f"Pata {LEG_NAMES[e['leg']]} cerrada ({reason}). "
                                 f"P&L total: {e.get('pnl', 0.0):.2f}",
                       balance=self.b.account_balance())

    def _adopt_opening(self, e, pos):
        """Pata que quedo en 'opening' (caida entre envio y guardado): adopta los
        tercios vivos por comentario; si no hay ninguno, la da por omitida."""
        name = LEG_NAMES[e["leg"]]
        for i in range(3):
            if e["thirds"][i] is None:
                p = next((p for p in pos if p.comment == f"E2 {name} T{i + 1}"
                          and int(p.time) >= int(e["entry_epoch"])), None)
                if p is not None:
                    e["thirds"][i] = p.ticket
        fills = {p.ticket: p.price_open for p in pos}
        first = next((t for t in e["thirds"] if t is not None), None)
        self._dirty = True
        if first is None:
            e["status"] = "skipped"
            e["reason"] = "caida durante la apertura, sin tercios vivos"
            self.log.write("OMITIDA", f"E2 {name}: apertura interrumpida y sin tercios en MT5.")
            return
        self._arm(e, fills[first])
        self.log.write("SYSTEM", f"E2 {name}: apertura interrumpida recuperada; tercios "
                                 f"adoptados {e['thirds']}.")

    def _arm(self, e, entry_price):
        """Fija precio de entrada, candado y objetivos; deja la pata en 'open'."""
        side = 1 if e["side"] == "buy" else -1
        e["entry_price"] = float(entry_price)
        e["lock_price"] = sessions.lock_trigger(side, entry_price, e["atr_d"],
                                                float(self._p("e2_lock_atrd_mult")))
        tp2, tp3 = sessions.tp_prices(side, entry_price, e["atr15"],
                                      tuple(self._p("e2_tp_atr15_mults")))
        e["tp"] = [None, tp2, tp3]
        e["status"] = "open"

    # ==============================================================
    # Entradas
    # ==============================================================
    def _windows(self, day):
        """[(leg, inicio_ventana, T_evento)] de hoy para las patas activas."""
        legs = self._legs_enabled()
        out = []
        if "bigone" in legs:
            out.append(("bigone", day * DAY + 3600, None))
        if "mom" in legs:
            out.append(("mom", day * DAY + 15 * 3600, None))
        if "nfp" in legs:
            for ev in self._events():
                if NFP_EVENT_NAME in ev.get("name", ""):
                    T = (int(ev["time"]) // sessions.SLOT) * sessions.SLOT
                    if (T + 3600) // DAY == day:
                        out.append(("nfp", T + 3600, T))
                        break
        return out

    def _entries(self, tick, day):
        if not _is_weekday(day):
            return
        grace = int(self._p("e2_entry_grace_s"))
        for leg, start, T in self._windows(day):
            if self.state.entered(leg, day) or self.now < start:
                continue
            if self.now >= start + grace:
                self._skip(leg, start, f"ventana {self._hhmm(start)} pasada sin tick dentro de "
                                       f"los {grace} s")
                continue
            self._try_enter(leg, start, T, tick, day)

    @staticmethod
    def _hhmm(t):
        s = int(t) % DAY
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}"

    def _skip(self, leg, start, reason):
        self.state.put({"leg": leg, "entry_epoch": start, "status": "skipped", "reason": reason})
        self._dirty = True
        self.log.write("OMITIDA", f"E2 {LEG_NAMES[leg]} omitida hoy: {reason}.",
                       balance=self.b.account_balance())

    def _try_enter(self, leg, start, T, tick, day):
        name = LEG_NAMES[leg]
        d1 = self._rates_d1(120)
        m15 = self._rates_m15(200)
        if d1 is None or m15 is None or len(d1) == 0 or len(m15) == 0:
            self._err(f"rates:{leg}", f"E2 {name}: sin velas D1/M15 de MT5; se reintenta "
                                      f"dentro de la ventana.")
            return
        prev = d1[(d1["time"] // DAY) < day]               # sin el dia en formacion
        s = sessions.trend_state(prev["close"].dropna().to_numpy())
        atr_d = sessions.atr_daily(prev["high"].to_numpy(), prev["low"].to_numpy())
        closed = m15[m15["time"] + sessions.SLOT <= self.now]   # sin la vela en formacion
        a15 = sessions.atr15(closed["high"].to_numpy(), closed["low"].to_numpy(),
                             closed["close"].to_numpy())

        def bar_open(t):
            row = m15[m15["time"] == t]
            return float(row["open"].iloc[0]) if len(row) else None

        weight = 1.0
        if leg == "bigone":
            side = 1
            event_day = any(int(ev["time"]) // DAY == day
                            and any(w in ev.get("name", "") for w in BIGONE_EVENT_WORDS)
                            for ev in self._events())
            weight = sessions.bigone_weight(s, event_day,
                                            float(self._p("e2_bigone_weight_nontrend")),
                                            float(self._p("e2_bigone_event_weight")))
            info = f"evento={'si' if event_day else 'no'}"
        elif leg == "mom":
            p01 = bar_open(day * DAY + 3600)
            if p01 is None:
                return self._skip(leg, start, "no hay vela M15 de las 01:00")
            thr = float(self._p("e2_mom_threshold_pct"))
            if sessions.momentum_side(p01, tick.ask, s, thr) == 1:
                side = 1
            elif sessions.momentum_side(p01, tick.bid, s, thr) == -1:
                side = -1
            else:
                return self._skip(leg, start, f"sin senal (p01={p01:.2f}, bid={tick.bid:.2f}, "
                                              f"s={s})")
            info = f"p01={p01:.2f}"
        else:
            ob = bar_open(T - sessions.SLOT)
            if ob is None:
                return self._skip(leg, start, "no hay vela M15 de T-15")
            side = sessions.nfp_side(ob, tick.bid)
            if side == 0:
                return self._skip(leg, start, f"sin senal (open T-15 = bid = {ob:.2f})")
            info = f"open T-15={ob:.2f}"

        balance = self.b.account_balance()
        lots = sessions.ladder_lots(balance, float(self._p("e2_risk_pct")), weight, atr_d,
                                    self.b.volume_step(), self.b.volume_min(), self.b.volume_max())
        if not lots:
            return self._skip(leg, start, f"ATR_D invalido ({atr_d})")
        if not (a15 > 0 and math.isfinite(a15)):
            return self._skip(leg, start, f"ATR15 invalido ({a15})")
        otype = mt5.ORDER_TYPE_BUY if side == 1 else mt5.ORDER_TYPE_SELL
        if not self.b.check_free_margin(sum(lots), otype):
            return self._skip(leg, start, f"margen libre insuficiente para {sum(lots):.2f} lotes")

        e = {"leg": leg, "side": "buy" if side == 1 else "sell", "entry_epoch": self.now,
             "exit_epoch": sessions.exit_epoch(leg, self.now, int(self._p("e2_nfp_hold_bars"))),
             "entry_price": None, "atr_d": atr_d, "atr15": a15, "s": s, "weight": weight,
             "lots": lots, "lock_price": None, "tp": [None, None, None],
             "thirds": [None, None, None], "closed_thirds": [], "lock_ticket": None,
             "lock_closed": False, "pnl": 0.0, "status": "opening"}
        self.state.put(e)
        self._dirty = True
        self._persist()   # antes de enviar: una caida a mitad no duplica la entrada

        ref = tick.ask if side == 1 else tick.bid
        spread = tick.ask - tick.bid
        fill = None
        for i in range(3):
            res = self.b.market_order(otype, lots[i], f"E2 {name} T{i + 1}", sl=0.0, tp=0.0)
            if not self._ok(res) or not getattr(res, "order", 0):
                self.log.write("ERROR", f"E2 {name} T{i + 1} RECHAZADA (retcode "
                                        f"{getattr(res, 'retcode', None)}); no se reintenta.",
                               ref, lots[i], balance)
                continue
            e["thirds"][i] = res.order
            if fill is None:
                fill = float(getattr(res, "price", 0.0) or 0.0) or ref
        if fill is None:
            e["status"] = "skipped"
            e["reason"] = "ninguna orden de la escalera entro"
            self.log.write("OMITIDA", f"E2 {name}: ninguna de las 3 ordenes entro.", ref, 0, balance)
            return
        self._arm(e, fill)
        self._dirty = True
        got = sum(l for l, t in zip(lots, e["thirds"]) if t)
        risk = sessions.effective_risk(got, atr_d, balance) if balance > 0 else float("nan")
        e["effective_risk"] = risk
        self.log.write(
            "APERTURA",
            f"E2 {name} {'COMPRA' if side == 1 else 'VENTA'} {got:.2f} lotes "
            f"({'/'.join(f'{l:.2f}' for l in lots)}); riesgo efectivo {risk * 100:.2f}% "
            f"(peso {weight:g}); s={s}; ATR_D={atr_d:.2f}; ATR15={a15:.2f}; "
            f"spread={spread:.2f}; deslizamiento={(fill - ref) * side:+.2f}; {info}; "
            f"candado {e['lock_price']:.2f}; TP {e['tp'][1]:.2f}/{e['tp'][2]:.2f}; "
            f"salida {self._hhmm(e['exit_epoch'])} (epoch {e['exit_epoch']}).",
            fill, got, balance, ticket=e["thirds"][0] or 0)

    # ==============================================================
    # Cierre forzado (dashboard)
    # ==============================================================
    def close_all(self, reason):
        """Cierra todo lo propio (tercios y candado), verificando retcodes.
        True solo si la instancia quedo plana; si no, el caller reintenta."""
        if self.b.shadow:
            self.log.write("SHADOW", f"CLOSE ALL ({reason}): sin ordenes reales en modo sombra.")
            return True
        total = 0.0
        closed = 0
        for p in self.b.positions():
            money = p.profit + p.swap
            res = self.b.close_position(p, "Close: Forzado (usuario)")
            rc = getattr(res, "retcode", None)
            if rc not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL):
                self.log.write("ERROR", f"Cierre forzado RECHAZADO (retcode {rc}).",
                               p.price_current, p.volume, self.b.account_balance(),
                               ticket=p.ticket)
                continue
            total += money
            closed += 1
            self.log.write("CIERRE", f"Leg cerrado ({reason}). PnL: {money:.2f}",
                           p.price_current, p.volume, self.b.account_balance(), ticket=p.ticket)
        if self.b.positions():
            return False
        for e in self.state.legs.values():
            if e.get("status") in ("opening", "open", "locked"):
                e["status"] = "closed"
                e["closed_at"] = self.now
                e["reason"] = reason
                self._dirty = True
        self._persist()
        if closed:
            self.log.write("EXITO", f"Cierre TOTAL ({reason}). PnL: {total:.2f}",
                           balance=self.b.account_balance())
        return True

    # ==============================================================
    # HUD
    # ==============================================================
    def _update_hud(self, day):
        active = [e for e in self.state.legs.values() if e.get("status") in ("open", "locked")]
        nxt = None
        if _is_weekday(day):
            try:
                for leg, start, _ in self._windows(day):
                    if start >= self.now and not self.state.entered(leg, day):
                        if nxt is None or start < nxt[1]:
                            nxt = (leg, start)
            except Exception:  # noqa: BLE001  (el HUD nunca tumba el tick)
                nxt = None
        self.hud = {
            "next_entry": f"{LEG_NAMES[nxt[0]]} {self._hhmm(nxt[1])}" if nxt else "-",
            "active_legs": [f"{LEG_NAMES[e['leg']]}:{e['status']}" for e in active],
            "effective_risk": sum(e.get("effective_risk") or 0.0 for e in active),
        }
