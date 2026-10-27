# Línea C: regímenes y cambio de estrategia según el régimen (27-oct-2026)

Sesión de optimización del e2 (oro, XAUUSD+). Objetivo: subir el MAR (CAGR ÷ caída máxima) de la cartera e2 al 8 % usando el régimen del mercado. El régimen se calcula **solo con datos hasta el cierre del día anterior** (nada mira adelante).

**Reglas del protocolo** (`bot_backtesting/fullsim/OPT_PROTOCOLO.md`): sin stop loss, costos reales, elegir con `sel` (2022-10 → 2024-12), mirar `val` (2025) una sola vez con los finalistas, y 2026 guardado.

## Resumen

- **Lo único que se sostiene es apagar la Big One los días de volatilidad alta (F1).** Volatilidad alta quiere decir que el ATR diario relativo al precio está por encima de su mediana de los últimos 12 meses.
  - Funciona en `sel` (×1,58), en `val` (×1,64), en 2023 y 2024 por separado y con los umbrales vecinos.
  - Le gana al nulo de días al azar (percentil 99,7).
  - **No pasa del todo** por dos criterios: `p` del bootstrap = 0,17 (se pide ≤ 0,10) y un peor día 0,3 pp peor en `sel`. Veredicto: **vigilancia fuerte**.
- Darle además ×1,5 a la Big One en los días de volatilidad baja (F2) mejora más el MAR (sel ×2,14 con p = 0,07; val ×1,73). Pero empeora el peor día y el peor mes, porque es más lote: **vigilancia**.
- El Momentum por eficiencia de Kaufman (F3) brilla en `sel` y **falla en `val`** (×0,99). Descartado.
- Las estrategias nuevas para los regímenes «malos» no pasan: reversión intradía en rango, Momentum dado vuelta, Big One vendida, venta EE. UU. y compra refugio. Son inestables entre años y entre vecinos.
- HMM y clustering no añaden nada sobre la regla simple de volatilidad.

## 1. Cómo se detecta el régimen (`opt_C_regimen.py`, `opt_C_politica.py`)

Todas las características se miden por día de servidor, con datos hasta el día anterior. La historia diaria del oro sale del M15 de Dukascopy (2021-01 → 2022-08) y del M15 del broker después.

| Familia | Característica | Detalle |
|---|---|---|
| Reglas: tendencia o rango | `er10`, `er20`, `er40` (eficiencia de Kaufman), `adx` (ADX 14 diario), `slope20` (retorno de 20 días ÷ volatilidad de 20 días) | |
| Reglas: volatilidad | `vpct` = percentil, en 252 días, de ATR_D ÷ precio (el mismo ATR_D del e2); `rvr` = volatilidad de 5 días ÷ volatilidad de 60 días | |
| Reglas: riesgo | VIX, `vix_rel` (VIX ÷ su media de 60 días − 1), USDX a 20 días y SP500 a 20 días | Todos del broker, cierre del día anterior |
| HMM | `MarkovRegression` de 2 y 3 estados sobre el retorno diario; `MarkovAutoregression(1)` de 2 estados; `hmmvol` = 2 estados sobre log(rango ÷ precio) | Reajuste mensual con ventana expandida. El mes siguiente se filtra con los parámetros fijos y se usan **probabilidades filtradas**, no suavizadas |
| Clustering | GaussianMixture de 2, 3 y 4 grupos y KMeans de 3 sobre (`vpct`, `er20`, `slope20`, `rvr`) | Reajuste mensual solo con el pasado. Etiquetas ordenadas por volatilidad |

Dos notas sobre los HMM:
- El HMM de 2 estados sobre retornos salió **degenerado**: en `sel` el estado «agitado» tiene probabilidad ≥ 0,5 casi todos los días. Lo mismo pasa con `hmmvol` (casi siempre 0).
- El HMM-AR sí reparte los días (mediana 0,49).

## 2. R de cada pata por régimen en `sel` (tabla completa en `results/opt_C_tabla.txt`)

R = P&L ÷ ATR_D por operación. Selección de los cortes más informativos:

