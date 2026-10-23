"""Simulacion del M5Engine REAL (bot/strategy_m5.py) sobre velas M5, por tramos de N dias.

Para estudiar donde fallan las entradas del scalper M5 por regimen (scalper / surfer).
Para cada fecha de arranque (cada STEP dias, tramos sin solape) se abre una cuenta nueva
con BALANCE, se corre el motor hasta el fin del tramo y se guarda cada operacion cerrada
con el ESTADO DEL MOTOR AL ENTRAR (regimen, ADX, RSI, ATR, bandas, Gran Hermano, hora...).

Modelo (solo simulacion; bot/ no se toca):
  * Reloj = cierre de cada vela M5 (== primer tick de la siguiente). El motor ve las velas
    M5 cerradas + una vela "viva" sintetica de un tick (o=h=l=c=precio actual), asi la vela
    CERRADA del motor (.iloc[-2]) es la que acaba de cerrar, como en vivo.
  * M15 sin lookahead: velas M15 completas + la vela M15 en curso armada con las M5 ya
    cerradas dentro de ella (Gran Hermano, fractales y ruptura usan .iloc[-1]/[-2]).
  * Mismo broker que race.py (MultiBroker: spread 20 pts, comision 6 $/lote/lado, swap de
    symbol.json); SL intravela con process_bar_sl. Trailing y TimeStop se evaluan al cierre
    de cada vela M5 (en vivo: cada tick).
  * Un solo motor en su magic M5 (config.MAGIC_M5); el vecino M15 no existe (peer net = 0).
    Noticias, alertas, MT5, DB y red desactivados.

Uso (desde la raiz del repo):
  python -m bot_backtesting.fullsim.m5race <etiqueta> [--balance 5000] [--step 120]
         [--from 2021-03-01] [--to 2024-01-01] [--regime both|scalper|surfer]
         [--set clave=valor,...] [--workers 1]
Salida: results/m5race_<etiqueta>.pkl (lista de dicts por tramo).
"""
import argparse
import calendar
import datetime as dt
import os
import pickle
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.harness import (DATA, RESULTS, SYMBOL_SPECS, MultiBroker, View, _NoNews, _Null,
                                             load_symbol, mt5)
from bot import config  # noqa: E402
from bot.strategy_m5 import DEFAULTS, M5Engine  # noqa: E402

MAGIC_M5 = config.MAGIC_M5
MAGIC_M15 = config.MAGIC_M15
M5, M15 = config.TIMEFRAME_M5, config.TIMEFRAME_CORE


# ----------------------------------------------------------------------------------------------
# Velocidad: bot/indicators.py en pandas cuesta ~100 ms por vela en este server. Aqui va una
# replica en numpy de las MISMAS formulas (ewm adjust=False de pandas, Wilder, NaN incluidos) y
# un DataFrame minimo con lo que el motor usa (.iloc, .values, len). Se instala solo en el
# proceso de simulacion (strategy_m5.indicators = FAST); check_parity() la compara con pandas.
# ----------------------------------------------------------------------------------------------
class _Col:
    __slots__ = ("values",)

    def __init__(self, v):
        self.values = v

    @property
    def iloc(self):
        return self

    def __getitem__(self, k):
        return self.values[k]

    def __len__(self):
        return len(self.values)


class _TimeCol(_Col):
    __slots__ = ()

    def __getitem__(self, k):
        return pd.Timestamp(int(self.values[k].astype("int64")), unit="s")


class _Frame:
    __slots__ = ("cols",)

    def __init__(self, t, o, h, l, c):
        self.cols = {"time": _TimeCol(t.astype("datetime64[s]")), "open": _Col(o), "high": _Col(h),
                     "low": _Col(l), "close": _Col(c)}

    def __getitem__(self, k):
        return self.cols[k]

    def __len__(self):
        return len(self.cols["close"].values)


def _ewm(x, alpha):
    """pandas .ewm(alpha=alpha, adjust=False).mean() con ignore_na=False (mismo algoritmo)."""
    out = np.empty(len(x))
    w = np.nan
    old = 1.0
    started = False
    a1 = 1.0 - alpha
    for i, v in enumerate(x.tolist()):
        if v == v:   # no NaN
            if started:
                old *= a1
                w = (old * w + alpha * v) / (old + alpha)
                old = 1.0
            else:
                w, started = v, True
        elif started:
            old *= a1
        out[i] = w
    return out


def _v(x):
    return np.asarray(getattr(x, "values", x), dtype=float)


