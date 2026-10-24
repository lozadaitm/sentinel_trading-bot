"""Modo LITE del motor e2 (tres patas). Ver bot/lite.py.

Uso:                 python -m bot.lite_e2
Uso (via launcher):  scripts\\run_instance.ps1 instances\\<usuario>-e2.env -BotId e2 -Lite
"""

from .lite import run_lite
from .strategy_e2 import SessionEngine


def main():
    run_lite(engine_cls=SessionEngine)


if __name__ == "__main__":
    main()