| Pata | Régimen | n | R medio | desvío | R 2023 | R 2024 |
|---|---|---|---|---|---|---|
| Big One | `vpct` < 0,5 (vol baja) | 285 | **+0,044** | 0,19 | +0,031 | +0,052 |
| Big One | `vpct` ≥ 0,5 (vol alta) | 294 | **−0,001** | 0,22 | −0,001 | +0,001 |
| Big One | `s` = −2 | 63 | +0,050 | 0,17 | +0,034 | +0,163 |
| Big One | `s` = +2 | 333 | +0,016 | 0,22 | +0,010 | +0,018 |
| Momentum | `er10` ≥ 0,325 (tendencia) | 106 | +0,095 | 0,27 | +0,073 | +0,122 |
| Momentum | `er10` < 0,325 (rango) | 118 | +0,021 | 0,37 | −0,031 | +0,032 |
| Momentum | `slope20` ≥ 0,25 | 161 | +0,072 | 0,31 | +0,054 | +0,082 |
| Momentum | `slope20` < 0,25 | 63 | +0,014 | 0,37 | −0,025 | +0,046 |
| Momentum | `vpct` < 0,5 / ≥ 0,5 | 108 / 116 | +0,071 / +0,042 | | | |
| NFP | (n = 26: demasiado pocas para cortar) | | | | | |

**En `val`** (la única mirada, ya con F1 elegido):
- Big One: vol baja +0,045 (n = 115) frente a vol alta +0,013 (n = 143). **Se repite.**
- Momentum: vol baja +0,008 frente a vol alta +0,032. Esto no se usa.

Por qué tiene sentido en la Big One: la deriva de la reapertura es de tamaño casi fijo en $/oz. Con ATR_D alto, esa deriva se diluye en R y el ruido crece; el tamaño se calcula por ATR_D. Esto es una interpretación, no algo probado.

## 3. Acciones probadas y veredicto

### 3a. Filtros y pesos por régimen (grilla de `opt_C_regimen.py`: 1 413 variantes; política de dos lados de `opt_C_politica.py`: 900)

La grilla cruza 13 reglas × umbrales × lado × pata (Big One, Momentum, ambas) × multiplicador (0; 0,5; 1,5), más 15 grupos de clustering.

Ojo: apagar operaciones siempre baja la caída, y eso solo no cuenta. Por eso se mira **la CAGR del candidato contra la base con lote menor a la misma caída** (columna «CAGR lote mayor») y **el nulo de días al azar**.

### 3b. Estrategias para los regímenes donde el e2 no rinde (`opt_C_estrategias.py`: 2 796 variantes)

Todas se simulan con el camino intra-vela de `opt_base`:
- gestión vigente (tercios hora / TP 2 / TP 3 ATR15, candado −1 ATR_D, cierre a la hora);
- costos reales;
- **sin stop**;
- niveles calculados solo con opens de velas ya abiertas (no hay niveles de la misma vela, el artefacto que señaló la línea A).

Las estrategias:
- **S1, reversión en rango:** a las 10, 12, 16 o 18 h, si el precio se alejó más de k × ATR_D del open de las 01:00, se opera en contra durante 3 o 5 h.
- **S2:** el Momentum dado vuelta (o el Momentum en `s` = 0) en rango o en bajista.
- **S3:** ventanas alternativas del Momentum, y Big One corta, en vol alta o en rango.
- **S4:** Big One vendida / venta 15 → 21 en bajista.
- **S5:** compra 15 → 21 en *risk-off*.

### Finalistas (`opt_C_final.py`; `val` mirado una sola vez)

Base: MAR sel 3,39 (CAGR 117 %, caída 34 %, peor día −9,2 %, peor mes −15,7 %); MAR val 3,60 (122 %, 34 %, −10,1 %, −13,7 %).

