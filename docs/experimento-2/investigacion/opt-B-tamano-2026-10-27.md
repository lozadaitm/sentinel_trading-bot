# Línea B: tamaño inteligente y meta-labeling — 27-oct-2026

> **Veredicto corto:** ningún modelo «sabe» qué operación va a ganar. El meta-labeling se ve bien en 2022-24 y en 2025 se hunde (MAR de 0,3 a 0,8 veces el de la base). El volatility targeting, el riesgo por régimen y el reparto entre patas no pasan.
>
> **Lo único que sale de aquí es quitar algo, no añadir:** el peso vigente de la Big One (1 si `s = +2`, 0,5 si no, ×0,5 en día de noticia) rinde **peor que repartir esos mismos pesos al azar**. Queda en el percentil 2,5 % de 200 repartos al azar en sel y en el 16 % en val.
>
> **Candidato para la prueba de 2026 (U1):** Big One con peso **0,75 fijo** todos los días, sin el ×0,5 de noticia. MAR ×1,40 en sel y ×1,42 en val, con mejor peor día y mejor peor mes. **No** es una señal: solo quita una inclinación que no aporta nada.

Solo simulación: no se tocó MT5, ni `bot/`, ni se hicieron commits. 2026 no se miró.

## Cómo se midió

- **Base:** `base_trades()`, con la gestión vigente. Solo cambia la columna de peso; la dirección y las salidas son las de siempre.
- **Evaluación:** `compare(C, B, per, wcol='w')` al 8 %, cuenta de 10 000 $.
  - **sel** = 2022-10 → 2024-12, para elegir.
  - **val** = 2025: una sola mirada, solo para finalistas.
- **Modo «crudo»:** peso = peso base × multiplicador, tal cual.
  - Ojo: el MAR **sube solo con más exposición**. La base da MAR 3,39 al 8 % y 4,16 al 12 %.
  - Por eso miramos siempre **edge_lm** = CAGR del candidato ÷ CAGR de la base con un lote mayor que da la misma caída. Mayor que 1 significa que le gana a «subir el lote».
- **Nulo de días al azar:** se permutan los pesos del candidato entre operaciones de la misma pata, 200 veces. Se reporta el percentil del MAR del candidato.
- **Ruido del MAR:** quitar al azar el 30 % de las operaciones da un MAR de ×1,42 en el percentil 95 y de ×1,93 en el percentil 99. **El umbral de ×1,25 está dentro del ruido.** Sin el nulo de días al azar, cualquier grilla «encuentra» ganadores.

## Lluvia de ideas, ordenada por ganancia esperada ÷ costo

| # | Idea | Costo | ¿Probada? |
|---|---|---|---|
| 1 | Revisar el peso vigente de la Big One (tendencia `s`, ×0,5 en noticia) | muy bajo | sí (`bo_w`, 81) |
| 2 | Riesgo por régimen: terciles de una variable, con cortes de cuantiles **pasados** | bajo | sí (`bucket`, 124) |
| 3 | Día de la semana en la Big One; noticia en el Momentum | bajo | sí (`dow`, 22) |
| 4 | Reparto fijo entre patas | bajo | sí (`leg_alloc`, 16) |
| 5 | Desempeño rodante: t-stat de las últimas N, racha, inverso de la volatilidad del R, paridad de riesgo, solape entre patas | bajo | sí (`roll`, 25) |
| 6 | Volatility targeting (objetivo ÷ previsto)^k en [0,5; 1,5], con HAR, rv1, rv5, desviación del R, VIX del broker, GVZ y ATR15/ATR_D | bajo | sí (`voltgt`, 21) |
| 7 | Meta-labeling: logística L2, LightGBM pequeño y ridge; todas las variables o pocas; por pata o conjunto; CV purgada o walk-forward; 5 mapas a peso | medio | sí (`meta`, 120) |
| 8 | Flujos de ETF (GLD/IAU) | — | **no**: no hay datos gratis descargados y el protocolo prohíbe bajar cosas nuevas del broker. Se saltó. |
| 9 | Modelos secuenciales o de ticks | alto | no: con unas 850 operaciones se sobreajustan; ya se descartó en `deteccion-minimo` |

## Resultados por familia (sel; mediana y máximo de MAR ÷ base)

| Familia | Variantes | Mediana | Máximo | Pasan la regla formal en sel |
|---|---|---|---|---|
| bo_w (peso de la Big One) | 81 | 1,30 | 1,62 | 38 |
| bucket (régimen) | 124 | 0,94 | 2,39 | 8 |
| dow / noticia | 22 | 1,21 | 1,52 | 0 (empeora el peor mes) |
| leg_alloc | 16 | 1,01 | 1,18 | 0 |
| roll | 25 | 0,98 | 1,19 | 0 |
| voltgt | 21 | 0,91 | 1,08 | 0 |
| meta | 120 | 1,29 | 1,87 | 21 |

