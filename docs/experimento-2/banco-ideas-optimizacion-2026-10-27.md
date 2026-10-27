# Banco de ideas de optimización del e2 e informe final — 27-oct-2026

> Solo simulación. Sin MT5 y sin tocar `bot/`. Rama `experimento-2-rediseno`.
> **Pregunta:** ¿hay algo que haga ganar al e2 **claramente más por unidad de riesgo**? La métrica es el MAR
> (retorno anual ÷ caída máxima) de la cartera completa al 8 %, con costos reales.
> **Respuesta corta: no.** Se probaron ~12 000 variantes en 7 líneas. Tres candidatos pasaron 2022-24 y 2025,
> pero los tres **fracasaron en 2026**, el periodo que estaba guardado. **Recomendación: no cambiar el e2.**

## 1. Cómo se midió

- **Herramienta común:** `bot_backtesting/fullsim/opt_base.py`. El protocolo de los subagentes está en `bot_backtesting/fullsim/OPT_PROTOCOLO.md`.
- **Camino de precios dentro de cada operación:**
  - velas de 5 minutos: de Dukascopy, ajustadas al broker con un desfase diario (residuo de 0,03 $/oz), hasta mayo de 2025; del broker desde entonces;
  - velas de 1 minuto del broker en 2026.
- **Costos:**
  - spread por minuto del día, medido con ticks del broker;
  - comisión de 3 $ por lote y lado;
  - deslizamiento de 0,05 $/oz en cada orden a mercado;
  - swap;
  - la Big One entra a las 01:01: +0,0061 × ATR_D sobre el precio de las 01:00, que son los 0,64 $/oz medidos en 2026.
- **Periodos:**
  - elegir: 2022-10 → 2024-12 (`sel`);
  - validar: 2025 (`val`);
  - prueba final: 2026, guardado y abierto solo para los 3 mejores.
- **Una idea gana si:**
  - mejora el MAR ×1,25 o más en `sel` y en `val`;
  - no empeora el peor día ni el peor mes;
  - el remuestreo da p ≤ 0,10;
  - tiene vecindario estable;
  - funciona en 2023 y en 2024;
  - le gana a los nulos.
- **Nulos:**
  - el lote mayor al mismo riesgo;
  - días al azar;
  - momentos al azar.

**Base e2 al 8 % (cuenta de 10 000):**

| Periodo | MAR | Crecimiento anual | Caída máx. | Peor día | Peor mes |
|---|---|---|---|---|---|
| 2022-10 → 2024 | 3,39 | 117 % | 34 % | −9,2 % | −15,7 % |
| 2025 | 3,60 | 122 % | 34 % | −10,1 % | −13,7 % |
| 2026 (ene-oct) | 5,98 | 74 % | 12 % | −8,4 % | −7,4 % |

## 2. Banco de ideas por línea

Total en el registro (`results/opt_registry.jsonl`, fuera de git): **11 994 variantes**.