| Finalista | Regla | sel MAR (×base) | val MAR (×base) | CAGR sel / val | Caída sel / val | Peor día sel / val | Peor mes sel / val | p sel | CAGR lote mayor sel / val | 2023 / 2024 | Vecinos mín | Nulo días al azar | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **F1** | Big One ×0 si `vpct` ≥ 0,5 | 5,34 (**×1,58**) | 5,91 (**×1,64**) | 134 % / 107 % | 25 % / 18 % | −9,5 % / −8,3 % | −12,6 % / −12,1 % | 0,17 | 70 % / 58 % | ×1,54 / ×1,43 | ×1,21 | pct 99,7 (p95 del azar ×1,29) | **Vigilancia fuerte** (falla p ≤ 0,10 y el peor día en sel por 0,3 pp) |
| F2 | Big One ×1,5 si `vpct` < 0,5, ×0 si no | 7,26 (×2,14) | 6,22 (×1,73) | 175 % / 143 % | 24 % / 23 % | −10,2 % / −11,1 % | −12,4 % / −17,4 % | 0,07 | 67 % / 70 % | ×2,10 / ×1,99 | ×1,39 | pct 99,7 (p95 ×1,49) | Vigilancia (más lote en días buenos: empeora el peor día y el peor mes) |
| F3 | Momentum ×1,5 si `er10` ≥ 0,35, ×0 si no | 5,47 (×1,61) | 3,57 (×0,99) | 135 % / 128 % | 25 % / 36 % | −9,2 % / −12,1 % | −13,7 % / −10,6 % | 0,27 | 70 % / 142 % | ×2,38 / ×0,97 | ×1,35 | pct 96,7 | **Descartada** (falla en val y en 2024) |
| F4 | F2 + F3 | 9,44 (×2,79) | 5,56 (×1,54) | 198 % / 148 % | 21 % / 27 % | −9,7 % / −12,3 % | −11,4 % / −15,1 % | 0,07 | 57 % / 86 % | ×3,80 / ×2,74 | ×2,19 | pct 100 | Descartada como tal (lo que sirve es F2; F3 resta en val) |
| F5 | Reversión a las 18:00 en rango (`er20` < 0,2, desvío > 0,5 ATR_D, salida 21:00) añadida a la base | 5,00 (×1,47) | 4,75 (×1,32) | 126 % / 133 % | 25 % / 28 % | −9,2 % / −9,5 % | **−19,5 %** / −11,9 % | 0,38 | 70 % / 90 % | ×2,00 / **×0,65** | **×0,89** | momentos al azar: pct 97,5 (p95 ×1,18) | **Descartada** (inestable entre años y vecinos; peor mes −19,5 %) |

Notas sobre los nulos:
- **Nulo de días al azar:** se permutan las características de régimen entre los días de `sel` (300 veces, misma fracción de días buenos y malos) y se mide el MAR.
- **Para F5, nulo de momentos al azar:** las mismas operaciones, a la misma hora, en días hábiles al azar (`random_entries`, 40 semillas), con el mismo filtro de rango.

### Lo demás, en una línea cada uno (todo en `sel`; ninguno llegó a finalista)

- **Momentum apagado si `slope20` < −0,5:** ×1,50, pero sus vecinos dan ×0,94. Descartado.
- **El Momentum dado vuelta en bajista (S2):** ×1,59, pero casi todo viene de apagar el Momentum (ese filtro solo ya da ×1,50); el *fade* suma poco. Descartado.
- **Filtros por VIX, USDX, SP500, HMM y clustering:** los mejores dan ×1,2–1,45, siempre con apagados masivos y vecinos inestables. Descartados.
  - Esto coincide con el aviso de la línea B: los filtros macro del Momentum daban ×2 en `sel` y fallaban en `val`.
- **Big One vendida o venta EE. UU. en bajista (S4):** ×1,23 como máximo. Descartado.
  - Ya estaba descartado en el diseño («entradas cortas empeoran»).
- **Compra refugio con VIX alto (S5):** ×1,23 y empeora el peor día (−12 %). Descartado.
- **Hallazgo lateral, fuera del tema régimen:** la Big One con salida a las **08:00** en vez de 10:00, **todos los días**, da ×1,46 en `sel` (CAGR 121 %, caída 24 %).
  - La réplica de control 01:00 → 10:00 da ×1,00, así que el simulador es consistente.
  - No es de régimen y no lo miré en `val`. Le corresponde a la línea A (salidas): lo dejo anotado para el coordinador.

## 4. Robustez de F1

- **Años:** ×1,54 en 2023 y ×1,43 en 2024. **Val** 2025: ×1,64.
- **Vecinos del umbral** (×base en `sel`):

| Umbral `vpct` | 0,3 | 0,4 | **0,5** | 0,6 | 0,7 | 0,8 |
|---|---|---|---|---|---|---|
| ×base | 1,15 | 1,62 | **1,58** | 1,21 | 0,94 | 1,05 |

  Con ±1 paso (0,4 y 0,6) se cumple ≥ 1,15. La meseta buena va de 0,4 a 0,5.
- **Bajar a la mitad en vez de apagar** (×0,5) da solo ×1,24. Lo que ayuda es quitar la Big One de esos días, no reducirla.
- **Contra el «lote mayor»:** la base con el riesgo que da la misma caída (25 %) rinde 70 % de CAGR. F1 rinde 134 %, casi el doble, y **en `val` también** (107 % contra 58 %).
  - La ganancia no es solo menos exposición: en vol alta la Big One rinde R ≈ 0 y solo añade varianza.
