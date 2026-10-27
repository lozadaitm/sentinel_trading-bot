# Línea E: patas nuevas poco correlacionadas (cartera), 27-oct-2026

**Pregunta:** ¿varias ventajas pequeñas y poco correlacionadas con el e2 bajan la caída de la cartera más de lo que la diluyen?

**Respuesta corta:** no.
- En `sel` aparecieron patas de calendario que suben mucho el MAR de la cartera (hasta ×2,2).
- **En 2025 (`val`) ninguna lo sostiene.** La mejor da ×1,07.
- Los nulos explican la ilusión: en `sel` y en `val`, poner las mismas operaciones **en días al azar** da un MAR de cartera parecido o mejor. Lo que se ve es exposición larga a índices y oro en un mercado alcista, no el calendario.
- **No se recomienda añadir ninguna pata.** Total: **462 variantes** en `sel`, 5 validaciones y 16 filas de nulos (todas en `results/opt_registry.jsonl`, línea `E`).

## Cómo se midió

**Gestión:** cada pata usa la gestión e2 en su propio símbolo:
- tercios por hora / TP 2×ATR15 / TP 3×ATR15;
- candado a −1×ATR_D del símbolo;
- cierre a la hora.

**Riesgo:** 1 R = distancia del candado. La pata arriesga `w × 8 %` por operación. En una cesta, `w` se reparte entre sus símbolos.

**Otros símbolos:** velas M15 del broker (`data/broker_multi`).
- Dentro de cada vela va primero el lado en contra.
- Las TP son límites fijos desde la entrada: no dependen del máximo o mínimo de la misma vela.
- Nada entra entre 00:00 y 01:05 servidor.

**Oro:** camino fino M5 de `opt_base`.

**Costos conservadores** (`_info.csv` no trae el spread típico):

| Costo | Supuesto |
|---|---|
| Spread | 1,25 × máx(spread de la vela, mediana de los 60 días previos a esa hora). En el oro, el spread de la vela es ~1/1,2 del de los ticks. Piso de 0,2 pip en divisas |
| Deslizamiento | 0,5 × spread por orden a mercado |
| Comisión | 0,006 % del nominal en divisas y metales (3 $/lote/lado). Colchón de 0,002 % en índices y CFD |
| Swap en divisas y metales | Puntos del broker; un crédito cuenta como 0 |
| Swap en el resto de CFD | Largo −6 %/360 del precio, corto −2 %/360 |

**Cartera:** `opt_E_common.evaluate_mix`.
- Filas del oro: con lotes reales, igual que `opt_base.evaluate`. **Comprobado: da exactamente el mismo MAR para la base** (3,3887 en `sel` y 3,6002 en `val`).
- Filas de otros símbolos: ganancia = balance al entrar × 8 % × w × R (lote continuo).

`compare_mix` = `compare` con el mismo bootstrap, el nulo «lote mayor» y la misma regla de aceptación.

**Base e2:** MAR 3,39 en `sel` y 3,60 en `val`.

## Paso 1: criba de 25 hipótesis fijadas de antemano (`opt_E_patas.py`, w = 0,5, `sel`)

Regla para seguir: R ≥ 0 en 2023 **y** en 2024, y que no hunda la cartera.

