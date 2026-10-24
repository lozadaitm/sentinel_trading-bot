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
GONE_RECHECK_S = 5        # re-consulta del historial de un ticket ausente
RECONCILE_EVERY_S = 3600  # aviso de posiciones sin pata: al arrancar y cada hora
OPENING_MISS_READS = 5    # lecturas seguidas sin tercios antes de dar por perdida una apertura


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
        self._gone_next = {}      # ticket -> epoch de la proxima consulta de historial
        self._gone_ok = set()     # tickets con cierre confirmado en historial
        self._opening_miss = {}   # id(pata opening) -> lecturas seguidas sin tercios
        self._next_reconcile = 0
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
        """Guarda si hay cambios. False si el guardado fallo (queda pendiente)."""
        if not self._dirty:
            return True
        try:
            self.state.save()
            self._dirty = False
            return True
        except OSError as e:
            self._err("save", f"E2: no se pudo guardar el estado ({e}); "
                              f"se conserva en memoria y se reintenta.")
            return False

    def _err(self, key, msg, price=0.0, lots=0.0, ticket=0):
        """ERROR con throttle por clave (una vez por minuto)."""
        if self.now < self._err_next.get(key, 0):
            return
        self._err_next[key] = self.now + ERR_EVERY_S
        self.log.write("ERROR", msg, price, lots, self.b.account_balance(), ticket=ticket)

    def _ok(self, res):
        """Cierre completado (solo DONE: un DONE_PARTIAL deja resto vivo y se reintenta)."""
        return self.b.shadow or (res is not None and getattr(res, "retcode", None) in OK_RC)

    @staticmethod
    def _filled(res, requested):
        """Volumen ejecutado de una apertura (DONE o DONE_PARTIAL con ticket); 0 si no entro."""
        if res is None or not getattr(res, "order", 0):
            return 0.0
        rc = getattr(res, "retcode", None)
        if rc == mt5.TRADE_RETCODE_DONE:
            return float(getattr(res, "volume", 0) or requested)
        if rc == mt5.TRADE_RETCODE_DONE_PARTIAL:
            return float(getattr(res, "volume", 0) or 0.0)
        return 0.0

    def _gone(self, t):
        """True solo si el historial de MT5 confirma el cierre del ticket (deals OUT
        >= IN). La mera ausencia en una lectura de posiciones NO basta: durante una
        reconexion MT5 puede devolver una lista vacia o corta."""
        if t in self._gone_ok:
            return True
        if self.now < self._gone_next.get(t, 0):
            return False
        self._gone_next[t] = self.now + GONE_RECHECK_S
        try:
            deals = self.b.history_deals_for_position(t) or []
        except Exception:  # noqa: BLE001
            return False
        vin = sum(d.volume for d in deals if d.entry == mt5.DEAL_ENTRY_IN)
        vout = sum(d.volume for d in deals
                   if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY))
        if vout > 0 and vout >= vin - 1e-9:
            self._gone_ok.add(t)
            return True
        return False

    # ==============================================================
    # Tick
    # ==============================================================
    def on_tick(self):
        """Nunca deja escapar una excepcion al bucle de main: se loguea (con
        throttle por tipo) y el siguiente tick vuelve a intentar."""
        try:
            self._tick()
        except Exception as exc:  # noqa: BLE001
            self._err(f"tick:{type(exc).__name__}",
                      f"E2: error en on_tick ({type(exc).__name__}: {exc}); se reintenta.")
            try:
                self._persist()
            except Exception:  # noqa: BLE001
                pass

    def _tick(self):
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
            self._reconcile()
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

    def _tracked(self):
        out = set()
        for e in self.state.legs.values():
            if e.get("status") in ("opening", "open", "locked"):
                out |= {t for t in e.get("thirds", []) if t}
                out |= {t for t, _ in self._locks(e)}
        return out

    def _reconcile(self):
        """Aviso (al arrancar y luego cada hora) de posiciones del magic que no
        gestiona ninguna pata activa: nadie les pondria candado ni salida."""
        if self.now < self._next_reconcile:
            return
        self._next_reconcile = self.now + RECONCILE_EVERY_S
        pos = self.b.positions_checked()
        if pos is None:
            self._next_reconcile = self.now + ERR_EVERY_S
            return
        tracked = self._tracked()
        stray = [p for p in pos if p.ticket not in tracked]
        if stray:
            det = ", ".join(f"#{p.ticket} '{p.comment}' {p.volume:.2f}" for p in stray)
            self.log.write("WARNING", f"E2: {len(stray)} posicion(es) del magic {self.b.magic} "
                                      f"sin pata activa que las gestione: {det}.",
                           balance=self.b.account_balance())

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
                self._close_leg(e, pos, by_ticket, "salida por hora")
                continue
            live, unknown = self._live_thirds(e, by_ticket)
            if e["status"] == "open":
                if not live:
                    if not unknown and not self._leg_positions(e, pos):
                        self._finish(e, "sin tercios vivos")
                    continue
                if self._locks(e) or self._lock_hit(e, tick):
                    self._open_lock(e, live, pos, by_ticket)
                    continue
                self._check_targets(e, tick, by_ticket)
            else:
                if live and not unknown:
                    self._open_lock(e, live, pos, by_ticket)   # completa si quedo corto
                elif not live and not unknown and not self._locks_pending(e, by_ticket) \
                        and not self._leg_positions(e, pos):
                    self._finish(e, "sin posiciones vivas")

    def _live_thirds(self, e, by_ticket):
        """(vivos, dudosos) de los tercios aun no cerrados. Un ticket ausente solo
        se apunta como cerrado si el historial lo confirma; si no, queda dudoso."""
        live, unknown = [], []
        for i, t in enumerate(e["thirds"]):
            if t is None or t in e["closed_thirds"]:
                continue
            if t in by_ticket:
                live.append(by_ticket[t])
            elif self._gone(t):
                e["closed_thirds"].append(t)
                self._dirty = True
                self.log.write("SYSTEM", f"E2 {LEG_NAMES[e['leg']]} T{i + 1}: el ticket #{t} se "
                                         f"cerro fuera del motor (confirmado en historial).", ticket=t)
            else:
                unknown.append(t)
        return live, unknown

    def _leg_comment(self, e, comment):
        name = LEG_NAMES[e["leg"]]
        return comment.startswith(f"E2 {name} T") or comment == f"E2 Lock {name}"

    def _leg_positions(self, e, pos):
        """Posiciones vivas con comentario de esta pata abiertas desde su entrada."""
        return [p for p in pos if self._leg_comment(e, p.comment or "")
                and int(p.time) >= int(e["entry_epoch"])]

    @staticmethod
    def _locks(e):
        """[[ticket, volumen]] del candado (admite el formato antiguo lock_ticket)."""
        if "locks" not in e:
            t = e.get("lock_ticket")
            e["locks"] = [[t, None]] if t else []
            e.setdefault("closed_locks", [t] if t and e.get("lock_closed") else [])
        e.setdefault("closed_locks", [])
        return e["locks"]

    def _locks_pending(self, e, by_ticket):
        """True si algun ticket del candado sigue vivo o sin cierre confirmado."""
        pending = False
        for t, _ in self._locks(e):
            if t in e["closed_locks"]:
                continue
            if t in by_ticket or not self._gone(t):
                pending = True
            else:
                e["closed_locks"].append(t)
                self._dirty = True
        return pending

    @staticmethod
    def _lock_hit(e, tick):
        if e["side"] == "buy":
            return tick.bid <= e["lock_price"]
        return tick.ask >= e["lock_price"]

    def _open_lock(self, e, live, pos, by_ticket):
        """Abre (o completa) el candado hasta cubrir el volumen de los tercios vivos.
        Un candado ya presente en MT5 (confirmacion tardia) se adopta, no se duplica."""
        name = LEG_NAMES[e["leg"]]
        comment = f"E2 Lock {name}"
        locks = self._locks(e)
        known = {t for t, _ in locks} | {t for t in e["thirds"] if t}
        for p in pos:
            if p.comment == comment and p.ticket not in known \
                    and int(p.time) >= int(e["entry_epoch"]):
                locks.append([p.ticket, float(p.volume)])
                self._dirty = True
                self.log.write("CANDADO", f"Candado {name} adoptado: #{p.ticket} {p.volume:.2f} lotes.",
                               p.price_open, p.volume, self.b.account_balance(), ticket=p.ticket)

        def covered():
            v = 0.0
            for t, vol in locks:
                if t in e["closed_locks"]:
                    continue
                if t in by_ticket:
                    v += by_ticket[t].volume
                else:
                    v += vol if vol is not None else float("inf")
            return v

        target = round(sum(p.volume for p in live), 2)
        need = round(target - covered(), 2)
        if need >= 0.01 - 1e-9:
            otype = mt5.ORDER_TYPE_SELL if e["side"] == "buy" else mt5.ORDER_TYPE_BUY
            res = self.b.market_order(otype, need, comment, sl=0.0, tp=0.0)
            got = need if self.b.shadow else self._filled(res, need)
            if got <= 0:
                rc = getattr(res, "retcode", "sin respuesta del broker")
                self._err(f"lock:{e['leg']}",
                          f"Candado {name} FALLIDO (retcode {rc}) por {need:.2f} lotes. "
                          f"Entrada DESNUDA; se reintenta en cada tick.",
                          e["lock_price"], need)
                return
            tkt = getattr(res, "order", 0) or None
            if tkt:
                locks.append([tkt, round(got, 2)])
            self._dirty = True
            self.log.write("CANDADO", f"Candado {name} abierto: {got:.2f} de {need:.2f} lotes "
                                      f"opuestos a {e['side']}; precio gatillo {e['lock_price']:.2f}. "
                                      f"Perdida congelada hasta la salida.",
                           e["lock_price"], got, self.b.account_balance(), ticket=tkt or 0)
        if locks and not e.get("lock_ticket"):
            e["lock_ticket"] = locks[0][0]
        if covered() >= target - 1e-9 and e["status"] != "locked":
            e["status"] = "locked"
            e["locked_at"] = self.now
            self._dirty = True
        elif e["status"] != "locked":
            self._err(f"lockpart:{e['leg']}", f"Candado {name} PARCIAL: cubre {covered():.2f} de "
                                              f"{target:.2f} lotes; se completa en el proximo tick.")

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

    def _close_leg(self, e, pos, by_ticket, reason):
        """Cierra tercios abiertos, candado y cualquier posicion viva con comentario
        de la pata. closed solo cuando no queda nada vivo ni dudoso."""
        name = LEG_NAMES[e["leg"]]
        all_done = True
        targets = [(t, "third") for t in e["thirds"] if t and t not in e["closed_thirds"]]
        targets += [(t, "lock") for t, _ in self._locks(e) if t not in e["closed_locks"]]
        known = {t for t, _ in targets}
        targets += [(p.ticket, "extra") for p in self._leg_positions(e, pos)
                    if p.ticket not in known]
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
            elif not self._gone(t):
                all_done = False   # ausente sin cierre confirmado: lectura dudosa, se reintenta
                continue
            if kind == "lock":
                e["closed_locks"].append(t)
            elif kind == "third":
                e["closed_thirds"].append(t)
            self._dirty = True
        if all_done:
            self._finish(e, reason)

    def _finish(self, e, reason):
        e["status"] = "closed"
        e["closed_at"] = self.now
        if e.get("locks") and all(t in e.get("closed_locks", []) for t, _ in e["locks"]):
            e["lock_closed"] = True
        self._dirty = True
        self.log.write("CIERRE", f"Pata {LEG_NAMES[e['leg']]} cerrada ({reason}). "
                                 f"P&L total: {e.get('pnl', 0.0):.2f}",
                       balance=self.b.account_balance())

    def _adopt_opening(self, e, pos):
        """Pata que quedo en 'opening' (caida entre envio y guardado): adopta los
        tercios vivos por comentario. Solo la da por omitida tras varias lecturas
        seguidas sin ninguno (una lectura vacia puede ser una reconexion)."""
        name = LEG_NAMES[e["leg"]]
        for i in range(3):
            if e["thirds"][i] is None:
                p = next((p for p in pos if p.comment == f"E2 {name} T{i + 1}"
                          and int(p.time) >= int(e["entry_epoch"])), None)
                if p is not None:
                    e["thirds"][i] = p.ticket
                    e["lots"][i] = float(p.volume)
        fills = {p.ticket: p.price_open for p in pos}
        first = next((t for t in e["thirds"] if t is not None and t in fills), None)
        if first is None:
            k = id(e)
            self._opening_miss[k] = self._opening_miss.get(k, 0) + 1
            if self._opening_miss[k] < OPENING_MISS_READS:
                return
            e["status"] = "skipped"
            e["reason"] = "caida durante la apertura, sin tercios vivos"
            self._dirty = True
            self.log.write("OMITIDA", f"E2 {name}: apertura interrumpida y sin tercios en MT5.")
            return
        self._dirty = True
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
                if str(ev.get("name", "")).strip() == NFP_EVENT_NAME:
                    T = (int(ev["time"]) // sessions.SLOT) * sessions.SLOT
                    if (T + 3600) // DAY == day:
                        out.append(("nfp", T + 3600, T))
                        break
        return out

    @staticmethod
    def _is_bigone_event(name):
        """NFP, IPC o FOMC; los ADP ('ADP Non-Farm Employment Change') no cuentan."""
        name = name.strip()
        return not name.startswith("ADP") and any(w in name for w in BIGONE_EVENT_WORDS)

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
                            and self._is_bigone_event(str(ev.get("name", "")))
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
             "lots": list(lots), "lots_plan": list(lots), "lock_price": None, "tp": [None, None, None],
             "thirds": [None, None, None], "closed_thirds": [], "lock_ticket": None,
             "lock_closed": False, "pnl": 0.0, "status": "opening"}
        k = self.state.put(e)
        self._dirty = True
        if not self._persist():
            # Sin el registro 'opening' en disco, una caida a mitad permitiria reabrir.
            del self.state.legs[k]
            self.log.write("ERROR", f"E2 {name}: no se pudo persistir la apertura; NO se envian "
                                    f"ordenes (se reintenta dentro de la ventana).",
                           balance=balance)
            return

        ref = tick.ask if side == 1 else tick.bid
        spread = tick.ask - tick.bid
        fill = None
        for i in range(3):
            res = self.b.market_order(otype, lots[i], f"E2 {name} T{i + 1}", sl=0.0, tp=0.0)
            got_i = self._filled(res, lots[i])
            if got_i <= 0:
                e["lots"][i] = 0.0
                self.log.write("ERROR", f"E2 {name} T{i + 1} RECHAZADA (retcode "
                                        f"{getattr(res, 'retcode', None)}); no se reintenta.",
                               ref, lots[i], balance)
                continue
            e["thirds"][i] = res.order
            e["lots"][i] = round(got_i, 2)
            if got_i < lots[i] - 1e-9:
                self.log.write("ERROR", f"E2 {name} T{i + 1} ejecucion PARCIAL: {got_i:.2f} de "
                                        f"{lots[i]:.2f} lotes.", ref, got_i, balance, ticket=res.order)
            if fill is None:
                fill = float(getattr(res, "price", 0.0) or 0.0) or ref
        if fill is None:
            e["status"] = "skipped"
            e["reason"] = "ninguna orden de la escalera entro"
            self.log.write("OMITIDA", f"E2 {name}: ninguna de las 3 ordenes entro.", ref, 0, balance)
            return
        self._arm(e, fill)
        self._dirty = True
        got = round(sum(l for l, t in zip(e["lots"], e["thirds"]) if t), 2)
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
        pos = self.b.positions_checked()
        if pos is None:
            self.log.write("ERROR", f"Cierre forzado ({reason}): lectura de posiciones fallida; "
                                    f"se reintenta.", balance=self.b.account_balance())
            return False
        for p in pos:
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
        after = self.b.positions_checked()
        if after is None or after:
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
