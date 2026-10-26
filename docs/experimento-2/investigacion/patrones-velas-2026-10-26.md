# Banco de patrones de velas (equipo «velas»): M15 / M5 / M1, 2026-10-26

Código: `bot_backtesting/fullsim/pat_velas.py` (se corrió con prioridad BelowNormal; ~6 min).
Protocolo: [patrones-protocolo-2026-10-26.md](patrones-protocolo-2026-10-26.md). Solo análisis: no se tocó el bot.

## Veredicto

**Ningún patrón de velas pasa todos los filtros del protocolo.** Con la corrección
Benjamini-Hochberg al 10 % sobre las **14 400 variantes** probadas, **ninguna** sobrevive en la mitad A.
La mejor variante de toda la búsqueda tiene t_A = 3,51 (p de una cola 0,00022). Para pasar BH hacía falta
p ≤ 0,1 / 14 400 ≈ 0,000007, es decir, t_A ≈ 4,3.

Solo una variante pasaría si se usara la convención de dos colas de `econ_intraday.py`. La describo abajo
como **observación, no como hallazgo**:

- Variante: M5, racha de 5 velas bajistas tras una caída de ≥ 2 ATR → comprar y salir a las 4 velas.
- Resultado: n = 336; A +2,02 $/oz (t 2,74); B +1,98 $/oz (t 2,63).
- Esa convención está inflada: la abren 1 448 variantes muy negativas por el costo.

Los vecinos de esa variante no la confirman (ver § 6). Además, hay 3 variantes con t > 2 en A y en B a la
vez entre 13 090, y el azar puro esperaría 1,1. Conclusión honesta: **en las velas japonesas clásicas y en
las rachas no hay nada que se cumpla «siempre o casi siempre»**. Tampoco hay nada con ventaja neta
estable después del costo.

## 1. Datos y simulación

| Marco | Datos | Mitad A | Mitad B | Velas | Entradas válidas |
|---|---|---|---|---|---|
| M15 | broker_m15_full 2022-08 → 2026-10 | hasta 2024-09-19 | después | 99 000 | 95 398 |
| M5 | broker_m5_full 2025-05 → 2026-10 | hasta 2026-02-09 | después | 100 000 | 97 104 |
| M1 | broker_m1_ticks 2026-01-12 → 2026-10-23 | hasta 2026-06-03 | después | 279 854 | 272 298 |

**Entrada:**
- Se decide con la vela i ya cerrada y se entra a la apertura de la vela i+1, que debe ser contigua.
- En M1 esa apertura es el primer tick del minuto, así que el precio de entrada es exacto.
- No se entra de 23:45 a 01:05, ni el viernes desde las 22:00.
- El patrón no puede contener velas del rollover ni huecos.
- Todas las posiciones se cierran, como tarde, en la última vela que empieza antes de las 23:45 del mismo día.

**Costo:**
- M15 y M5: `max(0,23; spread de la vela + 0,06)` $/oz. El spread de la vela de MT5 es el mínimo de la vela
  (mediana 0,07) y subestima el real, por eso hay un piso de 0,23.
- M1: spread del primer tick de la vela de entrada + 0,06 (ticks reales, ~0,12 + 0,06).

**Salidas** (fijadas antes de mirar resultados; ATR = ATR14 del marco, incluida la vela i):

| Salida | Regla |
|---|---|
| E1 | objetivo 1 ATR / freno 1 ATR, tope 48 velas |
| E2 | objetivo 2 ATR / freno 1 ATR, tope 48 velas |
| E3_4, E3_12 | cierre a 4 / 12 velas, sin freno |
| E4 | escalera Big One: tercios a 12 velas / objetivo 2 ATR / objetivo 3 ATR. Candado a −1 ATR sobre los tercios abiertos (equivale a un freno de 1 ATR) |

- Si el objetivo y el freno caen en la misma vela, cuenta el freno en M15/M5.
- En M1 ese caso se resuelve con los ticks: hubo 4 869 casos y en 2 239 el objetivo llegó primero.
- Si el precio abre más allá del freno (hueco), el freno se llena a la apertura.

