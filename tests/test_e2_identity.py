"""Identidad del motor e2 (tres patas): magic 100300 en la configuracion.

Correr:  python -m tests.test_e2_identity
"""

from bot import config

FAILS = []


def check(cond, name):
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        FAILS.append(name)


def main():
    check(config.MAGIC_E2 == 100300, "MAGIC_E2 == 100300")
    check(config.EXPECTED_MAGIC["e2"] == 100300, "EXPECTED_MAGIC['e2'] == 100300")
    check(100300 in config.ALL_MAGICS, "100300 en ALL_MAGICS")
    check(len(set(config.ALL_MAGICS)) == len(config.ALL_MAGICS), "magics distintos")
    if FAILS:
        raise SystemExit(f"\ntest_e2_identity: FALLOS {FAILS}")
    print("\ntest_e2_identity: TODO OK")


if __name__ == "__main__":
    main()
