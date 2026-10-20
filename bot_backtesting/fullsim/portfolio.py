"""Los tres modulos juntos como un solo bot, con trailing elegido por validacion movil.

Modulos (bot_backtesting/fullsim/entrylab.py):
  big_one : compra en la reapertura (01:00 servidor) con tendencia diaria alcista; cierre <= 10:00
  noise   : banda de ruido de Zarattini (10:00-22:00, una por dia); cierre a las 23:00
  squeeze : compresion de Bollinger H1 + ruptura; cierre a las 24 h
Salidas candidatas (sin salida en contra de precio; siempre cierre por hora):
  - solo hora;  - objetivo a TP x ATR;  - trailing: se activa a A x ATR a favor y sigue a D x ATR.
Para cada ano de prueba (2023..2026) y modulo se elige la salida con mejor ganancia media en
los dos anos anteriores; se aplica en ese ano. Costes: spread 0,20, comision 0,12 $/oz, swap.

Cuentas: lote base = 0,12 lotes por 5 000 $ (DEFAULTS del bot) x factor de riesgo, con la
Big One al doble; minimo 0,01 y paso 0,01. Cada operacion se dimensiona con el equity del momento.

Uso: python -m bot_backtesting.fullsim.portfolio
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.entrylab import COMM, DATA, RESULTS, SPREAD, families, swap_cost

TEST_YEARS = (2023, 2024, 2025, 2026)
# Candado (Hedge Lock) a LOCK x ATR en contra: congela la perdida hasta la hora de cierre del
# modulo; en dinero equivale a salir alli, mas el coste de abrir y cerrar la cobertura.
LOCKS = (1.0, 2.0, 3.0)
_BASE = ([("time", None, None)] + [("tp", tp, None) for tp in (1.0, 2.0, 3.0)]
         + [("trail", a, d) for a in (1.0, 1.5, 2.0) for d in (0.5, 1.0, 1.5)])
EXITS = [(k, a, d, lk) for (k, a, d) in _BASE for lk in LOCKS]
MODULES = {"big_one": "asia_long_if_up", "noise": "noise_band", "squeeze": "squeeze_H1"}
BIG_MULT = 2.0


class Paths:
    def __init__(self, B):
        m5 = B["M5"]
        self.T, self.O, self.H, self.L, self.C = (m5[c].values for c in ("time", "open", "high", "low", "close"))

    def trade(self, t, side, scale, hz):
        """{salida: (pnl $/oz, minimo a favor en $/oz durante la operacion, hora de cierre)}."""
        k = np.searchsorted(self.T, t)
        if k <= 0 or k >= len(self.T):
            return None
        n = min(int(hz * 12), len(self.T) - k)
        if n < 3:
            return None
        O, H, L, C = self.O[k:k + n], self.H[k:k + n], self.L[k:k + n], self.C[k:k + n]
        if side == 1:
            px = O[0] + SPREAD
            fav, low, opn, last = H - px, L - px, O - px, C[-1] - px
        else:
            px = O[0]
            fav, low, opn, last = px - (L + SPREAD), px - (H + SPREAD), px - (O + SPREAD), px - (C[-1] + SPREAD)
        peak = np.maximum.accumulate(fav)
        peak_prev = np.r_[-np.inf, peak[:-1]]
        res = {}
        lock_cost = COMM + SPREAD           # abrir y cerrar la cobertura
        for kind, a, d, lk in EXITS:
            i_out, r = n - 1, last
            if kind == "tp":
                hit = np.nonzero(fav >= a * scale)[0]
                if len(hit):
                    i_out, r = hit[0], a * scale
            elif kind == "trail":
                stop = peak_prev - d * scale
                hit = np.nonzero((peak_prev >= a * scale) & (low <= stop))[0]
                if len(hit):
                    i_out = hit[0]
                    r = min(opn[i_out], stop[i_out])          # si abre por debajo del stop, sale a la apertura
            # candado: primer toque de -lk ATR antes de la salida elegida
            lstop = -lk * scale
            lh = np.nonzero(low[:i_out + 1] <= lstop)[0]
            extra = 0.0
            if len(lh):
                i_out = lh[0]
                r = min(opn[i_out], lstop)
                extra = -lock_cost
            mae = low[:i_out + 1].min() if not len(lh) else r
            res[(kind, a, d, lk)] = (r - COMM + extra + swap_cost(self.T[k], self.T[k + i_out] + 300, side), mae,
                                     self.T[k + i_out] + 300, lk * scale)
        return res


def evaluate_module(name, rule, F, P):
    E = F[rule]()
    rows = []
    for e in E.itertuples():
        o = P.trade(e.t, e.side, e.scale, e.hz)
        if o is None:
            continue
        for ex, (pnl, mae, t_out, risk_oz) in o.items():
            rows.append((name, e.t, t_out, e.side, ex[0], ex[1], ex[2], ex[3], pnl, mae, risk_oz))
    R = pd.DataFrame(rows, columns=["module", "t", "t_out", "side", "kind", "a", "d", "lock", "pnl", "mae", "risk_oz"])
    R["year"] = pd.to_datetime(R.t, unit="s").dt.year
    R["exit"] = R.kind + "_" + R.a.astype(str) + "_" + R.d.astype(str) + "_L" + R.lock.astype(str)
    R["r_mult"] = R.pnl / R.risk_oz              # resultado en unidades de riesgo (perdida al candado = -1)
    return R


def walk_forward(R):
    """Salida elegida por ano (con los 2 anteriores) y operaciones de ese ano con esa salida."""
    sel, choice = [], []
    for Y in TEST_YEARS:
        tr = R[R.year.isin([Y - 2, Y - 1])]
        te = R[R.year == Y]
        if tr.empty or te.empty:
            continue
        best = tr.groupby("exit").r_mult.mean().idxmax()       # mejor ganancia POR UNIDAD DE RIESGO
        choice.append((Y, best, tr.groupby("exit").r_mult.mean().max()))
        sel.append(te[te.exit == best])
    return pd.concat(sel, ignore_index=True), choice


def account(trades, balance0, risk):
    """Curva de una cuenta. `risk` = % del equity que se pierde si salta el candado (la Big One
    el doble). Lote = equity * risk / (distancia del candado * 100), minimo 0,01, paso 0,01."""
    trades = trades.sort_values("t").reset_index(drop=True)
    eq, peak, max_dd, rows = balance0, balance0, 0.0, []
    for x in trades.itertuples():
        r = risk / 100.0 * (BIG_MULT if x.module == "big_one" else 1.0)
        lots = eq * r / (x.risk_oz * 100)
        lots = max(0.01, np.floor(lots / 0.01 + 1e-9) * 0.01)
        worst = eq + min(0.0, x.mae) * lots * 100            # peor flotante de esta operacion
        max_dd = max(max_dd, (peak - worst) / peak)
        eq += x.pnl * lots * 100
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)
        rows.append((x.t_out, eq))  # noqa
        if eq <= 0:
            break
    curve = pd.DataFrame(rows, columns=["t", "equity"])
    curve["month"] = pd.to_datetime(curve.t, unit="s").dt.to_period("M")
    return curve, max_dd


def main():
    B = pd.read_pickle(os.path.join(DATA, "bars_all.pkl"))
    F = families(B)
    P = Paths(B)
    allsel = []
    for name, rule in MODULES.items():
        R = evaluate_module(name, rule, F, P)
        R.to_pickle(os.path.join(RESULTS, f"portfolio_{name}.pkl"))
        S, ch = walk_forward(R)
        allsel.append(S)
        print(f"== {name} ({rule}) ==")
        for Y, ex, v in ch:
            y = S[S.year == Y]
            print(f"  {Y}: salida {ex:24s} (entrenamiento {v:+.2f} R) -> en {Y}: n={len(y)} "
                  f"{y.r_mult.mean():+.2f} R por operacion ({y.pnl.mean():+.2f} $/oz), candados {int((y.r_mult <= -0.99).sum())}")
        g = R[R.year.isin(TEST_YEARS)].groupby("exit").r_mult.mean().sort_values(ascending=False)
        print("  referencia 2023-2026 (R):", ", ".join(f"{k} {v:+.2f}" for k, v in g.head(5).items()))
    T = pd.concat(allsel, ignore_index=True)
    T.to_pickle(os.path.join(RESULTS, "portfolio_trades.pkl"))
    print(f"\nOperaciones 2023-2026: {len(T)} ({T.groupby('module').size().to_dict()})")
    print("\n== Cuentas (2023-01 -> 2026-10) ==")
    out = []
    for bal in (1000, 5000, 10000):
        for risk in (0.25, 0.5, 1.0):
            curve, dd = account(T, bal, risk)
            final = curve.equity.iloc[-1]
            yrs = (curve.t.iloc[-1] - curve.t.iloc[0]) / (365.25 * 86400)
            cagr = (final / bal) ** (1 / yrs) - 1 if final > 0 else -1
            m = curve.groupby("month").equity.last()
            mret = m.pct_change().fillna(m.iloc[0] / bal - 1)
            out.append(dict(cuenta=bal, riesgo=risk, final=round(final), anual_pct=round(cagr * 100, 1),
                            mes_medio_pct=round(mret.mean() * 100, 2), meses_pos=f"{int((mret > 0).sum())}/{len(mret)}",
                            peor_mes_pct=round(mret.min() * 100, 1), caida_max_pct=round(dd * 100, 1)))
    print(pd.DataFrame(out).to_string(index=False))


if __name__ == "__main__":
    main()
