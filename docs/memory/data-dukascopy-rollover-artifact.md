---
name: data-dukascopy-rollover-artifact
description: Las velas M5 de Dukascopy traen el bid hundido en la reapertura 00:00-01:05 servidor (oro 0,2-2,7 $/oz, divisas varios pb); toda ventaja horaria se valida con precios del broker
metadata:
  type: project
---

**Hallazgo del 2026-10-24.** En el rollover (00:00–01:05 servidor), el bid de Dukascopy queda hundido mientras el spread está ancho. Una simulación que compra a ese bid + un spread fijo gana dinero que no existe.

| Mercado | Efecto del artefacto |
|---|---|
| Oro | −2,7 $/oz frente al broker en 2026; −0,4 a −0,55 en 2022–24 (lo normal es −0,1 a −0,3) |
| Divisas | Todos los pares parecían subir a la 01:00. Con ticks reales comprando al ask, pierden |

**Why:** esto infló la «Big One» de +0,08 R a +0,20 R por operación, y la estimación de ~2 %/mes a ~7 %/mes. También produjo falsos hallazgos en divisas.

**How to apply:**
- Para entradas cercanas al rollover, usar precios del broker. Están en `bot_backtesting/fullsim/data/` (fuera de git):
  - `broker_m15_full.pkl`: 2022-08 → 2026-10;
  - `broker_m5_full.pkl`: 2025-05 → 2026-10;
  - ticks con `copy_ticks_range`, solo con el mercado cerrado o en ventanas cortas.
- El terminal limita la descarga a 100 000 velas por temporalidad.
- Confirmar con ticks que el precio de entrada sea ejecutable.
- Detalle en `docs/experimento-2/correccion-artefacto-reapertura-2026-10-24.md`. Relacionado: [[decision-bigone-combo]], [[fullsim-simulator]].