| Grupo | Patas | R por operación (sel) | Corr. con e2 | MAR cartera vs base | Veredicto |
|---|---|---|---|---|---|
| FX, fixes de Londres y Tokio (Krohn, Mueller y Whelan 2024), cesta de 7 pares, antes y después del fix | 4 | −0,005 a −0,014 | −0,06 a +0,10 | ×0,72–0,81 | descartada: los costos se comen el efecto |
| FX, hora local (Breedon y Ranaldo): EUR, Asia, EE. UU. | 3 | −0,009 a −0,018 | −0,12 a +0,08 | ×0,59–0,71 | descartada |
| Índices EE. UU., deriva nocturna 23:00 → 16:15 | 1 | +0,002 (2023 −0,006) | +0,02 | ×0,83 | descartada (como dice la literatura, ≈0 desde 2021) |
| Índices, apertura europea 09:00 → 10:00 | 1 | −0,026 | +0,03 | ×0,43 | descartada |
| Índices, momentum de la última media hora (Gao; Baltussen) | 2 | −0,017 / −0,021 | ≈0 | ×0,55 | descartada |
| Índices, cambio de mes | 1 | +0,126 | −0,06 | ×1,02 | pasa a vecindario |
| Índices, víspera del FOMC | 1 | +0,105 | +0,01 | ×1,07 | pasa a vecindario |
| NAS100, momentum 13 → 18 (banco previo) | 1 | −0,002 | +0,06 | ×0,95 | descartada |
| USDJPY, momentum 10 → 15 (banco previo) | 1 | +0,024 (2024 −0,00003) | −0,05 | ×1,23 | pasa a vecindario |
| Petróleo, inventarios EIA | 1 | −0,047 | −0,01 | ×0,64 | descartada |
| BTC, fin de semana | 1 | +0,052 (solo desde dic-2023) | +0,10 | ×1,09 | vecindario, pero vigilancia por construcción (un solo año) |
| Plata, «Big One» 01:15 → 10:00 | 1 | −0,083 | **+0,35** | ×0,08 | descartada (cara y correlacionada) |
| Oro, ventanas nuevas: venta EE. UU. 16:30 → 20:30 (con y sin días de Momentum), tarde 21:00 → 23:45 (fija y siguiendo), fix PM, última media hora, LBMA AM | 7 | −0,008 a −0,018 | −0,17 a +0,12 | ×0,57–0,79 | descartadas: ninguna ≥0 en los dos años |

Descartadas sin probar:
- **Platino:** el spread de ~0,26 % es prohibitivo.
- **VIX:** el spread es de ~0,4 %.
- **Par oro/plata y oro contra USDX o bonos:** los lead-lag ya fallaron solos (`entry_tanda5`). La razón oro/plata tuvo tendencia en 2022-25, y un par largo/corto en metales, con swap en las dos patas y candado sobre un sintético sin velas reales, no es ejecutable en esta simulación de forma conservadora.

## Paso 2: vecindario y pesos (`opt_E_vecinos.py` + vecindario de `prehol` en `opt_E_cartera.py vec`, `sel`)

93 variantes × 4 pesos (0,25 / 0,5 / 1 / 1,5) + 15. Se añadieron tres patas de la misma familia, fijadas antes de mirar:
- **eu_tom:** cambio de mes en Europa;
- **idx_prehol:** víspera de feriado bursátil de EE. UU.;
- **g_prefomc:** oro comprado la víspera del FOMC.

| Pata (w = 1) | R 2023 / 2024 | MAR vs base | p | Vecinos | Veredicto en sel |
|---|---|---|---|---|---|
| Cambio de mes EE. UU. (compra el último día 22:45 → 3.er día) | +0,18 / +0,09 | ×1,07 | 0,37 | inestable: entrar un día antes da 2024 −0,36; candado 2 ATR_D ×0,94; solo por hora ×0,83; empeora el peor día (−14,7 %) | **descartada** |
| Cambio de mes Europa | −0,01 / +0,10 | ×0,84 | 0,49 | — | **descartada** |
| Víspera del FOMC, índices (21:00 de la víspera → 20:45) | +0,11 / +0,11 | ×1,14 | 0,13 | 20:30: ×1,14; 22:45: ×1,11; 16:30: ×0,84; dos días antes: ×0,85 | no llega a 1,25 |
| **Víspera de feriado, índices** (22:45 de d−2 → 22:45 de d−1) | +0,10 / +0,11 | **×1,28** | 0,04 | 16:30: ×1,15; 21:00: ×1,25; los 4 índices por separado: ×1,21–1,33 | finalista (empeora el peor día en 0,13 pp: no cumple la regla estricta) |
| **Oro, víspera del FOMC** (21:00 → 20:45) | +0,20 / +0,20 | **×1,45** | 0,008 | 20:30: ×1,49; 22:45: ×1,40; 16:30: ×1,23 | finalista (solo 19 eventos) |
| USDJPY momentum (umbral 0,7; 10 → 15) | +0,08 / +0,01 | ×1,60 | 0,08 | 11:00: ×0,70; umbral 0,3: ×0,96; cartera 2024 ×0,82; peor mes −19,3 % | **descartada** (inestable, empeora el peor mes, viene de un banco previo) |
| BTC fin de semana | +0,12 (dic) / +0,05 | ×1,16 | 0,41 | ×1,10–1,33 | **vigilancia** (un solo año de historia en sel) |

