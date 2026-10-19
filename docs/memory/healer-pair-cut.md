---
name: healer-pair-cut
description: Decisión firme (19-oct-2026): sin recovery recortable, la bolsa del Healer paga lotes iguales de dos patas opuestas (primero recovery + Op4 (T), después Op1 + su cobertura); el neto no cambia; healer_pair_cut=false revierte; migración 015
metadata:
  type: project
---

**Regla (`bot/strategy.py`: `_heal_with`, `_pair_cut_candidate`, `_try_pair_cut`, `_retry_pair_cut_pending`):**
- **Recovery primero:** si hay un perdedor real amputable, manda la amputación de siempre, aunque la bolsa aún no llegue al lote mínimo (en ese caso, la bolsa espera a la recovery).
- **Sin perdedor amputable,** la bolsa paga una pareja de lados opuestos:
  - primero, una RECOVERY/RESCUE de cada lado fuera de par (recovery + Op4 (T));
  - si no hay ninguna, el HEDGE con la pata que cubre (Op1 + Op2).
  - Nunca se mezclan tipos. Nunca entran patas LOCK.
  - La pareja vale si su pérdida es de al menos 2 $/oz (`healer_min_move_usd`).
- **Lotes:** `floor(bolsa / coste por lote)`. Si no llegan al lote mínimo, la bolsa espera y no se libera.
- **Orden de cierre:** primero el miembro rojo y luego el verde.
- **Si falla el segundo cierre:** deuda `pair_cut_pending` en el meta del ciclo y alerta CRITICA. Solo se reintenta esa deuda (cada 60 s, sin pasarse del neto previo).
- **Sin recorte** con el freno de volatilidad activo.
- **Interruptor:** `healer_pair_cut` (por defecto `true`).
- **Junto con este cambio,** el DEFAULT de `rescue_trend_max_legs` pasó a 1000 (sin límite).

**Why:** simulación de ciclo completo con el motor real (1-mar → 16-oct), con Op4 sin límite:
- 10k: −36 → −29 %;
- 5k: −35 → −27 %;
- 1k: igual.

Las parejas congeladas Op1 + Op2 pagaban swap durante meses sin que nada pudiera tocarlas. Ver `docs/experimento-2/analisis-ciclo-paralelo-2026-10-19.md`.

**How to apply:** vigilar los logs «Recorte por parejas» y que no aparezca ninguna deuda pendiente.

Relacionado: [[healer-real-loser-bag]], [[op4-trend]], [[healer-deal-window-lag]].
