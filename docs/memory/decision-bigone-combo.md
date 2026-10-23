---
name: decision-bigone-combo
description: [EN REVISIÓN: cifras infladas por artefacto de datos, ver correccion-artefacto-reapertura] Decisión (24-oct) del rumbo E2: Big One todos los días + satélites de noticias + riesgo por racha hasta 6 % + freno por caída; cualquier mejora que sume sin añadir riesgo se acepta
metadata:
  type: project
---

> **EN REVISIÓN (24-oct, más tarde).** Las cifras de abajo usaban velas de Dukascopy con el bid hundido en la
> reapertura de la 01:00. Con precios reales del broker, la Big One da +0,08 R por operación (~2 %/mes al 3 %),
> no +0,20 R (~7 %/mes). Ver `docs/experimento-2/correccion-artefacto-reapertura-2026-10-24.md`. El rumbo y
> el principio («todo lo que sume sin añadir riesgo») siguen; los números y el tamaño se rehacen con datos del broker.
> **Propuesta rehecha (24-oct, noche):** Big One + momentum EE.UU. (sigue a Asia) + satélites FOMC/NFP (IPC fuera),
> candado amplio en ATR diario, tamaño con piso de Grossman-Zhou (50 %, 4-6 %): ~8-9 %/mes, P(2x 12m) ~60 %,
> caída real 2024-26 43-48 %. Ver `docs/experimento-2/cartera-broker-2026-10-24.md`. Pendiente de aprobación y demo.
> **Actualización:** con salida fija de antemano (hora + candado 1 ATR diario), las patas robustas 5/5 años son
> Big One, momentum EE.UU. y NFP; la FOMC y el IPC quedan fuera. Al 5 %: ~6 %/mes 2022-26, caída 30 %.
> La cuenta de 1 000 queda forzada a ~8 % de riesgo por el lote mínimo. Ver `cuentas-scalping-2026-10-24.md`.

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
