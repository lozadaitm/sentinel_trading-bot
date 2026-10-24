"""Reporte diario por correo de las cuentas (M15 + M5). SOLO LECTURA.

Lee, sin tocar nada:
  * MT5: cuenta, posiciones y deals de las ultimas 24 h, contra los terminales YA
    abiertos (igual que scripts/news_exporter.py; solo lecturas ligeras: nunca
    copy_rates ni historial profundo, ver docs/memory/mt5-history-download-blocks-bots.md);
  * Supabase: logs de las ultimas 24 h (recortes, amputaciones, Op4, errores) y latidos;
  * ledger del ciclo (instances/cycle_ledger_m15_<id>.json): bolsa del curador.
Envia un correo (Resend, el mismo canal que las alertas) a ALERT_EMAIL_TO del .env raiz.
Guarda un resumen minimo en instances/daily_report_state.json para comparar con el
reporte anterior (no se versiona).

Uso:  python -m scripts.daily_report            # envia
      python -m scripts.daily_report --dry-run  # solo imprime, no envia ni guarda
"""

import datetime as dt
import glob
import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5  # noqa: E402

from bot import config, notify  # noqa: E402  (config carga el .env raiz)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCES_DIR = os.path.join(ROOT, "instances")
STATE_PATH = os.path.join(INSTANCES_DIR, "daily_report_state.json")
MAGIC_M15, MAGIC_M5, MAGIC_E2 = 100100, 100200, config.MAGIC_E2
E2_LEGS = ("BigOne", "MomUS", "NFP")
SYMBOL = "XAUUSD+"
HEARTBEAT_STALE_S = 180


def _readenv(path):
    d = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                d[k] = v.strip().strip('"').strip("'")
    return d


def _instances():
    out = []
    for p in sorted(glob.glob(os.path.join(INSTANCES_DIR, "*.env"))):
        name = os.path.basename(p)
        if name.startswith(("_", "example", "template")):
            continue
        out.append((name[:-4], _readenv(p)))
    return out


def _sb_get(env, table, params):
    url = f"{env['SUPABASE_URL']}/rest/v1/{table}?{urllib.parse.urlencode(params)}"
    key = env["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(url, headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _terminal_path(env):
    p = env.get("MT5_PATH", "")
    if p and os.path.exists(p):
        return p
    hits = glob.glob(rf"C:\MT5_instances\mt5_{env.get('MT5_LOGIN', '')}\terminal64.exe")
    return hits[0] if hits else None


def _read_mt5(env):
    """Cuenta, posiciones y deals de 24 h. None si el terminal no responde."""
    path = _terminal_path(env)
    if not path or not mt5.initialize(path=path, portable=True, timeout=15000):
        return None
    try:
        ai = mt5.account_info()
        tick = mt5.symbol_info_tick(SYMBOL)
        if ai is None or tick is None:
            return None
        pos = list(mt5.positions_get() or ())
        # Ventana amplia en reloj local y filtro por la hora del SERVIDOR (tick.time):
        # los deals vienen en hora de servidor (memoria healer-deal-window-lag).
        now_local = dt.datetime.now()
        deals = list(mt5.history_deals_get(now_local - dt.timedelta(days=2),
                                           now_local + dt.timedelta(days=1)) or ())
        all_deals = deals
        since = tick.time - 86400
        deals = [d for d in deals if d.time >= since]
        return dict(balance=ai.balance, equity=ai.equity, positions=pos, deals=deals, deals_2d=all_deals,
                    server_time=tick.time, bid=tick.bid)
    finally:
        mt5.shutdown()


def _e2_leg(comment):
    """Pata de e2 segun el comentario ('E2 BigOne T1', 'E2 Lock NFP', 'E2 Salida MomUS'...), o None."""
    c = comment or ""
    if not c.startswith("E2 "):
        return None
    for leg in E2_LEGS:
        if leg in c.split():
            return leg
    return None


def _e2_summary(positions, deals, history=None):
    """Resumen de e2 (magic 100300): abiertas, flotante, realizado y cierres por pata.

    positions/deals: objetos con .magic/.profit/.swap/.commission/.comment/.entry/.position_id.
    `deals` ya filtrados a 24 h. Devuelve dict o None si no hay nada de e2."""
    pos = [p for p in positions if p.magic == MAGIC_E2]
    outs = [d for d in deals if d.magic == MAGIC_E2 and d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY)]
    if not pos and not outs and not any(d.magic == MAGIC_E2 for d in deals):
        return None
    leg_by_pid = {}
    for d in (history if history is not None else deals):
        if d.magic == MAGIC_E2 and d.entry == mt5.DEAL_ENTRY_IN and _e2_leg(d.comment):
            leg_by_pid[d.position_id] = _e2_leg(d.comment)
    for p in pos:
        if _e2_leg(p.comment):
            leg_by_pid[getattr(p, "ticket", None)] = _e2_leg(p.comment)
    legs = {k: dict(open=0, floating=0.0, closes=0, real=0.0) for k in E2_LEGS + ("?",)}
    for p in pos:
        g = legs[_e2_leg(p.comment) or "?"]
        g["open"] += 1
        g["floating"] += p.profit + p.swap
    for d in outs:
        g = legs[_e2_leg(d.comment) or leg_by_pid.get(d.position_id) or "?"]
        g["closes"] += 1
        g["real"] += d.profit + d.swap + d.commission
    return dict(open=len(pos), floating=sum(p.profit + p.swap for p in pos),
                real=sum(g["real"] for g in legs.values()), closes=len(outs),
                legs={k: v for k, v in legs.items() if k != "?" or v["open"] or v["closes"]})