**Calidad de los modelos** (fuera de muestra en sel):
- Big One: AUC de 0,50 a 0,60; correlación de rango con el R de 0,00 a 0,17.
- Momentum: AUC de 0,48 a 0,60.

Son tan débiles como los de `deteccion-minimo` (0,57-0,61). Con **variables nuevas** (macro con retraso, VIX y USDX del broker, COT, sesión previa) **tampoco hay señal**.

## Finalistas: sel y val

`p` = bootstrap pareado (probabilidad de **no** mejorar el MAR). «Percentil al azar» = posición del candidato frente a los 200 repartos al azar.

| Candidato | sel: MAR ×base | sel: p | sel: percentil al azar | val: MAR ×base | val: p | val: percentil al azar | val: peor día / mes | Veredicto |
|---|---|---|---|---|---|---|---|---|
| **U1** Big One con peso 0,75 fijo, sin ×0,5 de noticia | **1,40** (2023: 1,57 · 2024: 1,23) | 0,03 | n/a (\*) | **1,42** | 0,42 | n/a (\*) | −8,7 % / −10,9 % (base −10,1 / −13,7) | **pasa con reparo** |
| R1 Big One 0,5 si `s=+2`, si no 1; sin ×0,5 de noticia | 1,62 (1,97 · 1,26) | 0,10 | 87 % | 1,78 | 0,47 | 82 % | −8,0 % / −7,5 % | vigilancia: no le gana al azar |
| R2 Momentum = 0 si la tasa real (DFII10) subió en 5 días por encima del tercil alto | 2,39 (2,80 · 1,34) | 0,09 | 96,5 % | 1,01 | 0,51 | 30 % | −10,2 % / −11,8 % | descartada |
| R3 Momentum = 0 si el hueco de las 01:00 cae en el tercil alto | 1,97 | 0,14 | 91 % | 0,93 | 0,44 | 34 % | — | descartada |
| R4 Momentum = 0 si el GVZ bajó en 5 días (tercil bajo) | 1,99 (peor mes −17,9 %) | 0,04 | 86 % | 1,35 | 0,26 | 64 % | — | descartada (empeora el peor mes) |
| R5 = R1 + R2 | 4,16 | 0,02 | 100 % | 1,72 | 0,38 | 76 % | — | descartada (en val es solo R1) |
| meta lgbm, todas, conjunto, cv, quita el 30 % más bajo | 1,84 | 0,16 | 93 % | **0,30** | 0,93 | 18 % | — | descartada |
| meta logit, todas, conjunto, cv, quita el 30 % más bajo | 1,78 | 0,41 | 93 % | 0,33 | 0,79 | 43 % | — | descartada |
| meta lgbm, pocas, conjunto, cv, quita el 30 % más bajo | 1,74 | 0,08 | 93 % | 0,31 | 0,88 | 14 % | — | descartada |
| meta logit, todas, conjunto, cv, 0,5 bajo la mediana | 1,72 | 0,09 | 91 % | 0,83 | 0,82 | 41 % | — | descartada |
| meta ridge, pocas, conjunto, wf, quita el 30 % más bajo | 1,63 | 0,03 | 85 % | 0,67 | 0,84 | 44 % | — | descartada |

(\*) U1 tiene un peso constante dentro de la Big One, así que permutarlo no cambia nada. Su nulo es el de la **base**: el reparto vigente queda en el percentil 2,5 % en sel y 16 % en val. U1 cae donde cae un reparto típico al azar: MAR 4,74 frente a una media de 4,79 al azar en sel, y 5,11 frente a 4,93 en val.

**Vecinos de U1:**

| Variante | MAR ×base (sel) |
|---|---|
| 0,5 fijo | 1,22 |
| **0,75 fijo (U1)** | **1,40** |
| 1,0 fijo | 1,51 |
| 0,75 con ×0,75 en noticia | 1,34 |
| 0,75 con ×0,5 en noticia | 1,25 |

Todos dan ≥ 1,15. A más peso, más exposición: lo que importa es edge_lm. El de U1 es 1,63 en sel y 1,47 en val.

**Por semestre (U1 frente a la base):**

| Semestre | MAR ×base |
|---|---|
| 2023 | ×1,57 |
| 2024 | ×1,23 |
| 2025, 1.er semestre | ×1,65 |
| 2025, 2.º semestre | **×0,75** |

En el gran rally del 2.º semestre de 2025, cargar los días `s=+2` sí convino. R1 cae ahí a ×0,44.

## Veredicto por idea

