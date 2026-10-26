# Patrones geométricos clásicos (V, W/M, HCH, banderas, triángulos, compresiones, ruptura falsa) — 2026-10-26

Equipo «geométricos» del banco de patrones. Protocolo: [patrones-protocolo-2026-10-26.md](patrones-protocolo-2026-10-26.md).
Código: `bot_backtesting/fullsim/pat_geometricos.py` (`python -m bot_backtesting.fullsim.pat_geometricos`,
lanzado con prioridad BelowNormal; ~31 min, casi todo en la simulación tick a tick de M1).
Datos del broker: M15 2022-08 → 2026-10, M5 2025-05 → 2026-10, M1 y ticks 2026-01-12 → 2026-10.
Mitad A/B = primera/segunda mitad del calendario de cada marco.

## Conclusión

**Ningún patrón geométrico pasó el filtro.** De **8 600 variantes**, una sola superó BH al 10 % en A,
y era un caso con muestra mínima (n = 21) que en B dio −0,07 $/oz (t = −0,16). Ninguna variante tiene
t > 2 en A **y** en B a la vez. Con el costo real, el patrón típico pierde entre 0,15 y 0,26 $/oz por
operación: el resultado es el de una entrada al azar menos el costo. No hay ninguna regla que replicar en el bot.

## Qué se probó (parámetros fijados antes de ver resultados, sin ajustarlos con B)

| Patrón | Definición exacta | Entrada |
|---|---|---|
| Pivotes `zz` | zigzag: el giro se confirma cuando el precio se aleja ≥ 1,5 ATR14 del extremo | — |
| Pivotes `fr` | fractal de 3 velas a cada lado (se confirma 3 velas después), forzado a alternar | — |
| V3 / V3inv | caída (subida) ≥ 3 ATR en ≤ 8 velas hasta el mínimo (máximo) de las últimas 8; ATR medido antes del tramo | cierre que recupera ≥ 50 % del tramo |
| V2 / V2inv | ídem con ≥ 2 ATR en ≤ 4 velas | recupera ≥ 60 % |
| W / M (`zz`, `fr`) | L1 pivote, cuello H pivote, L2 = mínimo desde H; \|L2−L1\| ≤ 0,5 ATR; cuello ≥ 1 ATR; ≥ 2 velas entre puntos; vigente max(20, 3×ancho) velas | cierre por encima (debajo) del cuello |
| HCH / HCHi (`zz`, `fr`) | hombro izq., N1, cabeza, N2 pivotes; hombro der. = extremo desde N2; cabeza ≥ 0,5 ATR más allá de ambos hombros; \|HI−HD\| ≤ 1 ATR; hombros ≥ 0,5 ATR del cuello | cierre al otro lado de la línea N1-N2 extrapolada |
| Triángulo (`zz`, `fr`) | últimos 4 pivotes: 2 máximos descendentes y 2 mínimos ascendentes, líneas que no se cruzaron | cierre fuera de la línea superior (compra) o inferior (venta) |
| Bandera alcista/bajista | impulso: cierre − mínimo de 7 velas ≥ 2,5 ATR; 3–15 velas de consolidación sin retroceder > 50 % | cierre más allá del extremo del impulso + bandera |
| Compresión | rango de 12 velas ≤ 2 × ATR(96) previo y mitad reciente más estrecha | cierre fuera de la caja |
| Ruptura falsa techo/suelo | caja de 20 velas de ancho ≤ 4 ATR; perforación ≥ 0,1 ATR | cierre de vuelta dentro en esa vela o en las 3 siguientes → operar en contra de la ruptura |

