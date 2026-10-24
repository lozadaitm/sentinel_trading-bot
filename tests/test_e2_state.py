"""Estado persistente de las patas (bot/e2_state.py).

Correr:  python -m tests.test_e2_state
"""

import os
import sys
import tempfile

from bot.e2_state import E2State

FAILS = []


def check(cond, name):
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        FAILS.append(name)


def entry(leg, day, status="open"):
    return {
        "leg": leg, "side": "buy", "entry_epoch": day * 86400 + 3600,
        "exit_epoch": day * 86400 + 40000, "entry_price": 2000.0,
        "atr_d": 30.0, "atr15": 3.0, "lock_price": 1970.0,
        "tp": [None, 2006.0, 2009.0], "thirds": [11, 12, 13],
        "closed_thirds": [], "lock_ticket": None, "status": status,
    }


def main():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sub", "e2_state_x.json")

        # archivo ausente
        st = E2State(path)
        st.load()
        check(st.legs == {}, "archivo ausente -> vacio")

        # guardar y recargar (crea el directorio padre)
        st.put(entry("bigone", 100))
        st.put(entry("mom", 100, "locked"))
        st.save()
        check(os.path.exists(path), "save crea archivo y carpeta")
        check(not os.path.exists(path + ".tmp"), "sin tmp residual")
        st2 = E2State(path)
        st2.load()
        check(st2.legs == st.legs and len(st2.legs) == 2, "guardar y recargar iguala")
        check(st2.legs["bigone:100"]["tp"][0] is None, "None del tercio 1 se conserva")
        check(st2.load_error is None, "carga limpia sin error")

        # basura
        with open(path, "w") as f:
            f.write("{{{ no es json")
        st3 = E2State(path)
        st3.load()
        check(st3.legs == {} and st3.load_error, "basura -> vacio y load_error")
        with open(path, "w") as f:
            f.write("[1, 2]")
        st3.load()
        check(st3.legs == {}, "JSON no-dict -> vacio")

        # valores malformados: se descartan solo esos y se avisa en load_error
        import json
        with open(path, "w") as f:
            json.dump({"bigone:100": entry("bigone", 100), "mom:100": "basura",
                       "nfp:100": {"leg": "xx", "entry_epoch": 1},
                       "bigone:101": {"leg": "bigone", "entry_epoch": None}}, f)
        st4 = E2State(path)
        st4.load()
        check(list(st4.legs) == ["bigone:100"], "malformados descartados, el valido se queda")
        check(st4.load_error and "mom:100" in st4.load_error,
              "malformados -> load_error con las claves")

        # entered / active
        s = E2State(os.path.join(d, "a.json"))
        s.put(entry("bigone", 100, "skipped"))
        s.put(entry("mom", 100, "open"))
        s.put(entry("nfp", 100, "locked"))
        s.put(entry("bigone", 101, "closed"))
        check(s.entered("bigone", 100), "entered con skipped")
        check(s.entered("bigone", 101), "entered con closed")
        check(not s.entered("nfp", 101), "no entered otra clave")
        act = sorted(e["leg"] for e in s.active())
        check(act == ["mom", "nfp"], "active filtra open/locked")

        # prune
        s.put(entry("mom", 90, "closed"))
        s.put(entry("nfp", 90, "skipped"))
        s.put(entry("bigone", 90, "open"))   # viejo pero activo: se queda
        s.put(entry("mom", 95, "closed"))    # reciente
        s.prune(95)
        check("mom:90" not in s.legs and "nfp:90" not in s.legs, "prune borra viejo cerrado/omitido")
        check("bigone:90" in s.legs, "prune conserva viejo activo")
        check("mom:95" in s.legs and "bigone:101" in s.legs, "prune conserva recientes")

    if FAILS:
        print(f"\n{len(FAILS)} FALLOS")
        sys.exit(1)
    print("\nOK")


if __name__ == "__main__":
    main()
