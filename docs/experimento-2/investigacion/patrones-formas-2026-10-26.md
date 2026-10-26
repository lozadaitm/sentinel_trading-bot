# Banco de patrones, equipo FORMAS: motivos sin nombre en M15 / M5 / M1 (2026-10-26)

Código: `bot_backtesting/fullsim/pat_formas.py` (corrido con prioridad BelowNormal, 20 permutaciones,
~3 h). Resultados crudos (no versionados): `bot_backtesting/fullsim/data/econ/pat_formas.pkl`.
Protocolo: `patrones-protocolo-2026-10-26.md` (datos del broker, costos, horario, filtro).

## Veredicto corto

**Nada pasa el filtro con holgura.** Probé 309 120 variantes. En A, 53 pasan BH al 10 % y solo 2
confirman en B. Al barajar los retornos futuros y repetir **toda** la búsqueda, el azar da en
promedio **143 «ganadoras» BH en A** (rango 21-258) y **1,55 confirmadas en B** (rango 0-8). La
búsqueda real no supera al azar. Queda **un candidato al límite** (M5, «comprar tras una caída
fuerte en tendencia alcista», más abajo). Pasa la versión secuencial de todos los filtros, pero
en la versión de la búsqueda su t en B queda en 1,92, por debajo de 2. No lo recomiendo para el
bot. Como mucho sirve para una prueba hacia adelante en papel.

## Qué se probó

| Elemento | Detalle |
|---|---|
| Marcos | M15 (2022-08 → 2026-10), M5 (2025-05 → 2026-10), M1 desde ticks (2026-01 → 2026-10) |
| Mitades | A = primera mitad de los días de cada marco, B = segunda. Todo se entrena y elige en A |
| Ventanas | L = 3, 5, 8, 12, 20 velas, normalizadas por el ATR(14) del marco, relativas al cierre de la última vela |
| km_C | k-means (k = 30, solo A) sobre los cierres relativos |
| km_OHLC | k-means (k = 30, solo A) sobre O/H/L/C relativos |
| sax3 / sax5 | La ventana se parte en w tramos (3 letras: w = min(L,4); 5 letras: w = min(L,3)). Cada letra es el cambio del tramo / ATR, con cortes equiprobables tomados de A |
| knn (análogos) | Vecinos de la forma km_C, k = 50 / 200, base solo A (en A se excluyen los vecinos del mismo día). Se opera si la puntuación (neto medio de los vecinos) está en el 20 % / 5 % superior de A y es > 0. En B se usa la misma base, sin reentrenar. L = 5, 12, 20 (en M1 la base A se toma cada 3 minutos por costo de cómputo) |
| Contextos | todos; bloque horario de la entrada (asia 01-08, londres 09-14, eeuu 15-19, cierre 20-23); tendencia diaria s = +2 / 0 / −2 |
| Salidas | E1 TP 1 / SL 1 ATR; E2 TP 2 / SL 1; E3 tiempo 4 y 12 velas; E4 escalera (tercios: tiempo 12 velas / TP 2 / TP 3 ATR, los tres con freno 1 ATR). Horizonte máximo de 48 velas y cierre forzado antes de las 23:45. Si TP y SL caen en la misma vela, cuenta el freno |
| Lados | compra y venta |
| Costo | spread de la vela de entrada (M1: spread medio desde ticks) + 0,06 $/oz |
| Horario | sin entradas de 23:45 a 01:05 ni el viernes desde las 22:00 |

**Total: 309 120 variantes** = 3 marcos × 103 040. De ellas, 291 095 tienen al menos 30 operaciones
y 10 días en A. Las demás entran al BH con p = 1, lo que es conservador.

Detalles para evitar autoengaño:
- Una sola operación por racha: si la misma forma se repite en velas seguidas, solo cuenta la primera.
- El t se calcula con **errores agrupados por día**.
- Las finalistas se vuelven a simular **una posición a la vez**, que es como operaría el bot.
- En M1 las finalistas se re-simulan **con ticks**: compra al ask, venta al bid, TP/SL tick a tick
  y salida por tiempo en el primer tick.

## Resultado del filtro

| Paso | Variantes |
|---|---|
| Probadas | 309 120 |
| BH 10 % en A (neto > 0) | 53 (M15 15, M5 20, M1 18; ninguna de knn) |
| … y en B neto > 0 con t > 2 (versión de la búsqueda) | 2 |
| Re-simulación secuencial: B t > 2, períodos positivos ≥ todos − 1, n ≥ 100, bootstrap por días p < 0,05 | 1 (la de M5; ver abajo; en la versión de la búsqueda tenía t_B = 1,92) |

