"""Reglas puras de las tres patas del motor e2 (sin MT5).

Diseno: docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md (secciones 2-4).
Replican exactamente lo que calcula el simulador de investigacion. Los tiempos son
epochs de servidor, tratados como UTC ingenuo (convencion del repo).
"""

import datetime
import functools
import math

import numpy as np
import pandas as pd

SLOT = 900  # franja de 15 minutos


@functools.lru_cache(maxsize=None)
def _no_entry_dates(year):
    """Feriados federales de EE. UU. (con fecha observada) del año, mas el viernes
    tras Thanksgiving, el 24 y el 31 de diciembre. Incluye el 31-dic del año
    anterior observado por un 1-ene en sabado (rango con margen)."""
    from pandas.tseries.holiday import USFederalHolidayCalendar
    hol = USFederalHolidayCalendar().holidays(start=f"{year - 1}-12-01", end=f"{year + 1}-01-31")
    out = {ts.date() for ts in hol}
    thursdays = [d for d in pd.date_range(f"{year}-11-01", f"{year}-11-30") if d.weekday() == 3]
    out.add((thursdays[3] + pd.Timedelta(days=1)).date())   # viernes tras Thanksgiving
    out.add(datetime.date(year, 12, 24))
    out.add(datetime.date(year, 12, 31))
    return frozenset(out)


@functools.lru_cache(maxsize=4096)
def us_no_entry_day(day):
    """True si el dia de servidor (epoch // 86400) es feriado de EE. UU. o de cierre
    anticipado: Momentum y NFP no entran (la salida de 21:00 puede no llegar)."""
    d = (pd.Timestamp(0, unit="s") + pd.Timedelta(days=int(day))).date()
    return d in _no_entry_dates(d.year)


def trend_state(d1_close):
    """signo(C - C[-22]) + signo(C - C[-64]); cierres D1 hasta el dia anterior.
    Menos de 64 cierres -> 0."""
    c = np.asarray(d1_close, dtype=float)
    if len(c) < 64:
        return 0
    return int(np.sign(c[-1] - c[-22]) + np.sign(c[-1] - c[-64]))


def atr_daily(day_high, day_low):
    """Media de (H - L) de los ultimos 14 dias (solo dias anteriores); NaN si hay menos."""
    r = np.asarray(day_high, dtype=float) - np.asarray(day_low, dtype=float)
    if len(r) < 14:
        return float("nan")
    return float(r[-14:].mean())


def atr15(high, low, close):
    """Media simple del rango verdadero de las ultimas 14 velas M15 cerradas.
    La primera vela del arreglo usa TR = H - L (sin cierre previo)."""
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    tr = h - l
    if len(h) > 1:
        pc = c[:-1]
        tr[1:] = np.maximum(tr[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    if len(tr) < 14:
        return float("nan")
    return float(tr[-14:].mean())


def bigone_weight(state, event_day, w_nontrend=0.5, w_event=0.5):
    """Peso del Big One: 1.0 con tendencia alcista (+2), w_nontrend si no;
    se multiplica por w_event en dia de evento."""
    w = 1.0 if state == 2 else w_nontrend
    return w * w_event if event_day else w


def momentum_side(p01, p15, state, thr_pct=0.232):
    """+-1 si |(p15-p01)/p01*100| > thr y la tendencia es +-2; si no, 0."""
    if state not in (2, -2) or not p01:
        return 0
    mov = (p15 - p01) / p01 * 100.0
    if abs(mov) > thr_pct:
        return 1 if mov > 0 else -1
    return 0


def nfp_side(open_before, price_after):
    """Signo de price_after - open_before (0 si iguales)."""
    d = price_after - open_before
    return 1 if d > 0 else (-1 if d < 0 else 0)


def ladder_lots(balance, risk_pct, weight, atr_d, step=0.01, vmin=0.01, vmax=100.0):
    """Tres tercios iguales; cada uno acotado a [vmin, vmax]. [] si atr_d invalido."""
    if atr_d is None or not math.isfinite(atr_d) or atr_d <= 0:
        return []
    third = balance * risk_pct * weight / (atr_d * 100.0) / 3.0
    lot = math.floor(third / step + 1e-9) * step
    lot = round(min(max(lot, vmin), vmax), 2)
    return [lot, lot, lot]


def lock_trigger(side, entry, atr_d, mult=1.0):
    """Precio del candado: entry - side * mult * atr_d."""
    return entry - side * mult * atr_d


def tp_prices(side, entry, atr_15, mults=(2.0, 3.0)):
    """Precios objetivo de los tercios 2 y 3."""
    return tuple(entry + side * m * atr_15 for m in mults)


def effective_risk(lots_total, atr_d, balance):
    """Riesgo efectivo como fraccion del balance."""
    return lots_total * atr_d * 100.0 / balance


def _is_market_slot(t):
    """Franja abierta: lunes a viernes, de 01:00 a 23:59 (hora de servidor)."""
    day = t // 86400
    return (day + 3) % 7 < 5 and (t % 86400) >= 3600


def _next_market_slot(t):
    """Primer inicio de franja >= t que sea de mercado."""
    while not _is_market_slot(t):
        day = t // 86400
        if (day + 3) % 7 >= 5:
            t = (day + 1) * 86400 + 3600 if (day + 3) % 7 == 6 else (day + 1) * 86400
        elif (t % 86400) < 3600:
            t = day * 86400 + 3600
        else:
            t += SLOT
    return t


def add_market_bars(t, n):
    """Fin de la n-esima franja M15 de mercado; la franja que empieza en t cuenta como la primera."""
    cur = _next_market_slot((int(t) // SLOT) * SLOT)
    for _ in range(n - 1):
        cur = _next_market_slot(cur + SLOT)
    return cur + SLOT


def exit_epoch(leg, entry_epoch, nfp_bars=96):
    """Hora de salida de la pata (epoch de servidor)."""
    day0 = (int(entry_epoch) // 86400) * 86400
    if leg == "bigone":
        return day0 + 10 * 3600
    if leg == "mom":
        return day0 + 21 * 3600
    if leg == "nfp":
        return add_market_bars(entry_epoch, nfp_bars)
    raise ValueError(f"pata desconocida: {leg}")