| Línea | Variantes | Qué se probó | Mejor resultado | Veredicto | Informe / scripts |
|---|---|---|---|---|---|
| **A. Salidas** | 544 | TP por cuantiles, trailing en ganancia (ATR, Chandelier, que se aprieta, que se activa a +x, parabólico), salida por agotamiento, parciales, hora adaptativa, candado a 0,5–1,5 ATR_D, deshacer el candado | Trailing en ganancia de los tercios 2 y 3: ×1,23 en `sel`, ×1,22 en `val`, p = 0,12 | **Vigilancia.** Todo lo demás descartado. El candado a 1,0 ATR_D ya es el mejor. | `investigacion/opt-A-salidas-2026-10-27.md`, `opt_A_*.py` |
| **B. Tamaño / meta-labeling** | 450 | LightGBM, logística y ridge con 57 variables (VIX, GVZ, DXY, tasas reales, gap, Asia, COT, día y noticias), objetivo de volatilidad, reparto entre patas, riesgo por régimen | U1: la Big One con peso 0,75 fijo. ×1,40 en `sel`, ×1,42 en `val` | Candidato → **fracasó en 2026** (×0,40) | `investigacion/opt-B-tamano-2026-10-27.md`, `opt_B_*.py` |
| **C. Regímenes** | 7 908 | Reglas (Kaufman, ADX, vol, VIX/USDX), HMM con probabilidades filtradas, clustering, estrategias alternativas por régimen | F1: sin Big One en vol alta. ×1,52 en `sel`, ×1,64 en `val` | Candidato → **fracasó en 2026** (×0,26) | `investigacion/opt-C-regimenes-2026-10-27.md`, `opt_C_*.py` |
| **D. Entradas** | 1 106 | Límite a −x con y sin fallback, límite en el cuantil previsto del mínimo, escalonado, TWAP, stop de entrada, Momentum adelantado | Stop de entrada en el Momentum: ×1,66 en `sel`, pero quita la mitad de las operaciones; en `val`, ×0,84–1,03 | **Descartada.** El límite se llena justo en las perdedoras. | `investigacion/opt-D-entradas-2026-10-27.md`, `opt_D_*.py` |
| **E. Más patas** | 483 | 25 patas: horas del oro, fixes en divisas, índices, petróleo, plata, BTC, calendario | Víspera de FOMC y de feriado: ×1,3–2,2 en `sel`; en `val`, ×0,76–1,07 | **Descartada** (vigilancia: FOMC en índices y BTC en fin de semana). Es exposición alcista, no calendario. | `investigacion/opt-E-cartera-2026-10-27.md`, `opt_E_*.py` |
| **F. IA y datos externos** | 1 463 | Chronos (Bolt y Chronos-2) sin entrenar, FRED ampliado, CBOE (VIX9D/VIX3M, SKEW), GLD, GDELT, meta-logística, bandido contextual | T3 (filtro del Momentum por la vol prevista por Chronos): ×1,24 sobre F1 en `val`, pero no le gana al azar | **Descartada.** Chronos iguala a un HAR simple y adivina la dirección como una moneda. | `investigacion/opt-F-ia-datos-2026-10-27.md`, `opt_F_*.py` |
| **G. Coordinador** | 40 | Hora de salida de la Big One (05–10 h) y combinaciones de candidatos | Salida a las 08:00: ×1,46 en `sel`, ×1,20 en `val`, ×1,0 en 2024; empeora el peor mes. U1+F1: ×1,85 / ×1,65 | Salida a las 08:00 **descartada**. U1+F1 candidato → **fracasó en 2026** (×0,22) | este documento, `opt_G_hora_combos.py` |

**No se pudo hacer:**
- **Moirai y Lag-Llama:** no instalan en Python 3.14.
- **TimesFM y Kronos:** no se corrieron porque Chronos-2 no le ganó al HAR.
- **Finnhub, Alpha Vantage y FMP:** piden registro con email, así que no me registré.
- **Sin datos gratis con histórico:** opciones (put/call) y un calendario con la sorpresa del dato.
- **API de Claude para clasificar titulares (de pago, sin usar):** costaría ~0,15 $ con Haiku 5.5 y ~3 $ con Sonnet 5.5. No se recomienda, porque el tono de GDELT no aportó nada.

### Ideas propias de la línea G (justificadas en 3 líneas)

1. **Cerrar la Big One antes.** Si la ganancia se concentra en las primeras horas de Asia, salir antes baja la caída sin perder retorno. Resultado: funciona en 2023 pero no en 2024, y empeora el peor mes → descartada.
2. **Combinar el peso fijo (U1) con el filtro de volatilidad (F1).** Atacan cosas distintas: la inclinación por tendencia, que no aportaba, y los días de vol alta, que no ganaban. Resultado: la mejor combinación hasta 2025, y aun así fracasó en 2026.
3. **Control «sin Big One».** Comprueba que la mejora de F1 no sea solo «menos Big One». Quitarla entera da ×0,76 / ×0,69: la Big One sí aporta, y F1 elegía días; no solo restaba exposición.

