"""Linea B (tamano inteligente): reglas simples de peso por operacion. Solo cambia la columna de peso;
direccion y salidas = base_trades() (gestion vigente). Todo con informacion conocida al entrar.

Modo (variable de entorno OPTB_MODE):
  crudo  (por defecto): el peso es w_base x multiplicador, tal cual (bajar peso = menos exposicion; subir = mas).
  neutro: ademas se reescala para que la suma de pesos en sel sea la de la base (presupuesto neutro).
  El nombre de cada variante lleva el sufijo |crudo o |neutro. (Las 11 primeras filas «dow ...» del registro,
  sin sufijo, se corrieron en modo neutro.)
Familias:
  bo_w      : pesos de la Big One por tendencia s (s=+2 / 0 / -2) y multiplicador en dia de noticia (idea 5).
  leg_alloc : reparto fijo de riesgo entre patas (Momentum, NFP frente a Big One) (idea 4).
  roll      : peso por desempeno rodante de la pata (t-stat de las ultimas N cerradas), racha, inverso de la
              volatilidad rodante del R de la pata, y recorte cuando hay solape con otra pata abierta (idea 4).
  voltgt    : volatility targeting (objetivo / previsto)^k acotado [0,5; 1,5]; previsto = HAR, rv1, rv5 (en
              unidades de ATR_D), desviacion rodante del R, VIX del broker, GVZ, ATR15/ATR_D (idea 2).
  bucket    : riesgo por regimen: terciles (cortes con cuantiles PASADOS de la misma pata) de una variable y
              patron de pesos (sube / baja / quita el tercio bajo / quita el alto) (idea 3).
  dow       : Big One por dia de la semana (lunes / jueves-viernes) y Momentum en dia de noticia (idea 3).
Cada variante se anota en results/opt_registry.csv (linea B) y en results/opt_B_log.csv (con extras).
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_B_rules [familia ...]
"""
import os
import sys
import time

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.opt_B_feats import build
from bot_backtesting.fullsim.opt_B_lib import evalw, normalize
from bot_backtesting.fullsim.opt_base import base_trades, low_priority

LEGS = ("big_one", "momentum", "nfp")
MODE = os.environ.get("OPTB_MODE", "crudo")


def past_quantile(B, x, qs, min_n=40):
    """Cortes por cuantil con SOLO operaciones anteriores de la misma pata (t estrictamente menor)."""
    x = np.asarray(x, float)
    out = np.full((len(B), len(qs)), np.nan)
    legs, t = B.leg.values, B.t.values
    for lg in LEGS:
        j = np.nonzero(legs == lg)[0]
        j = j[np.argsort(t[j])]
        for a, i in enumerate(j):
            prev = x[j[:a]]
            prev = prev[np.isfinite(prev)]
            if len(prev) >= min_n:
                out[i] = np.quantile(prev, qs)
    return out


def past_median(B, x, min_n=40):
    return past_quantile(B, x, [0.5], min_n)[:, 0]


def bucket_w(B, x, cuts, pattern):
    """pattern: pesos por tramo (len(cuts)+1). Sin cortes conocidos (inicio) -> 1."""
    x = np.asarray(x, float)
    k = np.sum(x[:, None] > cuts, axis=1)
    m = np.asarray(pattern, float)[np.clip(k, 0, len(pattern) - 1)]
    bad = ~np.isfinite(cuts).all(1) | ~np.isfinite(x)
    return np.where(bad, 1.0, m)


def open_overlap(B):
    """Numero de operaciones e2 abiertas en el momento de entrar (conocido al entrar)."""
    ti, to = B.t_in.values, B.t_out.values
    return np.array([int(((ti < ti[i]) & (to > ti[i])).sum()) for i in range(len(B))])


