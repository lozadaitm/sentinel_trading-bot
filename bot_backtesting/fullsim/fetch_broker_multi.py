"""Historia M15 del BROKER para muchos simbolos (solo lectura; correr con el mercado del oro cerrado).

Guarda data/broker_multi/<SIMBOLO>.pkl con time, open, high, low, close, tick_volume, spread (puntos) y
el punto/contrato del simbolo en data/broker_multi/_info.csv. El terminal limita a ~100 000 velas.
Uso: python -m bot_backtesting.fullsim.fetch_broker_multi [--login 26275221] [SIMBOLO ...]
"""
import glob
import os
import sys
import time

import MetaTrader5 as mt5
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "broker_multi")
SYMBOLS = ["BTCUSD", "ETHUSD", "EURUSD+", "GBPUSD+", "USDJPY+", "AUDUSD+", "USDCAD+", "USDCHF+", "NZDUSD+", "EURJPY+",
           "GBPJPY+", "XAGUSD", "XPTUSD", "USOUSD", "UKOUSD", "CL-OIL", "NG-C", "COPPER-C", "SP500", "NAS100", "DJ30",
           "GER40", "UK100", "FRA40", "EU50", "Nikkei225", "HK50", "CHINA50", "SPI200", "US2000", "USDX", "VIX",
           "Coffee-C", "Cocoa-C", "Sugar-C", "Wheat-C", "Soybean-C"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    login = "26275221"
    path = glob.glob(rf"C:\MT5_instances\mt5_{login}\terminal64.exe")
    if not path or not mt5.initialize(path=path[0], portable=True, timeout=15000):
        print("sin conexion", mt5.last_error()); return 1
    os.makedirs(OUT, exist_ok=True)
    info = []
    try:
        for s in (args or SYMBOLS):
            if not mt5.symbol_select(s, True):
                print(s, "no disponible"); continue
            time.sleep(0.5)
            r = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_M15, 0, 99000)
            if r is None or len(r) == 0:
                print(s, "sin velas", mt5.last_error()); continue
            X = pd.DataFrame(r)[["time", "open", "high", "low", "close", "tick_volume", "spread"]]
            X.to_pickle(os.path.join(OUT, f"{s}.pkl"))
            si = mt5.symbol_info(s)
            info.append(dict(simbolo=s, point=si.point, contrato=si.trade_contract_size, vol_min=si.volume_min, digits=si.digits,
                             swap_l=si.swap_long, swap_s=si.swap_short, calc=si.trade_calc_mode, desde=pd.to_datetime(X.time.min(), unit="s")))
            print(s, len(X), pd.to_datetime(X.time.min(), unit="s"), "->", pd.to_datetime(X.time.max(), unit="s"), flush=True)
            time.sleep(1)
    finally:
        mt5.shutdown()
        pd.DataFrame(info).to_csv(os.path.join(OUT, "_info.csv"), index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
