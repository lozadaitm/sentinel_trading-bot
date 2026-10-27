"""Linea F (27-oct-2026): descarga y carga de DATOS EXTERNOS GRATIS no usados por B y C.

Fuentes (todo sin clave ni registro; se guarda en bot_backtesting/fullsim/data/ext/<fuente>/, fuera de git):
  * fred/   : T5YIE (breakeven 5 a), T5YIFR (inflacion 5a5a), DFII5 (tasa real 5 a), T10Y2Y (pendiente),
              DGS3MO, STLFSI4 (estres financiero, SEMANAL), USEPUINDXD (incertidumbre de politica, diario).
  * cboe/   : VIX9D, VIX3M, SKEW, GVZ (historicos CSV publicos de cdn.cboe.com).
  * gld/    : tenencias del SPDR Gold Trust (xlsx del historical-archive de spdrgoldshares.com).
  * gdelt/  : tono y volumen de noticias en ingles sobre oro / Fed / inflacion (API DOC 2.0, 15 min o 1 h).
Los archivos descargados son DATOS NO CONFIABLES: solo se leen con pandas (csv/xlsx/json), nunca se ejecutan.

Retraso de publicacion (ver informe): cada serie se indexa por la HORA EN QUE YA ES PUBLICA (avail, segundos UTC
servidor) y se une "as of" con la hora de entrada de la operacion (asof_join). Nada mira adelante.

Correr:  .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_ext download   (descarga; GDELT tarda ~30-60 min)
         .venv/Scripts/python -m bot_backtesting.fullsim.opt_F_ext check      (resumen de cobertura)
"""
import io
import json
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "data", "ext")
UA = {"User-Agent": "Mozilla/5.0 (research; low volume)"}

FRED = ["T5YIE", "T5YIFR", "DFII5", "T10Y2Y", "DGS3MO", "STLFSI4", "USEPUINDXD"]
CBOE = {"VIX9D": "VIX9D_History.csv", "VIX3M": "VIX3M_History.csv", "SKEW": "SKEW_History.csv",
        "GVZ": "GVZ_History.csv", "VIX": "VIX_History.csv"}
GDELT_Q = {"gold": '(gold OR bullion) (price OR prices OR ounce OR futures)',
           "fed": '("federal reserve" OR fomc OR powell) (rate OR rates OR inflation)'}


def _get(url, tries=6, wait=6.0):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=90).read()
        except Exception as e:  # 429 / timeouts: espera creciente
            print("  reintento", k + 1, type(e).__name__, str(e)[:80])
            time.sleep(wait * (k + 1) * 2)
    return None


def download_fred():
    os.makedirs(os.path.join(EXT, "fred"), exist_ok=True)
    for s in FRED:
        fp = os.path.join(EXT, "fred", f"{s}.csv")
        if os.path.exists(fp):
            continue
        b = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}&cosd=2019-01-01")
        if b:
            open(fp, "wb").write(b); print("fred", s, len(b))
        time.sleep(1)


