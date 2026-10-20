"""Simulacion de ciclo completo con el SentinelEngine REAL (bot/strategy.py) sobre velas M15.

Piezas comunes de los experimentos de bot_backtesting/fullsim:
  * MultiBroker: SimBroker con swap diario (triple el dia del rollover), deals etiquetados
    por magic y con el comentario de la orden de cierre (el Healer filtra por comentario).
  * View: lo que un motor ve del broker (solo su magic; la cuenta es compartida).
  * Eng: BacktestEngine sin red, alertas ni noticias.
No toca el repo ni MT5. Datos en bot_backtesting/fullsim/data/ (no se versionan).
"""
import datetime as dt
import json
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.environ.get("FULLSIM_DATA") or os.path.join(HERE, "data")
RESULTS = os.path.join(HERE, "results")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import MetaTrader5 as mt5  # noqa: E402
import pandas as pd  # noqa: E402

from bot import config  # noqa: E402
from bot_backtesting.config_bt import SYMBOL_SPECS  # noqa: E402,F401
from bot_backtesting.market import Market  # noqa: E402,F401
from bot_backtesting.sim_broker import SimBroker  # noqa: E402
from bot_backtesting.sim_engine import BacktestEngine  # noqa: E402

MAGIC_A = 100100


class _Null:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _NoNews:
    def check(self, *a, **k):
        return False, None


class MultiBroker(SimBroker):
    """SimBroker con swap diario, deals por magic y comentario de cierre en cada deal."""

    def __init__(self, market, specs, logger, balance, swap_long, swap_short, triple_dow):
        super().__init__(market, specs, logger, balance)
        self.swap_long, self.swap_short, self.triple_dow = swap_long, swap_short, triple_dow
        self._last_day = None

    def _record_close(self, pos, volume, exit_price, reason):
        n, nd = len(self.closed_trades), len(self._deals)
        sw = pos.swap * (volume / pos.volume) if pos.volume > 0 else 0.0   # swap prorrateado
        super()._record_close(pos, volume, exit_price, reason)
        self.balance += sw
        pos.swap -= sw
        d = self._deals[nd]
        self._deals[nd] = SimpleNamespace(ticket=d.ticket, magic=pos.magic, entry=d.entry, profit=d.profit + sw,
                                          time=d.time, volume=d.volume, type=d.type, price=d.price,
                                          comment=reason)
        self.closed_trades[n]["magic"] = pos.magic
        self.closed_trades[n]["profit"] += sw
        self.closed_trades[n]["comm"] = volume * self.specs["commission_per_lot"] * 2

    def apply_swap(self):
        """Rollover a medianoche de servidor (hora del epoch de MT5)."""
        day = self.market.current_time // 86400
        if self._last_day is None:
            self._last_day = day
            return
        if day == self._last_day:
            return
        for d in range(self._last_day + 1, day + 1):
            dow = dt.datetime.fromtimestamp(d * 86400 - 1, dt.timezone.utc).weekday()   # dia que termina
            if dow >= 5:
                continue
            mult = 3 if dow == self.triple_dow else 1
            for p in self._positions:
                pts = self.swap_long if p.type == mt5.POSITION_TYPE_BUY else self.swap_short
                p.swap += pts * self.specs["tick_value"] * p.volume * mult
        self._last_day = day

    def account_equity(self):
        return super().account_equity() + sum(p.swap for p in self._positions)


class View:
    """Lo que un motor ve del broker: solo su magic; la cuenta es compartida."""

    def __init__(self, broker, magic):
        self._b, self.magic = broker, magic

    def __getattr__(self, name):
        return getattr(self._b, name)

    def positions(self):
        return [p for p in self._b._positions if p.magic == self.magic]

    def positions_checked(self):
        return self.positions()

    def positions_all(self):
        return list(self._b._positions)

    def positions_all_checked(self):
        return list(self._b._positions)

    def own_margin(self):
        return self._b.magic_margin(self.magic)

    def market_order(self, order_type, lots, comment, sl=0.0, tp=0.0):
        res = self._b.market_order(order_type, lots, comment, sl, tp)
        self._b._positions[-1].magic = self.magic
        return res


class Eng(BacktestEngine):
    def __init__(self, view, logger, market, magic=MAGIC_A):
        super().__init__(view, logger, market)
        self.alerts = _Null()
        self.news = _NoNews()
        if hasattr(self, "surv"):   # el tope de supervivencia no existe en versiones viejas (main)
            self.surv.own_magic = magic


def net(positions):
    return sum(p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume for p in positions)


def frozen(eng):
    """Ciclo congelado: >= 3 patas, neto 0 y en rojo."""
    pos = eng.b.positions()
    if len(pos) < 3 or abs(net(pos)) > 1e-6:
        return False
    return sum(p.profit + p.swap for p in pos) < 0


def load_frames(name="frames.pkl"):
    """{TIMEFRAME: DataFrame(time, open, high, low, close)} desde data/<name>."""
    fr = pd.read_pickle(os.path.join(DATA, name))
    return {config.TIMEFRAME_CORE: fr["M15"], config.TIMEFRAME_M5: fr["M5"], config.TIMEFRAME_STRUCT: fr["H4"]}


def load_symbol():
    """Swap del simbolo (puntos/lote/noche) y dia del triple: symbol.json versionado."""
    with open(os.path.join(HERE, "symbol.json"), encoding="utf-8") as f:
        m = json.load(f)
    return m["swap_long"], m["swap_short"], m["triple_dow"]
