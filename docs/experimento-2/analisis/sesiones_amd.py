"""Analisis D (sesiones) + G (AMD / Power of 3) sobre XAUUSD+ M5/M15 propios.

Solo lectura de bot_backtesting/data/. No toca el bot. Uso (desde la raiz):
    python docs/experimento-2/analisis/sesiones_amd.py
Escribe tablas en docs/experimento-2/analisis/out/.

Convenciones:
- Hora del servidor = hora de Nueva York + 7 h (corte diario a las 00:00 servidor =
  17:00 NY). Todo se convierte a UTC.
- Sesiones en hora LOCAL de cada plaza (siguen su propio horario de verano):
  Asia = Tokio 09:00-15:00 (00:00-06:00 UTC), Londres = 08:00-13:00 Londres,
  Nueva York = 08:00-17:00 NY.
- 1 pip de oro = 0,10 $ (convencion retail). 1 punto MT5 = 0,01 $.
"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = os.path.join(ROOT, "bot_backtesting", "data")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
PIP = 0.10
rng = np.random.default_rng(7)


def load(tf):
    d = pd.read_csv(os.path.join(DATA, f"XAUUSD+_{tf}.csv"))
    naive_ny = pd.to_datetime(d.time, unit="s") - pd.Timedelta(hours=7)
    d["utc"] = naive_ny.dt.tz_localize("America/New_York", ambiguous="NaT",
                                       nonexistent="shift_forward").dt.tz_convert("UTC")
    return d.dropna(subset=["utc"]).set_index("utc").sort_index()


m5 = load("M5")
m15 = load("M15")
# ATR(14) M15 (Wilder simple) para medir en unidades de volatilidad
tr = pd.concat([m15.high - m15.low, (m15.high - m15.close.shift()).abs(),
                (m15.low - m15.close.shift()).abs()], axis=1).max(axis=1)
m15["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
atr_m5 = m15.atr.reindex(m5.index, method="ffill")


def local_window(day_utc, tz, h0, h1):
    """Ventana [h0,h1) en hora local de `tz` para la fecha `day_utc` -> (ini, fin) UTC."""
    base = pd.Timestamp(day_utc.date()).tz_localize(tz)
    return (base + pd.Timedelta(hours=h0)).tz_convert("UTC"), (base + pd.Timedelta(hours=h1)).tz_convert("UTC")


SESS = {"Asia": ("Asia/Tokyo", 9, 15), "Londres": ("Europe/London", 8, 13), "NuevaYork": ("America/New_York", 8, 17)}

# ------------------------------------------------------------------ D. sesiones
rows = []
days = sorted({ts.normalize() for ts in m5.index if ts.dayofweek < 5})
for day in days:
    r = {"dia": day.date()}
    ok = True
    for name, (tz, h0, h1) in SESS.items():
        a, b = local_window(day, tz, h0, h1)
        s = m5[(m5.index >= a) & (m5.index < b)]
        if len(s) < (h1 - h0) * 12 * 0.8:
            ok = False
            break
        r[f"{name}_rango"] = s.high.max() - s.low.min()
        r[f"{name}_neto"] = s.close.iloc[-1] - s.open.iloc[0]
        r[f"{name}_hi"], r[f"{name}_lo"] = s.high.max(), s.low.min()
        r[f"{name}_atr"] = atr_m5.loc[s.index[0]]
    if ok:
        rows.append(r)
S = pd.DataFrame(rows)
S["Londres_rompe_Asia"] = (S.Londres_hi > S.Asia_hi) | (S.Londres_lo < S.Asia_lo)
S["Londres_rompe_ambos"] = (S.Londres_hi > S.Asia_hi) & (S.Londres_lo < S.Asia_lo)
S["NY_confirma"] = np.sign(S.NuevaYork_neto) == np.sign(S.Londres_neto)
S.to_csv(os.path.join(OUT, "sesiones_por_dia.csv"), index=False)

lines = [f"# Sesiones XAUUSD+ — {S.dia.min()} a {S.dia.max()} ({len(S)} dias completos)\n",
         "| Sesion | Rango mediano $ | p25–p75 $ | Rango mediano pips | % dias en lo que dice el video | Rango / ATR15 mediano |",
         "|---|---|---|---|---|---|"]
claims = {"Asia": (20, 30), "Londres": (40, 100), "NuevaYork": (100, 350)}
for name in SESS:
    x = S[f"{name}_rango"]
    lo, hi = claims[name]
    inside = ((x / PIP >= lo) & (x / PIP <= hi)).mean() * 100
    lines.append(f"| {name} | {x.median():.1f} | {x.quantile(.25):.1f}–{x.quantile(.75):.1f} | "
                 f"{x.median() / PIP:.0f} | {inside:.0f}% (video: {lo}-{hi} pips) | "
                 f"{(x / S[f'{name}_atr']).median():.1f} |")
lines += ["",
          f"- Londres rompe el rango de Asia por al menos un lado: **{S.Londres_rompe_Asia.mean() * 100:.0f}%** de los dias "
          f"(por ambos lados: {S.Londres_rompe_ambos.mean() * 100:.0f}%).",
          f"- Nueva York sigue la direccion neta de Londres: **{S.NY_confirma.mean() * 100:.0f}%** de los dias "
          f"(revierte: {100 - S.NY_confirma.mean() * 100:.0f}%).",
          f"- Asia es la sesion mas estrecha en {((S.Asia_rango < S.Londres_rango) & (S.Asia_rango < S.NuevaYork_rango)).mean() * 100:.0f}% de los dias.",
          ""]
# rango por hora UTC (perfil intradia) en multiplos del rango medio
m5h = m5.assign(r=m5.high - m5.low, h=m5.index.hour)
prof = m5h.groupby("h").r.mean()
lines += ["## Perfil por hora UTC (rango medio de vela M5, $)", "",
          "| Hora UTC | " + " | ".join(str(h) for h in prof.index) + " |",
          "|---|" + "---|" * len(prof),
          "| $ | " + " | ".join(f"{v:.2f}" for v in prof.values) + " |", ""]

# ------------------------------------------------------------------ G. AMD
K = [0.05, 0.10, 0.20]
N = [3, 6, 12]
HORIZ = {"1h": 12, "2h": 24, "4h": 48, "8h": 96}


def path_stats(i0, side, atr):
    """MFE/MAE en $ y en ATR desde la apertura de la vela i0+1; side=+1 compra, -1 venta.
    Ademas: ¿llega a +fav$ antes de -2*ATR (proxy de 'OP1 sale sin pasar a OP2')?"""
    out = {}
    entry = m5.close.iloc[i0]
    for hn, n in HORIZ.items():
        seg = m5.iloc[i0 + 1:i0 + 1 + n]
        if len(seg) < n * 0.8:
            return None
        fav = (seg.high - entry) if side > 0 else (entry - seg.low)
        adv = (entry - seg.low) if side > 0 else (seg.high - entry)
        out[f"mfe_{hn}"] = fav.max() / atr
        out[f"mae_{hn}"] = adv.max() / atr
    seg = m5.iloc[i0 + 1:i0 + 1 + HORIZ["8h"]]
    fav = ((seg.high - entry) if side > 0 else (entry - seg.low)).values
    adv = ((entry - seg.low) if side > 0 else (seg.high - entry)).values
    hit_f = np.argmax(fav >= 1.5) if (fav >= 1.5).any() else 10 ** 9   # ~armado+trail de OP1
    hit_a = np.argmax(adv >= 2 * atr) if (adv >= 2 * atr).any() else 10 ** 9  # ~distancia de hedge (2 ATR)
    out["op1_verde_antes_op2"] = float(hit_f < hit_a) if min(hit_f, hit_a) < 10 ** 9 else np.nan
    return out


pos = {ts: i for i, ts in enumerate(m5.index)}
sig = []
for day in days:
    a0, a1 = day + pd.Timedelta(hours=0), day + pd.Timedelta(hours=6)
    A = m5[(m5.index >= a0) & (m5.index < a1)]
    if len(A) < 60:
        continue
    AH, AL = A.high.max(), A.low.min()
    R = AH - AL
    W = m5[(m5.index >= a1) & (m5.index < day + pd.Timedelta(hours=10))]
    for k in K:
        for n in N:
            done = False
            for j, (ts, row) in enumerate(W.iterrows()):
                up, dn = row.high >= AH + k * R, row.low <= AL - k * R
                if not (up or dn):
                    continue
                side_sweep = 1 if up else -1
                conf = W.iloc[j:j + n + 1]
                inside = conf[(conf.close <= AH) & (conf.close >= AL)]
                if len(inside):
                    i0 = pos[inside.index[0]]
                    atr = atr_m5.iloc[i0]
                    for tipo, side in (("reversion", -side_sweep), ("continuacion", side_sweep)):
                        st = path_stats(i0, side, atr)
                        if st:
                            sig.append({"dia": day.date(), "k": k, "N": n, "tipo": tipo, "R": R, **st})
                    # control: entrada aleatoria (lado al azar) a la misma hora en otro dia
                    other = days[rng.integers(len(days))]
                    tsr = other + (inside.index[0] - day)
                    if tsr in pos:
                        i1 = pos[tsr]
                        st = path_stats(i1, int(rng.choice([-1, 1])), atr_m5.iloc[i1])
                        if st:
                            sig.append({"dia": other.date(), "k": k, "N": n, "tipo": "azar", "R": R, **st})
                done = True
                break
            if not done:
                pass
G = pd.DataFrame(sig)
G.to_csv(os.path.join(OUT, "amd_senales.csv"), index=False)
cut = sorted(G.dia.unique())[int(len(G.dia.unique()) * 0.7)]
lines += ["## AMD: barrido del rango asiatico (00-06 UTC) entre 06 y 10 UTC + cierre de vuelta dentro", "",
          f"Desarrollo: dias < {cut} · Reservado (30% final): dias >= {cut}. MFE/MAE en multiplos de ATR15. "
          "`OP1 verde antes de OP2` = el precio avanza 1,5 $ a favor antes de ir 2 ATR en contra (proxy).", "",
          "| k | N | muestra | tipo | señales | MFE 2h | MAE 2h | MFE/MAE 4h | % OP1 verde antes de OP2 |",
          "|---|---|---|---|---|---|---|---|---|"]
for (k, n), g in G.groupby(["k", "N"]):
    for part, gp in (("dev", g[g.dia < cut]), ("reserva", g[g.dia >= cut])):
        for tipo in ("reversion", "continuacion", "azar"):
            x = gp[gp.tipo == tipo]
            if not len(x):
                continue
            lines.append(f"| {k} | {n} | {part} | {tipo} | {len(x)} | {x.mfe_2h.median():.2f} | {x.mae_2h.median():.2f} | "
                         f"{(x.mfe_4h.median() / x.mae_4h.median()):.2f} | {x.op1_verde_antes_op2.mean() * 100:.0f}% |")
n_days = len(days)
lines += ["", f"Dias con barrido (k=0,10, N=6): {G[(G.k == .10) & (G.N == 6) & (G.tipo == 'reversion')].dia.nunique()} de {n_days}."]
open(os.path.join(OUT, "resultados.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