## 2. Definiciones (umbrales fijados a priori, no ajustados con B)

Notación:
- A = ATR14 de las 14 velas anteriores al patrón, sin incluirlo.
- b = cuerpo; r = rango.

| Patrón (lado natural) | Regla en la vela i |
|---|---|
| envolvente alcista (compra) / bajista | i−1 de color contrario; el cuerpo de i envuelve el de i−1; b ≥ 0,5 A |
| martillo-pin alcista / estrella fugaz-pin bajista | r ≥ 0,7 A; mecha dominante ≥ 2 b y ≥ 0,6 r |
| doji tras subida (venta) / tras bajada (compra) | b ≤ 0,1 r; r ≥ 0,3 A; impulso c[i−1] − c[i−5] ≥ 2 A en contra |
| interior y ruptura alcista / bajista | i−1 dentro de i−2; i cierra fuera del rango de i−2 |
| exterior alcista / bajista | h > h[i−1]; l < l[i−1]; b ≥ 0,5 r; color = lado |
| tres soldados / tres cuervos | 3 velas del mismo color con b ≥ 0,4 A; cierres escalonados; cierre en el 30 % extremo |
| estrella de la mañana / de la tarde | i−2 con b ≥ 0,6 A; i−1 con b ≤ 0,3 A; i contraria con b ≥ 0,6 A y cierre más allá del medio de i−2 |
| harami alcista / bajista | i−1 con b ≥ 0,6 A; i de color contrario con el cuerpo dentro del de i−1 y b ≤ 0,5 b[i−1] |
| pinza suelo / techo | colores opuestos; mínimos (máximos) a ≤ 0,1 A; r ≥ 0,5 A en ambas |
| rango amplio alcista / bajista | r ≥ 2 A; «seguir» = continuación, «revés» = reversión |
| racha alcista / bajista de N (N = 3…7) | la racha del mismo color que termina en i mide exactamente N |

En total son 30 patrones direccionales. Cada uno se prueba con 2 lados: **seguir** (el lado natural) y
**revés**.

**Contextos** (16, de uno en uno):
- todos;
- hora de entrada: Asia 01–09, Londres 09–15, NY 15–20, tarde 20–23:45;
- tendencia diaria s = +2 / 0 / −2;
- tras un impulso de ≥ 2 A al alza / a la baja (c[i−1] − c[i−6]);
- vela en el máximo / mínimo de 20 velas;
- cerca, a ≤ max(1 A; 0,1 × rango de ayer), del máximo / mínimo del día anterior;
- volatilidad alta / baja: A dividido por la mediana de A en 20 días, ≥ 1,3 / ≤ 0,77.

**Número de variantes:** 30 patrones × 2 lados × 5 salidas × 16 contextos × 3 marcos = **14 400**. Todas
entran en el BH; las que tienen n_A < 20 cuentan con p = 1. Hay 13 140 con n_A ≥ 20.

## 3. Resultado de los filtros

| Filtro | M15 | M5 | M1 | Total |
|---|---|---|---|---|
| Variantes probadas | 4 800 | 4 800 | 4 800 | **14 400** |
| 2. BH 10 % en A (p de una cola, hipótesis neto > 0) | 0 | 0 | 0 | **0** |
| 3. … y B neto > 0 con t > 2 | 0 | 0 | 0 | **0** |
| (referencia) BH con la convención de dos colas de econ_intraday | 2 | 15 | 6 | 23 |
| (referencia) … y B neto > 0 con t > 2 | 0 | 1 | 0 | 1 |
| (referencia) … y trimestres, n ≥ 100, bootstrap y azar | – | 1 | – | 1 |

**Por qué la prueba principal es de una cola.** La hipótesis es «neto > 0». Con el costo, 1 448 variantes
tienen t_A < −2,5. Si se usan p de dos colas, esas variantes perdedoras «descubiertas» suben el umbral de BH
para todas: 23 variantes positivas pasan con p ≈ 0,009, cuando lo honesto con 14 400 pruebas es
p ≈ 0,000007.

