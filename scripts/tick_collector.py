"""Colector de ticks del broker (solo lectura) para simular con precios reales.

Baja los ticks (bid/ask) de cada dia de servidor y los guarda comprimidos, uno por dia y simbolo, en
bot_backtesting/fullsim/data/ticks/<SIMBOLO>/<AAAA-MM-DD>.pkl.gz (fuera de git). Salta los dias ya
guardados. Ademas resume el spread por minuto del dia en spread_<SIMBOLO>.csv (mediana y maximo).

Pensado para correr con el MERCADO CERRADO (sabado): las descargas profundas contra un terminal vivo
con mercado abierto cuelgan el IPC de los bots (docs/memory/mt5-history-download-blocks-bots.md).
Se conecta en modo portable al terminal ya instalado de la cuenta indicada y no envia ordenes.

Uso: python scripts/tick_collector.py [--login 26275221] [--days 8] [--symbols XAUUSD+] [--since AAAA-MM-DD]
"""
import argparse
import datetime as dt
import glob
import os
import sys
import time

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "bot_backtesting", "fullsim", "data", "ticks")


def _log(msg):
    print(f"[tick_collector] {msg}", flush=True)


def collect_day(symbol, day):
    """Ticks del dia de servidor `day` (date), en tramos de 2 h para no pedir bloques grandes."""
    base = int(pd.Timestamp(day).timestamp())
    parts = []
    for h in range(0, 24, 2):
        a = dt.datetime.fromtimestamp(base + h * 3600, dt.timezone.utc)
        b = dt.datetime.fromtimestamp(base + (h + 2) * 3600, dt.timezone.utc)
        x = mt5.copy_ticks_range(symbol, a, b, mt5.COPY_TICKS_INFO)
        if x is not None and len(x):
            parts.append(pd.DataFrame(x)[["time_msc", "bid", "ask"]])
        time.sleep(0.2)
    if not parts:
        return None
    X = pd.concat(parts).drop_duplicates("time_msc").sort_values("time_msc").reset_index(drop=True)
    X = X[(X.time_msc // 1000 >= base) & (X.time_msc // 1000 < base + 86400)]
    return X


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", default="26275221")
    ap.add_argument("--days", type=int, default=8)
    ap.add_argument("--since", default=None, help="primer dia a bajar (relleno historico)")
    ap.add_argument("--symbols", nargs="+", default=["XAUUSD+"])
    a = ap.parse_args()
    path = glob.glob(rf"C:\MT5_instances\mt5_{a.login}\terminal64.exe")
    if not path or not mt5.initialize(path=path[0], portable=True, timeout=15000):
        _log(f"no se pudo conectar al terminal de {a.login}: {mt5.last_error()}")
        return 1
    try:
        for sym in a.symbols:
            mt5.symbol_select(sym, True)
            last = mt5.symbol_info_tick(sym)
            if last is None:
                _log(f"{sym}: sin ticks"); continue
            end = pd.Timestamp(last.time, unit="s").normalize()
            start = pd.Timestamp(a.since) if a.since else end - pd.Timedelta(days=a.days)
            os.makedirs(os.path.join(OUT, sym), exist_ok=True)
            summ = []
            for day in pd.date_range(start, end):
                if day.dayofweek >= 5:
                    continue
                fp = os.path.join(OUT, sym, f"{day.date()}.pkl.gz")
                if os.path.exists(fp):
                    continue
                X = collect_day(sym, day.date())
                if X is None or X.empty:
                    _log(f"{sym} {day.date()}: sin ticks"); continue
                X.to_pickle(fp, compression="gzip")
                m = (X.time_msc // 60000) % 1440
                sp = (X.ask - X.bid).groupby(m).agg(["median", "max"])
                sp.index.name = "minuto"; sp["dia"] = str(day.date())
                summ.append(sp.reset_index())
                _log(f"{sym} {day.date()}: {len(X)} ticks, spread mediano {np.median(X.ask - X.bid):.3f}")
            if summ:
                fs = os.path.join(OUT, f"spread_{sym}.csv")
                S = pd.concat(summ)
                S.to_csv(fs, mode="a", header=not os.path.exists(fs), index=False)
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
