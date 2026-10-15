"""Tope de supervivencia de la cuenta (spec 2026-10-13-candado-supervivencia §5.1-5.2).

S = cuantos USD (por onza) puede moverse el precio en contra de la posicion NETA
de la cuenta antes de llegar al stop-out:

    S = max(0, equity - so% * margen / 100) / (|neto| * contrato)

Con cesta cubierta (neto ~ 0) S es infinito. Antes de abrir una orden que
AGRANDA el neto, SurvivalGuard.fit() recorta el lote al mayor que mantiene
S >= survival_move_usd, y reparte el cupo entre bots por `equity_weight`.

Las ordenes PROTECTORAS (Hedge Lock / Basket Lock) NUNCA pasan por aqui.
"""

import calendar
import datetime
import math

import MetaTrader5 as mt5

DEFAULTS = {
    "equity_weight": 1.0,           # fraccion del cupo de neto que es de este bot
    "survival_move_usd": 350.0,     # aguante minimo exigido (USD por onza)
    "lock_trigger_usd": 150.0,      # S bajo el cual se pone el candado
    "unlock_rebound_usd": 50.0,     # rebote que afloja el candado
    "risk_hours_utc": "1",          # horas de riesgo fijas en UTC (sesion asiatica, sin DST)
    "risk_hours_ny": "9,10,11",     # horas de riesgo en hora de Nueva York (siguen su DST)
    "lock_dissolve_after_h": 24,
    "lock_dissolve_fraction": 0.34,
    "lock_dissolve_hours_utc": "3,4",
    # Umbrales en movimiento (spec §5.9), en USD por onza
    "basket_arm_move_usd": 0.83,
    "rescue_arm_move_usd": 0.56,
    "min_green_move_usd": 0.33,
    "retrace_min_move_usd": 0.11,
    "retrace_max_move_usd": 5.6,
    "fixed_retrace_move_usd": 0.22,
    "unwind_floor_move_usd": 3.33,
    "rescue_l2_move_usd": 16.7,
    "rescue_l3_move_usd": 44.4,
}

_EPS = 1e-9


def net_lots(positions):
    """Compras - ventas, en lotes."""
    return sum(p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume for p in positions)


def survival_usd(equity, margin, so_pct, net, contract):
    if abs(net) < _EPS:
        return float("inf")
    return max(0.0, equity - so_pct * margin / 100.0) / (abs(net) * contract)


def parse_hours(s):
    out = set()
    for tok in str(s or "").split(","):
        tok = tok.strip()
        if tok.isdigit() and 0 <= int(tok) <= 23:
            out.add(int(tok))
    return out


def _nth_sunday(year, month, n):
    """Dia del mes del n-esimo domingo."""
    first_wd = calendar.weekday(year, month, 1)        # lunes=0 .. domingo=6
    return 1 + (6 - first_wd) % 7 + 7 * (n - 1)


