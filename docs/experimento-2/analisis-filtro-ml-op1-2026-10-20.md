# Filtro predictivo de la Op1 (meta-labeling con machine learning): sin capacidad de predicción (20-oct)

**Pedido del usuario (19–20 oct):** que el bot «lea el gráfico» y tenga capacidad de análisis predictivo. Revisar los videos de TikTok (jessepbuilds, savipww), la evidencia publicada y las librerías disponibles.

## 1. Pregunta medida

Un modelo «juez» que dice sí o no antes de cada Op1 (*meta-labeling*, López de Prado):
- La Op1 sale con sus señales de siempre.
- El modelo estima la probabilidad de que esa entrada acabe en **cobertura (Op2)** en vez de cerrar en verde.
- Si la probabilidad es alta, la entrada se veta.

**Por qué esta pregunta:** la cobertura es lo que crea los ciclos congelados (ver `analisis-op4-criterio-propio-2026-10-19.md`, sección 5).

## 2. Datos

- **Velas del oro en M5, de 2021-01 a 2026-01, de Dukascopy (bid, gratis).**
  - Se pasaron a hora de servidor (UTC+2/+3) y de ahí se armaron M15 y H4.
  - Se descargaron de internet, sin tocar MT5: un historial profundo desde MT5 cuelga los terminales (memoria `mt5-history-download-blocks-bots`).
- **2026-02 a 2026-10:** velas del broker ya guardadas.
- **Señales:** cada vela en que el **motor real** (`SentinelEngine`, compuertas del ESTADO 0) abriría una Op1. Se simula la Op1 sola en M5 hasta que cierra en verde o llega a la distancia de cobertura (2 ATR, con suelo de 8 $).
  - 22 370 velas con señal y 8 161 primeras entradas.
  - **Tasa de cobertura: 13,5 %.**
- **Características** (solo información pasada, normalizada por ATR y según el lado de la entrada), 32 en total:
  - **Volatilidad:** ATR frente a su mediana de 5 y 20 días, ATR en $, volatilidad de 1 h frente a 24 h, rango de 24 h.
  - **Tendencia:** pendiente de la EMA50 en H4, distancia a la EMA200 en H4, momentum de 1 h, 4 h y 24 h, distancia a la EMA9, RSI, alineación con la estructura H4.
  - **Smart money:** huecos de precio (FVG) a favor y en contra en las últimas 16 velas, barridos de liquidez (perfora el extremo de 48 velas y cierra dentro), recorrido hasta el extremo de 48 velas y hasta el máximo o mínimo del día anterior, posición en el rango de 24 h.
  - **Vela:** rango, cuerpo, mechas a favor y en contra, velas seguidas en la misma dirección.
  - **Tiempo:** hora y día de la semana.
  - **La señal en sí:** distancia al nivel roto, número de re-entrada y lado.
- **Modelo:** LightGBM (árboles pequeños y regularizados).
- **Validación walk-forward semestral desde 2022-07:** cada semestre se predice con un modelo entrenado solo con lo anterior, con una purga de 3 días entre entrenamiento y prueba.
  - 6 162 primeras entradas fuera de muestra.

## 3. Resultados (fuera de muestra)

**AUC global: 0,508.** 0,5 es azar; un filtro útil necesitaría más de 0,6 de forma estable.

| Semestre | Entradas | Tasa de cobertura | AUC |
|---|---|---|---|
| 2022-S2 | 713 | 15,7 % | 0,420 |
| 2023-S1 | 687 | 14,0 % | 0,455 |
| 2023-S2 | 670 | 13,7 % | 0,537 |
| 2024-S1 | 735 | 13,1 % | 0,423 |
| 2024-S2 | 828 | 15,9 % | 0,521 |
| 2025-S1 | 811 | 12,1 % | 0,515 |
| 2025-S2 | 725 | 12,0 % | 0,623 |
| 2026-S1 | 547 | 11,3 % | 0,520 |
| 2026-S2 | 446 | 9,4 % | 0,494 |

