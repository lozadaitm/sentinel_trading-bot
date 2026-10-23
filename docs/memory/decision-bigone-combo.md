---
name: decision-bigone-combo
description: Decisión (24-oct) del rumbo E2: Big One todos los días + satélites de noticias + riesgo por racha hasta 6 % + freno por caída; cualquier mejora que sume sin añadir riesgo se acepta
metadata:
  type: project
---

**Decisión del usuario (2026-10-24), en simulación.**

Rumbo del Experimento 2: «Big One todos los días + noticias + racha hasta 6 % + freno».

**Componentes:**
- **Big One:** compra en la reapertura de la 01:00 (servidor).
  - Peso 1 en días con tendencia diaria alcista; ×0,5 en neutros y bajistas.
  - Escala por volatilidad prevista: HAR diario en vez del ATR.
  - Candado a k·escala.
  - Riesgo ×0,5 en días de NFP, IPC o FOMC.
- **Satélites de noticias** al 2 %:
  - seguir el salto de FOMC y NFP;
  - ir en contra del salto del IPC;
  - entrada a T+60 min, objetivo 3 y candado 2 × ATR M15, máximo 24 h.
- **Riesgo dinámico:**
  - base 3 %;
  - ×2 (hasta 6 %) tras 20 operaciones con R medio > 0, ×0,75 si no;
  - freno lineal por caída, hasta la mitad del riesgo.

**Resultado simulado** (2023–2026, calendario completo, cuenta de 5 000 $):

| Medida | Valor |
|---|---|
| Crecimiento mediano compuesto | ~7 %/mes |
| P(2x en 12 meses) | 56 % |
| P(3x en 12 meses) | 37 % |
| P(caída ≥ 50 %) | 3 % |
| Caída real en el camino 2023–26 | 49 % |

Detalle en `docs/experimento-2/banco-modelos-econometricos-2026-10-23.md`.

**Principio del usuario:** toda mejora que aumente la ganancia suma, siempre que no añada riesgo ni peligro. La búsqueda de más fuentes de ventaja sigue abierta; la meta es acercarse al 2x mensual.

**Why:** de unas 30 reglas, ~5 000 pruebas y 25 modelos econométricos, la única ventaja direccional robusta es la reapertura de la 01:00. La volatilidad (HAR), el horario y las noticias son predecibles y sirven para el tamaño. M15 y M5 no tienen ventaja.

**How to apply:**
- Es una decisión de **rumbo**, no un cambio de código aprobado.
- Antes de tocar el bot se necesita:
  - un diseño escrito aprobado por el usuario;
  - una demo aparte para medir el spread y el deslizamiento a la 01:00.
- Las restricciones siguen vigentes ([[bot-design-constraints]]): sin stop catastrófico ni cierre de emergencia; el candado (Hedge Lock) sí está permitido.