## Paso 3: carteras en `sel` (`opt_E_cartera.py sel`) y validación única en 2025 (`opt_E_cartera.py val`)

50 carteras en `sel`: pesos 0 / 0,5 / 1 de cada pata de calendario, más combinaciones con USDJPY. **Se fijaron 5 finalistas** y se miró `val` una sola vez.

| Finalista (w por pata) | sel: MAR (× base) | sel: CAGR / caída | sel: peor día / mes | sel: p | **val: MAR (× base)** | val: CAGR / caída | val: peor día / mes | val: p |
|---|---|---|---|---|---|---|---|---|
| Oro víspera FOMC 1,0 | 4,92 (×1,45) | 139 % / 28,4 % | −9,2 / −14,9 % | 0,008 | **2,73 (×0,76)** | 103 % / 37,6 % | −9,2 / −13,2 % | 0,95 |
| Víspera de feriado 1,0 | 4,32 (×1,28) | 133 % / 30,9 % | −9,3 / −12,7 % | 0,04 | **3,11 (×0,86)** | 123 % / 39,7 % | −8,9 / −17,8 % | 0,63 |
| FOMC índices 1,0 + oro 1,0 | 5,52 (×1,63) | 156 % / 28,3 % | −9,1 / −14,7 % | 0,004 | **3,63 (×1,01)** | 124 % / 34,1 % | −10,1 / −13,5 % | 0,64 |
| Feriado 1,0 + FOMC índices 1,0 | 4,95 (×1,46) | 148 % / 29,8 % | −9,3 / −12,8 % | 0,03 | **3,87 (×1,07)** | 140 % / 36,2 % | −9,7 / −17,9 % | 0,43 |
| Las tres, 1,0 cada una | 7,43 (×2,19) | 176 % / 23,7 % | −9,3 / −12,7 % | 0,000 | **2,93 (×0,81)** | 117 % / 39,9 % | −9,1 / −17,2 % | 0,69 |

Referencia de la base: `sel` peor día −9,2 % y peor mes −15,7 %; `val` −10,1 % y −13,7 %.

**R por operación en 2025:**

| Pata | R en 2025 | Años anteriores |
|---|---|---|
| Víspera de feriado | −0,02 | +0,10 / +0,11 |
| FOMC índices | +0,13 | sigue positiva |
| Oro víspera FOMC | **−0,15** | +0,20 / +0,20 |

## Nulos (`sel` / `val`)

En la tabla, el percentil indica qué fracción de los 200 sorteos queda por debajo del MAR real. **Lote mayor:** el MAR de la base con el riesgo que da la misma caída es 2,9–3,2 en `sel` (menor que el de la base, así que no explica la mejora) y 3,5–4,0 en `val`.

