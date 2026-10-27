# Línea F: IA y datos externos (27-oct-2026)

Sesión de optimización del e2 (oro, XAUUSD+). Pregunta: ¿la **información nueva** (modelos fundacionales de series temporales, noticias, datos de API gratuitos que B y C no usaron, o aprendizaje por refuerzo) mejora el MAR de la cartera al 8 %, sola o encima de F1 de la línea C?

Solo simulación: no se tocó MT5, ni `bot/`, ni se hicieron commits. 2026 no se miró (todas las previsiones y datos se cortan en 2025-12-31).

## Resumen

- **Nada pasa.** Ninguna de las 1 453 variantes en `sel` (más 10 miradas a `val`) mejora a F1 de forma que se sostenga en 2025.
- **Chronos (IA de series temporales), sin entrenar:**
  - en volatilidad empata con un HAR de tres líneas;
  - en dirección de la Big One acierta como una moneda al aire.
  - Como filtro del Momentum se ve espectacular en `sel` (×2 sobre F1), pero en `val` queda en ×0,93-1,24 sobre F1 y dentro del azar.
- **Datos nuevos** (breakevens de inflación, curva, estrés financiero, VIX9D/VIX3M, SKEW, GVZ/VIX, flujos de GLD, tono de noticias GDELT): repiten el patrón de la línea B.
  - Los mejores son filtros del Momentum que doblan el MAR en `sel` y en `val` no suman nada sobre F1 (×0,74-1,02).
  - El mejor de toda la línea, «Momentum apagado si el breakeven a 5 años subió en la semana», es primo del R2 de B (tasa real), que también se cayó en `val`.
- **Meta-modelo con todas las variables nuevas** (logística con CV purgada): AUC 0,42-0,51. Peor que el azar.
- **Bandido contextual** (aprendizaje por refuerzo acotado): **redescubre solo la regla de C** (apagar la Big One en vol alta y cargar 1,5 en vol baja, es decir F2).
  - Añadir más contexto (tendencia, flujo de GLD) lo empeora.
  - En `val` empeora el peor día y el peor mes.
- **Recomendación:** no añadir IA ni datos externos al bot. Quedarse con los candidatos de B (U1) y C (F1) para la prueba de 2026.

Base al 8 % (cuenta de 10 000): MAR **sel 3,39**, **val 3,60**. F1 (línea C): MAR sel 5,34 (×1,58), val 5,91 (×1,64).

## Ideas, ordenadas por ganancia esperada ÷ costo

| # | Idea | Costo | Ganancia esperada (a priori) | ¿Probada? |
|---|---|---|---|---|
| 1 | Datos gratis nuevos como filtro (FRED nuevas, CBOE, GLD) | bajo | baja (B ya vio que lo macro falla en `val`) | sí, 828 + 276 variantes |
| 2 | Chronos-Bolt / Chronos-2 sin entrenar: retorno y rango previstos de la ventana de cada pata | medio (CPU ~35 min) | baja-media (la literatura dice: algo en vol, nada en dirección) | sí, 312 variantes + 6 nulos |
| 3 | Tono y atención de noticias GDELT | medio (la API limita mucho) | baja | sí, dentro del 1 (216 + 72) |
| 4 | Meta-modelo con todas las nuevas | bajo | muy baja (B: AUC 0,50-0,60) | sí, 4 variantes |
| 5 | Bandido contextual sobre el peso 0/0,5/1/1,5 | bajo | muy baja | sí, 15 variantes + 2 en `val` |
| 6 | Calendario con sorpresa (dato real − consenso) | — | media | **no: no hay histórico gratis sin registro** (ver «Pendiente») |
| 7 | Opciones: put/call | — | baja | no: no encontré histórico gratuito vigente; se usó SKEW y VIX9D/VIX3M como sustituto |
| 8 | Ajuste fino (fine-tuning) de Chronos | alto en CPU | — | no: el modelo sin entrenar no mostró nada en `val` |
| 9 | Clasificar titulares con la API de Claude | bajo (de pago) | baja | no (requiere aprobación). Ver la propuesta |