def utc_hour_from_server(ts):
    """Hora UTC (0-23) a partir de un timestamp de hora de servidor.

    El servidor va a Nueva York + 7 h. Nueva York cambia de hora el 2.º domingo
    de marzo 02:00 y el 1.er domingo de noviembre 02:00 (hora local NY). Se
    calcula a mano: Windows no trae tzdata para zoneinfo.
    Verano: NY = UTC-4 => servidor = UTC+3. Invierno: UTC-5 => UTC+2.
    """
    wall = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(ts) - 7 * 3600)
    y = wall.year
    start = datetime.datetime(y, 3, _nth_sunday(y, 3, 2), 2)
    end = datetime.datetime(y, 11, _nth_sunday(y, 11, 1), 2)
    off = 3 if start <= wall < end else 2
    return ((int(ts) - off * 3600) // 3600) % 24


def ny_hour_from_server(ts):
    """Hora local de Nueva York (0-23) desde un timestamp de hora de servidor.

    El servidor va SIEMPRE a Nueva York + 7 h (ver utc_hour_from_server), asi
    que no hace falta calcular el DST: sigue solo el cambio de hora de NY.
    """
    return ((int(ts) - 7 * 3600) // 3600) % 24


class _Snap:
    """Foto de la cuenta para UNA evaluacion: posiciones, equity, margen, stop-out y contrato."""
    __slots__ = ("positions", "equity", "margin", "so", "contract")

    def __init__(self, positions, equity, margin, so, contract):
        self.positions, self.equity, self.margin = positions, equity, margin
        self.so, self.contract = so, contract


def _s_txt(s):
    """S para logs: 'inf' con neto 0, 'n/a' si no se pudo evaluar."""
    if s is None:
        return "n/a"
    if s == float("inf"):
        return "inf"
    return f"{s:.0f}"


class SurvivalGuard:
    """Calcula S y recorta lotes aditivos. Si MT5 no responde (account_info o
    positions_get None) S es DESCONOCIDO (None): nunca se confunde con S=0
    (dispararia un candado en falso) ni con S=inf (dejaria abrir sin tope)."""

    def __init__(self, broker, cfg_provider, logger, own_magic):
        self.b = broker
        self._cfg = cfg_provider
        self.log = logger
        self.own_magic = own_magic
        self._last_logged = {}   # dedupe del BUDGET: label -> tipo ("recorte"/"bloqueo"/...)

    def _p(self, key):
        """Valor de config; None o no numerico cae al DEFAULT (nunca revienta)."""
        val = (self._cfg() or {}).get(key)
        if val is None:
            return DEFAULTS[key]
        return val

    def _f(self, key):
        try:
            return float(self._p(key))
        except (TypeError, ValueError):
            return float(DEFAULTS[key])

    def _target(self):
        """survival_move_usd > 0 (un 0 o negativo dividiria por cero en n_max)."""
        v = self._f("survival_move_usd")
        return v if v > 0 else float(DEFAULTS["survival_move_usd"])

    # --------------------------------------------------------------
    def snapshot(self):
        """UNA lectura de cuenta + posiciones; None si MT5 no respondio."""
        info = self.b.account_snapshot()
        if info is None:
            return None
        pos = self.b.positions_all_checked()
        if pos is None:
            return None
        try:
            return _Snap(pos, float(info.equity), float(info.margin),
                         float(info.margin_so_so), float(self.b.contract_size()))
        except (AttributeError, TypeError, ValueError):
            return None

    @staticmethod
    def _s(snap, delta_net, delta_margin):
        net = net_lots(snap.positions) + delta_net
        margin = max(0.0, snap.margin + delta_margin)
        return survival_usd(snap.equity, margin, snap.so, net, snap.contract)

    def s_with_delta(self, delta_net, delta_margin, snap=None):
        """S tras sumar delta_net al neto y delta_margin al margen. None si desconocido."""
        snap = snap or self.snapshot()
        if snap is None:
            return None
        return self._s(snap, delta_net, delta_margin)

    def s_now(self, snap=None):
        return self.s_with_delta(0.0, 0.0, snap)

    def n_max(self, snap=None):
        """Neto maximo (lotes) de la cuenta que aun aguanta survival_move_usd. None si desconocido."""
        snap = snap or self.snapshot()
        if snap is None:
            return None
        free = max(0.0, snap.equity - snap.so * snap.margin / 100.0)
        return free / (self._target() * snap.contract)

    # --------------------------------------------------------------
    def _budget_log(self, label, kind, msg):
        """BUDGET deduplicado POR ETIQUETA (alternar etiquetas no re-loguea)."""
        if self.log is not None and self._last_logged.get(label) != kind:
            self.log.write("BUDGET", msg, balance=self.b.account_balance())
            self._last_logged[label] = kind

    def fit(self, order_type, requested, label):
        """Mayor lote <= requested que cabe en el tope; 0.0 si no cabe ninguno
        o si la cuenta no se pudo leer (desconocido = bloqueado)."""
        snap = self.snapshot()
        if snap is None:
            self._budget_log(label, "no_evaluable",
                             f"{label} bloqueada: cuenta no evaluable (MT5 sin respuesta). "
                             f"Se reintenta en el proximo tick.")
            return 0.0
        sign = 1.0 if order_type == mt5.ORDER_TYPE_BUY else -1.0
        acct = net_lots(snap.positions)
        if abs(acct + sign * requested) < abs(acct) - _EPS:
            return requested    # reduce el neto: no suma riesgo

        step = self.b.volume_step()
        vmin = self.b.volume_min()
        own = net_lots([p for p in snap.positions if p.magic == self.own_magic])
        cap = self._f("equity_weight") * self.n_max(snap)
        target = self._target()

        def ok(k):
            v = round(k * step, 8)
            if self._s(snap, sign * v, self.b.order_margin(order_type, v)) < target - _EPS:
                return False
            if abs(own + sign * v) > abs(own) + _EPS:
                return abs(own + sign * v) <= cap + _EPS
            return True

        # Busqueda binaria (como _maybe_unlock): S cae y |neto| crece con v, asi
        # que ok(k) es monotona. Acota las llamadas a MT5 (order_calc_margin)
        # a ~log2(k) en vez de una por step en reintentos bloqueados.
        k_req = int(math.floor(requested / step + _EPS))
        kmin = max(1, int(math.ceil(vmin / step - _EPS)))
        chosen = 0.0
        if k_req >= kmin:
            if ok(k_req):
                chosen = round(k_req * step, 8)
            else:
                lo, hi = kmin - 1, k_req          # invariante: ok(hi) falso; lo ok o kmin-1
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if ok(mid):
                        lo = mid
                    else:
                        hi = mid
                if lo >= kmin:
                    chosen = round(lo * step, 8)

        if chosen >= requested - _EPS:
            self._last_logged.pop(label, None)
            return requested
        s_txt = _s_txt(self._s(snap, 0.0, 0.0))
        if chosen > 0:
            kind = "recorte"
            msg = (f"{label} reducida {requested:.2f} → {chosen:.2f} "
                   f"por tope de supervivencia (S={s_txt} $)")
        else:
            kind = "bloqueo"
            msg = (f"{label} bloqueada por tope de supervivencia: no cabe {vmin:.2f} "
                   f"(S={s_txt} $)")
        self._budget_log(label, kind, msg)
        return chosen

    def s_after_close(self, position):
        """S de la cuenta si se cerrara `position` (el margen liberado cuenta). None si desconocido."""
        contrib = position.volume if position.type == mt5.POSITION_TYPE_BUY else -position.volume
        return self.s_with_delta(-contrib, -self.b.order_margin(position.type, position.volume))
