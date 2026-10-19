# Simulador de ciclo completo (`bot_backtesting/fullsim`)

Usa el **motor real** del bot (`bot/strategy.py`, con sus `DEFAULTS`) sobre velas M15, con:
- swap diario (triple el día del rollover), con los valores de `symbol.json`, sacados de deals reales;
- los deals etiquetados por magic y con el comentario de la orden (el curador filtra por comentario).

No toca MT5 ni Supabase. Sirve para medir variantes **antes** de proponerlas.

Se corre desde la raíz del repo con `python -m bot_backtesting.fullsim.<script>`.

## Datos (`data/`, no se versiona)

| Archivo | Qué es | Cómo se genera |
|---|---|---|
| `frames.pkl` | Velas del broker M5/M15/H4 (2026-01 → 2026-10) | `fetch_broker.py <login>`, **solo con el mercado cerrado** |
| `frames_duka.pkl` | Oro M5/M15/H4 de Dukascopy (2021-01 → 2026-01), en hora de servidor | `fetch_dukascopy.py` (sin MT5) |
| `sig_broker.pkl`, `sig_duka.pkl` | Señales de Op1 del motor y su desenlace (WIN o HEDGE) | `signals.py` |

> **Nunca** descargues historial profundo desde MT5 con el mercado abierto: cuelga los terminales en vivo (`docs/memory/mt5-history-download-blocks-bots.md`).

## Scripts

- **`harness.py`:** piezas comunes: `MultiBroker`, `View` (cada motor ve solo su magic), `Eng`, `frozen()`, `load_frames()`, `load_symbol()`.
- **`lab.py`:** variantes sobre el ciclo completo:
  - `actual`: el bot tal cual. Con `--set clave=valor` cambia cualquier parámetro de `DEFAULTS`.
  - `suave`, `completa` y `dir`: Op4 con criterio de mercado y Op5 direccional. **Descartadas el 19-oct.**
  - Hay dos pruebas:
    - el periodo completo;
    - `--ms`: 15 ventanas de 30 días, sin posiciones al inicio. Es la prueba más informativa.
  - Ejemplos:
    ```
    python -m bot_backtesting.fullsim.lab actual 10000
    python -m bot_backtesting.fullsim.lab actual 10000 --ms --set healer_pair_order=recovery_first
    python -m bot_backtesting.fullsim.lab completa 10000 --sig dc20 --ms
    ```
- **`signals.py`:** cada vela en que el motor abriría una Op1 y si esa Op1 sola habría cerrado en verde o llegado a la cobertura:
  ```
  python -m bot_backtesting.fullsim.signals frames_duka.pkl 2021-01-15 2026-01-09 sig_duka.pkl
  ```
- **`meta_label.py`:** filtro de machine learning (LightGBM, walk-forward semestral) que predice qué Op1 acabará en cobertura. Necesita `lightgbm`; en un venv aparte, porque los bots no lo usan.
- **`fetch_broker.py`** y **`fetch_dukascopy.py`:** descargas de datos (ver la tabla de arriba).

## Resultados de referencia

| Archivo | Qué midió |
|---|---|
| `docs/experimento-2/analisis-op4-criterio-propio-2026-10-19.md` | Op4 con criterio de mercado, Op5 direccional, freno de re-entradas y orden de los recortes |
| `docs/experimento-2/analisis-filtro-ml-op1-2026-10-20.md` | Filtro ML de la Op1: AUC 0,508, sin capacidad de predicción |
| `docs/experimento-2/analisis-ciclo-paralelo-2026-10-19.md` y `analisis-limite-op4-y-entrada-op1-2026-10-19.md` | Ciclo paralelo, cupo de la Op4, entrada y salida de la Op1 |

Los análisis del 19-oct usaban una versión anterior en el scratchpad de la sesión: imitaba el recorte por parejas y el orden. Desde el 20-oct el bot los trae, así que `lab.py actual` ya mide el bot de hoy.

## Límites

- Velas M15: el trailing y las coberturas se evalúan al cierre de cada vela.
- Sin noticias, sin M5 y con un solo camino de precios.
- Dukascopy no es el feed del broker y su spread es una constante.
- Las mejoras medidas son orientativas, no garantías.
- Las corridas largas cargan la CPU: bájales la prioridad (Idle) para no frenar a los bots en vivo.
