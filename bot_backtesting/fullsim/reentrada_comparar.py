"""Complemento de reentrada_confirmacion: estabilidad IS->OOS de toda la rejilla y cartera al 8 % para
variantes "representativas" (muchos disparos), no solo la de menor p en IS (que elige muestras chicas).
Uso: python -m bot_backtesting.fullsim.reentrada_comparar
"""
import os

import numpy as np
import pandas as pd

from bot_backtesting.fullsim.recargas_minimo import RESULTS, bh, low_priority
from bot_backtesting.fullsim.reentrada_confirmacion import stats


def main():
    low_priority()
    S = pd.read_pickle(os.path.join(RESULTS, "reentrada_summary.pkl"))
    meta, store = pd.read_pickle(os.path.join(RESULTS, "reentrada_store.pkl"))
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    isv, Rb, legv = meta.is_.values, meta.R.values, meta.leg.values
    for leg in ("big_one", "momentum"):
        I = S[(S.leg == leg) & (S.per == "IS")].set_index("var")
        O = S[(S.leg == leg) & (S.per == "OOS")].set_index("var")
        ok = I.alfa.notna() & O.alfa.notna()
        print(f"\n--- {leg}: corr alfa IS/OOS {np.corrcoef(I.alfa[ok], O.alfa[ok])[0, 1]:.2f}; "
              f"corr R/disparo IS/OOS {np.corrcoef(I.R_por_disparo[ok], O.R_por_disparo[ok])[0, 1]:.2f}")
        for c in ("p_any", "p_near"):
            passed = I.index[bh(I[c].values)]
            if len(passed):
                print(f"   pasan BH {c} en IS: {len(passed)}; en OOS p<0,05: {(O.loc[passed, c] < 0.05).mean():.0%}; "
                      f"R/disparo OOS mediana {O.loc[passed, 'R_por_disparo'].median():.3f} vs nulo {O.loc[passed, 'nulo_near' if c == 'p_near' else 'nulo_any'].median():.3f}")
        big = I[I.disparos >= 0.25 * I.n]
        print(f"   variantes con >=25 % de disparos: {len(big)}; R/disparo IS mediana {big.R_por_disparo.median():.3f} "
              f"(nulo azar-en-entrada {big.nulo_near.median():.3f}); OOS {O.loc[big.index, 'R_por_disparo'].median():.3f} "
              f"(nulo {O.loc[big.index, 'nulo_near'].median():.3f}); alfa>0 OOS {(O.loc[big.index, 'alfa'] > 0).mean():.0%}")
    # cartera para variantes representativas
    reps = {"big_one": ["D0.5a15_t0_wall_c60_same", "D0.2ad_t0_wall_c60_same", "D1.0a15_c5_w60_c60_same"],
            "momentum": ["D0.5a15_t0_wall_c60_same", "D0.2ad_t0_wall_c60_same", "D1.0a15_c5_w60_c60_same"]}
    rows = []
    for leg, vs in reps.items():
        legm = legv == leg
        for v in vs:
            addR1, fired, inlock = store[v]
            lk = meta.lock.values & legm
            for sz in (1 / 3, 1.0):
                addR = addR1 * sz
                for per, msk in (("IS", isv), ("OOS", ~isv)):
                    base = np.where(msk, Rb, 0.0)
                    lm = legm & msk
                    tot = base + np.where(lm, addR, 0.0)
                    k = 1 + addR[lm].sum() / Rb[lm].sum()
                    for lab, x in (("base", base), ("re-entrada", tot), (f"lote x{k:.2f}", base * np.where(lm, k, 1.0))):
                        day = pd.Series(x, index=meta.d.values)[msk].groupby(level=0).sum()
                        rows.append(dict(pata=leg, var=v, tam=round(sz, 2), per=per, cartera=lab,
                                         disparos=fired[lm].mean(), candado_con_reent=(lk & fired & msk).sum(),
                                         **stats(day)))
            print(f"{leg} {v}: R añadido por año (1x)", pd.Series(addR1[legm]).groupby(meta.year.values[legm]).sum().round(2).to_dict())
    C = pd.DataFrame(rows).drop_duplicates(["pata", "var", "tam", "per", "cartera"])
    C = C[~((C.cartera == "base") & C.duplicated(["per", "cartera"]))]
    print(C.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