22 patrones-dirección × 3 marcos; en M1 además la entrada «toque» (primer tick que cruza el nivel de
confirmación dentro de la vela) para los 20 patrones con nivel previo. Cada uno × 2 lados (seguir / al revés)
× 10 contextos (todo; bloque horario asia 01–10, londres 10–15, nueva_york 15–20, tarde 20–23:45 hora servidor;
tendencia diaria s = +2 / 0 / −2; volatilidad alta / baja = ATR14 sobre/bajo su mediana de 500 velas)
× 5 salidas (E1 1/1 ATR, E2 2/1 ATR, E3 tiempo 4 y 12 velas, E4 escalera de tercios con freno común
1 ATR: tiempo 12 velas / 2 ATR / 3 ATR). **Total: 8 600 variantes** (M15 2 200, M5 2 200, M1 4 200),
1,65 millones de operaciones simuladas. 854 variantes con < 20 operaciones en A entraron a BH con p = 1.

Ejecución: M15/M5 entran en la apertura siguiente con costo max(0,23; spread de la vela + 0,06) $/oz
(sin ticks); M1 entra y sale con ticks reales (compra al ask, venta al bid, salidas tick a tick + 0,06).
Sin entradas 23:45–01:05 ni viernes desde las 22:00; todo se cierra antes de las 23:45. Una operación
a la vez por variante. Objetivo y freno en la misma vela: freno.

## Embudo de filtros

| Filtro | Variantes que quedan |
|---|---|
| Probadas | 8 600 |
| 2. BH 10 % en A con neto > 0 | 1 (M1 TRI_dn_zz, cierre, seguir, E3 4 velas, s=+2; **n_A = 21**) |
| 3. B neto > 0 con t > 2 | **0** (esa dio −0,07 $/oz, t_B −0,16) |
| 4–6. Periodos, n ≥ 100, remuestreo | 0 |

Nota sobre la única que pasó BH: pasó porque BH se aplica sobre p bilaterales y hay **muchas** variantes
significativamente *negativas* (13 % con t_A < −2, por el costo), lo que relaja el umbral. Con 21 operaciones
no era un candidato serio y B lo confirmó. Sin el costo, el reparto de t sería simétrico: solo el 0,6 % de las
variantes tiene t_A > +2, **menos** de lo que daría el puro azar (≈ 2,3 %).

## Mejores en A (por t_A, n_A ≥ 30) y lo que hicieron en B

$/oz netos por operación; R = $/oz ÷ ATR del marco; «acierto» = % de operaciones con neto > 0.

| Marco | Patrón | Entrada | Lado | Salida | Contexto | n_A | neto A | acierto A | t_A | n_B | neto B | acierto B | t_B | p azar¹ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5 | W_fr | cierre | seguir | E3 12 | asia | 129 | +3,17 | 61 % | 2,96 | 129 | −0,94 | 43 % | −0,81 | 0,72 |
| M1 | COMP_up | cierre | revés | E3 12 | s=0 | 67 | +1,29 | 61 % | 2,77 | 240 | −0,39 | 50 % | −1,54 | — |
| M15 | TRI_up_fr | cierre | seguir | E2 | s=0 | 63 | +0,86 | 56 % | 2,63 | 77 | +0,83 | 40 % | 0,62 | 0,23 |
| M1 | HCHi_zz | cierre | seguir | E3 4 | s=−2 | 50 | +1,24 | 58 % | 2,54 | 110 | +0,40 | 43 % | 0,64 | — |
| M5 | M_fr | cierre | revés | E3 12 | tarde | 48 | +2,39 | 58 % | 2,53 | 51 | −4,11 | 37 % | −2,67 | 0,96 |
| M1 | HCHi_zz | cierre | seguir | E3 12 | s=−2 | 50 | +1,98 | 60 % | 2,48 | 110 | +0,26 | 46 % | 0,35 | — |
| M1 | HCHi_fr | toque | seguir | E1 | nueva_york | 116 | +1,07 | 59 % | 2,46 | 106 | +0,22 | 55 % | 0,83 | — |
| M15 | BAND_baj | cierre | seguir | E3 4 | s=0 | 34 | +0,82 | 65 % | 2,44 | 44 | +3,97 | 50 % | 1,11 | 0,02 |
| M1 | M_zz | toque | seguir | E2 | todo | 1 143 | +0,42 | 37 % | 2,41 | 1 170 | +0,03 | 35 % | 0,31 | — |
| M5 | W_fr | cierre | seguir | E3 12 | vol. baja | 183 | +1,90 | 56 % | 2,36 | 167 | −1,68 | 40 % | −1,82 | 0,92 |
| M5 | M_zz | cierre | revés | E3 12 | vol. alta | 113 | +3,62 | 68 % | 2,36 | 138 | −0,72 | 51 % | −0,43 | — |
| M5 | M_zz | cierre | revés | E3 12 | s=+2 | 151 | +3,04 | 68 % | 2,35 | 66 | −1,65 | 58 % | −0,66 | — |