| Finalista | Días al azar: percentil sel / val | Lado al azar: percentil sel / val | Correlación diaria con e2 sel / val |
|---|---|---|---|
| Oro víspera FOMC | 0,99 / **0,08** (mediana al azar en val: 3,93 > real 2,73) | 0,99 / **0,01** | +0,03 / −0,01 |
| Víspera de feriado | 0,85 / 0,22 | 0,99 / 0,56 | +0,02 / +0,04 |
| FOMC índices + oro | 0,98 / 0,41 | 0,995 / 0,42 | +0,03 / +0,03 |
| Feriado + FOMC índices | 0,90 / 0,53 | 1,00 / 0,88 | +0,02 / +0,06 |
| Las tres | 0,99 / 0,29 | 1,00 / 0,33 | +0,03 / +0,05 |

**Lectura de los nulos:**
- En `val`, las mismas operaciones **en días al azar** suben el MAR de la cartera tanto o más que en los días del calendario. La mediana al azar es 3,7–4,1, frente a 3,60 de la base.
- O sea: añadir exposición larga a índices u oro, poco correlacionada, ayuda un poco en un mercado alcista, sea el día que sea. El «día especial» no aporta nada medible.
- En `sel`, el percentil alto (0,85–0,99) es lo que esperaríamos de una selección hecha sobre esos mismos datos. Es justo lo que los nulos advierten (línea B: el MAR es muy ruidoso).

## Veredicto por idea

| Idea | Veredicto |
|---|---|
| 1. Otras ventanas del oro (venta EE. UU., tarde, fixes, última media hora, LBMA) | **Descartada.** Ninguna es ≥0 en 2023 y 2024 |
| 2. Otros símbolos con estacionalidad horaria (fixes y hora local en FX, deriva nocturna, apertura europea, última media hora de índices, EIA, plata, BTC) | **Descartada.** Los costos reales del broker se comen los efectos intradía. BTC queda en vigilancia por falta de historia |
| 2b. Calendario en índices y oro (cambio de mes, víspera de FOMC, víspera de feriado) | **Descartada tras `val`.** Brilla en `sel` (×1,3–2,2), cae a ×0,76–1,07 en 2025 y no supera el nulo de días al azar |
| 3. Pares y spreads (oro/plata, oro/USDX, bonos) | **Descartada** sin simular (motivos arriba) |
| 4. Combinar varias patas pequeñas | **No pasa.** La correlación es ≈0, como se buscaba, pero las patas no tienen ventaja propia que sobreviva fuera de muestra. Diversificar sin ventaja solo diluye |

**Vigilancia (no entra al bot):**
- **Víspera del FOMC en índices EE. UU.** (largo 21:00 de la víspera → 20:45 del día, 4 índices). R positivo los 4 años, incluido 2025 (+0,13). Pero solo da ×1,14 en `sel`, con 8 eventos al año. No se validó sola como cartera.
- **BTC fin de semana.** Un solo año de historia.

## Recomendación

**No añadir patas nuevas al e2.** Con la evidencia actual, el MAR de la cartera solo sube en el periodo donde se eligió.

Para retomar esta línea haría falta una de dos cosas:
- más años de datos del broker en otros símbolos;
- una ventaja intradía con R ≥ 0,03 neta de costos en un símbolo barato.

Nada de lo probado se acerca a eso.

## Archivos

| Archivo | Qué hace |
|---|---|
| `bot_backtesting/fullsim/opt_E_common.py` | Simulador M15 de otros símbolos con la gestión e2, costos, `evaluate_mix` y `compare_mix`. Autocomprobación contra `opt_base.evaluate` |
| `bot_backtesting/fullsim/opt_E_patas.py` | Las 25 hipótesis y la criba |
| `bot_backtesting/fullsim/opt_E_vecinos.py` | Vecindario y pesos |
| `bot_backtesting/fullsim/opt_E_cartera.py` | Uso: `sel` (carteras), `sel vec` (vecindario de feriados), `val` (finalistas y nulos), `lado` (nulo de lado al azar corregido para el oro) |

Resultados crudos en `bot_backtesting/fullsim/results/opt_E_*.csv|txt|pkl` (fuera de git).
