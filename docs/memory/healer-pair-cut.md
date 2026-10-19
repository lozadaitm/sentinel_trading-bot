---
name: healer-pair-cut
description: Decisión firme (19/20-oct-2026): sin recovery recortable, la bolsa del Healer paga lotes iguales de dos patas opuestas (desde el 20-oct primero Op1 + Op2, luego recovery + Op4); el neto no cambia; la bolsa ignora los cierres propios; migraciones 015 y 016
metadata:
  type: project
---

**Regla (`bot/strategy.py`: `_heal_with`, `_pair_cut_candidate`, `_try_pair_cut`, `_retry_pair_cut_pending`):**
- **Recovery primero:** si hay un perdedor real amputable, manda la amputación de siempre, aunque la bolsa aún no llegue al lote mínimo (en ese caso, la bolsa espera a la recovery).
- **Sin perdedor amputable,** la bolsa paga una pareja de lados opuestos:
  - **Desde el 20-oct (`healer_pair_order = 'cover_first'`, por defecto):** primero el HEDGE con la pata que cubre (Op1 + Op2) y después una RECOVERY/RESCUE de cada lado fuera de par (recovery + Op4 (T)). `'recovery_first'` vuelve al orden del 19-oct.
  - **Ancla:** con recovery/Op4 vivas, la Op1 + Op2 no baja del lote mínimo. Si ya no puede recortar ni el mínimo, no cuenta como candidata y la bolsa pasa a la pareja siguiente.
  - Nunca se mezclan tipos. Nunca entran patas LOCK.
  - La pareja vale si su pérdida es de al menos 2 $/oz (`healer_min_move_usd`).
- **Lotes:** `floor(bolsa / coste por lote)`. Si no llegan al lote mínimo, la bolsa espera y no se libera.
- **Orden de cierre:** primero el miembro rojo y luego el verde.
- **Si falla el segundo cierre:** deuda `pair_cut_pending` en el meta del ciclo y alerta CRITICA. Solo se reintenta esa deuda (cada 60 s, sin pasarse del neto previo).
- **Sin recorte** con el freno de volatilidad activo.
- **Interruptor:** `healer_pair_cut` (por defecto `true`).
- **Junto con este cambio,** el DEFAULT de `rescue_trend_max_legs` pasó a 1000 (sin límite).
- **Sin doble conteo (20-oct):** `_check_healing` ignora los deals con comentario de `HEALER_OWN_COMMENTS` (`Healer Pair Cut`, `Healer Amputacion`, `Basket Dissolve`). El miembro verde de un recorte ya está neteado: su ganancia queda en la cuenta y no vuelve a entrar en la bolsa. Antes, la bolsa se inflaba y gastaba dinero que no existía.

**Why:** simulación de ciclo completo con el motor real (1-mar → 16-oct), con Op4 sin límite:
- 10k: −36 → −29 %;
- 5k: −35 → −27 %;
- 1k: igual.

Las parejas congeladas Op1 + Op2 pagaban swap durante meses sin que nada pudiera tocarlas. Ver `docs/experimento-2/analisis-ciclo-paralelo-2026-10-19.md`.

Orden Op1 + Op2 primero (20-oct): por el mismo dinero frena el mismo swap (≈15 $/oz frente a ≈93 $/oz). Simulación: 10k −31,9 → −21,5 %; 5k −29,9 → −20,2 %; 1k igual. Ver `docs/experimento-2/analisis-op4-criterio-propio-2026-10-19.md` y la spec `docs/superpowers/specs/2026-10-20-bolsa-sin-doble-conteo-y-op1op2-primero-design.md`.

**How to apply:** vigilar los logs «Recorte por parejas» y que no aparezca ninguna deuda pendiente.

Relacionado: [[healer-real-loser-bag]], [[op4-trend]], [[healer-deal-window-lag]].
