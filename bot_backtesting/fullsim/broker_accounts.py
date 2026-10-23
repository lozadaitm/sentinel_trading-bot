"""Cuentas de 1 000 / 5 000 / 10 000 mes a mes con la cartera del broker (solo simulacion).

Operaciones: las de broker_final (validacion movil): Big One (medio riesgo en noticias y en dias no
alcistas), momentum EE.UU. (todas las tendencias), satelites FOMC y NFP.
Contabilidad realista: lote = equity x riesgo x peso / (distancia del candado x 100), redondeado a
0,01 hacia abajo con minimo 0,01 (en la cuenta chica el minimo puede obligar a arriesgar MAS de lo
previsto: se informa el riesgo efectivo); operaciones superpuestas (cada una usa el equity cerrado al
abrir); P&L en $ al cerrar; margen 800 $/lote (1:500) controlado.
Uso: python -m bot_backtesting.fullsim.broker_accounts
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.broker_rule import RESULTS, exit_label, walk_forward

# Salida FIJADA DE ANTEMANO para todas las patas (sin elegir entre ~30 salidas, que sobreajustaba):
# salida por hora + candado a 1 ATR diario. Patas robustas 5/5 años: Big One (dias alcistas),
# momentum EE.UU. (umbral 0,5) y NFP (seguir el salto). FOMC e IPC descartados (inestables).
FIXED = "atrd_time_0_0_L1"

MARGIN_LOT = 800.0


LADDER = ("atrd_time_0_0_L1", "atrd_tp_2_0_L1", "atrd_tp_3_0_L1")


def pick(R, ladder):
    """Una salida (FIXED) o ESCALERA: la posicion se reparte en 3 tercios que salen por hora, a TP 2 y a
    TP 3 ATR M15, con el mismo candado (1 ATR diario). P&L = media de los tres tercios."""
    if not ladder:
        return R[R.exit == FIXED]
    X = R[R.exit.isin(LADDER)]
    g = X.groupby("t")
    out = g.first()
    out["pnl"] = g.pnl.mean(); out["mae"] = g.mae.min(); out["r_mult"] = g.r_mult.mean()
    return out[g.size() == len(LADDER)].reset_index()


def trades_fixed(ladder=False):
    L = lambda n: pd.read_pickle(os.path.join(RESULTS, f"broker_r2_{n}.pkl")).assign(exit=lambda x: exit_label(x))
    # Big One todos los dias (x0,5 si la tendencia no es alcista); momentum EE.UU. con tendencia +2 o -2
    bo = pick(L("bigone"), ladder).assign(pata="big_one"); bo["w"] = np.where(bo.state == 2, 1.0, 0.5)
    ny = pick(L("ny_mom_05_todas"), ladder); ny = ny[ny.state.isin([2, -2])].assign(w=1.0, pata="momentum_eeuu")
    nf = pick(L("news_nfp"), ladder).assign(w=1.0, pata="nfp")
    T = pd.concat([bo, ny, nf], ignore_index=True)
    T["t_out"] = T.t + T.pata.map({"big_one": 9 * 3600, "momentum_eeuu": 6 * 3600, "nfp": 24 * 3600})
    return T.sort_values("t").reset_index(drop=True)


def trades():
    L = lambda n: pd.read_pickle(os.path.join(RESULTS, f"broker_r2_{n}.pkl"))
    bo = pd.concat([walk_forward(g).assign(w={2: 1.0, 0: .5, -2: .5}[s]) for s, g in L("bigone").groupby("state") if s in (2, 0, -2)])
    bo["w"] = bo.w * np.where(bo.ev == 1, 0.5, 1.0); bo["pata"] = "big_one"
    ny = walk_forward(L("ny_mom_05_todas")).assign(w=1.0, pata="momentum_eeuu")
    fo = walk_forward(L("news_fomc")).assign(w=1.0, pata="fomc")
    nf = walk_forward(L("news_nfp")).assign(w=1.0, pata="nfp")
    T = pd.concat([bo, ny, fo, nf], ignore_index=True)
    # hora de cierre: t + duracion aproximada segun la pata (para ordenar cierres)
    T["t_out"] = T.t + T.pata.map({"big_one": 9 * 3600, "momentum_eeuu": 6 * 3600, "fomc": 24 * 3600, "nfp": 24 * 3600})
    return T.sort_values("t").reset_index(drop=True)


def run(T, bal0, scheme, start, end):
    T = T[(T.t >= start.timestamp()) & (T.t < end.timestamp())]
    ev = [(r.t, 0, i) for i, r in T.iterrows()] + [(r.t_out, 1, i) for i, r in T.iterrows()]
    ev.sort()
    eq, peak, openl, lots = bal0, bal0, {}, {}
    rows, riskeff, max_margin, min_eq = [], [], 0.0, bal0
    for t, kind, i in ev:
        r = T.loc[i]
        if kind == 0:
            if scheme[0] == "fijo":
                f = scheme[1]
            else:
                fl, f0 = scheme[1], scheme[2]
                f = f0 * max(0.0, (eq - fl * peak) / eq) / (1 - fl)
            f *= r.w
            raw = eq * f / (r.risk_oz * 100)
            lot = max(0.01, np.floor(raw / 0.01 + 1e-9) * 0.01) if f > 0 else 0.0
            lots[i] = lot
            riskeff.append(lot * r.risk_oz * 100 / eq)
            max_margin = max(max_margin, sum(lots[j] for j in openl) * MARGIN_LOT + lot * MARGIN_LOT)
            openl[i] = True
            min_eq = min(min_eq, eq + min(0.0, r.mae) * lot * 100)
        else:
            eq += r.pnl * lots[i] * 100
            peak = max(peak, eq); openl.pop(i, None)
            rows.append((pd.Timestamp(t, unit="s"), eq, r.pata, r.pnl * lots[i] * 100))
    R = pd.DataFrame(rows, columns=["t", "equity", "pata", "pnl_usd"])
    R["mes"] = R.t.dt.to_period("M")
    M = R.groupby("mes").agg(equity_fin=("equity", "last"), pnl=("pnl_usd", "sum"), ops=("pnl_usd", "size"))
    M = M.reindex(pd.period_range(start, end - pd.Timedelta(days=1), freq="M")).fillna({"pnl": 0, "ops": 0}).ffill().fillna({"equity_fin": bal0})
    M["ret_%"] = M.equity_fin.pct_change().fillna(M.equity_fin.iloc[0] / bal0 - 1) * 100
    eqs = R.equity.values
    dd = np.max(1 - eqs / np.maximum.accumulate(np.r_[bal0, eqs])[1:]) if len(eqs) else 0
    por_pata = R.groupby("pata").pnl_usd.sum().round(0).to_dict()
    return M, dict(final=eq, x=eq / bal0, caida_max=dd, riesgo_medio=np.mean(riskeff), riesgo_max=np.max(riskeff),
                   margen_max_pct=max_margin / bal0, peor_flotante=min_eq), por_pata


def compare_ladder():
    print("ESCALERA vs UNA SALIDA (49 meses desde 2022-10, cuenta 5 000):")
    rows = []
    for lad in (False, True):
        T = trades_fixed(lad)
        for pata, g in T.groupby("pata"):
            rows.append(dict(escalera=lad, pata=pata, n=len(g), R=g.r_mult.mean(), desvio=g.r_mult.std(), razon=g.r_mult.mean() / g.r_mult.std()))
        for sch in (("fijo", 0.03), ("fijo", 0.05), ("fijo", 0.08), ("fijo", 0.10)):
            M, s, pp = run(T, 5000, sch, pd.Timestamp("2022-10-01"), pd.Timestamp("2026-10-17"))
            rows.append(dict(escalera=lad, pata=f"cuenta {sch}", x=s["x"], caida=s["caida_max"], peor_mes=M["ret_%"].min()))
    print(pd.DataFrame(rows).round(3).to_string(index=False))


def main():
    compare_ladder()
    T = trades_fixed(ladder=True)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    start, end = pd.Timestamp("2025-11-01"), pd.Timestamp("2026-10-17")
    schemes = (("fijo", 0.03), ("fijo", 0.05), ("fijo", 0.08), ("gz", 0.5, 0.06), ("gz", 0.5, 0.10))
    summary, monthly = [], {}
    for bal in (1000, 5000, 10000):
        for sch in schemes:
            M, s, pp = run(T, bal, sch, start, end)
            summary.append(dict(cuenta=bal, esquema=str(sch), **s, **{f"$ {k}": v for k, v in pp.items()}))
            monthly[(bal, str(sch))] = M
    S = pd.DataFrame(summary)
    print("ULTIMOS 12 MESES (2025-11 -> 2026-10-16), cuenta nueva al inicio:")
    print(S.round(3).to_string(index=False))
    for sch in ("('fijo', 0.05)", "('gz', 0.5, 0.1)"):
        print(f"\nEquity a fin de mes, esquema {sch}:")
        tab = pd.DataFrame({f"{b}": monthly[(b, sch)].equity_fin.round(0) for b in (1000, 5000, 10000)})
        tab = tab.join(pd.DataFrame({f"{b} %": monthly[(b, sch)]["ret_%"].round(1) for b in (1000, 5000, 10000)}))
        tab["ops"] = monthly[(5000, sch)].ops.astype(int)
        print(tab.to_string())
    pd.to_pickle((S, monthly), os.path.join(RESULTS, "broker_accounts.pkl"))
    # contexto: desde 2024-01
    print("\nDESDE 2022-10 (49 meses), mismo calculo:")
    rows = []
    for bal in (1000, 5000, 10000):
        for sch in schemes:
            M, s, pp = run(T, bal, sch, pd.Timestamp("2022-10-01"), end)
            rows.append(dict(cuenta=bal, esquema=str(sch), final=s["final"], x=s["x"], caida_max=s["caida_max"],
                             meses_neg=int((M["ret_%"] < 0).sum()), peor_mes=M["ret_%"].min(), riesgo_medio=s["riesgo_medio"]))
    print(pd.DataFrame(rows).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