## 1. Modelos fundacionales sin entrenar (`opt_F_tsfm.py`)

**Cómo:**
- Cada día hábil de 2021-09 a 2025-12 se pidió al modelo la previsión de las velas M15 de la ventana de cada pata, con **solo las 512 velas M15 cerradas antes de entrar**:
  - Big One: contexto hasta la vela de las 23:45 y 36 velas de horizonte (01:00 → 10:00);
  - Momentum: contexto hasta la de las 14:45 y 24 velas (15:00 → 21:00).
- Serie: M15 del broker desde 2022-08-17; antes, Dukascopy M15 con el desfase diario al broker.
- De cada previsión salen dos números:
  - `mu` = mediana prevista al final ÷ último cierre − 1 (retorno previsto);
  - `sig` = (q90 − q10) al final ÷ último cierre (volatilidad prevista).
- Para el filtro se usa el **percentil de esa previsión entre los 252 días hábiles anteriores** (sin mirar adelante).

**Nulos triviales** con la misma interfaz:
- media estacional (retorno medio de esa ventana en los 60 días previos);
- AR(1) sobre los retornos M15 del contexto;
- HAR sobre el rango de la ventana.

**Instalación y tiempo** (CPU, 2 hilos, prioridad baja; 2 222 previsiones por modelo):

| Modelo | Tiempo total | Por previsión | Estado |
|---|---|---|---|
| chronos-bolt-tiny (9 M) | 134 s | 60 ms | instalado (`chronos-forecasting` 2.3.2, torch 2.14.1+cpu en `.venv`, Python 3.14) |
| chronos-bolt-small (48 M) | 471 s | 212 ms | ídem |
| chronos-2 (120 M) | 1 526 s | 687 ms | ídem; el proceso usó ~1 GB de RAM |
| Moirai (`uni2ts`) | — | — | **no instala en Python 3.14** (falla la compilación de dependencias) |
| Lag-Llama | — | — | **no está en PyPI** |
| TimesFM | — | — | `pip --dry-run` resuelve, pero no se corrió |
| Kronos | — | — | no está en PyPI (hay que clonar el repo); no se corrió |

TimesFM y Kronos no se corrieron porque Chronos-2, el más fuerte de su clase, no le gana a HAR en volatilidad y no ve nada en dirección: la ganancia esperada no justificaba el tiempo.

**Calidad en `sel`** (correlación de rango con lo realizado en la ventana; 579 días Big One, 573 Momentum):

| Ventana | Modelo | IC retorno | Acierto de signo | IC rango |
|---|---|---|---|---|
| Big One | media estacional | 0,015 | 56,3 % | 0,42 |
| Big One | HAR | 0,015 | 56,3 % | **0,48** |
| Big One | chronos-bolt-tiny | 0,019 | 53,9 % | 0,44 |
| Big One | chronos-bolt-small | 0,007 | 51,6 % | 0,45 |
| Big One | chronos-2 | −0,002 | 49,6 % | **0,48** |
| Momentum | AR(1) | 0,036 | 51,3 % | 0,24 |
| Momentum | chronos-bolt-tiny | 0,101 | 51,3 % | 0,24 |
| Momentum | chronos-bolt-small | 0,124 | 51,1 % | 0,21 |
| Momentum | chronos-2 | 0,023 | 51,8 % | 0,19 |

Cómo leer la tabla:
- En volatilidad, Chronos-2 = HAR. En la Big One, la «media histórica» (siempre sube) acierta más el signo que cualquier modelo.
- Lo único distinto del azar es el IC de 0,10-0,12 de Chronos-Bolt en la ventana del Momentum, con un acierto de signo de solo 51 %.