def download_cboe():
    os.makedirs(os.path.join(EXT, "cboe"), exist_ok=True)
    for k, f in CBOE.items():
        fp = os.path.join(EXT, "cboe", f)
        if os.path.exists(fp):
            continue
        b = _get(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{f}")
        if b:
            open(fp, "wb").write(b); print("cboe", k, len(b))
        time.sleep(1)


def download_gdelt(start="2022-08-01", end="2026-01-01", step_days=7):
    """Timeline de tono (TIMELINETONE) y volumen (TIMELINEVOLRAW) por bloques de 7 dias.
    Con bloques de 7 dias GDELT devuelve resolucion horaria. Una peticion cada >=6 s (pide 5 s)."""
    d = os.path.join(EXT, "gdelt"); os.makedirs(d, exist_ok=True)
    days = pd.date_range(start, end, freq=f"{step_days}D")
    for name, q in GDELT_Q.items():
        for mode in ("timelinetone", "timelinevolraw"):
            for a in days:
                b = min(a + pd.Timedelta(days=step_days), pd.Timestamp(end))
                fp = os.path.join(d, f"{name}_{mode}_{a:%Y%m%d}.json")
                if os.path.exists(fp) and os.path.getsize(fp) > 50:
                    continue
                url = ("https://api.gdeltproject.org/api/v2/doc/doc?query="
                       + urllib.request.quote(q + " sourcelang:english")
                       + f"&mode={mode}&format=json&startdatetime={a:%Y%m%d}000000&enddatetime={b:%Y%m%d}000000")
                raw = _get(url, wait=8)
                time.sleep(6.5)
                if raw is None:
                    print("FALLA", fp); continue
                try:
                    json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    print("no-json", fp, raw[:80]); continue
                open(fp, "wb").write(raw)
                print("gdelt", name, mode, a.date())


def download_gdelt_daily(start="20220801", end="20260101"):
    """Version de pocas peticiones: resolucion DIARIA para todo el periodo (4 peticiones). GDELT limita a 1 cada 5 s
    y en esta IP devuelve 429 a menudo: se espera hasta ~2 min entre intentos."""
    d = os.path.join(EXT, "gdelt"); os.makedirs(d, exist_ok=True)
    for name, q in GDELT_Q.items():
        for mode in ("timelinetone", "timelinevolraw"):
            fp = os.path.join(d, f"daily_{name}_{mode}.json")
            if os.path.exists(fp) and os.path.getsize(fp) > 200:
                continue
            url = ("https://api.gdeltproject.org/api/v2/doc/doc?query="
                   + urllib.request.quote(q + " sourcelang:english")
                   + f"&mode={mode}&format=json&startdatetime={start}000000&enddatetime={end}000000")
            for k in range(20):
                time.sleep(60 + 15 * k)
                try:
                    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()
                    j = json.loads(raw.decode("utf-8", "replace"))
                    open(fp, "wb").write(raw)
                    print("gdelt diario", name, mode, j.get("query_details"), len(j["timeline"][0]["data"]), flush=True)
                    break
                except Exception as e:
                    print("  intento", k + 1, name, mode, type(e).__name__, str(e)[:60], flush=True)


# ------------------------------------------------------------------ carga con hora de publicacion
NY = "America/New_York"


def _srv(ts_ny):
    """Timestamp NY (tz-aware) -> segundos 'servidor' (UTC naive + 7 h respecto a NY = como las velas)."""
    # servidor = NY + 7 h  -> segundos epoch de la hora servidor naive
    return ((ts_ny.tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)) - pd.Timestamp(0)).total_seconds()


def avail_daily(dates, bdays_lag, hour_ny):
    """Hora (seg. servidor) en que el dato de la fecha NY `dates` ya es publico: fecha + n dias habiles, hh NY.
    Servidor = hora NY + 7 h siempre (sigue el horario de verano de NY), asi que basta sumar."""
    d = pd.DatetimeIndex(pd.to_datetime(dates)) + pd.offsets.BDay(bdays_lag)
    return ((d + pd.Timedelta(hours=hour_ny + 7)) - pd.Timestamp(0)).total_seconds().values


def load_fred(s):
    X = pd.read_csv(os.path.join(EXT, "fred", f"{s}.csv"))
    X.columns = ["date", "v"]
    X["v"] = pd.to_numeric(X.v, errors="coerce")
    X = X.dropna()
    if s == "STLFSI4":     # semanal: fecha = viernes de fin de semana; se publica el jueves siguiente ~10:00 NY
        X["avail"] = avail_daily(X.date, 4, 12)
    elif s == "USEPUINDXD":  # diario, se actualiza con ~1-2 dias de retraso: 3 dias habiles por seguridad
        X["avail"] = avail_daily(X.date, 3, 12)
    else:                   # FRED/H.15 diario: 1 dia habil; usamos 2 (igual que la linea B)
        X["avail"] = avail_daily(X.date, 2, 9)
    return X[["date", "v", "avail"]]