## 4. Las 25 mejores en A (por t_A) y lo que hicieron en B

Neto en $/oz por operación; R = neto / ATR; «acierto» = fracción de operaciones con neto > 0.

| Marco | Patrón | Contexto | Lado | Salida | n_A | neto A | R A | acierto A | t_A | n_B | neto B | R B | acierto B | t_B |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5 | rango_amplio_baj | h_asia | revés | E3_12 | 532 | +2,43 | +0,41 | 55 % | 3,51 | 524 | −1,70 | −0,41 | 46 % | −2,21 |
| M5 | interior_ruptura_alc | cerca_max_ayer | seguir | E3_12 | 161 | +2,86 | +0,73 | 60 % | 3,35 | 81 | +0,76 | +0,20 | 49 % | 0,44 |
| M5 | interior_ruptura_alc | h_asia | seguir | E3_12 | 410 | +1,88 | +0,31 | 55 % | 3,29 | 406 | +0,97 | +0,03 | 50 % | 1,35 |
| M1 | rango_amplio_baj | cerca_max_ayer | revés | E3_12 | 234 | +1,71 | +0,20 | 58 % | 3,21 | 250 | +0,27 | −0,06 | 48 % | 0,61 |
| M1 | racha_baj_3 | tras_imp_sube | revés | E3_12 | 151 | +2,11 | +0,56 | 57 % | 3,16 | 169 | +0,09 | −0,05 | 49 % | 0,23 |
| M5 | interior_ruptura_alc | todos | seguir | E3_12 | 1 176 | +1,11 | +0,26 | 54 % | 3,03 | 1 077 | +0,42 | +0,02 | 49 % | 0,90 |
| M5 | harami_alc | tras_imp_baja | seguir | E3_4 | 334 | +1,22 | +0,19 | 55 % | 2,98 | 328 | −0,08 | +0,01 | 51 % | −0,12 |
| M5 | tres_soldados | cerca_max_ayer | seguir | E3_12 | 56 | +6,21 | +0,85 | 62 % | 2,97 | 32 | +3,58 | +1,00 | 56 % | 1,77 |
| M5 | doji_tras_bajada | en_min20 | seguir | E3_12 | 97 | +4,35 | +0,38 | 56 % | 2,96 | 140 | −1,50 | −0,17 | 51 % | −1,03 |
| M5 | racha_baj_6 | cerca_min_ayer | revés | E3_4 | 28 | +4,90 | +0,76 | 79 % | 2,94 | 40 | −1,19 | −0,05 | 55 % | −0,60 |
| M15 | racha_baj_7 | tend0 | revés | E3_4 | 33 | +1,73 | +0,89 | 67 % | 2,93 | 28 | +0,64 | −0,10 | 50 % | 0,32 |
| M1 | tres_cuervos | tras_imp_baja | revés | E3_12 | 482 | +1,82 | +0,31 | 60 % | 2,83 | 536 | +0,35 | +0,14 | 51 % | 1,37 |
| M5 | tres_cuervos | tras_imp_baja | revés | E3_4 | 124 | +2,30 | +0,16 | 60 % | 2,82 | 106 | +1,53 | +0,35 | 57 % | 1,40 |
| **M5** | **racha_baj_5** | **tras_imp_baja** | **revés** | **E3_4** | **157** | **+2,02** | **+0,26** | **61 %** | **2,74** | **179** | **+1,98** | **+0,25** | **59 %** | **2,63** |
| M5 | rango_amplio_baj | tend-2 | revés | E3_12 | 29 | +1,82 | +0,77 | 59 % | 2,73 | 398 | −1,08 | −0,23 | 47 % | −1,45 |
| M5 | rango_amplio_alc | en_max20 | seguir | E3_12 | 522 | +1,36 | +0,42 | 54 % | 2,73 | 619 | +0,19 | −0,04 | 49 % | 0,28 |
| M5 | racha_baj_6 | cerca_min_ayer | revés | E3_12 | 28 | +7,69 | +1,28 | 75 % | 2,71 | 40 | −1,97 | +0,26 | 60 % | −0,61 |
| M1 | tres_cuervos | h_asia | revés | E3_4 | 404 | +0,99 | +0,21 | 59 % | 2,68 | 477 | −0,04 | −0,10 | 47 % | −0,28 |
| M1 | rango_amplio_baj | todos | revés | E3_12 | 3 500 | +0,52 | +0,07 | 55 % | 2,63 | 3 009 | +0,03 | −0,07 | 50 % | 0,27 |
| M15 | doji_tras_bajada | vol_alta | revés | E2 | 110 | +1,64 | +0,36 | 51 % | 2,62 | 81 | −4,31 | −0,36 | 24 % | −2,02 |
| M5 | tres_cuervos | tend0 | revés | E3_12 | 64 | +2,08 | +0,68 | 61 % | 2,62 | 141 | +1,00 | +0,10 | 53 % | 0,60 |
| M5 | doji_tras_bajada | todos | seguir | E3_12 | 225 | +2,40 | +0,26 | 59 % | 2,62 | 283 | −1,08 | −0,19 | 48 % | −1,09 |
| M1 | exterior_baj | en_min20 | revés | E3_12 | 694 | +1,14 | +0,06 | 58 % | 2,62 | 717 | +0,34 | +0,14 | 51 % | 1,20 |
| M5 | harami_alc | tras_imp_sube | seguir | E3_12 | 24 | +4,46 | +0,92 | 58 % | 2,59 | 28 | −1,22 | −0,30 | 54 % | −0,56 |
| M15 | doji_tras_bajada | vol_alta | revés | E3_4 | 110 | +1,51 | +0,33 | 62 % | 2,59 | 81 | −8,33 | −0,44 | 27 % | −3,90 |

