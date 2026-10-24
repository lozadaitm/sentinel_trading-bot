"""Entrypoint del motor e2 (tres patas: Big One, Momentum EE. UU., NFP).

Reusa todo el arranque del Sentinel (MT5, Supabase, broker, bucle de polling,
heartbeat, bot_positions) y solo cambia la clase de motor. Ver bot/main.py.

Uso (modo consola):  python -m bot.main_e2
Uso (via instancia): scripts\\run_instance.ps1 instances\\<usuario>-e2.env -BotId e2

El .env de la instancia debe fijar:
    BOT_ID=e2
    MAGIC_NUMBER=100300      # distinto del M15 y del M5
"""

from . import main as botmain
from .strategy_e2 import SessionEngine


def run():
    botmain.run(engine_cls=SessionEngine)


if __name__ == "__main__":
    run()