def load_cboe(k):
    X = pd.read_csv(os.path.join(EXT, "cboe", CBOE[k]))
    X.columns = [c.strip().upper() for c in X.columns]
    c = "CLOSE" if "CLOSE" in X.columns else X.columns[-1]
    X = pd.DataFrame({"date": pd.to_datetime(X["DATE"]), "v": pd.to_numeric(X[c], errors="coerce")}).dropna()
    # cierre 16:15 NY; el CSV historico se refresca al dia siguiente -> publico al dia habil siguiente 09:00 NY
    X["avail"] = avail_daily(X.date, 1, 9)
    return X


def load_gld():
    X = pd.read_excel(os.path.join(EXT, "gld", "gld_hist.xlsx"), sheet_name="US GLD Historical Archive")
    X = X.rename(columns=lambda c: str(c).strip())
    out = pd.DataFrame({"date": pd.to_datetime(X["Date"], format="%d-%b-%Y", errors="coerce"),
                        "tonnes": pd.to_numeric(X["Tonnes of Gold"], errors="coerce"),
                        "prem": pd.to_numeric(X.filter(like="Premium").iloc[:, 0], errors="coerce"),
                        "vol": pd.to_numeric(X["Daily Share Volume"], errors="coerce")}).dropna(subset=["date"])
    out = out.sort_values("date").reset_index(drop=True)
    out["tonnes"] = out.tonnes.ffill()
    # SPDR publica las tenencias del dia T por la noche de T o la manana de T+1 -> publico T+1 09:00 NY
    out["avail"] = avail_daily(out.date, 1, 9)
    return out


def load_gdelt(name):
    """Serie horaria (o 15 min) de tono medio y n de articulos. 'end' = fin del intervalo en UTC; la serie se
    considera publica al FIN del intervalo + 30 min (latencia de ingesta de GDELT ~15 min)."""
    d = os.path.join(EXT, "gdelt")
    rows = {}
    for mode, col in (("timelinetone", "tone"), ("timelinevolraw", "n")):
        for f in sorted(os.listdir(d)):
            if not (f == f"daily_{name}_{mode}.json"):
                continue
            try:
                j = json.loads(open(os.path.join(d, f), encoding="utf-8", errors="replace").read())
                ser = j["timeline"][0]["data"]
            except Exception:
                continue
            for p in ser:
                ts = pd.Timestamp(p["date"].replace("T", " ").replace("Z", ""))
                rows.setdefault(ts, {})[col] = p.get("value", np.nan)
                if col == "n" and "norm" in p:
                    rows[ts]["norm"] = p["norm"]
    if not rows:
        return None
    G = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    G.index.name = "utc"
    step = G.index.to_series().diff().median()
    ny = pd.DatetimeIndex(G.index + step + pd.Timedelta(minutes=30)).tz_localize("UTC").tz_convert(NY).tz_localize(None)
    G["avail"] = ((ny + pd.Timedelta(hours=7)) - pd.Timestamp(0)).total_seconds().values
    G["step_min"] = step.total_seconds() / 60
    return G.reset_index()


def asof_join(t_entry, X, col):
    """Ultimo valor de X[col] con avail <= t_entry (segundos servidor)."""
    X = X.dropna(subset=["avail", col]).sort_values("avail")
    i = np.searchsorted(X.avail.values, np.asarray(t_entry, float), side="right") - 1
    v = X[col].values
    return np.where(i >= 0, v[np.clip(i, 0, None)], np.nan)


def check():
    for s in FRED:
        try:
            X = load_fred(s); print("fred", s, len(X), X.date.min(), X.date.max())
        except Exception as e:
            print("fred", s, "ERR", e)
    for k in CBOE:
        try:
            X = load_cboe(k); print("cboe", k, len(X), X.date.min().date(), X.date.max().date())
        except Exception as e:
            print("cboe", k, "ERR", e)
    G = load_gld(); print("gld", len(G), G.date.min().date(), G.date.max().date())
    for n in GDELT_Q:
        g = load_gdelt(n)
        print("gdelt", n, None if g is None else (len(g), g.utc.min(), g.utc.max(), g.step_min.iat[0]))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "download":
        download_fred(); download_cboe()
        if "--gdelt-hourly" in sys.argv:
            download_gdelt()
        elif "--no-gdelt" not in sys.argv:
            download_gdelt_daily()
    check()
