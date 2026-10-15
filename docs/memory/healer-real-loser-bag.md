---
name: healer-real-loser-bag
description: Decisión firme (16-oct-2026): el Healer solo amputa perdedores reales (>= 2 $/oz) y su bolsa (90 %) solo se llena mientras exista uno; lo ganado sin perdedor queda como ganancia
metadata:
  type: project
---

**Problema (14-oct, cuentas de 5 000 $ y 10 000 $):**
- El Healer amputaba la recovery **recién abierta**, que iba en rojo solo por el spread, y al instante se reabría otra igual.
- Gastaba en eso lo que había ganado la recovery anterior.
- Además, el presupuesto se perdía si no había a quién curar, porque el cursor avanzaba igual.

**Regla actual (`bot/strategy.py`: `_healer_target`, `_check_healing`, `_apply_healing`):**
- **Perdedor real:** una pata amputable (no es par congelado ni pata LOCK, y no está excluida por la protección de cobertura) con pérdida (profit + swap) **>= `healer_min_move_usd`** por onza. DEFAULT 2.0; 0 = comportamiento viejo.
- **Bolsa (`healer_budget`):**
  - suma 0,90 × cada ganancia nueva **solo mientras exista un perdedor real**;
  - sin perdedor real, la ganancia queda como ganancia (log) y una bolsa con saldo se libera;
  - cada amputación cierra `floor(bolsa / pérdida_por_lote)` lotes y resta lo realizado, así que va cerrando la pata poco a poco;
  - vuelve a 0 al cerrar el ciclo y al reiniciar el bot.
- Siguen igual: core >= 3, el par entrada + cobertura congelado mientras el ciclo va en rojo, y las patas LOCK intocables.

**Why:** que el Healer no gaste el presupuesto en ruido de spread, y que las ganancias obtenidas sin nadie a quien curar no se conviertan después en pérdida realizada. La segunda parte es idea del usuario.

**How to apply:**
- En las revisiones, buscar `HEALER` con «Bolsa restante», «sin perdedor real» y «liberada».
- Tests: `python -m tests.test_healer`. Migración 012. Spec: `docs/superpowers/specs/2026-10-16-healer-patas-frescas-design.md`.
- Ver [[healer-unwind-hedge-cascade]] y [[healer-budget-accumulates-across-cycles]].