- **Lo que le falta:**
  - el bootstrap pareado da p = 0,17: con ~290 operaciones apagadas en `sel` el ruido es grande;
  - el peor día de `sel` sale −9,5 % contra −9,2 % de la base, peor por encima de la tolerancia de 0,1 pp;
  - en `val` el peor día mejora (−8,3 % contra −10,1 %) y el peor mes también.

## 5. Total de variantes

**7 908 filas de la línea C** en `results/opt_registry.jsonl`:

| Bloque | Filas |
|---|---|
| Grilla de reglas y clusters | 1 413 |
| Re-evaluación con bootstrap del top-25 | 25 |
| Política de dos lados | 900 |
| Estrategias, corrida 1 | 2 748 |
| Estrategias, corrida 2 | 2 796 |
| Finalistas, vecinos y `val` | 26 |

Detalles de la cuenta:
- La **corrida 1 de estrategias** omitía el retraso de la 01:01 en las variantes de Big One alternativa. Se corrigió y se repitió (corrida 2). Las dos cuentan en el registro.
- Las 2 338 filas escritas antes del cambio de CSV a JSONL **se migraron** al `.jsonl`, con la nota «migrado desde opt_registry.csv». En el CSV viejo están duplicadas.

## 6. Recomendación

1. **No cambiar el bot todavía.** F1 es el mejor resultado de régimen de la sesión, pero no cumple la regla formal (p = 0,17 y el peor día de `sel`).
2. **Candidato para 2026** (coordinador): F1, «Big One apagada si `vpct` ≥ 0,5». Si el coordinador quiere un segundo, F2 con ×1,25 en lugar de ×1,5 en los días buenos (sel ×1,84) es más conservador. Hay que verlo junto con la línea B (tamaño).
3. **Mientras tanto, en la demo:** registrar `vpct` en cada Big One (sin operarlo) para acumular evidencia.
4. **Descartado, no repetirlo:**
   - regímenes del Momentum (Kaufman, pendiente, VIX, USDX, HMM, clusters);
   - estrategias de reversión en rango;
   - cortos en bajista;
   - compra refugio.

### Función exacta de F1 (reproducible en 2026, parámetros fijados con datos ≤ 2025)

```
ATR_D(d)   = media de (H − L) de los 14 días de servidor anteriores a d      (el mismo ATR_D del e2)
x(d)       = ATR_D(d) / Cierre(d − 1)          (todo conocido antes de la 01:00 del día d)
vpct(d)    = rango percentil de x(d) entre x(d−251) … x(d) (252 días de trading, incluido él; mínimo 120)
              [en el código: a = (H−L).rolling(14).mean()/C ; vpct = a.rolling(252, min_periods=120).rank(pct=True).shift(1)]
Big One del día d: si vpct(d) >= 0,5 -> no se abre (peso 0); si no -> peso vigente (1 / 0,5, ×0,5 en noticia)
Días sin vpct: peso vigente.
```

- **Código:**
  - `bot_backtesting.fullsim.opt_C_final.regime_weights(T, POL["F1 bo_vpct_off"])`;
  - `T = attach(base_trades(), add_hmmvol(build_features()))` (de `opt_C_regimen` y `opt_C_politica`).
- **F2:** `POL["F2 bo_vpct_pol"]`.

## Scripts y archivos

| Script | Qué hace |
|---|---|
| `bot_backtesting/fullsim/opt_C_regimen.py` | Características, HMM y clusters; tabla de R por régimen; grilla de filtros y pesos |
| `bot_backtesting/fullsim/opt_C_politica.py` | Política de dos lados; `hmmvol`; CAGR del lote mayor por interpolación |
| `bot_backtesting/fullsim/opt_C_estrategias.py` | Estrategias S1–S5 por régimen |
| `bot_backtesting/fullsim/opt_C_final.py` | Finalistas: bootstrap, años, vecinos, `val`, nulos |

Resultados crudos (fuera de git) en `bot_backtesting/fullsim/results/`: `opt_C_feats.pkl`, `opt_C_tabla.txt`, `opt_C_grid.pkl`, `opt_C_top.pkl`, `opt_C_pol.pkl`, `opt_C_strat.pkl`, `opt_C_strat_rows.pkl` y `opt_C_final.pkl`.
