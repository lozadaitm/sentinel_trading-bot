# Corrección: el «efecto reapertura» estaba inflado por un artefacto de datos (24-oct)

## Qué pasó

Desde el 20-oct, la Big One (compra en la reapertura de la 01:00 servidor) se midió con velas
M5 de **Dukascopy** para 2021 → 2026-01 y del broker desde 2026-01-12.

Al buscar la misma ventaja en otros mercados aparecieron tres señales de alarma:
- **todos** los pares de divisas «subían» a la 01:00, incluidos EURUSD y USDCHF a la vez, lo que es imposible para el dólar;
- con **ticks reales del broker** (comprando al ask en el momento), ese efecto en divisas desaparece y se vuelve negativo;
- en 2026, el precio de Dukascopy a la 01:00 está **2,7 $/oz por debajo** del broker. A la 01:05 la diferencia ya es la normal (−0,3 a −0,5 $/oz).

**Causa:** en el rollover, el bid de Dukascopy queda hundido mientras el spread está ancho. La simulación compraba a ese bid hundido + 0,20 $/oz, un precio que en la realidad no existe. Tamaño del artefacto (Dukascopy − broker a la 01:00, menos la diferencia normal):

| Año | Artefacto aprox. |
|---|---|
| 2022 | 0,2 $/oz |
| 2023 | 0,45 $/oz |
| 2024 | 0,4 $/oz |
| 2025 | 0,8 $/oz |
| 2026 | 2,3 $/oz |

## Qué sigue siendo verdad (verificado con precios reales del broker)

- **Spread real a la 01:00:** 0,17 $/oz, medido en 49 días con ticks. Es menor que los 0,20 supuestos, y la entrada es ejecutable.
- **En 2026, ticks y velas del broker coinciden** (196 días, diferencia de +0,04 $/oz). El M15 y el M5 del broker sirven para simular.
- **La asimetría horaria existe con datos reales del broker** (M15, 2022-08 → 2026-10; neto de 0,32 $/oz; salida por hora a las 10:00):

| Año | Tendencia alcista: 01:00 → 10:00 | Tendencia alcista: 10:00 → 19:00 | Todos los días: 01:00 → 10:00 |
|---|---|---|---|
| 2022 (ago–dic) | +0,81 | −0,32 | −0,04 |
| 2023 | +0,33 | −1,25 | +0,48 |
| 2024 | +0,64 | −1,19 | +0,78 |
| 2025 | +3,58 | +0,34 | +3,25 |
| 2026 | +10,74 | −12,85 | +2,46 |

Total en días alcistas: **+2,64 $/oz por operación (t 2,5)**. El oro sube en horario asiático y baja en el de EE. UU., como documenta la literatura (`investigacion/literatura-anomalias-oro-2026-10-24.md`). La mayor parte del tamaño viene de 2025–2026.

## Qué cambia

- **Big One sobre datos del broker** (`bigone_broker.py`: validación móvil 2024–2026, candado de 2–6 ATR M15 o 0,5–1,5 ATR diario, trailing):
  - R por operación: **+0,08** (2024 −0,05; 2025 +0,14; 2026 +0,30). Antes se medía +0,20.
  - Al 3 %: crecimiento mediano **~2 %/mes**, P(2x en 12 meses) 22 %, P(caída ≥ 50 %) 11 %.
- Con candados ajustados (1 ATR M15) y entrada limpia a la 01:05 sobre Dukascopy, el R cae a **+0,03**. El artefacto regalaba un colchón inicial que evitaba que saltaran los candados.
- **Quedan invalidadas o en revisión** todas las cifras de cuenta de la Big One:
  - `banco-modelos-econometricos-2026-10-23.md`: HAR +0,20 R, ~6–7 %/mes, P(2x) 51–60 %;
  - la combinación con racha y freno;
  - el piso de Grossman-Zhou;
  - la decisión de rumbo del 24-oct ([[decision-bigone-combo]]).

  Las **herramientas** siguen valiendo: el HAR predice la volatilidad, el mapa horario, la ventana de noticias, las colas, el Kelly y el freno. Pero su efecto sobre la Big One hay que volver a medirlo con datos del broker.
- **Mapa de franjas (S1):** el único sobreviviente, «01:00 durante 15 min», era sobre todo el artefacto.
- **SPA de Hansen** (`spa_test.py`, 1 200 combinaciones regla × salida): el p = 0,011 de la familia Big One en 2024–26 también estaba medido con el bid hundido. Hay que repetirlo con datos del broker.
- **Divisas** (EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCHF, USDCAD): el efecto 00:00–01:00 era **todo artefacto**. Descartadas.

## Regla nueva para todo lo que siga

1. Toda ventaja que dependa de la hora de entrada se valida con **precios del broker**:
   - ticks, M5 desde 2025-05 y M15 desde 2022-08;
   - en `data/broker_m5_full.pkl` y `data/broker_m15_full.pkl`, fuera de git.
2. Dukascopy solo se usa lejos del rollover (00:00–01:15 servidor) o con la entrada desplazada.
3. Antes de dar por buena una entrada, se comprueba con ticks reales que el precio de entrada sea ejecutable.
