"""Reproduccion del motor e2 (bot/strategy_e2.py, SessionEngine) contra el simulador del broker.

Alimenta el SessionEngine REAL (sin tocarlo, solo por sus seams _fetch_tick/_rates_d1/_rates_m15/
_events) con un flujo de ticks sinteticos armado con las velas M15 del broker
(data/broker_m15_full.pkl, fuera de git) y un broker falso que ejecuta al precio del tick
(compra al ask, venta al bid; ask = bid + 0,17). Periodo 2025-11-01 -> 2026-10-16.

Camino dentro de la vela (decision documentada):
  * modo "sim" (el que se evalua): open; luego primero el extremo ADVERSO a la pata abierta
    (para una compra O, L, H, C; para una venta O, H, L, C; sin pata abierta, O-L-H-C si C >= O y
    O-H-L-C si no) -> igual que el simulador, que mira el candado en el extremo adverso antes que
    los objetivos. Ademas, como el precio real es continuo, cuando un tramo del camino cruza el
    precio del candado o de un objetivo se inserta un tick EXACTAMENTE en ese precio (el simulador
    ejecuta el candado en min(open, nivel) y el objetivo en el nivel). Cada pata corre en su propia
    instancia del motor (e2_legs = una pata) para que el orden adverso sea el de esa pata
    (NFP y momentum pueden estar abiertas a la vez con lados opuestos).
  * modo "raw" (referencia, todas las patas juntas): solo 4 ticks por vela, O-L-H-C si C >= O y
    O-H-L-C si no, sin ticks en los niveles. Sirve para cuantificar cuanto pesa el camino sintetico.
Hora de los ticks: open a la hora de la vela, los demas a +1/+2/+3 min (los insertados entre medio).

P&L en $/oz por tercio con la misma contabilidad del simulador: precio (incluye el spread de
entrada y del candado) - comision 0,06 por posicion (tercio y candado) + swap_cost hasta el cierre
del tercio o hasta el candado (convencion del simulador).
Uso: python -m bot_backtesting.fullsim.e2_replay
"""
import os
import sys
import tempfile
import time as _time
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_M15 = os.path.join(HERE, "data", "broker_m15_full.pkl")
EVENTS = os.path.join(HERE, "events_us.csv")
OUT = os.path.join(HERE, "results", "e2_replay.pkl")

START, END = pd.Timestamp("2025-11-01"), pd.Timestamp("2026-10-17")   # [START, END)
SPREAD, COMM = 0.17, 0.06
DAY = 86400
LEGS = ("bigone", "mom", "nfp")
PATA = {"bigone": "big_one", "mom": "momentum_eeuu", "nfp": "nfp"}
EVENT_NAMES = {"NFP": "Non-Farm Employment Change", "CPI": "CPI m/m", "FOMC": "Federal Funds Rate"}
TOL_PNL = 0.05
TOL_MATCH = 0.98


# ----------------------------------------------------------------------------- datos
def load_bars():
    X = pd.read_pickle(DATA_M15).sort_values("time").reset_index(drop=True)
    return X[["time", "open", "high", "low", "close"]].astype({"time": "int64"})


def load_events():
    """events_us.csv -> eventos USD/high con hora de servidor (UTC+3 con DST de NY, si no +2),
    igual que broker_round2.news_entries (sin el redondeo a 15 min: lo hace el motor)."""
    E = pd.read_csv(EVENTS)
    out = []
    for e in E.itertuples():
        utc = pd.Timestamp(f"{e.date} {e.time_utc}")
        ny = utc.tz_localize("UTC").tz_convert("America/New_York")
        t = int(utc.timestamp()) + (3 if ny.dst().total_seconds() else 2) * 3600
        out.append({"time": t, "currency": "USD", "importance": "high", "name": EVENT_NAMES[e.event]})
    return sorted(out, key=lambda ev: ev["time"])


