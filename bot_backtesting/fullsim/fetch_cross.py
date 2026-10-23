"""Series M5 de Dukascopy para ideas entre mercados: oro (con volumen), plata, EURUSD,
indice del dolar y bono del Tesoro de EE. UU. 2021-01 -> 2026-10. Sin MT5.

Pasa a hora de servidor (UTC+2/+3 con el horario de verano de EE. UU., como el broker).
Salida: data/cross_<nombre>.pkl con columnas time (epoch servidor), open, high, low, close, volume.
Requiere dukascopy-python (venv aparte). Uso: python bot_backtesting/fullsim/fetch_cross.py [nombre ...]
"""
import datetime as dt
import os
import sys

import dukascopy_python as d
import dukascopy_python.instruments as I
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SERIES = {
    "xau": I.INSTRUMENT_FX_METALS_XAU_USD,
    "xag": I.INSTRUMENT_FX_METALS_XAG_USD,
    "eurusd": I.INSTRUMENT_FX_MAJORS_EUR_USD,
    "dxy": I.INSTRUMENT_IDX_AMERICA_DOLLAR_IDX_USD,
    "ustbond": I.INSTRUMENT_BND_CFD_USTBOND_TR_USD,
    # indices y otros metales: ¿la deriva de la reapertura / nocturna existe fuera del oro?
    "sp500": I.INSTRUMENT_IDX_AMERICA_E_SANDP_500,
    "nas100": I.INSTRUMENT_IDX_AMERICA_E_NQ_100,
    "dj30": I.INSTRUMENT_IDX_AMERICA_E_D_J_IND,
    "ger40": I.INSTRUMENT_IDX_EUROPE_E_DAAX,
    "uk100": I.INSTRUMENT_IDX_EUROPE_E_FUTSEE_100,
    "jp225": I.INSTRUMENT_IDX_ASIA_E_N225JAP,
    "xpt": I.INSTRUMENT_CMD_METALS_XPT_CMD_USD,
    "copper": I.INSTRUMENT_CMD_METALS_COPPER_CMD_USD,
    # divisas contra el dolar: ¿el dolar se debilita en horario asiatico en todos los cruces?
    "gbpusd": I.INSTRUMENT_FX_MAJORS_GBP_USD,
    "audusd": I.INSTRUMENT_FX_MAJORS_AUD_USD,
    "nzdusd": I.INSTRUMENT_FX_MAJORS_NZD_USD,
    "usdjpy": I.INSTRUMENT_FX_MAJORS_USD_JPY,
    "usdchf": I.INSTRUMENT_FX_MAJORS_USD_CHF,
    "usdcad": I.INSTRUMENT_FX_MAJORS_USD_CAD,
}
START, END = dt.datetime(2021, 1, 1), dt.datetime(2026, 10, 17)


def fetch(name):
    parts = []
    a = START
    while a < END:
        b = min(dt.datetime(a.year + 1, 1, 1), END)
        df = d.fetch(SERIES[name], d.INTERVAL_MIN_5, d.OFFER_SIDE_BID, a, b)
        parts.append(df)
        print(name, a.year, len(df), flush=True)
        a = b
    m5 = pd.concat(parts)
    m5 = m5[~m5.index.duplicated()].sort_index()
    ny = m5.index.tz_convert("America/New_York")
    off = pd.to_timedelta([3 if x.dst().total_seconds() else 2 for x in ny], unit="h")
    m5.index = m5.index.tz_localize(None) + off
    out = m5[["open", "high", "low", "close", "volume"]].reset_index().rename(columns={m5.index.name or "index": "time"})
    out = out.rename(columns={out.columns[0]: "time"})
    out["time"] = ((out["time"] - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")).astype("int64")
    out.to_pickle(os.path.join(DATA, f"cross_{name}.pkl"))
    print(name, "OK", len(out), pd.to_datetime(out.time.iloc[0], unit="s"), "->", pd.to_datetime(out.time.iloc[-1], unit="s"))


if __name__ == "__main__":
    for n in (sys.argv[1:] or SERIES):
        fetch(n)
