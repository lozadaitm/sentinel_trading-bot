---
name: e2-optimizacion-descartada
description: Sesión de optimización del e2 por unidad de riesgo (27-oct-2026, ~12 000 variantes en salidas, tamaño, regímenes, entradas, patas nuevas e IA) — nada sobrevive a 2026; el e2 queda sin cambios
metadata:
  type: project
---

Probado el 2026-10-27 con `bot_backtesting/fullsim/opt_base.py`: camino intra-vela M5/M1 y costos reales, métrica MAR al 8 %.
- Periodos: elegir 2022-10→2024, validar 2025, 2026 guardado.
- Cuenta: 11 994 variantes, 7 líneas.
- **Ninguna idea pasa.** Los 3 candidatos que pasaron 2022-24 y 2025 fracasaron en 2026:
  - U1, la Big One con peso 0,75 fijo: ×0,40;
  - F1, sin Big One con vol alta (ATR_D/precio sobre su mediana de 252 días): ×0,26;
  - U1+F1: ×0,22.
- **Por qué:** en 2026 la Big One ganó en vol alta y perdió en vol baja, al revés que en 2023-25.
- **Descartado:**
  - salidas nuevas (TP por cuantiles, trailing, candado distinto de 1,0 ATR_D);
  - meta-labeling (AUC 0,50-0,60);
  - límites y stops de entrada;
  - 25 patas de otros símbolos y de calendario;
  - Chronos sin entrenar;
  - FRED, CBOE, GLD y GDELT;
  - el bandido contextual.
- En vigilancia, sin probar en 2026: el trailing en ganancia de los tercios 2 y 3 (×1,23 / ×1,22).

**Why:** el MAR es muy ruidoso. Quitar al azar el 30 % de las operaciones da ×1,42 en el p95, y las reglas de peso de la Big One se invierten entre años. El lote mayor del e2 tal cual le ganó a todos en 2026.
**How to apply:**
- No reproponer reglas de peso o filtro para la Big One, ni salidas o entradas nuevas, sin datos nuevos y sin un año fuera de muestra adicional.
- Toda idea futura se mide con `opt_base.py` y contra sus nulos (lote mayor, días al azar).
- La demo de 10 semanas manda.
- Detalle: `docs/experimento-2/banco-ideas-optimizacion-2026-10-27.md` y `docs/experimento-2/investigacion/opt-*-2026-10-27.md`.
- Relacionado: [[e2-recargas-descartadas]], [[decision-bigone-combo]], [[e2-motor-tres-patas]].