## 3. Pruebas múltiples

- **Variantes:** 11 994 en el registro. Se descontaron 2 338 filas que la línea C migró y que estaban duplicadas en el CSV viejo.
- **Benjamini-Hochberg (FDR 10 %)** sobre las 604 variantes que tienen p de remuestreo: salen **16 «descubrimientos»**. Los 16 son carteras de calendario de la línea E en `sel`, y **todas fallaron en `val`**.
  - Ojo: el BH es optimista, porque las grillas grandes no llevaban p y no entran en el cálculo.
- **Deflated Sharpe** (con 11 994 pruebas): el Sharpe de los candidatos supera el umbral (DSR ≈ 0,98–0,99), pero eso mide la estrategia entera, que ya tenía ventaja, **no la mejora sobre la base**. La base daría lo mismo.
- **El MAR es muy ruidoso:** quitar al azar el 30 % de las operaciones ya da ×1,42 en el percentil 95 (línea B). Por eso el umbral de ×1,25, por sí solo, no basta.

## 4. Informe final: los 3 mejores candidatos

**Los candidatos**, fijados con datos hasta 2025 y sin tocarlos después de mirar 2026:
- **U1** (línea B): la Big One con peso 0,75 fijo, sin mirar la tendencia ni el día de noticia. Momentum y NFP sin cambios.
- **F1** (línea C): la Big One no se abre si `vpct ≥ 0,5`, es decir, si el ATR_D/precio está por encima de su mediana de los últimos 252 días.
- **U1+F1** (línea G): las dos a la vez.

Script: `bot_backtesting/fullsim/opt_final.py`. Cuenta de 10 000 al 8 %.

| Candidato | Periodo | MAR (× base) | Crec. anual | Caída | Lote mayor a la misma caída: crec. anual | Peor día (base) | Peor mes (base) | Nulo días al azar (percentil) | p remuestreo |
|---|---|---|---|---|---|---|---|---|---|
| U1 | 2022-24 | 4,75 (×1,40) | 133 % | 28 % | 82 % | −8,9 % (−9,2) | −12,9 % (−15,7) | — | 0,03 |
| U1 | 2025 | 5,11 (×1,42) | 124 % | 24 % | 84 % | −8,7 % (−10,1) | −10,9 % (−13,7) | — | 0,42 |
| U1 | **2026** | **2,40 (×0,40)** | 44 % | 18 % | **80 %** | **−11,4 %** (−8,4) | **−10,6 %** (−7,4) | — | 0,85 |
| F1 | 2022-24 | 5,15 (×1,52) | 141 % | 27 % | 82 % | −9,2 % (−9,2) | −12,5 % (−15,7) | 89 % | 0,13 |
| F1 | 2025 | 5,91 (×1,64) | 107 % | 18 % | 58 % | −8,3 % (−10,1) | −12,1 % (−13,7) | 86 % | 0,44 |
| F1 | **2026** | **1,58 (×0,26)** | 27 % | 17 % | **82 %** | −7,5 % (−8,4) | **−8,7 %** (−7,4) | **19 %** | 0,74 |
| U1+F1 | 2022-24 | 6,28 (×1,85) | 143 % | 23 % | 64 % | −8,9 % (−9,2) | −12,5 % (−15,7) | 97 % | 0,11 |
| U1+F1 | 2025 | 5,92 (×1,65) | 104 % | 18 % | 60 % | −8,1 % (−10,1) | −8,8 % (−13,7) | 91 % | 0,49 |
| U1+F1 | **2026** | **1,33 (×0,22)** | 23 % | 17 % | **82 %** | −7,5 % (−8,4) | **−8,7 %** (−7,4) | **16 %** | 0,76 |

**Riesgo por remuestreo** (bloques de 10 días, horizonte de 12 meses, 4 000 caminos):