def _diff(x):
    d = np.empty(len(x))
    d[0] = np.nan
    d[1:] = x[1:] - x[:-1]
    return d


def _tr(df):
    h, l, c = _v(df["high"]), _v(df["low"]), _v(df["close"])
    pc = np.r_[np.nan, c[:-1]]
    return np.fmax(np.fmax(h - l, np.abs(h - pc)), np.abs(l - pc))


def _f_ema(series, span):
    return _Col(_ewm(_v(series), 2.0 / (span + 1.0)))


def _f_atr(df, period=14):
    return _Col(_ewm(_tr(df), 1.0 / period))


def _f_rsi(df, period=14):
    d = _diff(_v(df["close"]))
    with np.errstate(invalid="ignore", divide="ignore"):
        g = np.where(d != d, np.nan, np.maximum(d, 0.0))
        lo = np.where(d != d, np.nan, np.maximum(-d, 0.0))
        ag, al = _ewm(g, 1.0 / period), _ewm(lo, 1.0 / period)
        al = np.where(al == 0, np.nan, al)
        out = 100 - (100 / (1 + ag / al))
    return _Col(np.where(out != out, 100.0, out))


def _f_adx(df, period=14):
    h, l = _v(df["high"]), _v(df["low"])
    up, dn = _diff(h), -_diff(l)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdm = np.where((up > dn) & (up > 0), up, 0.0)
        mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
        a = 1.0 / period
        atr_w = _ewm(_tr(df), a)
        pdi = 100 * _ewm(pdm, a) / atr_w
        mdi = 100 * _ewm(mdm, a) / atr_w
        s = pdi + mdi
        s = np.where(s == 0, np.nan, s)
        dx = 100 * np.abs(pdi - mdi) / s
        out = _ewm(dx, a)
    return _Col(np.where(out != out, 0.0, out))


def _fast_indicators():
    from bot import indicators as I
    return SimpleNamespace(ema=_f_ema, atr=_f_atr, rsi=_f_rsi, adx=_f_adx, true_range=I.true_range,
                           fractal_range=I.fractal_range, check_m15_breakout=I.check_m15_breakout)


def check_parity(n=300, seed=0):
    """Max |fast - pandas| en ventanas reales de 200 velas M5 (ema50, adx14, rsi14, atr14)."""
    from bot import indicators as I
    m5 = _bars()["M5"]
    rng = np.random.default_rng(seed)
    worst = {}
    for s in rng.integers(0, len(m5) - 201, n):
        w = m5.iloc[s:s + 200].reset_index(drop=True)
        fr = _Frame(w.time.values, w.open.values, w.high.values, w.low.values, w.close.values)
        for k, f, g in (("ema", lambda d: I.ema(d["close"], 50), lambda d: _f_ema(d["close"], 50)),
                        ("adx", I.adx, _f_adx), ("rsi", I.rsi, _f_rsi), ("atr", I.atr, _f_atr)):
            diff = np.nanmax(np.abs(f(w).values - g(fr).values))
            worst[k] = max(worst.get(k, 0.0), float(diff))
    return worst


class M5Market:
    """Reloj sobre velas M5 (step i = cierre de la vela i) y rates sin lookahead."""

    def __init__(self, B):
        m5, m15 = B["M5"], B["M15"]
        self.t5 = m5.time.to_numpy(np.int64)
        self.o5, self.h5, self.l5, self.c5 = (m5[c].to_numpy(float) for c in ("open", "high", "low", "close"))
        self.t15 = m15.time.to_numpy(np.int64)
        self.o15, self.h15, self.l15, self.c15 = (m15[c].to_numpy(float) for c in ("open", "high", "low", "close"))
        self.i = 0
        self.current_time = 0
        self.current_price = 0.0
        self.bar_high = self.bar_low = 0.0

    def __len__(self):
        return len(self.t5)

    def step_to(self, i):
        self.i = i
        self.current_time = int(self.t5[i]) + 300
        self.current_price = float(self.c5[i])
        self.bar_high = float(self.h5[i])
        self.bar_low = float(self.l5[i])

    def start_index_for(self, ts):
        """Primer indice M5 cuyo cierre >= ts."""
        return int(np.searchsorted(self.t5 + 300, ts, side="left"))

    @staticmethod
    def _df(t, o, h, l, c):
        return _Frame(t, o, h, l, c)

    def rates(self, tf, count):
        now, px, i = self.current_time, self.current_price, self.i
        if tf == M5:
            lo = max(0, i + 1 - (count - 1))
            sl = slice(lo, i + 1)
            return self._df(np.append(self.t5[sl], now), np.append(self.o5[sl], px), np.append(self.h5[sl], px),
                            np.append(self.l5[sl], px), np.append(self.c5[sl], px))
        if tf == M15:
            hi = int(np.searchsorted(self.t15, now - 900, side="right"))   # velas M15 completas
            lo = max(0, hi - (count - 1))
            open15 = now - now % 900
            j0 = int(np.searchsorted(self.t5, open15, side="left"))
            if j0 <= i:
                po, ph, pl = self.o5[j0], max(self.h5[j0:i + 1].max(), px), min(self.l5[j0:i + 1].min(), px)
            else:
                po = ph = pl = px
            sl = slice(lo, hi)
            return self._df(np.append(self.t15[sl], open15), np.append(self.o15[sl], po),
                            np.append(self.h15[sl], ph), np.append(self.l15[sl], pl), np.append(self.c15[sl], px))
        return None