**Grilla** (156 variantes sobre la base y 156 sobre F1):
- regla = Momentum o Big One ×0 si el percentil de `mu` o `sig` cae por debajo o por encima de 0,33, 0,5 o 0,67;
- más dos reglas naturales sin umbral: Big One off si `mu` < 0, y Momentum off si lado × `mu` < 0.

**Resultados de la grilla:**
- Sobre la base: mediana ×0,84, p95 ×1,40.
- Sobre F1: mediana ×0,79 respecto de F1, p95 ×1,56.
- Máximo de cada modelo sobre F1 (×F1): chronos-2 2,01 · bolt-tiny 1,82 · bolt-small 1,68 · HAR 1,56 · media estacional 1,52 · AR(1) 1,37. El predictor trivial también «encuentra» ×1,5.
- **Comprobación:** el mejor filtro **no** es «apagar los Momentum cortos». Apagar todos los cortos da ×0,51 sobre la base, y Chronos-2 apaga sobre todo largos (66 %).

**Veredicto: descartada** (finalistas en la tabla de abajo).

## 2. Datos externos nuevos (`opt_F_ext.py`, `opt_F_datos.py`)

23 características. Cada una se une «as of» la hora de entrada con el **retraso real de publicación** y se pasa a percentil de los 252 días previos a la misma hora.

**Grilla:** 23 características × pata (Big One, Momentum o todas) × umbral (0,33 / 0,5 / 0,67) × lado × multiplicador (0 o 0,5). Son 828 variantes sobre la base y 276 sobre F1.

| Fuente | Variantes base / F1 | Mediana ×base | Máx ×base | Mediana ×F1 | Máx ×F1 |
|---|---|---|---|---|---|
| FRED nuevas | 324 / 108 | 0,86 | 2,10 | 0,76 | 2,28 |
| CBOE | 144 / 48 | 0,86 | 1,66 | 0,80 | 1,67 |
| GDELT | 216 / 72 | 0,86 | 1,40 | 0,77 | 1,56 |
| GLD | 144 / 48 | 0,84 | 1,25 | 0,82 | 1,36 |

Todas las medianas están **por debajo de 1**. Los máximos son lo que da el ruido en grillas de este tamaño: la línea B midió que quitar el 30 % de las operaciones al azar da ×1,42 en el p95.

GDELT y GLD, las fuentes realmente «nuevas» (noticias y flujos), no llegan ni a finalista.

### Retraso de publicación de cada fuente (verificado el 27-oct-2026)

| Dato | Fuente | Última fecha disponible el 27-oct | Retraso usado (dato publicable desde) |
|---|---|---|---|
| T5YIE, T5YIFR, T10Y2Y | FRED (Tesoro / Fed) | 26-oct | fecha + **2** días hábiles, 09:00 NY. FRED los trae con 1 día hábil; se usó 2 por seguridad, como B |
| DFII5, DGS3MO | FRED | 23-oct (2 días hábiles) | fecha + 2 días hábiles, 09:00 NY |
| STLFSI4 (estrés financiero, **semanal**) | FRED / Fed St. Louis | viernes 16-oct, publicado el jueves 22 | viernes + 4 días hábiles (jueves) 12:00 NY |
| USEPUINDXD (incertidumbre de política) | FRED | 26-oct | fecha + 3 días hábiles (se revisa los días siguientes) |
| VIX, VIX9D, VIX3M, SKEW, GVZ | CBOE (CSV público `cdn.cboe.com`) | 26-oct | cierre 16:15 NY; publicable al día hábil siguiente 09:00 NY |
| GLD: toneladas, prima/descuento, volumen | SPDR (xlsx del *historical archive*, gratis y sin registro) | 26-oct | fecha + 1 día hábil 09:00 NY. Aviso: el archivo prohíbe redistribuir los datos; solo uso interno, fuera de git |
| GDELT DOC 2.0: tono y nº de artículos sobre oro y sobre la Fed (inglés) | GDELT (gratis, sin clave) | — | bins **diarios** UTC; publicable al final del día UTC + 30 min. Para la Big One (18:00 NY) se usa el día UTC anterior completo |