**Lectura de la tabla:**
- De las 25 mejores en A, 11 son negativas en B.
- Las de M15 con doji tras una bajada se dan vuelta con fuerza (t_B −2 y −3,9).
- Solo una (en negrita) repite con t_B > 2.
- Muchas son «revés» de patrones bajistas en M5 o M1: es decir, comprar después de una caída. Eso coincide
  con la deriva alcista del oro en 2025-26 más que con un patrón de velas.

**Panorama general** (media sobre las variantes con n_A ≥ 50):
- El neto en A va de −0,13 a −0,27 $/oz por operación según el marco y la salida.
- Solo el 7 % (M15, E1) al 40 % (M5, E3_12) de las variantes es positivo en A.
- En total, el 25 % es positivo en A y el 29 % en B. Es lo que se espera de patrones sin ventaja a los que
  se les resta el costo, en un mercado alcista donde comprar suma un poco.

## 5. Tasa de acierto frente a expectativa neta

| Salida | Acierto medio en A | Neto medio en A ($/oz) | R medio | Correlación acierto–neto |
|---|---|---|---|---|
| E1 (1:1) | 49,4 % | −0,235 | −0,10 | +0,72 |
| E2 (2:1) | 34,6 % | −0,182 | −0,08 | +0,63 |
| E3_4 | 47,1 % | −0,212 | −0,09 | +0,55 |
| E3_12 | 48,3 % | −0,212 | −0,09 | +0,55 |
| E4 (escalera) | 32,9 % | −0,174 | −0,08 | +0,57 |

**Acierto ≥ 60 % en A con expectativa negativa:** aparecen 3 variantes (con n_A ≥ 50). Con un umbral algo
más bajo, 73 variantes tienen acierto ≥ 55 % y neto < 0.

| Marco | Patrón | Contexto | Lado | Salida | n_A | acierto A | neto A | acierto B | neto B |
|---|---|---|---|---|---|---|---|---|---|
| M5 | racha_baj_6 | vol_alta | revés | E3_4 | 87 | **62 %** | **−0,05** | 47 % | +0,36 |
| M5 | racha_alc_3 | tras_imp_baja | seguir | E3_12 | 66 | **61 %** | **−3,75** | 54 % | +1,73 |
| M5 | racha_baj_5 | vol_alta | revés | E3_12 | 180 | **60 %** | **−1,07** | 47 % | −1,75 |