def _ledger_budget(iid):
    try:
        with open(os.path.join(INSTANCES_DIR, f"cycle_ledger_m15_{iid}.json"), encoding="utf-8") as f:
            return float(json.load(f).get("meta", {}).get("healer_budget") or 0.0)
    except (OSError, ValueError, TypeError):
        return None


def _account(iid, env, prev, since_iso):
    login = env.get("MT5_LOGIN", "?")
    a = dict(login=login, iid=iid)
    m = _read_mt5(env)
    a["mt5_ok"] = m is not None
    if m:
        a["balance"], a["equity"], a["bid"] = m["balance"], m["equity"], m["bid"]
        m15 = [p for p in m["positions"] if p.magic == MAGIC_M15]
        a["legs"] = len(m15)
        a["net"] = round(sum(p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume for p in m15), 2)
        a["floating"] = sum(p.profit + p.swap for p in m15)
        a["open_swap"] = sum(p.swap for p in m["positions"])
        a["frozen"] = a["legs"] >= 3 and abs(a["net"]) < 1e-9 and a["floating"] < 0
        out = [d for d in m["deals"] if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY)]
        for mg, k in ((MAGIC_M15, "m15"), (MAGIC_M5, "m5")):
            ds = [d for d in out if d.magic == mg]
            a[f"real_{k}"] = sum(d.profit + d.swap + d.commission for d in ds)
            a[f"n_{k}"] = len(ds)
        a["m5_open"] = sum(1 for p in m["positions"] if p.magic == MAGIC_M5)
        a["e2"] = _e2_summary(m["positions"], m["deals"], m.get("deals_2d"))
    a["bag"] = _ledger_budget(iid)
    # Logs de 24 h
    try:
        logs = _sb_get(env, "bot_logs", {"select": "log_type,message,bot_id,created_at",
                                         "user_id": f"eq.{iid}", "created_at": f"gte.{since_iso}",
                                         "order": "created_at.asc", "limit": "5000"})
    except Exception as e:  # noqa: BLE001
        logs, a["logs_error"] = [], str(e)[:120]
    msgs = [(r.get("log_type"), r.get("message") or "") for r in logs]
    a["cuts"] = [m_ for t, m_ in msgs if m_.startswith("Recorte por parejas:") and "deuda" not in m_]
    a["amps"] = [m_ for t, m_ in msgs if m_.startswith("Amputacion Tactica")]
    a["op4"] = sum(1 for t, m_ in msgs if m_.startswith("Op4 tendencia:") and "cupo" not in m_)
    kinds = {}
    for t, m_ in msgs:
        if t == "ERROR":
            k = m_.split(":")[0][:60]
            kinds[k] = kinds.get(k, 0) + 1
    a["errors"] = kinds
    a["critical"] = [m_ for _, m_ in msgs if "INCOMPLETO" in m_ or "FALLIDO" in m_.upper()]
    try:
        st = _sb_get(env, "bot_state", {"select": "bot_id,updated_at", "user_id": f"eq.{iid}"})
        now = dt.datetime.now(dt.timezone.utc)
        a["stale"] = [r["bot_id"] for r in st
                      if (now - dt.datetime.fromisoformat(r["updated_at"])).total_seconds() > HEARTBEAT_STALE_S]
    except Exception:  # noqa: BLE001
        a["stale"] = ["?"]
    p = prev.get(login) or {}
    a["prev_equity"], a["prev_open_swap"] = p.get("equity"), p.get("open_swap")
    a["first_equity"] = p.get("first_equity", a.get("equity"))
    return a


def _money(x, sign=True):
    if x is None:
        return "n/d"
    s = f"{x:+,.2f}" if sign else f"{x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " $"


def _pct(x, base):
    if x is None or not base:
        return "n/d"
    return f"{(x / base) * 100:+.2f} %".replace(".", ",")