¹ Prueba de fechas al azar en la mitad B (mismas horas del día, días al azar, misma salida y lado, 200
repeticiones; solo M15/M5): probabilidad de que el azar iguale o supere lo observado en B. El remuestreo
por bloques de días en B (p de media ≤ 0) dio entre 0,14 y 0,998 para las 10 primeras: ninguna es distinguible
de cero. Patrón general: lo mejor de A se desinfla o se da vuelta en B (regresión a la media de 8 600 intentos).

Lo mejor de **B** tampoco se confirma en A (elegido en B, mirado en A): M5 TRI_dn_zz seguir E3 4 vol. baja
t_B 3,1 pero t_A 1,0; M15 bandera alcista E3 12 s=0 t_B 3,0 con n_A 32 y t_A 1,6. Con 8 600 variantes
se esperan ~70 con t_B > 2 por azar, y salieron 71.

## Tasa de acierto vs expectativa neta

- Promedio del contexto «todo»: E1 acierta ~48–50 % y pierde 0,18–0,26 $/oz; E2 y E4 aciertan solo
  30–35 % y pierden algo menos (0,12–0,23). La tasa de acierto no ordena las variantes por resultado.
- **Acierto alto con expectativa negativa (casos explícitos):**
  - M5 TRI_dn_fr, revés, E3 12, nueva_york: **62 % de acierto en A y −5,22 $/oz** (n = 60): las pérdidas son mucho más grandes que las ganancias.
  - M5 HCHi_fr, seguir, E3 12, nueva_york: 62 % de acierto, −0,09 $/oz (n = 42).
  - M15 TRI_up_fr, revés, E1, tarde: 61 % de acierto, −0,01 $/oz; en B 46 % y −1,88.
  - M5 W_zz, seguir, E3 12, nueva_york: 59 % de acierto, −0,50 $/oz.
  - En B: M5 HCHi_fr revés E3 12 s=0, **62 % de acierto y −0,70 $/oz**; M5 HCH_zz seguir E3 12 s=−2, 62 % y −0,41.
- De las 79 variantes con acierto ≥ 60 % en A (n ≥ 30), **44 tienen neto negativo en B**. Ejemplo: M5 M_zz
  revés E3 12 s=+2, con 68 % de acierto y +3,04 en A, bajó a 58 % de acierto y −1,65 $/oz en B.

## Observaciones

- El costo (0,23 $/oz fijo en M15/M5; spread real + 0,06 en M1) se come el poco borde que hay. En M1 el
  patrón medio pierde ~0,18 $/oz por operación, que es casi exactamente el spread más la comisión.
- Seguir o ir al revés da resultados parecidos (los dos pierden el costo). Que muchas variantes «al revés»
  salgan algo mejor en A no se sostiene en B: ninguno de los dos lados tiene un borde estable.
- La V (giro brusco), que era la pregunta de origen, pierde de forma consistente en los tres marcos y
  en los dos juegos de parámetros (ejemplo M1 V3 seguir en A: −0,10 a −0,47 $/oz según la salida y la entrada).
- Límites: M5 cubre 17 meses y M1 9,5 meses (mitad B de M1 ≈ 4,5 meses); los parámetros geométricos
  son un único juego razonable por patrón, no una búsqueda. Otros umbrales podrían dar otros números, pero
  probarlos aumentaría el número de pruebas, y este banco no muestra ninguna señal que justifique hacerlo.

**Veredicto: nada pasó todos los filtros.** No hay ninguna regla geométrica para el bot e2.
