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
    "risk_hours_utc": "1,13,14,15",
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


class SurvivalGuard:
    def __init__(self, broker, cfg_provider, logger, own_magic):
        self.b = broker
        self._cfg = cfg_provider
        self.log = logger
        self.own_magic = own_magic
        self._last_logged = None   # dedupe: (label, tipo)

    def _p(self, key):
        return (self._cfg() or {}).get(key, DEFAULTS[key])

    # --------------------------------------------------------------
    def _so(self):
        return float(self.b.stop_out_levels()[1])

    def s_with_delta(self, delta_net, delta_margin):
        net = net_lots(self.b.positions_all()) + delta_net
        margin = max(0.0, self.b.account_margin() + delta_margin)
        return survival_usd(self.b.account_equity(), margin, self._so(), net,
                            self.b.contract_size())

    def s_now(self):
        return self.s_with_delta(0.0, 0.0)

    def n_max(self):
        """Neto maximo (lotes) de la cuenta que aun aguanta survival_move_usd."""
        free = max(0.0, self.b.account_equity() - self._so() * self.b.account_margin() / 100.0)
        return free / (float(self._p("survival_move_usd")) * self.b.contract_size())

    def _own_net(self):
        return net_lots([p for p in self.b.positions_all() if p.magic == self.own_magic])

    # --------------------------------------------------------------
    def fit(self, order_type, requested, label):
        """Mayor lote <= requested que cabe en el tope; 0.0 si no cabe ninguno."""
        sign = 1.0 if order_type == mt5.ORDER_TYPE_BUY else -1.0
        acct = net_lots(self.b.positions_all())
        if abs(acct + sign * requested) < abs(acct) - _EPS:
            return requested    # reduce el neto: no suma riesgo

        step = self.b.volume_step()
        vmin = self.b.volume_min()
        own = self._own_net()
        cap = float(self._p("equity_weight")) * self.n_max()
        target = float(self._p("survival_move_usd"))
        k = int(math.floor(requested / step + _EPS))
        kmin = max(1, int(math.ceil(vmin / step - _EPS)))
        chosen = 0.0
        while k >= kmin:
            v = round(k * step, 8)
            ok = self.s_with_delta(sign * v, self.b.order_margin(order_type, v)) >= target - _EPS
            if ok and abs(own + sign * v) > abs(own) + _EPS:
                ok = abs(own + sign * v) <= cap + _EPS
            if ok:
                chosen = v
                break
            k -= 1

        if chosen >= requested - _EPS:
            self._last_logged = None
            return requested
        s = self.s_now()
        s_txt = s if s != float("inf") else 0.0
        if chosen > 0:
            key = (label, "recorte")
            msg = (f"{label} reducida {requested:.2f} → {chosen:.2f} "
                   f"por tope de supervivencia (S={s_txt:.0f} $)")
        else:
            key = (label, "bloqueo")
            msg = (f"{label} bloqueada por tope de supervivencia: no cabe {vmin:.2f} "
                   f"(S={s_txt:.0f} $)")
        if self.log is not None and key != self._last_logged:
            self.log.write("BUDGET", msg, balance=self.b.account_balance())
            self._last_logged = key
        return chosen

    def s_after_close(self, position):
        """S de la cuenta si se cerrara `position` (el margen liberado cuenta)."""
        contrib = position.volume if position.type == mt5.POSITION_TYPE_BUY else -position.volume
        return self.s_with_delta(-contrib, -self.b.order_margin(position.type, position.volume))