**Tasa de cobertura de las entradas que el filtro deja pasar** (base 13,3 %):

| Veto | Modelo (IC 90 %) | Solo por ATR alto | Al azar (p5–p95) |
|---|---|---|---|
| 10 % | 13,3 % (12,6–14,0) | 13,4 % | 13,3 % (13,0–13,5) |
| 20 % | 13,3 % (12,5–14,1) | 13,3 % | 13,3 % (12,9–13,6) |
| 30 % | 13,3 % (12,4–14,1) | 13,6 % | 13,3 % (12,8–13,7) |
| 50 % | 12,9 % (11,8–13,8) | 14,0 % | 13,3 % (12,5–14,0) |

**Hora y día de la semana:** la tasa de cobertura es plana. Todas las franjas de 3 h quedan entre el 12 % y el 15 % y cambian de orden según el año. Ningún día de la semana sobresale de forma estable.

**Conclusión:** con 5 años de datos y 32 características, incluidas las de smart money, **no se puede predecir qué Op1 acabará en cobertura**. El modelo veta igual que al azar. Esto confirma, con unas 7 veces más datos, lo que ya habían dado los indicadores uno por uno el 19-oct.

## 4. Por qué (interpretación)

La Op1 apuesta a un objetivo pequeño (del orden de 1 $/oz) frente a una distancia de cobertura grande (2 ATR, 8–18 $/oz). Que el precio recorra 2 ATR en contra antes de dar 1 $ a favor depende casi solo de la **geometría** de esas dos distancias y del ruido. La señal de entrada apenas influye, y ninguna característica del gráfico anticipa los tirones grandes. Con barreras que escalan con el ATR, la volatilidad prevista tampoco ayuda.

**Consecuencia práctica:** la tasa de cobertura, cerca del 13 %, no se puede bajar «leyendo mejor» el gráfico. La rentabilidad depende de **cuánto cuesta salir de cada ciclo cubierto**, no de predecir la entrada.

## 5. Videos y evidencia externa (resumen)

- **jessepbuilds:** es el día 1 de un sistema de investigación. Una IA junta ideas (ICT, SMC, orderflow), las comprueba contra precios reales y las somete a un motor de pruebas con costes y un filtro contra la suerte. No muestra resultados ni código. **El método coincide con el nuestro**; esto es lo que ese método da para nuestra Op1.
- **savipww:** memecoins con «bots de Grok». Promete pasar de 100 $ a 17 608 $ en 4 noches, sin verificar y con enlace de referido. No aplica al oro.
- **Evidencia publicada:**
  - Un preprint de 2026 no encuentra ventaja en seis reglas ICT/SMC programadas al pie de la letra en divisas. Además, los huecos de precio se «rellenan» igual que niveles al azar (83,4 % frente a 83,5 %).
  - Las reglas técnicas intradía en oro dependen mucho de los parámetros.
  - Lo que sí se predice bien es la **volatilidad**, no la dirección. En este caso tampoco alcanzó.
- **Kronos** (13-oct): 50,2 % de acierto de dirección en oro.

## 6. Reproducibilidad

Scripts en el scratchpad de la sesión (no están en el repo, porque traen datos crudos):
- `ml/dl_duka.py`: descarga de Dukascopy y paso a hora de servidor;
- `ml/scan_long.py`: escaneo de señales con el motor real;
- `ml/meta.py`: características, walk-forward y tablas.

Se instalaron en un entorno aislado (venv): `dukascopy-python` 4.0.1 y `lightgbm` 4.7.0. Los bots no usan ese entorno.

**Límites:**
- Dukascopy no es el feed del broker: hay pequeñas diferencias de precio y no hay spread real (se usó una constante de 0,20).
- La simulación de la Op1 sola es aproximada: no tiene el trailing de cesta exacto.
- La etiqueta (llegar a la cobertura) es la del diseño actual. Otro objetivo de la Op1 cambiaría la geometría.
