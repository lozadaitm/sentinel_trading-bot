"""Tabla diaria (dia servidor) para el estudio econometrico del XAUUSD.
Oro (broker/Dukascopy M5), cruzados (Dukascopy M5), FRED (macro EE.UU.), COT (CFTC), eventos.
Columnas *_l = conocidas ANTES de la reapertura 01:00 del dia d (sin mirar adelante).
Uso: python -m bot_backtesting.fullsim.econ_build [fetch]   (fetch baja FRED y CFTC a data/econ)
Salida: data/econ/econ_daily.pkl"""
import io, os, glob, sys, urllib.request, zipfile
import numpy as np, pandas as pd
FS = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.join(FS, "data", "econ")
FRED = ("DFII10", "DGS10", "DGS2", "T10YIE", "DTWEXBGS", "VIXCLS", "DFF", "BAMLH0A0HYM2", "DCOILWTICO")


def fetch():
    """Series publicas: FRED (macro EE.UU.) y CFTC (COT desagregado, oro COMEX)."""
    os.makedirs(os.path.join(HERE, "macro"), exist_ok=True); os.makedirs(os.path.join(HERE, "cot"), exist_ok=True)
    for k in FRED:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={k}&cosd=2019-01-01"
        open(os.path.join(HERE, "macro", f"{k}.csv"), "wb").write(urllib.request.urlopen(url, timeout=60).read())
    out = []
    for y in range(2019, pd.Timestamp.now().year + 1):
        raw = urllib.request.urlopen(f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{y}.zip", timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(raw)); d = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
        out.append(d[d.Market_and_Exchange_Names.str.startswith("GOLD - COMMODITY EXCHANGE")])
    pd.concat(out).to_csv(os.path.join(HERE, "cot", "gold_cot.csv"), index=False)


if len(sys.argv) > 1 and sys.argv[1] == "fetch":
    fetch()
B = pd.read_pickle(os.path.join(FS, "data", "bars_all.pkl"))
m5 = B["M5"].copy(); m5["d"] = m5.time // 86400
m5["lr"] = np.log(m5.close).diff()
g = m5.groupby("d")
D = pd.DataFrame({"o": g.open.first(), "h": g.high.max(), "l": g.low.min(), "c": g.close.last(),
                  "rv": np.sqrt(g.lr.apply(lambda x: (x ** 2).sum())) * 100, "n": g.size()})
D = D[D.n > 150]
D["ret"] = np.log(D.c).diff() * 100                       # % del dia (cierre a cierre)
D["rng_pct"] = (D.h - D.l) / D.c * 100
# reapertura: 01:00 -> 01:15 / 10:00 (en %), y resto del dia 10:00 -> cierre
s = m5.set_index("time")
def px(t, col):
    return s[col].reindex(t).values
t1 = D.index.values * 86400 + 3600
D["r_open15"] = (px(t1 + 600, "close") / px(t1, "open") - 1) * 100
D["r_asia"] = (px(t1 + 9 * 3600 - 300, "close") / px(t1, "open") - 1) * 100
D["r_rest"] = (D.c / px(t1 + 9 * 3600 - 300, "close") - 1) * 100
# cruzados: retorno diario % (dia servidor)
for nm in ("dxy", "ustbond", "xag", "eurusd"):
    x = pd.read_pickle(os.path.join(FS, "data", f"cross_{nm}.pkl")); x["d"] = x.time // 86400
    c = x.groupby("d").close.last()
    D[f"x_{nm}"] = (np.log(c).diff() * 100).reindex(D.index)
# FRED: fecha d = cierre EE.UU. del dia d ~ dia servidor d. Se publican al dia habil siguiente.
fr = {}
for f in glob.glob(os.path.join(HERE, "macro", "*.csv")):
    k = os.path.basename(f)[:-4]
    z = pd.read_csv(f); z.columns = ["date", k]
    z[k] = pd.to_numeric(z[k], errors="coerce")
    z["d"] = (pd.to_datetime(z.date) - pd.Timestamp("1970-01-01")).dt.days
    fr[k] = z.set_index("d")[k]
F = pd.DataFrame(fr).sort_index()
F = F.reindex(range(F.index.min(), D.index.max() + 1)).ffill()
lvl = {"DFII10": "ry", "DGS10": "y10", "DGS2": "y2", "T10YIE": "bei", "VIXCLS": "vix", "DFF": "ff", "BAMLH0A0HYM2": "hy"}
for k, n in lvl.items():
    F[f"d_{n}"] = F[k].diff()
F["d_usd"] = np.log(F.DTWEXBGS).diff() * 100
F["d_oil"] = np.log(F.DCOILWTICO.where(F.DCOILWTICO > 0)).diff() * 100
F["vix"] = F.VIXCLS; F["ry"] = F.DFII10; F["curve"] = F.DGS10 - F.DGS2
F["ry_chg20"] = F.DFII10.diff(20); F["usd_chg20"] = np.log(F.DTWEXBGS).diff(20) * 100
cols = ["d_ry", "d_y10", "d_y2", "d_bei", "d_vix", "d_ff", "d_hy", "d_usd", "d_oil", "vix", "ry", "curve", "ry_chg20", "usd_chg20"]
for k in cols:
    D[f"m_{k}"] = F[k].reindex(D.index).values                 # contemporaneo (explicativo)
    D[f"m_{k}_l"] = F[k].shift(2).reindex(D.index).values      # conocido antes de la 01:00 (rezago seguro)
# COT: posicion martes, publicada viernes; usable desde el lunes siguiente (+6 dias)
C = pd.read_csv(os.path.join(HERE, "cot", "gold_cot.csv"))
C["d"] = (pd.to_datetime(C["Report_Date_as_YYYY-MM-DD"]) - pd.Timestamp("1970-01-01")).dt.days + 6
C = C.sort_values("d").drop_duplicates("d")
net = (C.M_Money_Positions_Long_All - C.M_Money_Positions_Short_All) / C.Open_Interest_All * 100
cot = pd.DataFrame({"cot_net": net.values, "cot_chg": net.diff().values,
                    "cot_z": ((net - net.rolling(52).mean()) / net.rolling(52).std()).values}, index=C.d.values)
cot = cot.reindex(range(cot.index.min(), D.index.max() + 1)).ffill()
for k in cot.columns:
    D[f"{k}_l"] = cot[k].reindex(D.index).values
# eventos (dia de NFP/CPI/FOMC) y calendario
E = pd.read_csv(os.path.join(FS, "events_us.csv"))
ed = (pd.to_datetime(E.date) - pd.Timestamp("1970-01-01")).dt.days
for k in ("NFP", "CPI", "FOMC"):
    D[f"ev_{k}"] = D.index.isin(ed[E.event == k].values).astype(int)
D["ev_any"] = D[["ev_NFP", "ev_CPI", "ev_FOMC"]].max(axis=1)
D["dow"] = (D.index.values + 3) % 7
D["year"] = pd.to_datetime(D.index.values * 86400, unit="s").year
# tecnico del oro, conocido al cierre de d-1
c = D.c
D["mom1_l"] = D.ret.shift(1); D["mom5_l"] = (np.log(c).diff(5) * 100).shift(1)
D["mom20_l"] = (np.log(c).diff(20) * 100).shift(1); D["mom63_l"] = (np.log(c).diff(63) * 100).shift(1)
D["tsmom_l"] = (np.sign(c - c.shift(21)) + np.sign(c - c.shift(63))).shift(1)
D["rv_l"] = D.rv.shift(1); D["rv5_l"] = D.rv.rolling(5).mean().shift(1); D["rv22_l"] = D.rv.rolling(22).mean().shift(1)
D["dist_ma50_l"] = ((c - c.rolling(50).mean()) / (D.rv22_l * c / 100)).shift(1)
for nm in ("dxy", "ustbond", "xag", "eurusd"):
    D[f"x_{nm}_l"] = D[f"x_{nm}"].shift(1)
D.to_pickle(os.path.join(HERE, "econ_daily.pkl"))
print(D.shape, pd.to_datetime(D.index.min() * 86400, unit="s").date(), pd.to_datetime(D.index.max() * 86400, unit="s").date())
print(D.notna().mean().round(2).to_string())
