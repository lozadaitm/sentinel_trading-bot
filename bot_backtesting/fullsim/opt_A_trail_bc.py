"""Linea A - trailing en ganancia en modo 'al cierre de vela' (simulacion exacta con M5), solo 'sel'.

Motivo: con el modo intra-vela (opt_A_grid F1/F2/F3, opt_A_trail_fine G1-G4) el trailing corto mejoraba MAS
cuanto mas gruesas eran las velas (M15 >> M5): artefacto de resolucion (ignora los retrocesos dentro de la vela).
Aqui el stop se mueve SOLO al cerrar cada vela M5 (pico = maximo de las velas cerradas); dentro de la vela el
nivel esta fijo, se dispara si el minimo lo toca y se llena al nivel (o al open si hay hueco). Es exacto con M5
y es implementable tal cual en el bot (modificar el SL en cada cierre M5).
Repite: F1 (ATR15 y ATR_D, t3/t23/t123/t1), F2 (con tope), F3 (SAR), G1/G2 (grilla fina), G3 (por pata),
G4 (deslizamiento extra) y el mismo modo con velas M15 (stop movido cada 15 min).
Uso: .venv/Scripts/python -m bot_backtesting.fullsim.opt_A_trail_bc [F1 F2 F3 G1 G2 G3 G4 M15]
"""
import sys
import time

from bot_backtesting.fullsim import opt_A_common as AC
from bot_backtesting.fullsim import opt_A_grid as AG
from bot_backtesting.fullsim import opt_A_trail_fine as TF
from bot_backtesting.fullsim.opt_base import entries, low_priority


class BCRunner(AG.Runner):
    def test(self, fam, name, *a, **kw):
        return super().test("BC" + fam, name, *a, **kw)


def m15(R):
    C5 = R.C
    R.C = AC.cache_paths_m15(entries(), "e2")
    R.test("M15", "base_M15res", AC.BASE_RULES, params="base con camino M15", reg=False)
    for name, rules in TF.BEST.items():
        R.test("M15", f"{name}_M15res", rules, params=dict(base=name, resolucion="M15", barclose=True))
    R.C = C5


def g4(R):
    for name, rules in TF.BEST.items():
        for ss in (0.10, 0.25):
            AC.CFG["stop_slip"] = ss
            R.test("G4", f"{name}_slip+{ss}", rules, params=dict(base=name, stop_slip_extra=ss, barclose=True))
        AC.CFG["stop_slip"] = 0.0


FAMS = dict(F1=AG.fam_trail, F2=AG.fam_trail_tp, F3=AG.fam_sar, G1=TF.g1, G2=TF.g2, G3=TF.g3, G4=g4, M15=m15)

if __name__ == "__main__":
    low_priority()
    AC.CFG["barclose"] = True
    t0 = time.time()
    R = BCRunner()
    for f in (sys.argv[1:] or list(FAMS)):
        FAMS[f](R)
        R.save(); R.rows = []
        print(f"--- {f} listo ({time.time()-t0:.0f}s)", flush=True)
