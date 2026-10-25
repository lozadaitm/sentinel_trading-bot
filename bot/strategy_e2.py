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
reabrir (nunca se duplica una entrada). Las posiciones e2 que ninguna pata del
estado reclama (archivo perdido o corrupto) se adoptan por comentario al arrancar
y cada hora, y antes de entrar se comprueba que la pata de hoy no este ya en MT5.
Con el estado ilegible no se abren entradas el resto del dia de servidor.

Salvaguardas operativas: sin cuenta hedging no se entra; sin calendario fresco
(< 6 h y que cubra hoy) no hay NFP y la Big One va a peso de dia de evento; en
feriados de EE. UU. (sessions.us_no_entry_day) no entran Momentum ni NFP; si en
horario de mercado no llega un tick nuevo en 60 s se registra ERROR (reloj local).
"""

import math
import os
import shutil
import time

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
UNCONFIRMED_GIVEUP_S = 900   # tras la salida, espera maxima por tickets ausentes sin confirmar
UNCONF_ERR_EVERY_S = 600     # ERROR de ticket sin confirmar: cada 10 min
OPENING_MISS_READS = 5    # lecturas no vacias sin tercios antes de dar por perdida una apertura
CAL_MAX_AGE_S = 6 * 3600     # calendario mas viejo que esto no es fiable (= NewsGuard)
CAL_ERR_EVERY_S = 600        # ERROR de calendario no fiable: cada 10 min
NO_TICK_S = 60               # segundos de reloj sin tick nuevo (en horario de mercado) -> ERROR
NO_TICK_ERR_EVERY_S = 600    # ERROR de "sin ticks": cada 10 min de reloj
HEDGE_RECHECK_S = 3600       # cuenta no hedging: se vuelve a comprobar cada hora
# El broker cotiza desde las 01:00 pero acepta ordenes desde las 01:01: si la primera
# orden vuelve con "mercado cerrado" (10018) la pata se reintenta cada 5 s, hasta 10 min.
MARKET_CLOSED_RC = getattr(mt5, "TRADE_RETCODE_MARKET_CLOSED", 10018)
MARKET_CLOSED_RETRY_S = 600
MARKET_CLOSED_EVERY_S = 5
NFP_LATE_EXIT_S = 19 * 3600 + 45 * 60   # salida NFP en dia de cierre anticipado despues de 19:45


def _is_weekday(day):
    return (day + 3) % 7 < 5


def _parse_mults(v):
    """(m2, m3) desde lista/tupla o texto '2.0,3.0' / '{2,3}' / '[2, 3]'."""
    if isinstance(v, str):
        parts = [x for x in v.strip().strip("{}[]()").split(",") if x.strip()]
    else:
        parts = list(v)
    out = tuple(float(x) for x in parts)
    if len(out) != 2 or not all(math.isfinite(x) and x > 0 for x in out):
        raise ValueError(v)
    return out


def _parse_comment(c):
    """('bigone'|'mom'|'nfp', 'third'|'lock', indice 0..2 o None) del comentario de una
    posicion e2 ('E2 BigOne T1', 'E2 Lock NFP'); None si no es de una pata."""
    c = c or ""
    for leg, name in LEG_NAMES.items():
        if c == f"E2 Lock {name}":
            return leg, "lock", None
        pre = f"E2 {name} T"
        if c.startswith(pre) and c[len(pre):] in ("1", "2", "3"):
            return leg, "third", int(c[len(pre):]) - 1
    return None


class SessionEngine:
    """Motor e2. Misma forma que M5Engine: on_tick() por tick, close_all(reason)."""

    # main.trading_loop corre on_tick aunque no haya fila de bot_config: DEFAULTS
    # completos y las salidas deben cerrarse aunque falte la fila.
    runs_without_cfg = True

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
        self._next_reconcile = 0
        self._pruned_day = None
        self._block_pending = False   # estado ilegible al cargar: bloquear el dia en curso
        self._blocked_day = None      # dia de servidor sin entradas nuevas
        self._mc_retry = {}           # (pata, dia) -> proximo reintento tras "mercado cerrado"
        self._hedging = None          # True/False/None (sin comprobar o lectura fallida)
        self._hedging_next = 0
        self._last_tick_key = None    # (time, bid, ask) del ultimo tick distinto
        self._last_tick_wall = None   # reloj local (time.time) cuando llego
        self._last_tick_srv = None    # epoch de servidor de ese tick
        self._started_wall = None
        self._notick_next = 0.0

    # ==============================================================
    # Parametros / seams
    # ==============================================================
    def _p(self, key):
        """Parametro de bot_config con DEFAULTS: NULL/ausente/invalido -> default,
        y coercion al tipo del default (la fila de Supabase trae lo que trae)."""
        d = DEFAULTS[key]
        v = (self.cfg or {}).get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            return d
        try:
            if key == "e2_tp_atr15_mults":
                return _parse_mults(v)
            if isinstance(d, int):
                x = float(v)
                if not math.isfinite(x):
                    raise ValueError(v)
                return int(x)
            if isinstance(d, float):
                x = float(v)
                if not math.isfinite(x):
                    raise ValueError(v)
                return x
            return str(v)
        except (TypeError, ValueError):
            self._err(f"cfg:{key}", f"E2: bot_config.{key} = {v!r} no es valido; se usa el "
                                    f"valor por defecto {d!r}.", every=3600)
            return d

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

    def _wall(self):
        """Reloj local (no el del servidor): avanza aunque no lleguen ticks."""
        return time.time()

    def _calendar_status(self, day):
        """(fiable, motivo). Fiable = el export del calendario tiene < 6 h y sus
        eventos cubren el dia de servidor `day`."""
        try:
            self.news._load(self.now)
        except Exception as exc:  # noqa: BLE001
            return False, f"error al leer el calendario ({exc})"
        ga = int(self.news._generated_at or 0)
        if ga <= 0:
            return False, "calendario no disponible"
        # Antiguedad en horas de mercado: el exportador sella con la hora del ultimo
        # tick, que el fin de semana se queda en el viernes; el lunes a las 01:00 el
        # calendario no es viejo, solo no se ha refrescado todavia.
        age = sessions.market_seconds(ga, self.now)
        if age > CAL_MAX_AGE_S:
            return False, f"calendario generado hace {age / 3600:.1f} h de mercado"
        evs = self.news._events
        if not evs or not (int(evs[0]["time"]) // DAY <= day <= int(evs[-1]["time"]) // DAY):
            return False, "el calendario no cubre el dia de hoy"
        return True, ""

    def _calendar_ok(self, day, quiet=False):
        ok, why = self._calendar_status(day)
        if not ok and not quiet:
            self._err("calendar", f"E2: calendario de noticias NO fiable ({why}): pata NFP "
                                  f"desactivada y Big One a peso de dia de evento.",
                      every=CAL_ERR_EVERY_S)
        return ok

    def _hedging_ok(self):
        """La escalera y el candado necesitan cuenta hedging. Sin confirmacion
        (cuenta netting o account_info fallida) no se abren entradas."""
        if self._hedging is True:
            return True
        if self._hedging is False and self.now < self._hedging_next:
            return False
        f = getattr(self.b, "is_hedging_account", None)
        try:
            v = f() if f else None
        except Exception:  # noqa: BLE001
            v = None
        if v is True:
            if self._hedging is not None:
                self.log.write("SYSTEM", "E2: cuenta hedging confirmada; entradas habilitadas.")
            self._hedging = True
            return True
        self._hedging = False if v is False else None
        if v is False:
            self._hedging_next = self.now + HEDGE_RECHECK_S
            self._err("hedging", "E2: la cuenta NO es hedging (margin_mode != RETAIL_HEDGING); el "
                                 "candado no puede convivir con los tercios. Entradas BLOQUEADAS.",
                      every=HEDGE_RECHECK_S)
        else:
            self._err("hedging", "E2: no se pudo comprobar el modo de margen de la cuenta; "
                                 "entradas bloqueadas hasta confirmarlo.")
        return False

    def _watch_ticks(self, tick):
        """ERROR (con throttle de reloj local) si en horario de mercado pasan mas de
        NO_TICK_S segundos sin un tick nuevo, o si nunca llega ninguno."""
        wall = self._wall()
        if self._started_wall is None:
            self._started_wall = wall
        if tick is not None:
            key = (int(tick.time), float(tick.bid), float(tick.ask))
            if key != self._last_tick_key:
                self._last_tick_key = key
                self._last_tick_wall = wall
                self._last_tick_srv = int(tick.time)
                return
        ref = self._last_tick_wall if self._last_tick_wall is not None else self._started_wall
        silent = wall - ref
        if silent < NO_TICK_S:
            return
        if self._last_tick_srv is not None \
                and not sessions._is_market_slot(self._last_tick_srv + int(silent)):
            return   # fin de semana o pausa diaria: el silencio es normal
        if wall < self._notick_next:
            return
        self._notick_next = wall + NO_TICK_ERR_EVERY_S
        what = "ningun tick" if self._last_tick_key is None else "ningun tick nuevo"
        self.log.write("ERROR", f"E2: {what} de {config.SYMBOL} en {silent:.0f} s; la gestion "
                                f"(candado, objetivos, salida) esta detenida. Revisar MT5.",
                       balance=self.b.account_balance())

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
            # Sin estado fiable no se sabe que patas entraron hoy: se bloquean las
            # entradas del dia de servidor en curso y las posiciones e2 vivas se
            # adoptan por comentario en la primera reconciliacion (inmediata).
            self._block_pending = True
            self._next_reconcile = 0
            self.log.write("ERROR", f"E2: archivo de estado ilegible ({self.state.load_error}); "
                                    f"{where}. Se sigue con estado vacio: entradas BLOQUEADAS "
                                    f"el resto del dia de hoy y posiciones e2 vivas adoptadas.")

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

    def _err(self, key, msg, price=0.0, lots=0.0, ticket=0, every=ERR_EVERY_S):
        """ERROR con throttle por clave (por defecto una vez por minuto)."""
        if self.now < self._err_next.get(key, 0):
            return
        self._err_next[key] = self.now + every
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
        self._watch_ticks(tick)
        if tick is None:
            return
        self.tick = tick
        self.now = int(self._now())
        day = self.now // DAY
        if self._block_pending:
            self._block_pending = False
            self._blocked_day = day
        try:
            self._manage(tick)
            if self._reconcile():
                self._manage(tick)   # una pata adoptada con la salida ya pasada cierra ya
            hedge_ok = self._hedging_ok()
            if self.is_active and not self.close_only and hedge_ok:
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

    def _claimed(self, p, tracked, active):
        """La posicion la gestiona alguna pata activa (ticket propio, o comentario de
        la pata dentro de su vida: tercio sin confirmar del broker, candado tardio)."""
        return p.ticket in tracked or any(self._leg_comment(e, p.comment or "") and
                                          self._in_span(e, p) for e in active)

    def _reconcile(self):
        """Al arrancar, tras un estado ilegible y luego cada hora: las posiciones del
        magic que no gestiona ninguna pata activa. Las de comentario e2 se ADOPTAN
        (pata minima reconstruida); las demas solo se avisan. Devuelve las adoptadas."""
        if self.now < self._next_reconcile:
            return []
        self._next_reconcile = self.now + RECONCILE_EVERY_S
        pos = self.b.positions_checked()
        if pos is None:
            self._next_reconcile = self.now + ERR_EVERY_S
            return []
        tracked = self._tracked()
        active = [e for e in self.state.legs.values()
                  if e.get("status") in ("opening", "open", "locked")]
        stray = [p for p in pos if not self._claimed(p, tracked, active)]
        orphans = [p for p in stray if _parse_comment(p.comment)]
        other = [p for p in stray if not _parse_comment(p.comment)]
        if other:
            det = ", ".join(f"#{p.ticket} '{p.comment}' {p.volume:.2f}" for p in other)
            self.log.write("WARNING", f"E2: {len(other)} posicion(es) del magic {self.b.magic} "
                                      f"sin pata activa que las gestione: {det}.",
                           balance=self.b.account_balance())
        return self._adopt_orphans(orphans) if orphans else []

    def _adopt_orphans(self, ps):
        """Reconstruye una pata minima por grupo de posiciones e2 sin pata: pata por
        comentario, entrada = la posicion mas antigua del grupo, salida por la regla
        de la pata, lado por el tipo de los tercios, candado si hay posicion 'Lock'."""
        nfp_bars = int(self._p("e2_nfp_hold_bars"))
        groups = []
        # Primero los tercios (por hora): fijan el inicio de cada grupo; luego los candados.
        for p in sorted(ps, key=lambda p: (_parse_comment(p.comment)[1] != "third", int(p.time))):
            leg, kind, _ = _parse_comment(p.comment)
            t = int(p.time)
            g = next((g for g in groups if g["leg"] == leg and g["t0"] <= t < g["exit"]), None)
            if g is None:
                g = {"leg": leg, "t0": t, "exit": sessions.exit_epoch(leg, t, nfp_bars),
                     "thirds": [], "locks": []}
                groups.append(g)
            g["thirds" if kind == "third" else "locks"].append(p)
        adopted = []
        for g in groups:
            name = LEG_NAMES[g["leg"]]
            tickets = [p.ticket for p in g["thirds"] + g["locks"]]
            old = self.state.legs.get(f"{g['leg']}:{g['t0'] // DAY}")
            if old is not None and old.get("status") in ("opening", "open", "locked"):
                self._err(f"adopt:{g['leg']}:{g['t0']}",
                          f"E2 {name}: posiciones sin pata {tickets} pero la pata de ese dia ya "
                          f"esta activa; no se adoptan (revisar a mano).", every=3600)
                continue
            e = self._adopted_leg(g)
            if old is not None:
                e["replaced"] = {"status": old.get("status"), "reason": old.get("reason")}
            self.state.put(e)
            self._dirty = True
            adopted.append(e)
            how = ("candado y objetivos recalculados con el ATR" if e.get("lock_price") is not None
                   else "sin ATR: solo se gestiona la salida (sin candado ni objetivos nuevos)")
            self.log.write("ERROR", f"E2 {name}: pata adoptada desde MT5 (sin registro en el "
                                    f"estado): tercios {[p.ticket for p in g['thirds']]}, candado "
                                    f"{[p.ticket for p in g['locks']]}; lado {e['side']}; entrada "
                                    f"epoch {e['entry_epoch']}; salida {self._hhmm(e['exit_epoch'])} "
                                    f"(epoch {e['exit_epoch']}); {how}; estado {e['status']}.",
                           balance=self.b.account_balance())
        return adopted

    def _adopted_leg(self, g):
        thirds = sorted(g["thirds"], key=lambda p: int(p.time))
        if thirds:
            buy = thirds[0].type == mt5.POSITION_TYPE_BUY
        else:
            buy = g["locks"][0].type == mt5.POSITION_TYPE_SELL
        slots, lots = [None, None, None], [0.0, 0.0, 0.0]
        for p in thirds:
            i = _parse_comment(p.comment)[2]
            if slots[i] is None:
                slots[i], lots[i] = p.ticket, float(p.volume)
        locks = [[p.ticket, float(p.volume)] for p in g["locks"]]
        e = {"leg": g["leg"], "side": "buy" if buy else "sell", "entry_epoch": g["t0"],
             "exit_epoch": g["exit"], "entry_price": None, "atr_d": None, "atr15": None,
             "s": None, "weight": None, "lots": lots, "lots_plan": list(lots),
             "lock_price": None, "tp": [None, None, None], "thirds": slots,
             "closed_thirds": [], "locks": locks, "closed_locks": [],
             "lock_ticket": locks[0][0] if locks else None, "lock_closed": False,
             "pnl": 0.0, "status": "open", "adopted": True}
        atr = self._atr_at(g["t0"]) if thirds else None
        if atr is not None:
            e["atr_d"], e["atr15"] = atr
            self._arm(e, float(thirds[0].price_open))
        else:
            e["no_atr"] = True
            if thirds:
                e["entry_price"] = float(thirds[0].price_open)
        if locks:
            e["status"] = "locked"
            e["locked_at"] = self.now
        return e

    def _atr_at(self, t0):
        """(ATR_D, ATR15) como se habrian calculado al entrar en t0, o None si las
        velas disponibles (120 D1 / 200 M15) no lo permiten."""
        try:
            d1 = self._rates_d1(120)
            m15 = self._rates_m15(200)
        except Exception:  # noqa: BLE001
            return None
        if d1 is None or m15 is None or len(d1) == 0 or len(m15) == 0:
            return None
        prev = d1[(d1["time"] // DAY) < t0 // DAY]
        closed = m15[m15["time"] + sessions.SLOT <= t0]
        if len(prev) < 14 or len(closed) < 14:
            return None
        atr_d = sessions.atr_daily(prev["high"].to_numpy(), prev["low"].to_numpy())
        a15 = sessions.atr15(closed["high"].to_numpy(), closed["low"].to_numpy(),
                             closed["close"].to_numpy())
        if not all(math.isfinite(x) and x > 0 for x in (atr_d, a15)):
            return None
        return atr_d, a15

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
            try:
                self._manage_leg(e, tick, pos, by_ticket)
            except Exception as exc:  # noqa: BLE001  (una pata rota no frena a las demas)
                self._err(f"leg:{e.get('leg')}:{e.get('entry_epoch')}",
                          f"E2: error gestionando la pata {e.get('leg')} (entrada epoch "
                          f"{e.get('entry_epoch')}): {type(exc).__name__}: {exc}; se sigue con "
                          f"las demas y se reintenta.")

    def _manage_leg(self, e, tick, pos, by_ticket):
        if e["status"] == "opening":
            self._adopt_opening(e, pos)
            if e["status"] != "open":
                return
        if self.now >= e["exit_epoch"]:
            self._close_leg(e, pos, by_ticket, "salida por hora")
            return
        self._fill_slots(e, pos)
        live, unknown = self._live_thirds(e, by_ticket)
        live = live + self._extra_thirds(e, pos)
        if e["status"] == "open":
            if not live:
                if not unknown and not self._leg_positions(e, pos):
                    self._finish(e, "sin tercios vivos")
                return
            if self._locks(e) or self._lock_hit(e, tick):
                self._open_lock(e, live, pos, by_ticket)
                return
            self._check_targets(e, tick, by_ticket)
        else:
            if live and not unknown:
                self._open_lock(e, live, pos, by_ticket)   # completa si quedo corto
            elif not live and not unknown:
                if not self._locks_pending(e, by_ticket) and not self._leg_positions(e, pos):
                    self._finish(e, "sin posiciones vivas")
                else:
                    self._warn_lock_excess(e, 0.0, by_ticket)

    def _fill_slots(self, e, pos):
        """Un tercio cuya orden devolvio None/rechazo pero que SI entro (lo muestra
        MT5 con su comentario dentro de la vida de la pata) se adopta en su hueco."""
        name = LEG_NAMES[e["leg"]]
        known = {t for t in e["thirds"] if t} | {t for t, _ in self._locks(e)}
        for i in range(3):
            if e["thirds"][i] is not None:
                continue
            p = next((p for p in pos if p.comment == f"E2 {name} T{i + 1}"
                      and p.ticket not in known and self._in_span(e, p)), None)
            if p is None:
                continue
            e["thirds"][i] = p.ticket
            e["lots"][i] = float(p.volume)
            known.add(p.ticket)
            self._dirty = True
            self.log.write("WARNING", f"E2 {name} T{i + 1}: el broker no confirmo la orden pero "
                                      f"la posicion #{p.ticket} ({p.volume:.2f} lotes) existe; se "
                                      f"adopta y se gestiona.", p.price_open, p.volume,
                           self.b.account_balance(), ticket=p.ticket)

    def _extra_thirds(self, e, pos):
        """Posiciones con comentario de tercio de la pata, dentro de su vida, que no
        ocupan ningun hueco (p.ej. un duplicado): cuentan para el candado y la salida."""
        name = LEG_NAMES[e["leg"]]
        mine = {t for t in e["thirds"] if t}
        return [p for p in pos if (p.comment or "").startswith(f"E2 {name} T")
                and p.ticket not in mine and self._in_span(e, p)]

    def _covered(self, e, by_ticket):
        v = 0.0
        for t, vol in self._locks(e):
            if t in e["closed_locks"]:
                continue
            if t in by_ticket:
                v += by_ticket[t].volume
            else:
                v += vol if vol is not None else float("inf")
        return v

    def _warn_lock_excess(self, e, target, by_ticket):
        """El candado no se reduce solo (decision de diseno): si cubre mas que los
        tercios vivos (cierre externo), se avisa una vez por pata."""
        cov = self._covered(e, by_ticket)
        if cov > target + 0.005 and math.isfinite(cov) and not e.get("lock_excess_warned"):
            e["lock_excess_warned"] = True
            self._dirty = True
            self.log.write("WARNING", f"Candado {LEG_NAMES[e['leg']]}: cubre {cov:.2f} lotes y "
                                      f"los tercios vivos suman {target:.2f} (cierre externo); el "
                                      f"exceso queda como exposicion opuesta hasta la salida.",
                           balance=self.b.account_balance())

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
        return [p for p in pos if self._leg_comment(e, p.comment or "") and self._in_span(e, p)]

    @staticmethod
    def _in_span(e, p):
        """La posicion se abrio dentro de la vida de la pata [entrada, salida): las
        entradas de dias posteriores nunca casan con una pata vieja."""
        t = int(p.time)
        return int(e["entry_epoch"]) <= t < int(e.get("exit_epoch") or e["entry_epoch"] + DAY)

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
        if e.get("lock_price") is None:
            return False   # pata adoptada sin ATR: solo se gestiona la salida
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
            if p.comment == comment and p.ticket not in known and self._in_span(e, p):
                locks.append([p.ticket, float(p.volume)])
                self._dirty = True
                self.log.write("CANDADO", f"Candado {name} adoptado: #{p.ticket} {p.volume:.2f} lotes.",
                               p.price_open, p.volume, self.b.account_balance(), ticket=p.ticket)

        def covered():
            return self._covered(e, by_ticket)

        target = round(sum(p.volume for p in live), 2)
        self._warn_lock_excess(e, target, by_ticket)
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
                          e.get("lock_price") or 0.0, need)
                return
            tkt = getattr(res, "order", 0) or None
            if tkt:
                locks.append([tkt, round(got, 2)])
            self._dirty = True
            trig = e.get("lock_price")
            self.log.write("CANDADO", f"Candado {name} abierto: {got:.2f} de {need:.2f} lotes "
                                      f"opuestos a {e['side']}; precio gatillo "
                                      f"{f'{trig:.2f}' if trig is not None else 'n/d'}. "
                                      f"Perdida congelada hasta la salida.",
                           trig or 0.0, got, self.b.account_balance(), ticket=tkt or 0)
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
        live_failed = False
        unconfirmed = []
        targets = [(t, "third") for t in e["thirds"] if t and t not in e["closed_thirds"]]
        targets += [(t, "lock") for t, _ in self._locks(e) if t not in e["closed_locks"]]
        known = {t for t, _ in targets}
        targets += [(p.ticket, "extra") for p in self._leg_positions(e, pos)
                    if p.ticket not in known]
        had_live = any(t in by_ticket for t, _ in targets)
        for t, kind in targets:
            p = by_ticket.get(t)
            if p is not None:
                money = p.profit + p.swap
                res = self.b.close_position(p, f"E2 Salida {name}")
                if not self._ok(res):
                    all_done = False
                    live_failed = True
                    self._err(f"close:{t}", f"E2 {name}: cierre de #{t} RECHAZADO (retcode "
                                            f"{getattr(res, 'retcode', None)}); se reintenta.",
                              p.price_current, p.volume, ticket=t)
                    continue
                e["pnl"] = e.get("pnl", 0.0) + money
                self.log.write("CIERRE", f"E2 {name} #{t} cerrado ({reason}). PnL: {money:.2f}",
                               p.price_current, p.volume, self.b.account_balance(), ticket=t)
            elif not self._gone(t):
                all_done = False   # ausente sin cierre confirmado: lectura dudosa, se reintenta
                unconfirmed.append(t)
                continue
            if kind == "lock":
                e["closed_locks"].append(t)
            elif kind == "third":
                e["closed_thirds"].append(t)
            self._dirty = True
        if all_done:
            self._finish(e, reason)
            return
        for t in unconfirmed:
            self._err(f"unconf:{t}", f"E2 {name}: ticket #{t} ausente de MT5 y sin cierre "
                                     f"confirmado en el historial tras la salida; se sigue "
                                     f"esperando.", ticket=t, every=UNCONF_ERR_EVERY_S)
        if had_live or live_failed or not unconfirmed:
            # Algo de la pata se vio vivo en esta lectura: la espera vuelve a empezar.
            if "unconfirmed_since" in e or "unconfirmed_reads" in e:
                e.pop("unconfirmed_since", None)
                e.pop("unconfirmed_reads", None)
                self._dirty = True
            return
        if "unconfirmed_since" not in e:
            e["unconfirmed_since"] = self.now
            e["unconfirmed_reads"] = 0
            self._dirty = True
        if pos:
            # Solo cuentan lecturas NO vacias: una lista vacia puede ser una reconexion.
            e["unconfirmed_reads"] = e.get("unconfirmed_reads", 0) + 1
            self._dirty = True
        if e["unconfirmed_reads"] >= OPENING_MISS_READS \
                and self.now - int(e["unconfirmed_since"]) >= UNCONFIRMED_GIVEUP_S:
            # Espera acotada: N lecturas no vacias seguidas sin nada vivo de la pata
            # durante >= 15 min; los tickets dudosos quedan apuntados.
            e["unconfirmed"] = sorted(set(e.get("unconfirmed", [])) | set(unconfirmed))
            self.log.write("WARNING", f"E2 {name}: se da por cerrada sin confirmar en historial "
                                      f"los tickets {e['unconfirmed']} "
                                      f"({e['unconfirmed_reads']} lecturas no vacias y "
                                      f"{(self.now - int(e['unconfirmed_since'])) // 60} min sin "
                                      f"posiciones vivas de la pata).",
                           balance=self.b.account_balance())
            self._finish(e, reason + ", con tickets sin confirmar")

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
                          and self._in_span(e, p)), None)
                if p is not None:
                    e["thirds"][i] = p.ticket
                    e["lots"][i] = float(p.volume)
        fills = {p.ticket: p.price_open for p in pos}
        first = next((t for t in e["thirds"] if t is not None and t in fills), None)
        if first is None:
            # Misma regla que la salida: N lecturas NO vacias (una lista vacia puede
            # ser una reconexion) y >= 15 min desde la primera ausencia; pasada la
            # hora de salida (+15 min) se abandona igual: si aparecen tercios
            # despues, la reconciliacion los adopta y los cierra.
            if "opening_miss_since" not in e:
                e["opening_miss_since"] = self.now
                e["opening_miss_reads"] = 0
            if pos:
                e["opening_miss_reads"] = e.get("opening_miss_reads", 0) + 1
            self._dirty = True
            waited = self.now - int(e["opening_miss_since"])
            late = self.now >= int(e.get("exit_epoch") or 0) + UNCONFIRMED_GIVEUP_S
            if not late and (e["opening_miss_reads"] < OPENING_MISS_READS
                             or waited < UNCONFIRMED_GIVEUP_S):
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
    def _windows(self, day, quiet=False):
        """[(leg, inicio_ventana, T_evento)] de hoy para las patas activas. Sin un
        calendario fiable (fresco y que cubra hoy) la pata NFP no se programa."""
        legs = self._legs_enabled()
        out = []
        if "bigone" in legs:
            out.append(("bigone", day * DAY + 3600, None))
        if "mom" in legs:
            out.append(("mom", day * DAY + 15 * 3600, None))
        if "nfp" in legs and self._calendar_ok(day, quiet=quiet):
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
        if self._blocked_day == day:
            return   # estado ilegible al arrancar hoy: sin entradas nuevas (ERROR ya registrado)
        grace = int(self._p("e2_entry_grace_s"))
        nfp_bars = int(self._p("e2_nfp_hold_bars"))
        for leg, start, T in self._windows(day):
            if self.state.entered(leg, day) or self.now < start:
                continue
            if leg in ("mom", "nfp") and sessions.us_no_entry_day(day):
                self._skip(leg, start, "feriado EE. UU. (o cierre anticipado)")
                continue
            if leg == "nfp":
                ex = sessions.exit_epoch("nfp", start, nfp_bars)
                if sessions.us_no_entry_day(ex // DAY) and ex % DAY > NFP_LATE_EXIT_S:
                    self._skip(leg, start, f"la salida ({self._hhmm(ex)}) cae en feriado EE. UU. "
                                           f"despues de las 19:45")
                    continue
            retry_at = self._mc_retry.get((leg, day))
            if retry_at is not None:
                if self.now >= start + MARKET_CLOSED_RETRY_S:
                    self._skip(leg, start, f"el broker siguio respondiendo 'mercado cerrado' "
                                           f"hasta {self._hhmm(start + MARKET_CLOSED_RETRY_S)}")
                    continue
                if self.now < retry_at:
                    continue
            elif self.now >= start + grace:
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

    def _orphans_today(self, leg, start):
        """Posiciones vivas con comentario de la pata abiertas en la ventana de hoy
        [inicio, salida): si existen, la pata ya entro (estado perdido o caida antes
        del guardado) y NO se abre otra escalera. None si la lectura fallo."""
        pos = self.b.positions_checked()
        if pos is None:
            return None
        end = sessions.exit_epoch(leg, start, int(self._p("e2_nfp_hold_bars")))
        return [p for p in pos if (_parse_comment(p.comment) or (None,))[0] == leg
                and start <= int(p.time) < end]

    def _try_enter(self, leg, start, T, tick, day):
        name = LEG_NAMES[leg]
        dup = self._orphans_today(leg, start)
        if dup is None:
            self._err(f"prepos:{leg}", f"E2 {name}: lectura de posiciones fallida antes de "
                                       f"entrar; no se abre (se reintenta dentro de la ventana).")
            return
        if dup:
            self._err(f"dup:{leg}", f"E2 {name}: ya hay {len(dup)} posicion(es) de la pata de hoy "
                                    f"sin registro en el estado ({[p.ticket for p in dup]}); NO se "
                                    f"abre otra escalera: se adoptan.")
            self._next_reconcile = 0
            self._reconcile()
            if not self.state.entered(leg, day):
                self._skip(leg, start, "posiciones de la pata ya abiertas sin estado")
            return
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
            if self._calendar_ok(day):
                event_day = any(int(ev["time"]) // DAY == day
                                and self._is_bigone_event(str(ev.get("name", "")))
                                for ev in self._events())
                info = f"evento={'si' if event_day else 'no'}"
            else:
                event_day = True   # sin calendario fiable: peso reducido (conservador)
                info = "evento=desconocido (calendario no fiable: peso de dia de evento)"
            weight = sessions.bigone_weight(s, event_day,
                                            float(self._p("e2_bigone_weight_nontrend")),
                                            float(self._p("e2_bigone_event_weight")))
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
            self._err(f"presave:{leg}", f"E2 {name}: no se pudo persistir la apertura; NO se "
                                        f"envian ordenes (se reintenta dentro de la ventana).")
            return

        ref = tick.ask if side == 1 else tick.bid
        spread = tick.ask - tick.bid
        fill = None
        for i in range(3):
            # Tick fresco justo antes de cada orden: deslizamiento y spread por tercio.
            try:
                tk = self._fetch_tick() or tick
            except Exception:  # noqa: BLE001
                tk = tick
            ref_i = tk.ask if side == 1 else tk.bid
            spread_i = tk.ask - tk.bid
            if i == 0:
                ref, spread = ref_i, spread_i
            res = self.b.market_order(otype, lots[i], f"E2 {name} T{i + 1}", sl=0.0, tp=0.0)
            got_i = self._filled(res, lots[i])
            if i == 0 and got_i <= 0 and getattr(res, "retcode", None) == MARKET_CLOSED_RC:
                # Aun no abre la sesion de trading: nada entro, se deshace el registro
                # 'opening' y se reintenta en unos segundos (ver MARKET_CLOSED_RETRY_S).
                del self.state.legs[k]
                self._dirty = True
                self._persist()
                first = (leg, day) not in self._mc_retry
                self._mc_retry[(leg, day)] = self.now + MARKET_CLOSED_EVERY_S
                if first:
                    self.log.write("SYSTEM", f"E2 {name}: el broker aun no acepta ordenes "
                                             f"(retcode {MARKET_CLOSED_RC}, mercado cerrado); se "
                                             f"reintenta cada {MARKET_CLOSED_EVERY_S} s hasta las "
                                             f"{self._hhmm(start + MARKET_CLOSED_RETRY_S)}.",
                                   ref_i, lots[i], balance)
                return
            if got_i <= 0:
                e["lots"][i] = 0.0
                self.log.write("ERROR", f"E2 {name} T{i + 1} RECHAZADA (retcode "
                                        f"{getattr(res, 'retcode', None)}); no se reintenta.",
                               ref_i, lots[i], balance)
                continue
            fill_i = float(getattr(res, "price", 0.0) or 0.0) or ref_i
            self.log.write("SYSTEM", f"E2 {name} T{i + 1} ejecutada: {got_i:.2f} lotes; ref "
                                     f"{ref_i:.2f}; fill {fill_i:.2f}; deslizamiento "
                                     f"{(fill_i - ref_i) * side:+.2f}; spread {spread_i:.2f}.",
                           fill_i, got_i, balance, ticket=res.order)
            e["thirds"][i] = res.order
            e["lots"][i] = round(got_i, 2)
            if got_i < lots[i] - 1e-9:
                self.log.write("ERROR", f"E2 {name} T{i + 1} ejecucion PARCIAL: {got_i:.2f} de "
                                        f"{lots[i]:.2f} lotes.", ref, got_i, balance, ticket=res.order)
            if fill is None:
                fill, ref, spread = fill_i, ref_i, spread_i
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
                for leg, start, _ in self._windows(day, quiet=True):
                    if start >= self.now and not self.state.entered(leg, day):
                        if nxt is None or start < nxt[1]:
                            nxt = (leg, start)
            except Exception:  # noqa: BLE001  (el HUD nunca tumba el tick)
                nxt = None
        self.hud = {
            "next_entry": f"{LEG_NAMES[nxt[0]]} {self._hhmm(nxt[1])}" if nxt else "-",
            "active_legs": [f"{LEG_NAMES.get(e.get('leg'), e.get('leg'))}:{e['status']}"
                            for e in active],
            "effective_risk": sum(e.get("effective_risk") or 0.0 for e in active),
        }