Sobre GDELT:
- La API devolvió 429 (demasiadas peticiones) casi siempre, incluso con 1 petición por minuto.
- Por eso no se pudo bajar la serie **horaria** (habría tardado ~12 h). Se usó la diaria (4 peticiones).
- Con datos horarios se podría añadir la noticia de las ~22 h previas a la Big One. No se espera que cambie el veredicto: con el día completo anterior no hubo nada.

## 3. Meta-modelo con todas las nuevas (`opt_F_datos.py meta`)

**Cómo:** logística L2 (C = 0,1 y 1) sobre los 23 percentiles, por pata, para P(R > 0). CV purgada de 5 pliegues con embargo de 5 días dentro de `sel`. Se quita el 30 % más bajo, con el corte del pliegue de entrenamiento.

**Resultado:**
- AUC Big One 0,46-0,51; AUC Momentum 0,42-0,45.
- Sobre la base: ×0,90-1,12. Sobre F1: ×0,57-0,97.

**Veredicto: descartada** (4 variantes).

## 4. Aprendizaje por refuerzo acotado (`opt_F_bandit.py`)

**Cómo:**
- Bandido contextual tabular, en línea y en orden de tiempo. Solo aprende de operaciones **ya cerradas**.
- Elige el peso de {0; 0,5; 1; 1,5} que maximiza media − λ/2 · peso² · varianza de la celda, con encogimiento hacia la pata.
- Contextos:
  - A = pata × vpct;
  - B = A × tendencia `s`;
  - C = B × flujo de GLD de 20 días.

**Aviso honesto:** el resultado de cada operación se ve aunque el peso sea 0, así que en realidad es aprendizaje supervisado en línea.

**Resultados:**
- Con λ en escala absoluta (9 variantes) se vuelve tímido (peso 0 en el 50-95 % de las operaciones): ×0,6-1,1.
- Con λ relativo a la pata (6 variantes):

| Variante | sel ×base | sel ×F1 | p | sel peor día / mes | val ×base | val ×F1 | val peor día / mes |
|---|---|---|---|---|---|---|---|
| A, λ = 1 | 2,45 | 1,56 | 0,06 | **−10,1 % / −12,5 %** | 1,99 | 1,21 | **−11,4 % / −17,3 %** |
| C (con GLD), λ = 1 | 1,71 | 1,08 | 0,19 | −9,9 % / −13,8 % | 2,11 | 1,28 | −11,3 % / −15,2 % |

Lo que hace es reaprender F2 de la línea C: Big One a 0 en vol alta y a 1,5 en vol baja. La ganancia sale de **más lote** en los días buenos, y empeora el peor día y el peor mes en ambos periodos. Más contexto (B, C) no mejora a A en `sel`.

**Veredicto: descartada como idea nueva.** No aporta nada que F1/F2 no tengan ya, y falla la regla del peor día y del peor mes.

Costo de tiempo: ~10 % de la línea, dentro del tope del 15 %.

## Finalistas (`opt_F_final.py`; `val` mirado una vez)

- «×F1» = MAR del candidato ÷ MAR de F1 en el mismo periodo (lo que suma la información nueva).
- «Nulo» = percentil del candidato entre 200 permutaciones de la característica entre operaciones de la pata del periodo.

