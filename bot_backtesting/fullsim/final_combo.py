"""Combinacion final (solo simulacion): Big One (HAR + eventos) en dias alcistas o en todos con peso,
+ satelites de noticias, + riesgo por racha (x up tras 20 operaciones con R medio > 0, si no x0,75)
+ freno por caida. Calendario completo 2023-01 -> 2026-10. Uso: python -m bot_backtesting.fullsim.final_combo"""
import os, numpy as np, pandas as pd
from bot_backtesting.fullsim.bigone_plus import CAL
from bot_backtesting.fullsim.combo_news import sats
from bot_backtesting.fullsim.entrylab import RESULTS
T = pd.read_pickle(os.path.join(RESULTS, "bigone_plus_trades.pkl"))
S = sats(); S = S[S.year >= 2023].assign(w=1.0, big=0)
rows = []
for var in ("har_ev50", "har_ev50_todas"):
    B = T[T.variant == var].copy(); B["mr"] = B.mae / B.risk_oz; B["big"] = 1
    for fs in (0.0, 0.02):
        for up in (1.0, 1.5, 2.0):
            for freno in (False, True):
                A = pd.concat([B[["t", "r_mult", "mr", "w", "big"]], S[["t", "r_mult", "mr", "w", "big"]]]).sort_values("t")
                if fs == 0: A = A[A.big == 1]
                A["m"] = pd.to_datetime(A.t, unit="s").dt.to_period("M")
                months = [A.loc[A.m == p, ["r_mult", "mr", "w", "big"]].values.reshape(-1, 4) for p in CAL]
                def path(seq, bal=5000.0):
                    eq, peak, dd, hist = bal, bal, 0.0, []
                    for r, m, w, big in seq:
                        if big:
                            f = 0.03 * (up if len(hist) >= 20 and np.mean(hist[-20:]) > 0 else (0.75 if up > 1 else 1.0))
                        else:
                            f = fs
                        if freno: f *= max(0.5, 1 - ((peak - eq) / peak) / 0.6)
                        risk = eq * min(f, 0.10) * w
                        dd = max(dd, (peak - (eq + min(0.0, m) * risk)) / peak)
                        eq += r * risk; peak = max(peak, eq); dd = max(dd, (peak - eq) / peak)
                        if big: hist.append(r)
                        if eq <= bal * 0.05: return eq / bal, 1.0
                    return eq / bal, dd
                rng = np.random.default_rng(7)
                res = [path(np.vstack([months[i] for i in rng.integers(0, len(months), 12)])) for _ in range(2000)]
                mult = np.array([x[0] for x in res]); dds = np.array([x[1] for x in res]); real = path(np.vstack(months))
                rows.append(dict(bigone=var, satelites=fs, racha=up, freno=freno, x12_med=np.median(mult), crec_mes=np.median(mult) ** (1 / 12) - 1,
                                 p_x2=(mult >= 2).mean(), p_x3=(mult >= 3).mean(), p_dd50=(dds >= .5).mean(), p_perder=(mult < 1).mean(), real_x=real[0], real_dd=real[1]))
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).round(3).to_string(index=False))