1. **Meta-labeling: descartada.**
   - En sel, el 70 % de las variantes «mejoran», pero eso es lo mismo que hace el azar (percentil 85-93 %).
   - En val, todos los finalistas empeoran: MAR de 0,30 a 0,83 veces el de la base.
   - AUC 0,50-0,60. Confirma `deteccion-minimo` y `analisis-filtro-ml-op1`.
2. **Volatility targeting: descartada.** Ninguna de las 21 llega a ×1,1. El lote ya escala con ATR_D, y la variación sobrante del R no se predice.
3. **Riesgo por régimen: descartada.** Las 3 mejores de 124 (tasas reales, hueco y GVZ en el Momentum) se caen en val, hasta el percentil 30-64 % del azar. Día de la semana: el lunes de la Big One es negativo los 3 años, pero cortarlo empeora el peor mes.
4. **Diversificación entre patas: descartada.** El reparto fijo, la racha, el t-stat rodante, la paridad de riesgo y el solape dan ≤ ×1,19 y edge_lm ≤ 1,08.
5. **Peso vigente de la Big One: no ayuda.**
   - La inclinación por tendencia más el ×0,5 de noticia es **peor que el azar** en sel (percentil 2,5 %) y en val (16 %).
   - Quitarla (U1) pasa la regla formal en sel y en val.
   - Reparo 1: el bootstrap en val no es concluyente (p = 0,42).
   - Reparo 2: en el 2.º semestre de 2025 la inclinación sí ayudó.
   - Invertirla (R1) no le gana al azar: no hay que usar `s` en ningún sentido.

## Recomendación

- **Probar U1 en 2026** (el coordinador): peso de la Big One = 0,75 todos los días y sin ×0,5 de noticia. Momentum y NFP quedan igual.
- **No implementar** meta-labeling, volatility targeting ni pesos por régimen.
- Si U1 no mejora en 2026, se queda la base. La diferencia es de diseño, no de señal.

## Datos externos y su retraso

| Dato | Fuente | Cuándo se publica | Cómo se usó |
|---|---|---|---|
| VIX, USDX, plata, SP500, oro (M15) | broker, `data/broker_multi/*.pkl` | tiempo real | último cierre M15 **anterior** a `t_in` (el cierre de la vela de `time` se conoce en `time + 15 min`) |
| VIXCLS, GVZCLS | FRED / CBOE | día hábil siguiente, por la mañana en NY | valor de la fecha NY ≤ entrada − **2 días hábiles** |
| DFII10 (tasa real 10 años) | FRED / Tesoro | día hábil siguiente | −2 días hábiles |
| T10YIE | FRED | día hábil siguiente | −2 días hábiles |
| DTWEXBGS (dólar amplio) | FRED / Fed H.10 | **semanal** (lunes, con la semana previa) | −2 días hábiles. ⚠ Para los días de la semana anterior se adelanta hasta ~5 días. Solo entró en el conjunto «todas» del meta-labeling, que se descartó. No está en ningún finalista. |
| BAMLH0A0HYM2 | FRED | — | no se usó: la serie empieza en 2023-10 |
| COT oro (CFTC) | `gold_cot.csv` | viernes 15:30 NY, con datos del martes | desde el martes + 6 días (el lunes siguiente) |
| Calendario NFP/IPC/FOMC | `events_us.csv` | se conoce de antemano | día de la entrada |
| Flujos de ETF | — | — | no disponible gratis en el repo; se saltó |

## Variantes y archivos

**Total de variantes: 450 filas de la línea B en `results/opt_registry.csv`.**
- 409 de grilla: 289 de reglas (11 «dow» en modo neutro, sin sufijo) y 120 de meta-labeling.
- 14 vecinos nuevos y la combinación R5.
- Repeticiones con bootstrap en sel.
- 11 evaluaciones en val.

⚠ **Registro común descuadrado:** el encabezado lo creó una fila sin bootstrap (24 columnas). Las filas B tienen 30: las mismas 23 primeras, y después `p, mar_ratio_med, p_dd30_c, p_dd30_b, p_dd40_c, p_dd40_b, pasa`. El detalle con extras (edge_lm, r2023, r2024, exposición) está en `results/opt_B_log.csv`.

**Scripts** (en `bot_backtesting/fullsim/`):

| Script | Qué hace |
|---|---|
| `opt_B_feats.py` | 57 variables por operación, con lo disponible al entrar |
| `opt_B_lib.py` | evaluación, presupuesto neutro y nulo de días al azar |
| `opt_B_rules.py` | familias de reglas |
| `opt_B_meta.py` | meta-labeling; `fit_final(...)` y `weights_period(...)` para aplicar un modelo entrenado hasta una fecha |
| `opt_B_final.py` | finalistas, vecinos, val y nulos; `U1` y `bo_trend_w` |