Las 53 ganadoras de A, re-simuladas en secuencia, dan en B un neto medio de −0,17 $/oz con t medio
de −0,23. Es decir, en conjunto **se esfuman en B**, que es lo esperable si son ruido.

### Control de permutación (20 repeticiones)

Desplacé circularmente todos los retornos futuros (todas las salidas a la vez, lo que conserva su
autocorrelación) y repetí la búsqueda completa: mismas formas, knn re-puntuado, BH sobre las 309 120.

| | Real | Azar: media | mediana | mín | máx |
|---|---|---|---|---|---|
| Ganadoras BH en A | 53 | 142,9 | 149 | 21 | 258 |
| … que además confirman en B | 2 | 1,55 | 1 | 0 | 8 |

La búsqueda real encuentra **menos** ganadoras que el azar (el desplazamiento lleva a A retornos de
la subida de 2025-26, con deriva y ATR mayores, y eso infla el azar). Las 2 que confirman en B
están dentro de lo que el azar produce. **No hay evidencia de que alguna forma sin nombre tenga
ventaja real** con este método.

### Mejores en A y qué pasó en B

En la versión de la búsqueda, n y neto son por operación (primera vela de cada racha). En la
versión secuencial se toma una posición a la vez.

| Marco | Forma | Contexto | Salida | n_A | Neto A $/oz | t_A | n_B | Neto B $/oz | t_B | Sec. neto B | Sec. t_B |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 | km_OHLC L5 g28 | tend−2 | E4 compra | 71 | +1,92 | 4,77 | 61 | +0,31 | 0,57 | −0,15 (ticks) | −0,28 |
| M5 | sax3 L12 p54 | tend0 | E3-4 compra | 93 | +2,04 | 4,60 | 240 | −0,16 | −0,35 | −0,09 | −0,19 |
| M1 | km_OHLC L5 g28 | tend−2 | E2 compra | 71 | +1,94 | 4,19 | 61 | +0,35 | 0,67 | +0,05 | 0,10 |
| M5 | sax3 L8 p25 | tend0 | E3-12 compra | 105 | +2,20 | 4,15 | 232 | −0,11 | −0,09 | −0,14 | −0,11 |
| M5 | sax5 L5 p0 | londres | E3-4 compra | 96 | +1,97 | 4,01 | 75 | +0,56 | 0,42 | +0,71 | 0,49 |
| M5 | km_C L8 g8 | todos | E3-4 compra | 418 | +2,12 | 3,98 | 453 | +0,56 | 1,16 | +0,48 | 0,98 |
| M15 | sax5 L3 p20 | londres | E2 compra | 126 | +1,21 | 3,98 | 109 | +0,18 | 0,15 | −0,09 | −0,07 |
| M15 | sax5 L8 p40 | tend0 | E4 compra | 88 | +1,26 | 3,95 | 103 | −1,65 | −1,39 | −1,59 | −1,32 |
| **M5** | **km_C L8 g8** | **tend+2** | **E3-4 compra** | 333 | +2,53 | 3,93 | 89 | +1,81 | **1,92** | **+1,87** | **2,11** |
| M1 | sax5 L12 p48 | tend0 | E4 venta | 278 | +1,13 | 3,91 | 433 | +0,07 | 0,49 | +0,01 (ticks) | 0,10 |
| M1 | km_OHLC L5 g3 | tend+2 | E4 compra | 595 | +1,10 | 3,90 | 150 | −0,80 | −2,22 | −0,73 (ticks) | −2,90 |
| M15 | sax5 L20 p78 | tend−2 | E1 venta | 36 | +1,05 | 3,38 | 43 | +3,75 | 2,64 | +3,31 | 2,29 (n = 73 en total, < 100) |
| M5 | km_OHLC L12 g7 | londres | E3-4 compra | 266 | +1,05 | 3,32 | 275 | +0,97 | 2,06 | +0,99 | 1,96 (7/7 trimestres +) |
| M15 | km_OHLC L8 g16 | tend0 | E3-4 compra | 152 | +0,88 | 3,30 | 151 | +1,60 | 1,64 | +1,66 | 1,73 |

Casi todo lo que brilla en A cae a cero o a negativo en B. Esa es la firma del sobreajuste.

### Tasa de acierto vs expectativa neta (variantes con n_A ≥ 100)