def _lines(a):
    """Texto de una cuenta (lista de lineas)."""
    L = [f"Cuenta {a['login']}"]
    if not a["mt5_ok"]:
        L.append("  MT5 no respondio: sin datos de cuenta.")
    else:
        d_eq = a["equity"] - a["prev_equity"] if a["prev_equity"] is not None else None
        L.append(f"  Equity {_money(a['equity'], False)} | balance {_money(a['balance'], False)}"
                 f" | 24 h {_money(d_eq)} ({_pct(d_eq, a['prev_equity'])})"
                 f" | desde el primer reporte {_pct(a['equity'] - a['first_equity'], a['first_equity'])}")
        L.append(f"  Realizado 24 h: M15 {_money(a['real_m15'])} ({a['n_m15']} cierres)"
                 f", M5 {_money(a['real_m5'])} ({a['n_m5']} cierres)")
        d_sw = a["open_swap"] - a["prev_open_swap"] if a["prev_open_swap"] is not None else None
        L.append(f"  Swap acumulado de lo abierto {_money(a['open_swap'])}"
                 + (f" (cambio desde el reporte anterior {_money(d_sw)})" if d_sw is not None else ""))
        estado = "CONGELADO (neto 0, en rojo)" if a["frozen"] else ("sin ciclo" if a["legs"] == 0 else "activo")
        L.append(f"  Ciclo M15: {a['legs']} patas, neto {a['net']:+.2f}, flotante {_money(a['floating'])} -> {estado}")
    e2 = a.get("e2")
    if e2:
        L.append(f"  e2 (tres patas): {e2['open']} abiertas, flotante {_money(e2['floating'])}"
                 f" | realizado 24 h {_money(e2['real'])} ({e2['closes']} cierres)")
        for leg, g in e2["legs"].items():
            L.append(f"    - {leg}: {g['open']} abiertas (flotante {_money(g['floating'])}),"
                     f" {g['closes']} cierres, realizado {_money(g['real'])}")
    L.append(f"  Bolsa del curador: {_money(a['bag'], False)}")
    L.append(f"  Curador 24 h: {len(a['cuts'])} recortes por parejas, {len(a['amps'])} amputaciones; Op4 abiertas: {a['op4']}")
    for m_ in a["cuts"] + a["amps"]:
        L.append(f"    - {m_[:160]}")
    salud = []
    if a["stale"]:
        salud.append(f"SIN LATIDO: {', '.join(a['stale'])}")
    for k, n in sorted(a["errors"].items(), key=lambda x: -x[1]):
        salud.append(f"{n}x error '{k}'")
    if a["critical"]:
        salud.append(f"{len(a['critical'])} eventos criticos")
    L.append("  Salud: " + ("; ".join(salud) if salud else "OK"))
    return L


def build(accounts, when):
    text = [f"Sentinel - reporte diario ({when:%d-%m-%Y %H:%M} UTC)", ""]
    for a in accounts:
        text += _lines(a) + [""]
    text.append("Solo lectura. Generado por scripts/daily_report.py.")
    body = "\n".join(text)
    html_body = ("<pre style=\"font-family:Consolas,Menlo,monospace;font-size:13px\">"
                 + html.escape(body) + "</pre>")
    tot = [a for a in accounts if a["mt5_ok"] and a["prev_equity"] is not None]
    worst = any(a["stale"] or a["critical"] or not a["mt5_ok"] for a in accounts)
    resumen = ", ".join(f"{a['login'][-3:]} {_pct(a['equity'] - a['prev_equity'], a['prev_equity'])}" for a in tot)
    subject = f"[Sentinel] Reporte diario {when:%d-%m}" + (f": {resumen}" if resumen else "") + \
              (" - REVISAR" if worst else "")
    return subject, body, html_body


def main():
    dry = "--dry-run" in sys.argv
    now = dt.datetime.now(dt.timezone.utc)
    since_iso = (now - dt.timedelta(hours=24)).isoformat()
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = {}
    accounts = [_account(iid, env, prev, since_iso) for iid, env in _instances()]
    subject, body, html_body = build(accounts, now)
    print(subject)
    print(body)
    if dry:
        return 0
    if not (config.RESEND_API_KEY and config.ALERT_EMAIL_TO):
        print("RESEND_API_KEY o ALERT_EMAIL_TO sin configurar: no se envia.")
        return 1
    failed = []
    notify._send(config.ALERT_EMAIL_TO, subject, body, html=html_body, on_fail=lambda: failed.append(1))
    if failed:
        print("Fallo el envio del correo.")
        return 1
    state = {a["login"]: {"equity": a.get("equity"), "open_swap": a.get("open_swap"),
                          "first_equity": a.get("first_equity"), "at": now.isoformat()}
             for a in accounts if a["mt5_ok"]}
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    print("Enviado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
