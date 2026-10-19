"""Descarga XAUUSD M5 (bid) de Dukascopy 2021-01 -> 2026-01-12, pasa a hora de servidor
(UTC+2 / UTC+3 con el horario de verano de EE. UU., como los brokers MT5) y arma M5/M15/H4.

Sin MT5 (un historial profundo desde MT5 cuelga los terminales en vivo). Requiere
dukascopy-python (se uso 4.0.1 en un venv aparte). Salida: data/frames_duka.pkl.
Uso: python -m bot_backtesting.fullsim.fetch_dukascopy
"""
import os, datetime as dt, pandas as pd, dukascopy_python as d
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
from dukascopy_python.instruments import INSTRUMENT_FX_METALS_XAU_USD as X
parts = []
for y in range(2021, 2027):
    a = dt.datetime(y, 1, 1); b = min(dt.datetime(y + 1, 1, 1), dt.datetime(2026, 1, 12))
    if a >= b: break
    df = d.fetch(X, d.INTERVAL_MIN_5, d.OFFER_SIDE_BID, a, b)
    print(y, len(df), flush=True); parts.append(df)
m5 = pd.concat(parts); m5 = m5[~m5.index.duplicated()].sort_index(); m5.to_pickle(os.path.join(DATA, "duka_raw_m5.pkl"))
ny = m5.index.tz_convert("America/New_York")
off = pd.Series([3 if x.dst().total_seconds() else 2 for x in ny], index=m5.index)
srv = (m5.index.tz_localize(None) + pd.to_timedelta(off.values, unit="h"))
m5 = m5[["open", "high", "low", "close"]].copy(); m5.index = srv
def rs(rule):
    r = m5.resample(rule, label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    r = r.reset_index().rename(columns={"index": "time"}); r["time"] = ((r["time"] - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")).astype("int64")
    return r
out = {"M5": rs("5min"), "M15": rs("15min"), "H4": rs("4h")}
pd.to_pickle(out, os.path.join(DATA, "frames_duka.pkl"))
for k, v in out.items(): print(k, len(v), pd.to_datetime(v.time.iloc[0], unit="s"), pd.to_datetime(v.time.iloc[-1], unit="s"))