| | P(caída > 30 %) 2025 / 2026 | P(caída > 40 %) 2025 / 2026 | Peor mes p05 2025 / 2026 |
|---|---|---|---|
| Base | 40 % / 6 % | 12 % / 0,8 % | −28 % / −19 % |
| U1 | 26 % / 18 % | 5 % / 4 % | −24 % / −24 % |
| F1 | 10 % / 10 % | 1,4 % / 1,6 % | −19 % / −19 % |
| U1+F1 | 11 % / 12 % | 1,6 % / 2,1 % | −20 % / −20 % |

**Por qué fallaron en 2026.** R medio de la Big One por régimen de volatilidad:

| Año | Vol baja | Vol alta |
|---|---|---|
| 2023 | +0,030 | −0,007 |
| 2024 | +0,074 | −0,004 |
| 2025 | +0,045 | +0,013 |
| **2026** | **−0,035** | **+0,020** |

- En 2026 el patrón se dio vuelta: la Big One ganó en los días de volatilidad alta, que en 2026 fueron casi todos (166 de 210), y perdió en los de baja.
- F1 la apagó justo cuando funcionaba, y quedó por debajo del 81 % de los filtros al azar.
- U1 (0,75 fijo) perdió porque en 2026 el peso vigente (por tendencia y por día de noticia) sí acertó: los días a los que la base da peso 1 fueron los buenos.
- La lección: las reglas de peso de la Big One son **inestables entre años**. Lo que funcionó tres años seguidos se invirtió en el cuarto.
- Además, el lote mayor al mismo riesgo (es decir, el e2 tal cual con un poco más de lote) le gana en 2026 a los tres candidatos: 80–82 % de crecimiento anual contra 23–44 %.

**Cuentas en 2026** (crecimiento ×, caída):

| Cuenta | Base | U1 | F1 | U1+F1 |
|---|---|---|---|---|
| 3 000 | ×1,93 / 25 % | ×1,93 / 25 % (igual que la base por el lote mínimo) | ×1,47 / 30 % | ×1,47 / 30 % |
| 10 000 | ×1,57 / 12 % | ×1,34 / 18 % | ×1,21 / 17 % | ×1,18 / 17 % |
| 25 000 | ×1,51 / 15 % | ×1,42 / 20 % | ×1,24 / 15 % | ×1,23 / 15 % |

## 5. Veredicto y recomendación

| Pregunta | Respuesta |
|---|---|
| ¿Alguna idea gana claramente más por unidad de riesgo? | **No.** Ninguna sobrevive al periodo guardado. |
| ¿Cambiar el e2? | **No.** Mantener el diseño vigente: tres patas, escalera, candado a 1 ATR_D y 8 %. |
| ¿Prueba en sombra? | **No hay candidato que la merezca.** El protocolo pedía un plan solo para los que pasaran, y ninguno pasó. |
| ¿Qué vigilar sin operar? | El trailing en ganancia de los tercios 2 y 3 (A: ×1,23 / ×1,22). **No se probó en 2026**, que se reservó a los 3 mejores. Si algún día se quiere probar, que sea en sombra, con el criterio fijado antes: ≥ 12 semanas y MAR de la sombra ≥ 1,15 × el de la demo real en el mismo periodo. |

**Lo que sí deja esta sesión:**
1. **Una base de simulación intra-vela con costos reales**, reutilizable: `opt_base.py`.
2. **Un mapa de lo que no funciona.** No hace falta volver a probar, salvo con datos nuevos:
   - salidas nuevas;
   - meta-labeling;
   - reglas de régimen;
   - órdenes límite y stop de entrada;
   - patas de otros símbolos;
   - modelos fundacionales sin entrenar;
   - sentimiento de GDELT.
3. **Dos avisos de método:**
   - simular niveles con el máximo o el mínimo de la misma vela infla el resultado ×1,5–3;
   - quitar operaciones al azar ya mueve el MAR ×1,4.
4. **La demo de 10 semanas sigue siendo la prueba que importa.** El e2 tal cual es más robusto que cualquier variante «optimizada».