| Acierto en A | Variantes | Neto medio A $/oz | % con neto A > 0 | Neto medio B $/oz |
|---|---|---|---|---|
| ≤ 40 % | 86 919 | −0,15 | 31 % | −0,13 |
| 40-50 % | 89 373 | −0,25 | 19 % | −0,15 |
| 50-60 % | 44 593 | +0,08 | 53 % | −0,20 |
| 60-70 % | 484 | +1,05 | 96 % | **−0,19** |
| 70-80 % | 1 | +3,59 | 100 % | +0,79 |

Una tasa de acierto alta en A no anticipa nada en B. Las 484 variantes que acertaban entre el 60 y el
70 % en A pierden en promedio 0,19 $/oz en B. Ninguna forma «se cumple siempre o casi siempre»: los
aciertos más altos con muestra decente rondan el 67-71 % en A y vuelven a ~50 % en B.

## El único candidato al límite (no recomendado; solo para vigilar)

**M5 · «capitulación en tendencia alcista»: comprar y salir a las 4 velas.**

Por qué no lo doy por bueno:

1. En la versión de la búsqueda, su t_B es 1,92 (< 2). Solo pasa en la re-simulación secuencial
   (2,11).
2. El control de permutación dice que confirmar 1-2 variantes en B es lo que da el azar.
3. Hay solo 85 operaciones en B, porque los días con tendencia +2 en B son pocos.
4. Es una sola idea que aparece en dos variantes vecinas (km_C L8 g8 y km_OHLC L12 g7). Eso es
   coherente, pero no independiente.

| | n | Neto $/oz | R (ATR) | Acierto | t (agrupado por día) |
|---|---|---|---|---|---|
| A, secuencial | 312 | +2,02 | ~+0,27 | ~59 % | 3,88 |
| B, secuencial | 85 | +1,87 | — | 63,5 % | 2,11 |
| Trimestres positivos | 5 de 6 | | | | |
| Bootstrap por días en B, P(media ≤ 0) | 0,012 | | | | |
| Base: comprar cualquier vela M5 en tend+2, misma salida | A −0,03 / B −0,54 | | | | |

No es deriva alcista: comprar cualquier vela en tend+2 pierde. En el contexto «todos» la misma
forma da +2,12 en A y +0,56 (t 1,16) en B, más débil.

**Cómo reconocer la forma en vivo.** Al cierre de cada vela M5 i:
- Calcular ATR = media simple de 14 rangos verdaderos.
- Calcular x_j = (C[i−7+j] − C[i]) / ATR para j = 0..6.
- Asignar x al centroide más cercano de los 30 de `km_C L=8` (k-means con semilla 7 sobre la mitad
  A de M5; se regeneran de forma determinista con el script, o se leen de `pat_formas.pkl`).
- El grupo 8 tiene centroide **[3,72 3,60 3,32 2,84 2,14 1,33 0,65]**: el precio estaba ~3,7 ATR
  más arriba hace 7 velas (35 min) y cayó en forma acelerada hasta el cierre actual.
- Regla aproximada sin centroides: C[i−7] − C[i] ≳ 3 ATR, con caída monótona y acelerada en las
  últimas 3-4 velas.

**Regla de entrada y salida:**
- Solo días con s = +2.
- Compra al ask en la apertura de la vela siguiente.
- Salida por tiempo al cierre de la 4.ª vela (20 min), sin TP ni SL.
- Una posición a la vez.
- Respetar la franja sin entradas (23:45-01:05; viernes desde las 22:00).

No hay re-simulación con ticks, porque los ticks solo existen desde 2026-01.

## Límites

- El desplazamiento circular conserva la deriva de cada tramo. Por eso el azar da muchas
  ganadoras en A. El control es justo para comparar el **conteo** real con el del azar, y el
  conteo real es menor.
- M5 y M1 cubren poco tiempo: 17 y 9,5 meses. B en M1 son unos 4,5 meses.
- En la búsqueda masiva las salidas usan velas, no ticks. En M1 solo las finalistas se
  re-simularon con ticks, y ninguna sobrevivió.
- En M1, la base de knn se tomó cada 3 minutos. Ninguna variante knn pasó BH en ningún marco.

## Conclusión

La minería automática de formas, con 309 120 combinaciones y un control de sobreajuste serio, **no
encuentra ningún patrón sin nombre que se cumpla «siempre o casi siempre»** ni uno con ventaja neta
distinguible del azar. Lo único que asoma es la compra tras una capitulación de unos 3-4 ATR en M5,
en días de tendencia alcista, con salida a los 20 minutos. Está en el límite y el control de
permutación no lo respalda. Si se quiere, que se registre en papel hacia adelante. **No** debe
pasar al bot e2 con esta evidencia.