El caso más claro es la racha alcista de 3 tras una caída: acierta el 61 % de las veces y aun así pierde
3,75 $/oz por operación, porque las pocas pérdidas son mucho más grandes que las ganancias.

En el otro extremo, 1 379 variantes aciertan menos del 45 % y son positivas en A (sobre todo E2 y E4,
donde se gana más de lo que se arriesga).

**Ninguna variante acierta «casi siempre».** El acierto máximo con n_A ≥ 50 es del 67 % en A, y esas mismas
variantes bajan al 45–58 % en B.

## 6. La única que pasa (solo con la convención de dos colas): por qué no la recomiendo

**Regla exacta** (por si se quiere seguir en papel):
- En M5, al cierre de la vela i: la racha de velas bajistas que termina en i mide **exactamente 5**, y además
  c[i−1] − c[i−6] ≤ −2 × ATR14 (ATR14 de las velas i−14…i−1).
- No debe haber velas entre 23:45 y 01:05 en el patrón.
- Entrada: **compra** a la apertura de la vela i+1, dentro de la ventana 01:05–23:45 y nunca el viernes
  desde las 22:00.
- Salida: al cierre de la 4.ª vela, a los 20 minutos, sin freno ni objetivo.

**Resultados:**

| | n | neto $/oz | R | acierto | t |
|---|---|---|---|---|---|
| A (2025-05 → 2026-02) | 157 | +2,02 | +0,26 | 61 % | 2,74 |
| B (2026-02 → 2026-10) | 179 | +1,98 | +0,25 | 59 % | 2,63 |

- Por trimestre: 25T2 +0,32; 25T3 +0,58; 25T4 +1,88; 26T1 +5,08; 26T2 +4,04; 26T3 +1,15; 26T4 −0,61
  (son 24 operaciones). Es decir, 1 trimestre negativo de 7.
- Bootstrap por semanas de B: P(media ≤ 0) = 0,006.
- Nulo de entradas al azar en el mismo contexto (B): p = 0,0065.

**En contra:**
1. No pasa el BH correcto (p de una cola 0,003 frente a un umbral de 0,000007): es una de 14 400.
2. Tiene **3 coincidencias con t > 2 en A y B entre 13 090, cuando el azar esperaría 1,1**.
3. **Los vecinos no la sostienen:**
   - Las rachas de 4 y de 6 en el mismo contexto dan B +0,05 / +0,78 $/oz con t < 1,1.
   - La misma regla en M15 da B +1,67 (t 1,0) y en M1 da B −0,21 (t −1,4).
   - El espejo (vender tras 5 alcistas después de una subida) pierde en los 3 marcos.
4. La ganancia se concentra en el primer semestre de 2026 (26T1–26T2), con el oro en máximos y una
   volatilidad extrema. Es comprar la caída en un mercado alcista, no un patrón de velas.
5. Muestra corta en M5 (17 meses, 336 operaciones).

**Recomendación:** no llevarla al bot. Como mucho, anotarla en el registro de observación y volver a
medirla con 6 meses más de M5 y ticks, sin tocar la regla.

## 7. Conclusión

Probé 14 400 variantes de velas japonesas, vela interior y exterior, rango amplio y rachas de 3 a 7 velas,
en 3 marcos, 16 contextos, 5 salidas y ambos lados, con costo real. Ninguna pasa el filtro del protocolo.

- Las mejores de A se deshacen en B, con la proporción de coincidencias que daría el azar.
- La tasa de acierto ronda el 47–50 % en las salidas simétricas y no se acerca a «siempre».
- Donde aparece un acierto alto, la expectativa puede ser negativa.

Para el bot e2 no hay ningún patrón de velas que justifique una vigilancia tick a tick.
