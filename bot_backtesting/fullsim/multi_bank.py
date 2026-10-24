"""Banco de ideas aplicado a OTROS simbolos del broker, con la misma exigencia que el oro (solo analisis).

Datos: data/broker_multi/<SIMBOLO>.pkl (M15 del broker, ~4 años; cripto ~3). Costo por operacion:
spread mediano de las velas a esa hora (puntos x punto) + comision RAW en divisas y metales
(3 $/lote por lado = 0,006 % del nominal ida y vuelta). Sin entradas de 23:00 a 02:00 servidor (rollover:
ahi las velas mienten, ver data-dukascopy-rollover-artifact). Mitades: A = primera mitad, B = segunda.

  T1 mapa horario: hora 2..22, mantener 1/3/6 h (sin pasar de las 23:00), compra/venta, todos los dias o
     tendencia diaria +2 / 0 / -2. Pasa si: BH 10 % en A con neto > 0, B neto > 0 con t > 2, y años
     positivos >= todos menos uno.
  T2 momentum intradia (como Asia -> EE.UU. en el oro): signo del retorno 02:00 -> H (H = 10, 13, 16) si
     |ret| > 0,5 desv. -> operar H -> H+5 en esa direccion; mismos criterios.
  T3 NFP: seguir el salto (T-15 -> T+60) durante 6 h; por año.
  T4 dia de la semana (retorno 02:00 -> 22:00).
Uso: python -m bot_backtesting.fullsim.multi_bank [SIMBOLO ...]
"""
import os
import sys

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.econ_intraday import _p, bh

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "broker_multi")
INFO = None
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
FX_COMM = 0.006   # % del nominal ida y vuelta (3 $/lote/lado sobre 100 000)


def load(sym):
    global INFO
    if INFO is None:
        INFO = pd.read_csv(os.path.join(DATA, "_info.csv")).set_index("simbolo")
    X = pd.read_pickle(os.path.join(DATA, f"{sym}.pkl")).sort_values("time").reset_index(drop=True)
    pt = INFO.at[sym, "point"]
    X["sp"] = X.spread * pt
    comm = FX_COMM if (sym.endswith("+") or sym.startswith("XAG")) else 0.0
    return X, comm


def mats(X):
    day = X.time.values // 86400; slot = (X.time.values % 86400) // 900
    days = np.unique(day); di = np.searchsorted(days, day)
    O = np.full((len(days), 96), np.nan); C = O.copy(); S = O.copy()
    O[di, slot] = X.open.values; C[di, slot] = X.close.values; S[di, slot] = X.sp.values
    d1 = pd.Series(X.close.values).groupby(day).last()
    st = (np.sign(d1 - d1.shift(21)) + np.sign(d1 - d1.shift(63))).shift(1).reindex(days).values
    return days, O, C, S, st


def cost_pct(S, O, k, comm):
    sp_h = np.nanmedian(S[:, k:k + 4], axis=1)
    return sp_h / O[:, k] * 100 + comm


def judge(r, A, yr):
    a, b = r[A], r[~A]
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 40 or len(b) < 40:
        return None
    ys = pd.Series(r).groupby(yr).mean()
    return dict(m_A=a.mean(), t_A=a.mean() / a.std() * np.sqrt(len(a)), m_B=b.mean(), t_B=b.mean() / b.std() * np.sqrt(len(b)),
                n=len(a) + len(b), años_pos=int((ys > 0).sum()), años=int(ys.notna().sum()))


def bank(sym):
    X, comm = load(sym)
    days, O, C, S, st = mats(X)
    yr = pd.to_datetime(days * 86400, unit="s").year.values
    A = days < np.median(days); dow = (days + 3) % 7
    wk = dow < 5 if not sym.startswith(("BTC", "ETH")) else np.ones(len(days), bool)
    rows = []
    for h in range(2, 23):
        k = h * 4
        for nh in (1, 3, 6):
            if k + nh * 4 > 92:
                continue
            gross = (C[:, k + nh * 4 - 1] - O[:, k]) / O[:, k] * 100
            cst = cost_pct(S, O, k, comm)
            for side in (1, -1):
                r = gross * side - cst
                for g, m in (("todos", wk), ("tend+2", wk & (st == 2)), ("tend0", wk & (st == 0)), ("tend-2", wk & (st == -2))):
                    rr = np.where(m, r, np.nan)
                    j = judge(rr, A, yr)
                    if j:
                        rows.append(dict(prueba="T1", hora=h, horas=nh, lado=side, grupo=g, **j))
    for H in (10, 13, 16):
        k0, k = 8, H * 4
        if k + 20 > 92:
            continue
        pre = (O[:, k] - O[:, k0]) / O[:, k0] * 100
        sd = np.nanstd(pre[A])
        post = (C[:, k + 19] - O[:, k]) / O[:, k] * 100
        cst = cost_pct(S, O, k, comm)
        for g, m in (("todos", wk), ("tend!=0", wk & (st != 0))):
            sel = m & (np.abs(pre) > 0.5 * sd)
            r = np.where(sel, np.sign(pre) * post - cst, np.nan)
            j = judge(r, A, yr)
            if j:
                rows.append(dict(prueba="T2", hora=H, horas=5, lado=0, grupo=g, **j))
    R = pd.DataFrame(rows)
    if R.empty:
        return R
    R["bh"] = False
    m1 = R.prueba == "T1"
    R.loc[m1, "bh"] = bh(R[m1].t_A.apply(_p).values) & (R[m1].m_A > 0).values
    R.loc[~m1, "bh"] = (R[~m1].t_A > 2) & (R[~m1].m_A > 0)
    R["pasa"] = R.bh & (R.m_B > 0) & (R.t_B > 2) & (R.años_pos >= R.años - 1)
    R["simbolo"] = sym
    return R


def main():
    syms = sys.argv[1:] or sorted(f[:-4] for f in os.listdir(DATA) if f.endswith(".pkl"))
    allR = []
    for s in syms:
        try:
            R = bank(s)
        except Exception as e:  # noqa: BLE001
            print(s, "error", e); continue
        if R.empty:
            print(f"{s:10s} sin datos suficientes"); continue
        allR.append(R)
        t2 = R[R.prueba == "T2"].sort_values("t_A", ascending=False).head(1)
        print(f"{s:10s} pruebas {len(R):4d} | BH en A {int(R.bh.sum()):3d} | PASAN {int(R.pasa.sum()):2d} | "
              f"mejor T2: {t2[['hora', 'grupo', 'm_A', 't_A', 'm_B', 't_B', 'años_pos', 'años']].round(3).to_dict('records')}", flush=True)
        if R.pasa.any():
            print(R[R.pasa].sort_values("t_B", ascending=False).head(8).round(4).to_string(index=False))
    if allR:
        pd.concat(allR).to_pickle(os.path.join(DATA, "_bank.pkl"))


if __name__ == "__main__":
    main()