class M5View(View):
    """Vista del broker para el magic M5 que anota el estado del motor en cada apertura."""

    engine = None
    entry_state = None

    def market_order(self, order_type, lots, comment, sl=0.0, tp=0.0):
        res = super().market_order(order_type, lots, comment, sl, tp)
        E = self.engine
        if E is not None:
            tol = E._dynamic_tolerance(E.adx1, E.close1, E.atr1)
            now = E.now
            self.entry_state[self._b._positions[-1].ticket] = dict(
                regime=E.regime, adx=E.adx1, rsi=E.rsi1, atr=E.atr1, ema=E.ema1,
                close1=E.close1, high1=E.high1, low1=E.low1,
                band_upper=E.ema1 + tol, band_lower=E.ema1 - tol,
                band_w_atr=(2 * tol / E.atr1) if E.atr1 else np.nan,
                bigbro=E.bigbro_bias, brk15=E.brk15, range_high=E.range_high, range_low=E.range_low,
                last_win=E.last_op_was_win, hour=(now // 3600) % 24,
                dow=dt.datetime.fromtimestamp(now, dt.timezone.utc).weekday(),
                sl0=float(sl), sl_dist=abs(self._b._positions[-1].price_open - float(sl)))
        return res


class M5Eng(M5Engine):
    """M5Engine con el feed de datos del simulador; sin noticias, alertas ni red."""

    def __init__(self, view, logger, market):
        super().__init__(view, logger)
        self.market = market
        self.alerts = _Null()
        self.news = _NoNews()
        self.surv.own_magic = MAGIC_M5
        self.gov.peer_magics = (MAGIC_M15,)   # vecino M15 ausente: sin posiciones

    def _fetch_tick(self):
        return SimpleNamespace(time=self.market.current_time)

    def _rates(self, timeframe, count=200, min_bars=60):
        df = self.market.rates(timeframe, count)
        if df is None or len(df) < min_bars:
            return None
        return df


_B = None


def _bars():
    global _B
    if _B is None:
        _B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
    return _B


def _reason(t):
    r = t["close_reason"]
    if r == "SL":
        up = t["close_price"] > t["open_price"]
        good = up if t["side"] == "BUY" else not up
        return "Trail SL" if good else "Initial SL"
    return r


def one_run(args):
    start, end, balance, params, label = args
    from bot import strategy_m5
    from bot.logger import Logger
    strategy_m5.indicators = _fast_indicators()   # solo en este proceso (ver check_parity)
    market = M5Market(_bars())
    log = Logger(enable_file=False, console_print=False)
    br = MultiBroker(market, SYMBOL_SPECS, log, balance, *load_symbol())
    view = M5View(br, MAGIC_M5)
    view.entry_state = {}
    E = M5Eng(view, log, market)
    E.cfg = {**DEFAULTS, "news_enforce": False, **params}
    view.engine = E
    i0, i1 = market.start_index_for(start), market.start_index_for(end)
    min_eq, stop = balance, None
    for i in range(i0, min(i1, len(market))):
        market.step_to(i)
        br.apply_swap()
        br.process_bar_sl(); br.mark_to_market()
        E.on_tick()
        br.mark_to_market()
        eq = br.account_equity()
        min_eq = min(min_eq, eq)
        if SYMBOL_SPECS.get("stop_out_level") and br.margin_level() < SYMBOL_SPECS["stop_out_level"]:
            br.liquidate(); stop = market.current_time
            break
    br.close_all_eot()
    pt, tv = SYMBOL_SPECS["point"], SYMBOL_SPECS["tick_value"]
    trades = []
    for t in br.closed_trades:
        sgn = 1 if t["side"] == "BUY" else -1
        gross = (t["close_price"] - t["open_price"]) * sgn / pt * tv * t["volume"]
        spread = SYMBOL_SPECS["spread_points"] * tv * t["volume"]
        st = view.entry_state.get(t["ticket"], {})
        trades.append(dict(
            ticket=t["ticket"], open_time=t["open_time"], close_time=t["close_time"], side=t["side"],
            volume=t["volume"], open_price=t["open_price"], close_price=t["close_price"],
            gross=gross, spread=spread, swap=t["profit"] - gross, commission=t["comm"],
            profit=t["profit"], net=t["profit"] - t["comm"], open_comment=t["open_comment"],
            close_reason=_reason(t), minutes=(t["close_time"] - t["open_time"]) / 60, **st))
    return dict(label=label, start=start, end=end, final=br.account_equity(), min_eq=min_eq, stopout=stop,
                trades=trades)


def _summary(name, df):
    if not len(df):
        return f"{name:<14} trades 0"
    return (f"{name:<14} trades {len(df):5d}  win {100 * (df.net > 0).mean():5.1f}%  net {df.net.sum():9.2f}  "
            f"$/tr {df.net.mean():7.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label"); ap.add_argument("--balance", type=float, default=5000)
    ap.add_argument("--step", type=int, default=120)
    ap.add_argument("--from", dest="d0", default="2021-03-01"); ap.add_argument("--to", dest="d1", default="2024-01-01")
    ap.add_argument("--regime", default="both", choices=("both", "scalper", "surfer"))
    ap.add_argument("--set", default=""); ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    params = {}
    if a.regime == "scalper":
        params.update(m5_use_reversion=True, m5_use_surfer=False)
    elif a.regime == "surfer":
        params.update(m5_use_reversion=False, m5_use_surfer=True)
    for kv in filter(None, a.set.split(",")):
        k, v = kv.split("=", 1)
        params[k] = v.lower() == "true" if v.lower() in ("true", "false") else (
            float(v) if v.replace(".", "", 1).lstrip("-").isdigit() else v)
    ep = lambda s: calendar.timegm(dt.datetime.strptime(s, "%Y-%m-%d").timetuple())
    t0, t1 = ep(a.d0), ep(a.d1)
    jobs = [(s, min(s + a.step * 86400, t1), a.balance, params, a.label) for s in range(t0, t1, a.step * 86400)]
    out = []

    def report(r):
        out.append(r)
        d = pd.DataFrame(r["trades"])
        n = len(d)
        print(a.label, pd.to_datetime(r["start"], unit="s").date(), "->", pd.to_datetime(r["end"], unit="s").date(),
              "trades", n, "win%", round(100 * (d.net > 0).mean(), 1) if n else None,
              "net", round(d.net.sum(), 2) if n else 0, "final", round(r["final"], 2), "min_eq", round(r["min_eq"], 2),
              "STOPOUT" if r["stopout"] else "", flush=True)

    if a.workers <= 1:
        for j in jobs:
            report(one_run(j))
    else:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for r in ex.map(one_run, jobs):
                report(r)
    os.makedirs(RESULTS, exist_ok=True)
    pickle.dump(out, open(os.path.join(RESULTS, f"m5race_{a.label}.pkl"), "wb"))

    df = pd.DataFrame([t for r in out for t in r["trades"]])
    print("\nTOTAL", a.label, "params", params)
    if not len(df):
        print("sin operaciones")
        return
    print(_summary("all", df))
    print(f"  gross(pre-costs) {df.gross.sum() + df.spread.sum():.2f}  spread {df.spread.sum():.2f}  "
          f"commission {df.commission.sum():.2f}  swap {df.swap.sum():.2f}  net {df.net.sum():.2f}")
    print("by regime:")
    for k, g in df.groupby(df["regime"].fillna("?")):
        print(" ", _summary(str(k), g))
    print("by entry:")
    for k, g in df.groupby("open_comment"):
        print(" ", _summary(str(k), g))
    print("by close reason:")
    for k, g in df.groupby("close_reason"):
        print(" ", _summary(str(k), g))
    print("final equity per chunk:", [round(r["final"], 2) for r in out])


if __name__ == "__main__":
    main()
