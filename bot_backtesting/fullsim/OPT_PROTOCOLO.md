# Protocolo común — sesión de optimización e2 (27-oct-2026)

Lo leen todos los subagentes antes de empezar. Repositorio: `C:\Users\Administrator\Documents\sentinel_trading`, rama `experimento-2-rediseno`.

## Contexto en 10 líneas

- En esta máquina corren **en vivo** 3 bots e2 (`bot.lite_e2`, magic 100300) en demo, más `news_exporter`. **No toques nada de eso.**
- e2 = tres patas en XAUUSD+ (hora servidor = NY+7):
  - **Big One:** compra 01:01 → 10:00. Peso 1 si la tendencia `s=+2`, si no 0,5; ×0,5 en día de NFP, IPC o FOMC.
  - **Momentum:** 15:00 → 21:00, en la dirección de 01:00→15:00, si |ret| > 0,232 % y `s=±2`.
  - **NFP:** a T+60 sigue el salto durante 24 h.
- **Gestión:** 3 tercios (hora / TP 2×ATR15 / TP 3×ATR15), **candado** (cobertura opuesta que congela la pérdida) a −1×ATR_D y cierre de todo a la hora de salida. Riesgo 8 %: `lote = balance·0,08·peso/(ATR_D·100)`.
- Diseño: `docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md`. Memoria del proyecto: `docs/memory/MEMORY.md`.
- **Objetivo:** subir el **MAR** (CAGR / caída máxima) de la cartera completa al 8 % con costos reales. Subir el lote no cuenta.

## Reglas que no se rompen

1. **Nada de MT5** (ni lectura). Solo los datos ya descargados de `bot_backtesting/fullsim/data/`. No descargues nada del broker.
2. **No edites `bot/`**, ni `scripts/`, ni `.env`, ni `instances/`. No reinicies nada. **No hagas commits** (los hace el coordinador).
3. **Sin stop loss, sin cierre de emergencia, sin freno por caída.**
   - Salidas permitidas: el candado, la salida por hora, y salidas **en ganancia** (TP, trailing que solo cierra con P&L neto > 0 después de costos).
   - Si una idea necesita cerrar en pérdida antes de la hora (por ejemplo, deshacer el candado cerrando la cobertura en rojo), pruébala **aparte**, márcala como «REQUIERE CERRAR EN PÉRDIDA» y no la cuentes como candidata normal.
4. **Prioridad baja:** llama a `low_priority()` al empezar cada script. Corre **un solo proceso pesado a la vez** (no lances procesos en paralelo, no uses `n_jobs>1`, `num_threads=1` en lightgbm). La máquina tiene 4 núcleos y ~2 GB libres: mantén cada proceso por debajo de ~1,2 GB.
5. **Python:** usa `.venv/Scripts/python -m bot_backtesting.fullsim.<script>` desde la raíz del repo (venv de investigación con sklearn, lightgbm, statsmodels, scipy, optuna). Si necesitas otra librería, instálala **solo en `.venv`** (`.venv/Scripts/python -m pip install ...`), nunca en el Python global (lo usan los bots). hmmlearn no compila en 3.14: usa `statsmodels.tsa.regime_switching` o sklearn `GaussianMixture`.
6. **2026 está guardado.** No lo mires, no pongas `E2OPT_FINAL=1`, no grafiques 2026. Lo evalúa el coordinador al final con los 3 mejores.
7. **Repo público:** nada de emails, números de cuenta, UUIDs, valores de `.env` ni datos crudos en los `.md`. Los resultados crudos van a `bot_backtesting/fullsim/results/` (fuera de git).

## Herramienta común: `bot_backtesting/fullsim/opt_base.py`

Léelo entero. Resumen:

- `entries()`: operaciones e2 con `leg, t, t_in, t_out, side, w, state, ev, atrd, atr15, px, mid0, spr_in, spr_out, swap, day, k15`.
- `trade_path(r)`: el camino **intra-vela** de la operación, en $/oz desde el precio de entrada (`fav`, `adv`, `opn`, `cls`, `time`, `dur`).
  - Resolución: M5 (Dukascopy con desfase diario al broker hasta 2025-05-29; M5 del broker después) y M1 del broker en 2026.
  - Dentro de cada vela, el lado en contra va primero (conservador).
