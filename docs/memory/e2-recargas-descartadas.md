---
name: e2-recargas-descartadas
description: Recargas/promediar en el mínimo, detección del fondo con ML y reentrada al volver a la entrada en Big One/Momentum fueron probadas y descartadas (2026-10-27); 8 % de riesgo se mantiene
metadata:
  type: project
---

Probado el 2026-10-27 con OOS 2022-24 → 2025-26, nulo de azar y comparación contra lote inicial mayor:
- recargas a distancia/soportes/mechas (152 variantes), detección del mínimo con ML y detector de día malo (24 ideas, 222 variantes), reentrada al volver al precio de entrada (1 080 variantes): **ninguna pasa**. Lo que sube la ganancia es solo más exposición, igual que abrir más lote, y empeora el peor día y el candado.
- Riesgo: el margen aguanta ~20 %, pero lo sensato es 8 % (10 % solo si la demo confirma ≥75 % de la ventaja; nunca >12 %). Proyección real al 8 %: ×26-35 en 4 años, caída máx. 33 %.

**Why:** las perdedoras van 3-4× más en contra que las ganadoras; comprar el fondo es recargar en días malos. AUC del detector de fondo 0,57-0,61.
**How to apply:** no reproponer recargas/promediado ni «ver el mínimo» sin datos nuevos; en vigilancia solo el modelo de fondo del Momentum (12 meses de registro en demo sin operarlo). Detalle en docs/experimento-2/investigacion/{recargas-minimo,deteccion-minimo,reentrada-confirmacion,riesgo-maximo}-2026-10-27.md.
