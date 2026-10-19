"""Velas XAUUSD+ del broker (M15, H4, M5) -> data/frames.pkl. SOLO LECTURA.

!! Correr SOLO con el mercado cerrado (fin de semana). Con el mercado abierto, una
descarga de historial desde MT5 colgo el IPC del terminal ~13 min y dejo al bot sin
datos (docs/memory/mt5-history-download-blocks-bots.md). Para historia larga usar
fetch_dukascopy.py, que no toca MT5.

Une la cache bot_backtesting/data/XAUUSD+_<TF>.csv con lo descargado desde DESDE,
en tramos de 15 dias, contra el terminal ya abierto de la cuenta indicada.
Uso: python -m bot_backtesting.fullsim.fetch_broker <MT5_LOGIN> [DESDE=2026-06-01]
"""
import datetime as dt
import glob
import os
import sys

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from bot_backtesting.fullsim.harness import DATA, ROOT

SYMBOL = "XAUUSD+"


def main():
    login = sys.argv[1]
    start0 = dt.datetime.strptime(sys.argv[2] if len(sys.argv) > 2 else "2026-06-01", "%Y-%m-%d")
    path = glob.glob(rf"C:\MT5_instances\mt5_{login}\terminal64.exe")
    if not path or not mt5.initialize(path=path[0], portable=True, timeout=15000):
        sys.exit(f"No se pudo conectar al terminal de {login}")
    out = {}
    try:
        for name, tf in (("M15", mt5.TIMEFRAME_M15), ("H4", mt5.TIMEFRAME_H4), ("M5", mt5.TIMEFRAME_M5)):
            chunks, start = [], start0
            while start < dt.datetime.now() + dt.timedelta(days=1):
                end = start + dt.timedelta(days=15)
                r = mt5.copy_rates_range(SYMBOL, tf, start, end)
                if r is not None and len(r):
                    chunks.append(pd.DataFrame(r))
                start = end
            df = pd.concat(chunks) if chunks else pd.DataFrame(columns=["time"])
            cache = os.path.join(ROOT, "bot_backtesting", "data", f"{SYMBOL}_{name}.csv")
            if os.path.exists(cache):
                df = pd.concat([pd.read_csv(cache), df])
            df = (df.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)
                  [["time", "open", "high", "low", "close"]])
            out[name] = df
            gaps = np.diff(df.time.values)
            print(name, len(df), pd.to_datetime(df.time.min(), unit="s"), "->", pd.to_datetime(df.time.max(), unit="s"),
                  "huecos > 4 dias:", int((gaps > 4 * 86400).sum()))
    finally:
        mt5.shutdown()
    os.makedirs(DATA, exist_ok=True)
    pd.to_pickle(out, os.path.join(DATA, "frames.pkl"))


if __name__ == "__main__":
    main()