- `leg_ladder(P, r, tps, lock_k, fracs)`: la gestión vigente. Úsala de **plantilla** para escribir tu gestor; los gestores devuelven `(pnl $/oz, mae, locked, detalle)`.
- `run_trades(E, manager, **kw)`: aplica un gestor y devuelve las operaciones con `pnl`, `mae`, `locked` y `R`.
- `base_trades()`: la base e2 (cacheada).
- `evaluate(T, per, f=0.08, wcol='w')`: cartera con interés compuesto y lotes reales. Devuelve `cagr, dd, mar, peor_dia, peor_mes, n, sharpe_d`.
- `compare(C, B, per, label, wcol)`: candidato contra base. Incluye:
  - el nulo **«lote mayor»**: la base con el riesgo que da la misma caída (`cagr_lote_mayor`, `f_lote_mayor`);
  - un **bootstrap pareado** por bloques de 10 días: `p` = probabilidad de que no mejore el MAR, más `P(dd>30/40 %)` de cada uno;
  - `pasa` = regla de aceptación.
- `random_entries(E, seed, mode='day'|'time')`: el nulo de momentos al azar.
- `register(line, variant, res, params)`: **anota CADA variante que pruebes** en `results/opt_registry.csv` (una fila por variante, con el resultado de `compare` en `sel`). Es obligatorio: sirve para contar el total de variantes y para Benjamini-Hochberg. Si pruebas 500 variantes, son 500 filas. Para grillas grandes basta con registrar cada punto con `boot=False` y el bootstrap solo en los mejores; pero **todas** cuentan.
- `bh(p)` y `deflated_sharpe(...)`.

**Periodos:** `sel` = 2022-10 → 2024-12 (para elegir), `val` = 2025 (para validar).

**Base e2 al 8 %** (cuenta de 10 000):

| Periodo | MAR | CAGR | Caída | Peor día | Peor mes |
|---|---|---|---|---|---|
| sel | 3,39 | 117 % | 34 % | −9,2 % | −15,7 % |
| val | 3,60 | 122 % | 34 % | −10,1 % | −13,7 % |

## Protocolo de validación

1. **Lluvia de ideas** amplia → ordénalas por «ganancia esperada ÷ costo de probar» → prueba las mejores.
2. **Elige solo con `sel`.** Mira `val` una sola vez por familia de ideas, para los finalistas (máx. ~5 por familia) y **anota eso también**.
3. **Una idea «pasa»** si:
   - MAR ≥ 1,25 × base en `sel` **y** en `val`;
   - no empeora el peor día ni el peor mes;
   - `p` del bootstrap ≤ 0,10 en `sel`;
   - es **estable**: los parámetros vecinos (±1 paso de la grilla) dan ≥ 1,15× y no depende de un solo año (mira 2023 y 2024 por separado dentro de `sel`).
4. **Nulos obligatorios** para los finalistas:
   - **lote mayor** (lo da `compare`);
   - **días al azar**: para tamaño o filtros, permuta los pesos o el filtro entre días (≥200 permutaciones) y reporta el percentil del candidato;
   - **momentos al azar**: para salidas o entradas, aplica la misma regla a `random_entries` y reporta cuánto mejora ahí. Si mejora igual al azar, la ventaja es de la gestión y no de la señal; dilo.
5. **ML:** walk-forward rodante y CV con **purga y embargo** (embargo ≥ 5 días), solo con información disponible **en el momento de entrar**. Comprueba el **retraso real de publicación** de cada dato externo (FRED diario sale con 1 día hábil de retraso o más; el COT sale el viernes con datos del martes; etc.).
6. **Cuenta honesta:** reporta cuántas variantes probaste en total (filas en el registro con tu `line`).

## Entregable de cada línea

1. Un script (o varios) en `bot_backtesting/fullsim/opt_<linea>_<tema>.py`, con docstring en español que diga qué prueba y cómo correrlo.
2. El informe `docs/experimento-2/investigacion/opt-<linea>-<tema>-2026-10-27.md`, en español llano para un vibecoder, con:
   - tablas cortas;
   - por idea: **veredicto** (pasa / vigilancia / descartada), los números (`sel` y `val`: MAR, ratio vs base, CAGR, caída, peor día, peor mes, `p`), el nulo y el archivo de script;
   - el número total de variantes probadas;
   - una recomendación clara.
3. Tu respuesta final al coordinador:
   - un **resumen de 5 líneas**;
   - la tabla de finalistas (con `sel`/`val`);
   - el número de variantes;
   - la ruta del informe y los scripts;
   - y, si hay candidatos que pasan, **la función/gestor exacto** (módulo y nombre) para que el coordinador pueda reproducirlos en 2026.