class Market:
    """Velas M15 y D1 (agregadas por dia de servidor, como bigone_broker.load) vistas desde 'now'."""

    def __init__(self, X):
        self.X = X
        self.t = X.time.values
        self.o, self.h, self.l, self.c = (X[k].values for k in ("open", "high", "low", "close"))
        d = self.t // DAY
        D = X.assign(d=d).groupby("d").agg(open=("open", "first"), high=("high", "max"),
                                           low=("low", "min"), close=("close", "last"))
        self.D = D
        self.dkeys = D.index.values

    def m15(self, now, n):
        """Ultimas n velas con time <= now; la ultima (en formacion) solo trae su open."""
        j = int(np.searchsorted(self.t, now, side="right"))
        i = max(0, j - n)
        df = self.X.iloc[i:j].copy()
        if len(df) and df.time.iloc[-1] + 900 > now:
            o = df.open.iloc[-1]
            df.iloc[-1, df.columns.get_indexer(["high", "low", "close"])] = [o, o, o]
        return df.reset_index(drop=True)

    def d1(self, now, n):
        """Ultimas n filas D1; la del dia en curso parcial (velas cerradas + open de la que forma)."""
        day = now // DAY
        j = int(np.searchsorted(self.dkeys, day, side="left"))
        prev = self.D.iloc[max(0, j - (n - 1)):j]
        rows = prev.reset_index().rename(columns={"d": "time"})
        rows["time"] = rows.time * DAY
        cur = self.m15(now, 200)
        cur = cur[cur.time // DAY == day]
        if len(cur):
            rows = pd.concat([rows, pd.DataFrame([{"time": day * DAY, "open": cur.open.iloc[0],
                                                   "high": cur.high.max(), "low": cur.low.min(),
                                                   "close": cur.close.iloc[-1]}])], ignore_index=True)
        return rows.tail(n).reset_index(drop=True)


# ----------------------------------------------------------------------------- broker / logger
class ReplayBroker:
    """Ejecuta al precio del tick vigente; registra cada apertura y cierre."""

    def __init__(self, balance=10_000_000.0):
        import MetaTrader5 as mt5
        self.mt5 = mt5
        self.magic, self.shadow = 100300, False
        self._balance = balance
        self._pos, self._next = [], 1
        self.tick = None
        self.opens = {}     # ticket -> dict(time, price, comment, side, volume)
        self.closes = {}    # ticket -> dict(time, price, comment)

    def volume_step(self): return 0.01
    def volume_min(self): return 0.01
    def volume_max(self): return 1_000_000.0
    def account_balance(self): return self._balance
    def check_free_margin(self, lots, otype=None): return True
    def positions_checked(self): return list(self._pos)
    def positions(self): return list(self._pos)

    def market_order(self, otype, lots, comment, sl=0.0, tp=0.0):
        mt5 = self.mt5
        buy = otype == mt5.ORDER_TYPE_BUY
        px = self.tick.ask if buy else self.tick.bid
        tk = self._next
        self._next += 1
        p = SimpleNamespace(ticket=tk, type=mt5.POSITION_TYPE_BUY if buy else mt5.POSITION_TYPE_SELL,
                            volume=float(lots), price_open=px, price_current=px, time=int(self.tick.time),
                            comment=comment, magic=self.magic, sl=sl, tp=tp, swap=0.0, profit=0.0)
        self._pos.append(p)
        self.opens[tk] = dict(time=int(self.tick.time), price=px, comment=comment, side=1 if buy else -1,
                              volume=float(lots))
        return SimpleNamespace(retcode=mt5.TRADE_RETCODE_DONE, order=tk, volume=float(lots), price=px)

    def close_position(self, p, comment="Close"):
        buy = p.type == self.mt5.POSITION_TYPE_BUY
        px = self.tick.bid if buy else self.tick.ask
        self._pos.remove(p)
        self.closes[p.ticket] = dict(time=int(self.tick.time), price=px, comment=comment)
        return SimpleNamespace(retcode=self.mt5.TRADE_RETCODE_DONE)

    def history_deals_for_position(self, ticket):
        mt5 = self.mt5
        if ticket not in self.opens:
            return []
        v = self.opens[ticket]["volume"]
        deals = [SimpleNamespace(entry=mt5.DEAL_ENTRY_IN, volume=v)]
        if ticket in self.closes:
            deals.append(SimpleNamespace(entry=mt5.DEAL_ENTRY_OUT, volume=v))
        return deals


class ListLogger:
    def __init__(self):
        self.events = []

    def write(self, t, m, price=0.0, lots=0.0, balance=0.0, ticket=0):
        self.events.append((t, m))


# ----------------------------------------------------------------------------- flujo de ticks
def _tick(t, bid, ask=None):
    return SimpleNamespace(time=int(t), bid=float(bid), ask=float(bid + SPREAD if ask is None else ask))


def bar_ticks(t, o, h, l, c, mode, legs_open):
    """Ticks de una vela despues del open (el open se emite aparte, antes de mirar las patas)."""
    side = None
    if mode == "sim" and legs_open:
        sides = {1 if e["side"] == "buy" else -1 for e in legs_open}
        side = sides.pop() if len(sides) == 1 else None
    if side is None:
        side = 1 if c >= o else -1          # sin pata (o lados mezclados): orden por el cierre
    path = [o, l, h, c] if side == 1 else [o, h, l, c]
    levels = []                              # (precio bid del tick, ask exacto o None)
    if mode == "sim":
        for e in legs_open:
            if e["status"] != "open":
                continue
            buy = e["side"] == "buy"
            lv = [e["lock_price"]] + [e["tp"][i] for i in (1, 2)
                                      if e["thirds"][i] and e["thirds"][i] not in e["closed_thirds"]]
            for x in lv:
                levels.append((x, None) if buy else (x - SPREAD, x))
    out = []
    for j in range(3):
        a, b = path[j], path[j + 1]
        lo, hi = min(a, b), max(a, b)
        mids = [(bid, ask) for bid, ask in levels if lo < bid < hi]
        mids.sort(key=lambda z: abs(z[0] - a))
        for k, (bid, ask) in enumerate(mids):
            out.append(_tick(t + 60 * j + 1 + k, bid, ask))
        out.append(_tick(t + 60 * (j + 1), b))
    return out


def run_engine(M, events, legs, mode, tmpdir):
    """Corre el SessionEngine real sobre el periodo; devuelve (legs vistas, broker, logger)."""
    from bot.strategy_e2 import SessionEngine
    br, lg = ReplayBroker(), ListLogger()
    eng = SessionEngine(br, lg, state_path=os.path.join(tmpdir, f"e2_state_{mode}_{'-'.join(legs)}.json"))
    eng.cfg = {"e2_bigone_event_weight": 1.0, "e2_legs": ",".join(legs)}
    eng.is_active, eng.close_only = True, False
    cur = {"tick": None}
    eng._fetch_tick = lambda: cur["tick"]
    eng._rates_m15 = lambda n: M.m15(eng.now, n)
    eng._rates_d1 = lambda n: M.d1(eng.now, n)
    eng._events = lambda: events
    eng.init_history_cursor()
    seen = {}

    def feed(tk):
        cur["tick"] = tk
        br.tick = tk
        eng.on_tick()
        for k in eng.state.legs:
            if k not in seen:
                seen[k] = eng.state.legs[k]

    t0, t1 = int(START.timestamp()), int(END.timestamp())
    i0 = int(np.searchsorted(M.t, t0))
    for i in range(i0, len(M.t)):
        t = int(M.t[i])
        if t >= t1:
            eng.is_active = False            # sin entradas nuevas; se gestionan las abiertas
            if not any(e.get("status") in ("opening", "open", "locked") for e in eng.state.legs.values()):
                break
        feed(_tick(t, M.o[i]))
        live = [e for e in eng.state.legs.values() if e.get("status") in ("open", "locked")]
        for tk in bar_ticks(t, M.o[i], M.h[i], M.l[i], M.c[i], mode, live):
            feed(tk)
    return seen, br, lg


# ----------------------------------------------------------------------------- resultados del motor
def engine_trades(seen, br):
    from bot_backtesting.fullsim.entrylab import swap_cost
    rows = []
    for k, e in seen.items():
        if e.get("status") not in ("open", "locked", "closed") or e.get("entry_price") is None:
            continue
        side = 1 if e["side"] == "buy" else -1
        locks = [t for t, _ in e.get("locks", []) if t]
        lk = None
        if locks:
            lo, lc = br.opens[locks[0]], br.closes.get(locks[0])
            lk = dict(t=lo["time"], open=lo["price"], close=lc["price"] if lc else np.nan)
        rec = dict(leg=e["leg"], t=(int(e["entry_epoch"]) // 900) * 900, entry_epoch=int(e["entry_epoch"]),
                   side=side, s=e["s"], atr_d=e["atr_d"], atr15=e["atr15"], entry=e["entry_price"],
                   lock_price=e["lock_price"], status=e["status"], locked=lk is not None,
                   lock_t=lk["t"] if lk else np.nan)
        for i, tk in enumerate(e["thirds"]):
            o, c = br.opens.get(tk), br.closes.get(tk)
            if o is None or c is None:
                rec[f"pnl{i + 1}"], rec[f"lock{i + 1}"], rec[f"how{i + 1}"] = np.nan, False, "abierta"
                continue
            third_locked = lk is not None and lk["t"] <= c["time"] and not c["comment"].startswith("E2 TP")
            pnl = side * (c["price"] - o["price"]) - COMM
            if third_locked:
                pnl += -side * (lk["close"] - lk["open"]) - COMM
                end = (lk["t"] // 900) * 900 + 900
            elif c["comment"].startswith("E2 TP"):
                end = (c["time"] // 900) * 900 + 900
            else:
                end = c["time"]
            pnl += swap_cost(o["time"], end, side)
            rec[f"pnl{i + 1}"] = pnl
            rec[f"lock{i + 1}"] = third_locked
            rec[f"how{i + 1}"] = "candado" if third_locked else ("tp" if c["comment"].startswith("E2 TP") else "hora")
            rec[f"exit_t{i + 1}"] = c["time"]
        rec["pnl"] = np.nanmean([rec["pnl1"], rec["pnl2"], rec["pnl3"]])
        rows.append(rec)
    return pd.DataFrame(rows)


def engine_skips(seen):
    return pd.DataFrame([dict(leg=e["leg"], t=(int(e["entry_epoch"]) // 900) * 900, reason=e.get("reason", ""))
                         for e in seen.values() if e.get("status") == "skipped"])


# ----------------------------------------------------------------------------- simulador
def sim_trades():
    """broker_accounts.trades_fixed(ladder=True) en el periodo, con el detalle por tercio."""
    from bot_backtesting.fullsim.broker_accounts import LADDER, trades_fixed
    from bot_backtesting.fullsim.broker_rule import RESULTS, exit_label
    T = trades_fixed(ladder=True)
    T = T[(T.t >= START.timestamp()) & (T.t < END.timestamp())]
    files = {"big_one": "bigone", "momentum_eeuu": "ny_mom_05_todas", "nfp": "news_nfp"}
    leg_of = {v: k for k, v in PATA.items()}
    rows = []
    for pata, g in T.groupby("pata"):
        R = pd.read_pickle(os.path.join(RESULTS, f"broker_r2_{files[pata]}.pkl"))
        R = R.assign(exit=exit_label(R))
        R = R[R.t.isin(g.t) & R.exit.isin(LADDER)].set_index(["t", "exit"])
        for r in g.itertuples():
            rec = dict(leg=leg_of[pata], t=int(r.t), side=int(r.side), s=r.state, pnl=r.pnl, risk_oz=r.risk_oz)
            for i, ex in enumerate(LADDER):
                x = R.loc[(r.t, ex)]
                rec[f"pnl{i + 1}"] = x.pnl
                rec[f"lock{i + 1}"] = bool(x.mae <= -x.risk_oz + 1e-9)
            rec["locked"] = rec["lock1"]
            rows.append(rec)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- comparacion
def compare(S, E, K, M, label):
    """Tabla por pata y lista de diferencias."""
    summary, mism, joined = [], [], {}
    for leg in LEGS:
        s = S[S.leg == leg].set_index("t")
        e = E[E.leg == leg].set_index("t") if len(E) else pd.DataFrame()
        ks = set(s.index)
        ke = set(e.index) if len(e) else set()
        both = sorted(ks & ke)
        union = ks | ke
        J = s.loc[both].join(e.loc[both], lsuffix="_sim", rsuffix="_eng") if both else pd.DataFrame()
        if len(J):
            J = attribute(J, M, leg)
        same_side = (J.side_sim == J.side_eng) if len(J) else pd.Series(dtype=bool)
        ok_entries = int(same_side.sum()) if len(J) else 0
        agree = ok_entries / len(union) if union else 1.0
        row = dict(modo=label, pata=leg, n_sim=len(ks), n_motor=len(ke), coinciden=len(both),
                   entradas_y_lados_pct=100 * agree)
        if len(J):
            row["lado_pct"] = 100 * same_side.mean()
            row["candado_pct"] = 100 * (J.locked_sim == J.locked_eng).mean()
            row["candado_tercio_pct"] = 100 * np.mean([(J[f"lock{i}_sim"] == J[f"lock{i}_eng"]).mean()
                                                       for i in (1, 2, 3)])
            for i in (1, 2, 3):
                row[f"dif_T{i}"] = (J[f"pnl{i}_eng"] - J[f"pnl{i}_sim"]).mean()
            row["pnl_sim"] = J.pnl_sim.mean()
            row["pnl_motor"] = J.pnl_eng.mean()
            row["dif_media"] = (J.pnl_eng - J.pnl_sim).mean()
            row["dif_abs_media"] = (J.pnl_eng - J.pnl_sim).abs().mean()
            row["n_horizonte"] = int(J.horizonte.sum())
            row["dif_sin_horizonte"] = J.loc[~J.horizonte, "dif"].mean()
            row["residuo_sin_gap"] = J.loc[~J.horizonte, "residuo"].mean()
            row["residuo_abs_max"] = J.loc[~J.horizonte, "residuo"].abs().max()
        else:
            row["dif_media"] = np.nan
        row["veredicto"] = "OK" if (agree >= TOL_MATCH and np.isfinite(row["dif_media"])
                                    and abs(row["dif_media"]) < TOL_PNL) else "FALLA"
        summary.append(row)
        joined[leg] = J
        sk = K[K.leg == leg].set_index("t").reason if len(K) else pd.Series(dtype=object)
        for t in sorted(ks - ke):
            mism.append(dict(modo=label, pata=leg, t=pd.Timestamp(t, unit="s"), tipo="solo simulador",
                             detalle=sk.get(t, "sin registro en el motor")))
        for t in sorted(ke - ks):
            mism.append(dict(modo=label, pata=leg, t=pd.Timestamp(t, unit="s"), tipo="solo motor",
                             detalle=f"lado {int(e.loc[t].side):+d}, s={e.loc[t].s}"))
        for t in both:
            j = J.loc[t]
            if j.side_sim != j.side_eng:
                mism.append(dict(modo=label, pata=leg, t=pd.Timestamp(t, unit="s"), tipo="lado distinto",
                                 detalle=f"sim {int(j.side_sim):+d} motor {int(j.side_eng):+d}"))
            d = j.pnl_eng - j.pnl_sim
            if abs(d) >= TOL_PNL:
                cause = ("horizonte del simulador (cuenta velas; salida real " +
                         f"{pd.Timestamp(int(j.sim_end), unit='s')})" if j.horizonte else
                         "salida al open de la vela vs cierre de la anterior" if abs(j.residuo) < 0.01 else
                         "otra")
                mism.append(dict(modo=label, pata=leg, t=pd.Timestamp(t, unit="s"), tipo="P&L",
                                 causa=cause,
                                 detalle=f"dif {d:+.3f} $/oz (residuo {j.residuo:+.3f}); candado sim/motor {bool(j.locked_sim)}/"
                                         f"{bool(j.locked_eng)}; tercios sim "
                                         f"{j.pnl1_sim:+.2f}/{j.pnl2_sim:+.2f}/{j.pnl3_sim:+.2f} motor "
                                         f"{j.pnl1_eng:+.2f}/{j.pnl2_eng:+.2f}/{j.pnl3_eng:+.2f} "
                                         f"({j.how1}/{j.how2}/{j.how3})"))
    return pd.DataFrame(summary), pd.DataFrame(mism), joined


NBARS = {"bigone": 36, "mom": 24, "nfp": 96}   # horizonte del simulador en velas (broker_round2)


def attribute(J, M, leg):
    """Atribuye la diferencia de P&L de cada operacion:
      * horizonte: el simulador sale tras N VELAS de datos; el motor por RELOJ (10:00 / 21:00 / 96
        franjas de mercado). Difieren cuando faltan velas (cierre anticipado por feriado, hueco de
        datos): el simulador sigue hasta otra hora u otro dia.
      * gap de salida: en los tercios que salen por hora el motor cierra en el primer tick de la vela
        de salida (su open) y el simulador al cierre de la vela anterior: side * (O[k] - C[k-1]).
      * residuo = dif - gap medio de los tercios (lo que no explica el camino sintetico)."""
    idx = pd.Series(np.arange(len(M.t)), index=M.t)
    J = J.copy()
    J["dif"] = J.pnl_eng - J.pnl_sim
    hz, send, res = [], [], []
    for t, j in J.iterrows():
        k0 = idx[t]
        se = int(M.t[min(k0 + NBARS[leg] - 1, len(M.t) - 1)]) + 900
        send.append(se)
        hz.append(bool(j.how1 == "hora" and not j.lock1_sim and se != int(j.exit_t1)))
        gaps = []
        for i in (1, 2, 3):
            g = 0.0
            if j[f"how{i}"] == "hora":
                k = idx.get(int(j[f"exit_t{i}"]))
                if k is not None and k > 0:
                    g = j.side_eng * (M.o[k] - M.c[k - 1])
            gaps.append(g)
        res.append(j.dif - float(np.mean(gaps)))
    J["sim_end"], J["horizonte"], J["residuo"] = send, hz, res
    return J


def main():
    if not os.path.exists(DATA_M15):
        print(f"OMITIDO: falta {DATA_M15} (datos fuera de git); no se corre la reproduccion.")
        return 0
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.max_colwidth", 200)
    X = load_bars()
    M = Market(X)
    events = load_events()
    S = sim_trades()
    out = {"sim": S}
    tables, mism_all = [], []
    with tempfile.TemporaryDirectory() as tmp:
        runs = [("sim", (leg,)) for leg in LEGS] + [("raw", LEGS)]
        res = {}
        for mode, legs in runs:
            t0 = _time.time()
            seen, br, lg = run_engine(M, events, legs, mode, tmp)
            E, K = engine_trades(seen, br), engine_skips(seen)
            errs = [m for k, m in lg.events if k in ("ERROR", "WARNING")]
            print(f"[{mode} {','.join(legs)}] {len(E)} entradas, {len(K)} omitidas, "
                  f"{len(errs)} ERROR/WARNING, {_time.time() - t0:.0f} s")
            for m in errs[:5]:
                print("    ", m)
            res[(mode, legs)] = dict(E=E, K=K, logs=lg.events)
        Esim = pd.concat([res[("sim", (leg,))]["E"] for leg in LEGS], ignore_index=True)
        Ksim = pd.concat([res[("sim", (leg,))]["K"] for leg in LEGS], ignore_index=True)
        for label, E, K in (("sim", Esim, Ksim), ("raw", res[("raw", LEGS)]["E"], res[("raw", LEGS)]["K"])):
            tab, mm, J = compare(S, E, K, M, label)
            tables.append(tab)
            mism_all.append(mm)
            out[label] = dict(E=E, K=K, summary=tab, mismatches=mm, joined=J)
        out["logs"] = {f"{m}:{','.join(l)}": v["logs"] for (m, l), v in res.items()}
    T = pd.concat(tables, ignore_index=True)
    MM = pd.concat(mism_all, ignore_index=True)
    cols = ["modo", "pata", "n_sim", "n_motor", "coinciden", "entradas_y_lados_pct", "candado_pct",
            "candado_tercio_pct", "pnl_sim", "pnl_motor", "dif_T1", "dif_T2", "dif_T3", "dif_media",
            "dif_abs_media", "n_horizonte", "dif_sin_horizonte", "residuo_sin_gap", "residuo_abs_max",
            "veredicto"]
    print("\nCOMPARACION MOTOR vs SIMULADOR (2025-11-01 -> 2026-10-16), P&L en $/oz por tercio:")
    print(T[cols].round(3).to_string(index=False))
    print("\nDiferencias (modo sim):")
    m = MM[MM.modo == "sim"]
    print(m.to_string(index=False) if len(m) else "  ninguna")
    print("\nDiferencias (modo raw, 4 ticks por vela; solo para medir el camino sintetico):")
    m = MM[MM.modo == "raw"]
    print(m.to_string(index=False) if len(m) else "  ninguna")
    out["summary"], out["mismatches"] = T, MM
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pd.to_pickle(out, OUT)
    print()
    for r in T[T.modo == "sim"].itertuples():
        print(f"{r.pata}: {r.veredicto} (entradas y lados {r.entradas_y_lados_pct:.1f} %, "
              f"dif P&L media {r.dif_media:+.3f} $/oz)")
    print(f"detalle en {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
