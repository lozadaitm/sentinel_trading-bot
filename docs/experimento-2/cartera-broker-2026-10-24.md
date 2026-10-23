# Cartera sobre precios reales del broker (24-oct, noche)

Rehecha sin el artefacto de Dukascopy (`correccion-artefacto-reapertura-2026-10-24.md`).

**Datos:** M15 de XAUUSD+ del broker, 2022-08 → 2026-10. En 2026 se verificó contra ticks (diferencia de +0,04 $/oz).

**Costos:**
- spread 0,17 $/oz, medido a la 01:00;
- comisión 0,12 $/oz;
- swap;
- costo del candado.

**Método:** la salida y la escala del candado (ATR M15, ATR diario o HAR) se eligen por validación móvil, con los 2 años anteriores. Se juzga en 2024, 2025 y 2026.

## Mapa horario con datos del broker (`broker_map.py`)

1 280 pruebas: hora × duración × lado × tendencia × lo que hizo Asia.
- Con Benjamini-Hochberg al 10 %, **ninguna** pasa en un tramo y se confirma en el otro. Ni siquiera la Big One lo logra con 4 años de datos.
- Se ve un patrón coherente: **lo que hace Asia (01:00 → 15:00) continúa en EE. UU.** La pendiente de la regresión del retorno de EE. UU. sobre el de Asia es positiva en los dos tramos.
- Su forma más clara: vender a las 15:00 durante 6 h en días alcistas en que Asia bajó. Ganó los 5 años (+0,10 / +0,11 / +0,18 / +0,03 / +0,32 % por operación).

**«Vender porque EE. UU. baja», sin condición:** no se sostiene. Con datos del broker, ninguna venta fija en horario EE. UU. confirma (t < 1,3).

## Reglas (validación móvil 2024–2026, R por operación)

| Regla | n | R | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| Big One (01:00 → 10:00; peso 1 en días alcistas, 0,5 en el resto) | 721 | +0,070 | +0,01 | +0,15 | +0,05 |
| Momentum EE. UU. (15:00 → 21:00, sigue a Asia si \|Asia\| > 0,5 desv., días alcistas) | 330 | +0,081 | +0,13 | +0,03 | +0,14 |
| Ídem, todas las tendencias | 530 | +0,059 | +0,04 | +0,04 | +0,10 |
| Ídem, umbral 0,3 / 0,7 / 1,0 desv. | — | +0,04 / +0,04 / −0,08 | | | |
| Satélite FOMC (T+60 min, sigue el salto, 24 h) | 22 | +0,51 | +0,33 | +0,38 | +0,94 |
| Satélite NFP (ídem) | 32 | +0,26 | +0,08 | +0,20 | +0,58 |
| Satélite IPC (contra el salto) | 33 | −0,14 | −0,18 | 0,00 | −0,25 | ← descartado |

**Candado:** el amplio (en ATR **diario**) es el que más elige la validación móvil en el momentum, y baja mucho la caída. El HAR no supera de forma estable al ATR.

**Correlación diaria entre patas:** −0,04 a 0,03. Son prácticamente independientes.

## Cartera (2 000 caminos de 12 meses con meses reales remuestreados; cuenta de 5 000; calendario completo)

| Cartera | Tamaño | Crec./mes (mediana) | P(2x) | P(3x) | P(DD ≥ 50 %) | Real 2024–26 (×, caída) |
|---|---|---|---|---|---|---|
| Big One sola | 3 % fijo | 2,8 % | 26 % | 9 % | 13 % | ×2,6, 53 % |
| Big One + momentum EE. UU. | 3 % fijo | 5,5 % | 47 % | 23 % | 8 % | ×5,9, 53 % |
| + FOMC + NFP | 2 % fijo | 5,0 % | 41 % | 14 % | 1 % | ×5,2, 37 % |
| + FOMC + NFP | 3 % fijo | 7,2 % | 57 % | 34 % | 11 % | ×10, 51 % |
| **Big One + momentum (todas) + FOMC + NFP** | **piso G-Z 50 %, 4 %** | **7,8 %** | **60 %** | **41 %** | **0 %** | ×11, 43 % |
| ídem | piso G-Z 50 %, 6 % | 9,2 % | 63 % | 49 % | 0 % | ×12, 48 % |

**Piso de Grossman-Zhou:** el riesgo por operación es el máximo (4–6 %) cuando la cuenta está en su máximo. Baja en proporción al colchón sobre el 50 % del máximo, sin cerrar posiciones. Así la caída no puede pasar del 50 %, salvo saltos de precio que superen el candado.

## Cautelas

- 2024–2026 fue un mercado muy alcista para el oro. La Big One y parte del momentum se apoyan en eso.
- El momentum EE. UU. salió de un mapa de 1 280 pruebas y no pasa el filtro estricto. Su respaldo es que gana 3/3 años fuera de muestra, que sus vecinos van en la misma dirección y que la literatura documenta momentum intradía.
- FOMC y NFP tienen pocas operaciones (22 y 32).
- Falta probarlo en vivo, en una demo aparte, antes de cualquier cambio en el bot.
