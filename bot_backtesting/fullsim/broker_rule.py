"""Reglas horarias genericas sobre PRECIOS DEL BROKER (M15 XAUUSD+), con candado y validacion movil.
Mismo motor de salidas que bigone_broker (hora, objetivo, trailing; candado amplio en ATR M15 o diario).

Reglas:
  bigone          : compra 01:00 -> 10:00 (todas las tendencias; peso por estado en la cartera)
  ny_mom          : 15:00 -> 21:00 en la direccion de Asia (01:00 -> 15:00) si |Asia| > 0,5 desv.
                    (desv. fijada con 2022-08..2024-06); solo tendencia diaria +2
  ny_mom_venta    : solo la pata vendedora de ny_mom (Asia bajo en tendencia alcista)
Cartera: Big One + ny_mom; riesgo fijo o piso de Grossman-Zhou; calendario 2024-01 -> 2026-10.
Uso: python -m bot_backtesting.fullsim.broker_rule
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.bigone_broker import BASE, COMM, LOCK_COST, SCALES, SPREAD, load
from bot_backtesting.fullsim.entrylab import swap_cost

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
CAL = pd.period_range("2024-01", "2026-10", freq="M")
SPLIT = pd.Timestamp("2024-07-01").timestamp() // 86400


_HAR = None


def har_scale(d, px, D):
    """Volatilidad diaria prevista (HAR de econ_build) llevada a unidades de ATR M15 con la razon mediana
    ATR15/vol-22d de 2022-08..2023 (fija)."""
    global _HAR
    if _HAR is None:
        E = pd.read_pickle(os.path.join(DATA, "econ", "econ_daily2.pkl"))
        _HAR = (E.rvhat_3, E.rv22_l)
    rv, rv22 = _HAR
    return rv.get(d, np.nan) / 100 * px, rv22.get(d, np.nan) / 100 * px


def build(name, h, nbars, side_fn, entries=None):
    """entries: lista opcional de (epoch_servidor_alineado_a_M15, lado) en vez de hora fija + side_fn."""
    X, D = load()
    T, O, H, L, C = (X[c].values for c in ("time", "open", "high", "low", "close"))
    E = pd.read_csv(os.path.join(os.path.dirname(__file__), "events_us.csv"))
    evd = set((pd.to_datetime(E.date) - pd.Timestamp("1970-01-01")).dt.days)
    idx = pd.Series(np.arange(len(T)), index=T)
    rows = []
    if entries is None:
        plan = [(k, None) for k in np.nonzero(T % 86400 == h * 3600)[0]]
    else:
        plan = [(idx[t], sd) for t, sd in entries if t in idx.index]
    # razon fija ATR15 / vol-22d para la escala HAR (2022-08..2023)
    if "k_har" not in D:
        r = [(X.atr15.iat[k], har_scale(T[k] // 86400, O[k], D)[1]) for k in np.nonzero(T % 86400 == 3600)[0] if T[k] < 1.704e9]
        r = np.array([a / b for a, b in r if np.isfinite(a) and np.isfinite(b) and b > 0])
        D["k_har"] = np.median(r)
    k_har = D["k_har"].iat[0]
    for k, side0 in plan:
        d = T[k] // 86400
        if (d + 3) % 7 >= 5 or d not in D.index or not np.isfinite(D.at[d, "atrd"]) or not np.isfinite(X.atr15.iat[k]):
            continue
        if k + nbars > len(T) or T[k + nbars - 1] - T[k] > nbars * 900 + 3 * 86400:
            continue
        side = side0 if side0 is not None else side_fn(d, k, T, O, idx, D)
        if not side:
            continue
        har = har_scale(d, O[k], D)[0] * k_har
        if side == 1:
            px = O[k] + SPREAD
            fav, low, opn, last = H[k:k + nbars] - px, L[k:k + nbars] - px, O[k:k + nbars] - px, C[k + nbars - 1] - px
        else:
            px = O[k]
            fav = px - (L[k:k + nbars] + SPREAD); low = px - (H[k:k + nbars] + SPREAD)
            opn = px - (O[k:k + nbars] + SPREAD); last = px - (C[k + nbars - 1] + SPREAD)
        pprev = np.r_[-np.inf, np.maximum.accumulate(fav)[:-1]]
        for sc_name, locks in list(SCALES.items()) + [("har", (2.0, 3.0, 4.0, 6.0))]:
            sc = {"atr15": X.atr15.iat[k], "atrd": D.at[d, "atrd"], "har": har}[sc_name]
            if not np.isfinite(sc) or sc <= 0:
                continue
            u = X.atr15.iat[k] if sc_name != "har" else har
            for kind, a, dd in BASE:
                i_out, r = nbars - 1, last
                if kind == "tp":
                    hit = np.nonzero(fav >= a * u)[0]
                    if len(hit):
                        i_out, r = hit[0], a * u
                elif kind == "trail":
                    stop = pprev - dd * u
                    hit = np.nonzero((pprev >= a * u) & (low <= stop))[0]
                    if len(hit):
                        i_out = hit[0]; r = min(opn[i_out], stop[i_out])
                for lk in locks:
                    lh = np.nonzero(low[:i_out + 1] <= -lk * sc)[0]
                    io, rr, extra = i_out, r, 0.0
                    if len(lh):
                        io = lh[0]; rr = min(opn[io], -lk * sc); extra = -LOCK_COST
                    mae = rr if extra else low[:io + 1].min()
                    pnl = rr - COMM + extra + swap_cost(T[k], T[k + io] + 900, side)
                    rows.append((T[k], d, D.at[d, "s"], int(d in evd), side, sc_name, kind, a, dd, lk, pnl, mae, lk * sc))
    R = pd.DataFrame(rows, columns=["t", "d", "state", "ev", "side", "scale", "kind", "a", "dd", "lock", "pnl", "mae", "risk_oz"])
    R["year"] = pd.to_datetime(R.t, unit="s").dt.year
    R["exit"] = R.scale + "_" + R.kind + "_" + R.a.astype(str) + "_" + R.dd.astype(str) + "_L" + R.lock.astype(str)
    R["r_mult"] = R.pnl / R.risk_oz
    R["rule"] = name
    return R


def walk_forward(R):
    out = []
    for Y in (2024, 2025, 2026):
        tr, te = R[R.year.isin([Y - 2, Y - 1])], R[R.year == Y]
        if tr.empty or te.empty:
            continue
        best = tr.groupby("exit").r_mult.mean().idxmax()
        out.append(te[te.exit == best].assign(chosen=best))
    return pd.concat(out, ignore_index=True)


def asia_side(min_sd, only=None):
    cache = {}

    def fn(d, k, T, O, idx, D):
        if D.at[d, "s"] != 2:
            return 0
        k1 = idx.get(d * 86400 + 3600)
        if k1 is None:
            return 0
        a = (O[k] - O[k1]) / O[k1] * 100
        if "sd" not in cache:
            cache["sd"] = 0.46                                    # desv. de Asia 01->15 en 2022-08..2024-06 (broker_map)
        if abs(a) <= min_sd * cache["sd"]:
            return 0
        s = int(np.sign(a))
        return s if only is None or s == only else 0
    return fn


def account(T, scheme, bal=5000.0, n=2000):
    T = T.sort_values("t").copy(); T["m"] = pd.to_datetime(T.t, unit="s").dt.to_period("M"); T["mr"] = T.mae / T.risk_oz
    months = [T.loc[T.m == p, ["r_mult", "mr", "w"]].values.reshape(-1, 3) for p in CAL]

    def path(seq):
        eq, peak, dd = bal, bal, 0.0
        for r, m, w in seq:
            if scheme[0] == "fijo":
                f = scheme[1]
            else:                                                 # piso de Grossman-Zhou: riesgo ~ colchon sobre fl x maximo
                fl, f0 = scheme[1], scheme[2]
                f = f0 * max(0.0, (eq - fl * peak) / eq) / (1 - fl)
            risk = eq * min(f, 0.10) * w
            dd = max(dd, (peak - (eq + min(0.0, m) * risk)) / peak)
            eq += r * risk; peak = max(peak, eq); dd = max(dd, (peak - eq) / peak)
            if eq <= bal * 0.05:
                return eq / bal, 1.0
        return eq / bal, dd
    rng = np.random.default_rng(7)
    res = [path(np.vstack([months[i] for i in rng.integers(0, len(months), 12)])) for _ in range(n)]
    mult = np.array([x[0] for x in res]); dd = np.array([x[1] for x in res]); real = path(np.vstack(months))
    return dict(x12=np.median(mult), mes=np.median(mult) ** (1 / 12) - 1, p_x2=(mult >= 2).mean(), p_x3=(mult >= 3).mean(),
                p_dd50=(dd >= .5).mean(), real_x=real[0], real_dd=real[1])


def main():
    rules = {
        "bigone": (1, 36, lambda d, k, T, O, idx, D: 1),
        "ny_mom": (15, 24, asia_side(0.5)),
        "ny_mom_venta": (15, 24, asia_side(0.5, only=-1)),
    }
    W = {}
    pd.set_option("display.width", 250)
    for name, (h, nb, fn) in rules.items():
        fp = os.path.join(RESULTS, f"broker_rule_{name}.pkl")
        R = pd.read_pickle(fp) if os.path.exists(fp) else build(name, h, nb, fn)
        R.to_pickle(fp)
        ref = R[R.exit == "atrd_time_None_None_L1.5"] if (R.exit == "atrd_time_None_None_L1.5").any() else R[R.kind == "time"]
        print(f"{name}: n/año ~{R.groupby('year').t.nunique().mean():.0f} | salida por hora, R por año:",
              ref.groupby("year").r_mult.mean().round(3).to_dict())
        if name == "bigone":
            parts = [walk_forward(g).assign(w=w) for s, g in R.groupby("state") for w in [{2: 1.0, 0: 0.5, -2: 0.5}.get(s, 0)] if w > 0]
            W[name] = pd.concat(parts, ignore_index=True)
        else:
            W[name] = walk_forward(R).assign(w=1.0)
        x = W[name]
        print(f"   validacion movil: R por año {x.groupby('year').r_mult.mean().round(3).to_dict()} total {x.r_mult.mean():+.3f} n {len(x)}")
    rows = []
    for combo in (("bigone",), ("ny_mom",), ("bigone", "ny_mom"), ("bigone", "ny_mom_venta")):
        T = pd.concat([W[c] for c in combo], ignore_index=True)
        for sch in (("fijo", 0.02), ("fijo", 0.03), ("fijo", 0.05), ("gz", 0.5, 0.06), ("gz", 0.6, 0.06)):
            rows.append(dict(cartera="+".join(combo), esquema=str(sch), **account(T, sch)))
    a = W["bigone"].groupby("d").r_mult.sum(); b = W["ny_mom"].groupby("d").r_mult.sum()
    j = pd.concat([a, b], axis=1).fillna(0)
    print("correlacion diaria Big One vs ny_mom:", round(j.corr().iloc[0, 1], 3))
    print(pd.DataFrame(rows).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