| Id | Regla | sel ×base | sel ×F1 | p sel | 2023 / 2024 (×ref) | Nulo sel (p95 ×ref) | val ×base | val ×F1 | p val | Nulo val | val peor día / mes | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | F1 + Momentum ×0 si p(`mu` Chronos-2) < 0,33 | 3,17 | 2,01 | 0,11 | 3,48 / **0,98** | 100 % (1,60) | 1,68 | 1,02 | 0,43 | 65 % | −7,8 % / −7,9 % | descartada |
| T2 | F1 + Momentum ×0 si p(`mu` bolt-tiny) < 0,33 | 2,87 | 1,82 | 0,06 | 2,98 / **0,90** | 99 % (1,57) | 1,53 | 0,93 | 0,44 | 53 % | −8,4 % / −7,7 % | descartada |
| T3 | F1 + Momentum ×0 si p(`sig` Chronos-2) < 0,33 | 2,86 | 1,81 | 0,10 | 2,51 / 1,26 | 99,5 % (1,56) | **2,03** | 1,24 | 0,45 | **82 %** | −7,8 % / −10,0 % | vigilancia débil (no le gana al azar en `val`) |
| T4 | base + Momentum ×0 si p(`mu` Chronos-2) < 0,33 | 2,05 | 1,30 | 0,19 | 3,71 / **0,82** | 100 % (1,42) | 1,16 | 0,71 | 0,50 | 74 % | −8,7 % / −9,0 % | descartada |
| D1 | F1 + Momentum ×0 si p(Δ5d breakeven 5 a) ≥ 0,5 | **3,60** | **2,28** | 0,06 | 3,09 / 1,30 | 100 % (1,58) | 1,68 | 1,02 | 0,41 | 65 % | −8,7 % / −7,7 % | descartada (en `val` no suma a F1) |
| D2 | base + Momentum ×0 si p(Δ5d breakeven 5 a) ≥ 0,33 | 2,08 | 1,32 | 0,38 | 4,21 / **0,63** | 100 % (1,26) | 1,21 | 0,74 | 0,36 | 76 % | −8,8 % / −13,4 % | descartada |
| D3 | base + todo ×0 si p(VIX9D/VIX3M) < 0,5 | 1,66 | 1,05 | 0,63 | 2,48 / **0,84** | 97,5 % (1,41) | **0,30** | 0,18 | 0,90 | 30 % | −10,1 % / −10,1 % | descartada |
| D4 | F1 + Momentum ×0 si p(Δ5d inflación 5a5a) ≥ 0,67 | 2,76 | 1,75 | 0,10 | 2,25 / 1,17 | 96 % (1,66) | 1,57 | 0,96 | 0,36 | 51 % | −7,9 % / −14,8 % | descartada |
| RL-A | bandido pata × vpct, λ relativo = 1 | 2,45 | 1,56 | 0,06 | 3,04 / 2,15 (×base) | — | 1,99 | 1,21 | 0,35 | — | **−11,4 % / −17,3 %** | descartada (es F2; empeora las colas) |

Nota: la columna «2023 / 2024» es respecto de la referencia de la regla (F1 para T1-T3, D1 y D4; la base para T4, D2 y D3).

**Cómo se lee:**
- En `sel`, todos los finalistas le ganan al azar (p ≥ 96 %). Es lo esperable tras elegir el mejor de ~1 450.
- En `val`, todos caen al 51-82 % del azar.
- Sobre F1, aportan ×0,71-1,24: ninguno llega al ×1,25.
- T1, T2, T4 y D2 ya fallaban en 2024 dentro de `sel`.
- El único que no se cae del todo, T3 (apagar el Momentum cuando Chronos-2 prevé muy poca volatilidad), es una regla de volatilidad que no supera al azar en `val`.

## Total de variantes

**1 463 filas de la línea F** en `results/opt_registry.jsonl`:

| Bloque | Filas |
|---|---|
| Datos externos (grilla base + F1) | 1 104 |
| Finalistas de datos (`sel` + `val`) | 8 |
| Chronos y nulos triviales (grilla) | 312 |
| Comprobaciones «solo cortos / solo largos» | 10 |
| Finalistas de Chronos (`sel` + `val`) | 8 |
| Bandido | 17 (2 en `val`) |
| Meta-logística | 4 |

En total, 10 miradas a `val`.

⚠ El registro común tiene 1 línea ilegible (escritura simultánea de otra línea). `load_registry()` fallaría en esa línea: hay que saltarla.

## Pendiente para el usuario (no hice registros ni pagos)

