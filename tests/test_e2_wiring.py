"""Cableado del motor e2 fuera de la estrategia: provision --start, el bucle de
main sin fila de bot_config y validate_identity con BOT_ID=e2.

Sin MT5 (no se inicializa), sin Supabase y sin lanzar procesos.

Correr:  python -m tests.test_e2_wiring
"""

import sys
import threading
import time

from bot import config
from bot import main as botmain
from scripts import provision

FAILS = []


def check(cond, name, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILS.append(name)


def test_provision_modulos():
    check(provision.module_for("e2") == "bot.main_e2", "provision: e2 -> bot.main_e2")
    check(provision.module_for("m5") == "bot.main_m5", "provision: m5 -> bot.main_m5")
    check(provision.module_for("m15") == "bot.main", "provision: m15 -> bot.main")
    check(provision.module_for(" E2 ") == "bot.main_e2", "provision: normaliza mayusculas/espacios")
    check(provision.module_for("xx") is None, "provision: motor desconocido -> None (no se lanza)")


class _DB:
    def __init__(self):
        self.reports = []

    def load_config(self):
        return {}, "INACTIVE"            # sin fila de bot_config

    def get_instance(self):
        return {"is_active": False}

    def report(self, status):
        self.reports.append(status)

    def __getattr__(self, name):         # el resto del heartbeat: best-effort, no importa
        return lambda *a, **k: None


class _Broker:
    def positions(self):
        return []

    def capital_flows(self, *a):
        return []

    def trade_allowed(self):
        return True, None


class _Engine:
    def __init__(self, stop, flag):
        self.b = _Broker()
        self.cfg = None
        self.is_active = self.close_only = None
        self.ticks = 0
        self._stop = stop
        if flag is not None:
            self.runs_without_cfg = flag

    def on_tick(self):
        self.ticks += 1
        self._stop.set()


class _Log:
    def write(self, *a, **k):
        pass


def _loop(flag, rounds=3):
    stop = threading.Event()
    eng = _Engine(stop, flag)
    n = {"k": 0}
    orig_sleep = time.sleep

    def fake_sleep(_s):
        n["k"] += 1
        if n["k"] >= rounds:
            stop.set()
    time.sleep = fake_sleep
    try:
        botmain.trading_loop(_DB(), eng, _Log(), stop_event=stop)
    finally:
        time.sleep = orig_sleep
    return eng


def test_main_sin_cfg():
    e2 = _loop(True)
    check(e2.ticks == 1, "main: motor con runs_without_cfg corre on_tick sin bot_config", e2.ticks)
    check(e2.close_only is True and e2.cfg == {}, "main: sin fila -> close_only y cfg vacia (DEFAULTS)")
    m15 = _loop(None)
    check(m15.ticks == 0, "main: m15/m5 (sin el atributo) siguen esperando la fila", m15.ticks)


def test_identidad_e2():
    old = config.BOT_ID, config.MAGIC_NUMBER
    try:
        config.BOT_ID, config.MAGIC_NUMBER = "e2", 100300
        try:
            w = config.validate_identity()
            check(w == [], "identidad: BOT_ID=e2 + MAGIC 100300 pasa", w)
        except SystemExit as e:
            check(False, "identidad: BOT_ID=e2 + MAGIC 100300 pasa", e)
        for bad in (100100, 100200, 123):
            config.MAGIC_NUMBER = bad
            try:
                config.validate_identity()
                check(False, f"identidad: BOT_ID=e2 + MAGIC {bad} aborta")
            except SystemExit as e:
                check("ABORTADO" in str(e), f"identidad: BOT_ID=e2 + MAGIC {bad} aborta")
    finally:
        config.BOT_ID, config.MAGIC_NUMBER = old


def main():
    for fn in (test_provision_modulos, test_main_sin_cfg, test_identidad_e2):
        print(f"[{fn.__name__}]")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(False, f"{fn.__name__} lanzo {type(e).__name__}: {e}")
    print("\n" + "=" * 60)
    if FAILS:
        print("FALLOS (%d): %s" % (len(FAILS), FAILS))
        return 1
    print("TODO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