def run(families):
    B = base_trades()
    F = build()
    w0 = B.w.values
    isleg = {lg: (B.leg == lg).values for lg in LEGS}
    n = 0
    t0 = time.time()

    def go(name, m, params, base=None):
        nonlocal n
        w = (w0 if base is None else base) * np.asarray(m, float)
        if MODE == "neutro":
            w = normalize(B, w)
        name = f"{name} |{MODE}"
        r = evalw(B, w, name, params)
        n += 1
        print(f"{n:4d} {name:42s} MAR x{r['mar_ratio']:.3f} edge_lm {r['edge_lm']:.3f} "
              f"23 {r['r2023']:.2f} 24 {r['r2024']:.2f} dia {r['peor_dia_c']:.3f} mes {r['peor_mes_c']:.3f} "
              f"({time.time()-t0:.0f}s)", flush=True)

    s = F.s.values
    if "bo_w" in families:
        for a in (0.5, 0.75, 1.0):
            for b in (0.5, 0.75, 1.0):
                for c in (0.5, 0.75, 1.0):
                    for e in (0.5, 0.75, 1.0):
                        wb = np.where(s == 2, a, np.where(s == -2, c, b)) * np.where(F.ev_any.values == 1, e, 1.0)
                        base = np.where(isleg["big_one"], wb, w0)
                        go(f"bo_w a{a} b{b} c{c} e{e}", 1.0, dict(a=a, b=b, c=c, e=e), base=base)
    if "leg_alloc" in families:
        for mo in (0.75, 1.0, 1.25, 1.5):
            for nf in (0.5, 1.0, 1.5, 2.0):
                m = np.where(isleg["momentum"], mo, np.where(isleg["nfp"], nf, 1.0))
                go(f"leg_alloc mo{mo} nfp{nf}", m, dict(mo=mo, nfp=nf))
    if "roll" in families:
        sd = F.sd_leg60.values
        for N, col in ((20, "perf_leg20"), (60, "perf_leg60")):
            z = F[col].values / (sd / np.sqrt(N))
            for k in (0.25, 0.5, 1.0):
                m = np.where(np.isfinite(z), np.clip(1 + k * z / 2, 0.5, 1.5), 1.0)
                go(f"roll tstat N{N} k{k}", m, dict(N=N, k=k))
        for col in ("perf_leg20", "perf_leg60", "perf_all60"):
            for hi, lo in ((1.25, 0.75), (1.5, 0.5), (1.0, 0.5), (1.5, 1.0)):
                x = F[col].values
                m = np.where(np.isfinite(x), np.where(x > 0, hi, lo), 1.0)
                go(f"roll racha {col} hi{hi} lo{lo}", m, dict(col=col, hi=hi, lo=lo))
        ref = past_median(B, sd)
        for k in (0.5, 1.0):
            m = np.where(np.isfinite(sd) & np.isfinite(ref), np.clip((ref / sd) ** k, 0.5, 1.5), 1.0)
            go(f"roll invvol_leg k{k}", m, dict(k=k))
        # paridad de riesgo entre patas: peso relativo = 1/sd de la pata (sin referencia por pata)
        g = np.nanmedian(sd)
        m = np.where(np.isfinite(sd), np.clip(g / sd, 0.5, 1.5), 1.0)
        go("roll riskparity_legs", m, dict())
        ov = open_overlap(B)
        for f_ in (0.5, 0.75, 1.25, 1.5):
            go(f"roll overlap x{f_}", np.where(ov > 0, f_, 1.0), dict(f=f_))
    if "voltgt" in families:
        atrpct = (B.atrd / B.mid0 * 100).values
        prev = {"har": F.har.values / atrpct, "rv1": F.rv1.values / atrpct, "rv5": F.rv5.values / atrpct,
                "sdR": F.sd_leg60.values, "bvix": F.bvix.values, "gvz": F.f_gvz.values,
                "atr15_atrd": F.atr15_atrd.values}
        for nm, v in prev.items():
            ref = past_median(B, v)
            for k in (0.5, 1.0, 1.5):
                m = np.where(np.isfinite(v) & np.isfinite(ref), np.clip((ref / v) ** k, 0.5, 1.5), 1.0)
                go(f"voltgt {nm} k{k}", m, dict(v=nm, k=k))
    if "bucket" in families:
        feats = ["rv22_pct", "eff20", "adx", "bvix", "f_gvz", "gap", "us_prev", "ret5", "ret21", "cot_z",
                 "f_ry_d5", "usdx_r24", "atr15_atrd", "f_gvz_d5", "atr_ratio", "tod_fav"]
        pats = {"sube": (0.5, 1, 1.5), "baja": (1.5, 1, 0.5), "sin_bajo": (0, 1, 1), "sin_alto": (1, 1, 0)}
        for f_ in feats:
            cuts = past_quantile(B, F[f_].values, [1 / 3, 2 / 3])
            for lg in ("big_one", "momentum"):
                if f_ == "tod_fav" and lg == "big_one":
                    continue
                for pn, pat in pats.items():
                    m = np.where(isleg[lg], bucket_w(B, F[f_].values, cuts, pat), 1.0)
                    go(f"bucket {lg} {f_} {pn}", m, dict(leg=lg, f=f_, pat=pat, q="tercil"))
    if "dow" in families:
        dow = F.dow.values
        for mon in (0.0, 0.5, 0.75):
            for tf in (1.0, 1.25, 1.5):
                m = np.where(isleg["big_one"] & (dow == 0), mon, np.where(isleg["big_one"] & (dow >= 3), tf, 1.0))
                go(f"dow bo lun{mon} juevie{tf}", m, dict(mon=mon, tf=tf))
        for e in (0.5, 1.5):
            go(f"dow mo noticia x{e}", np.where(isleg["momentum"] & (F.ev_any.values == 1), e, 1.0), dict(e=e))
    print("variantes:", n)


if __name__ == "__main__":
    low_priority()
    fam = sys.argv[1:] or ["bo_w", "leg_alloc", "roll", "voltgt", "bucket", "dow"]
    run(fam)