| Servicio | Qué daría | Estado |
|---|---|---|
| Finnhub (noticias, calendario económico) | sentimiento por artículo; calendario con consenso (premium) | pide registro con email: **no me registré** |
| Alpha Vantage NEWS_SENTIMENT | sentimiento de noticias (~25 peticiones/día gratis) | pide clave con email: **no me registré** |
| FMP economic calendar | real vs consenso | plan gratis con registro: **no me registré** |
| Trading Economics | calendario con consenso e histórico | de pago |
| Put/call de CBOE | sentimiento de opciones | no encontré histórico gratuito vigente |

**Propuesta, API de Claude** (no usada; necesita tu aprobación): clasificar cada día ~50 titulares de oro y Fed (sacados de GDELT) en «alcista / bajista / riesgo».
- Tamaño: ~1 600 tokens de entrada y ~50 de salida por día; ~830 días de histórico.
- Costo del histórico completo (precios del 27-oct-2026):
  - **Claude Haiku 5.5** (0,10 $ / 0,50 $ por millón de tokens de entrada / salida): ≈ **0,15 $**;
  - **Claude Sonnet 5.5** (2 $ / 10 $): ≈ **3 $**;
  - con la API de lotes (batch), la mitad.
- En vivo: céntimos al mes.
- **No lo recomiendo**: el tono de GDELT, que mide lo mismo, no dio nada. El costo real está en bajar los titulares (GDELT limita mucho), no en el modelo.

## Recomendación

1. **No integrar** modelos fundacionales, datos externos, noticias, meta-modelo ni RL en el e2. Ninguno suma a F1 en 2025, y casi todos los «ganadores» son filtros del Momentum, que es justo donde las líneas B y C ya vieron el mismo espejismo: ~220 operaciones en `sel`, así que apagar un tercio es ruido.
2. Para 2026, el coordinador debe seguir con **U1** (línea B) y **F1** (línea C). Nada de esta línea entra entre los 3 mejores.
3. Si se quiere vigilar algo barato en la demo: registrar `sig` de Chronos-2 (T3) junto al `vpct` de F1, sin operarlo. Cuesta 0,7 s de CPU por día, pero añade torch (~1 GB) al servidor de los bots: **no lo haría** salvo que T3 se confirme con más datos.
4. No repetir: filtros macro o de tasas del Momentum, tono o atención de noticias, flujos de GLD, VIX9D/VIX3M, SKEW, meta-labeling con datos externos, bandidos sobre el peso.

## Scripts y archivos

| Script (`bot_backtesting/fullsim/`) | Qué hace |
|---|---|
| `opt_F_ext.py` | Descarga (FRED, CBOE, SPDR GLD, GDELT) y carga con la hora de publicación; `asof_join` |
| `opt_F_datos.py` | 23 características con percentil pasado; grilla sobre la base y sobre F1; `final()` con nulos y `val`; meta-logística purgada |
| `opt_F_tsfm.py` | Chronos-Bolt tiny/small y Chronos-2 sin entrenar, más media estacional, AR(1) y HAR; calidad; grilla de filtros |
| `opt_F_bandit.py` | Bandido contextual tabular sobre el peso |
| `opt_F_final.py` | Finalistas T1-T4 y D1-D4: bootstrap, años, permutaciones y `val` |

- **Datos descargados** (fuera de git): `bot_backtesting/fullsim/data/ext/{fred,cboe,gld,gdelt}/`.
- **Resultados crudos** (`results/`): `opt_F_feats.pkl`, `opt_F_grid.pkl`, `opt_F_tsfm_fc.pkl`, `opt_F_tsfm_feats.pkl`, `opt_F_tsfm_grid.pkl`, `opt_F_tsfm_final.pkl`, `opt_F_datos_final.pkl`.
- **Instalado en `.venv`:** `torch 2.14.1+cpu`, `chronos-forecasting 2.3.2` y sus dependencias (transformers, accelerate, huggingface_hub, einops…).
