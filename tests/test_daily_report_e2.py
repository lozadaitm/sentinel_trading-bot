"""Reporte diario: seccion e2 (scripts/daily_report.py). Sin MT5 ni Supabase.

Correr:  python -m tests.test_daily_report_e2
"""

import sys
from types import SimpleNamespace as NS

import MetaTrader5 as mt5

from scripts import daily_report as dr

FAILS = []


def check(name, cond, extra=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def deal(magic, entry, comment, profit, pid):
    return NS(magic=magic, entry=entry, comment=comment, profit=profit, swap=0.0,
              commission=0.0, position_id=pid)


def pos(magic, comment, profit, ticket):
    return NS(magic=magic, comment=comment, profit=profit, swap=0.0, ticket=ticket, volume=0.1,
              type=mt5.POSITION_TYPE_BUY)


IN, OUT = mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT
check("magic e2", dr.MAGIC_E2 == 100300)
check("_e2_leg", dr._e2_leg("E2 BigOne T1") == "BigOne" and dr._e2_leg("E2 Lock NFP") == "NFP"
      and dr._e2_leg("E2 Salida MomUS") == "MomUS" and dr._e2_leg("Sentinel") is None
      and dr._e2_leg(None) is None)

deals = [
    deal(100300, IN, "E2 BigOne T1", 0, 1), deal(100300, OUT, "E2 TP BigOne T1", 50.0, 1),
    deal(100300, IN, "E2 MomUS T1", 0, 2), deal(100300, OUT, "[sl 4000]", -20.0, 2),  # sin pata en el cierre
    deal(100300, OUT, "E2 Salida NFP", -5.0, 3),
    deal(100100, OUT, "x", 999.0, 9),  # m15: no cuenta
]
s = dr._e2_summary([pos(100300, "E2 MomUS T2", 7.0, 5), pos(100100, "", 1.0, 6)], deals)
check("resumen no vacio", s is not None)
check("abiertas/cierres", s["open"] == 1 and s["closes"] == 3, str(s))
check("realizado", abs(s["real"] - 25.0) < 1e-9, str(s))
check("por pata", s["legs"]["BigOne"]["real"] == 50.0 and s["legs"]["MomUS"]["real"] == -20.0
      and s["legs"]["MomUS"]["open"] == 1 and s["legs"]["NFP"]["closes"] == 1, str(s["legs"]))
check("sin e2 -> None", dr._e2_summary([pos(100100, "", 1.0, 1)], [deal(100100, OUT, "", 1.0, 1)]) is None)

acct = dict(login="123", iid="x", mt5_ok=True, balance=3000.0, equity=3010.0, bid=4000.0,
            legs=0, net=0.0, floating=0.0, open_swap=0.0, frozen=False,
            real_m15=0.0, n_m15=0, real_m5=0.0, n_m5=0, m5_open=0, e2=s, bag=None, cuts=[],
            amps=[], op4=0, errors={}, critical=[], stale=[], prev_equity=None,
            prev_open_swap=None, first_equity=3010.0)
import datetime as dt
subj, body, html_body = dr.build([acct], dt.datetime(2026, 10, 26, 12, 0))
check("texto e2", "e2 (tres patas): 1 abiertas" in body and "BigOne: 0 abiertas" in body, body)
acct2 = dict(acct, e2=None)
body2 = dr.build([acct2], dt.datetime(2026, 10, 26))[1]
check("m15/m5 sin e2 intacto", "e2 (tres patas)" not in body2 and "Ciclo M15" in body2)

print("\nFALLOS:", FAILS if FAILS else "ninguno")
sys.exit(1 if FAILS else 0)
