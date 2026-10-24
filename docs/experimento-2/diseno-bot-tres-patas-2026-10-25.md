# Diseño: bot del oro «tres patas» (Experimento 2) — 25-oct-2026

> **Estado:** **APROBADO por el usuario el 25-oct-2026** («Sí a todo: 8 %, capitales confirmados, quitemos las demos actuales»).
> Decisiones: D1 sí (cerrar el candado a la hora de salida); D2 8 %; D3 freno desactivado; D4 demos actuales
> desactivadas (los .env se renombraron con «_» y se detuvieron sus bots; las posiciones abiertas quedaron como estaban);
> D5 cuentas demo nuevas de 3 000 / 10 000 / 25 000.
> Evidencia: `cuentas-scalping-2026-10-24.md`, `scalping-capital-multiactivo-2026-10-25.md`,
> `correccion-artefacto-reapertura-2026-10-24.md` y la memoria [[decision-bigone-combo]].

## 1. Intención

**Objetivo:** un bot de XAUUSD+ «agresivo pero estable».

**Cambio de enfoque:** se reemplaza el ciclo Op1–Op4 del M15 y los regímenes del M5, que no tienen ventaja tras costos. En su lugar entran **tres operaciones de calendario**, con ventaja medida en precios reales del broker y positivas los 5 años de 2022 a 2026.

**Objetivos:**
- Operar solo donde hay evidencia.
- Tamaño por riesgo fijo.
- Pérdida máxima por operación acotada por un candado.

**No objetivos:**
- Predecir la dirección fuera de esas ventanas.
- Scalping: probado a fondo y descartado.
- Otros símbolos: sin evidencia suficiente.

**Antiobjetivos** (lo que lo haría un fracaso aunque «funcione»):
- Posiciones desnudas sin candado.
- Ciclos que se arrastran días.
- Lotes que se escapan del riesgo planeado.
- Que la demo no se pueda comparar contra la simulación.

## 2. Las tres patas (reglas exactas)

Todas son en hora del servidor (NY + 7 h, igual que las velas del broker).

**Notación:**
- `s`: tendencia diaria = signo(C − C21) + signo(C − C63) con cierres D1 del broker hasta el día anterior.
- `ATR_D`: media de (máximo − mínimo) diario de los 14 días anteriores.
- `ATR15`: ATR(14) de la vela M15 anterior cerrada.

| Pata | Entrada | Lado | Peso de riesgo | Salida por hora |
|---|---|---|---|---|
| **Big One** | 01:00:00, primer tick tras la reapertura (lunes a viernes) | Compra | 1,0 si `s = +2`; 0,5 si `s` = 0 o −2; ×0,5 adicional en día de NFP, IPC o FOMC | 10:00 |
| **Momentum EE. UU.** | 15:00:00, si \|retorno 01:00 → 15:00\| > 0,5 × 0,464 % = **0,232 %** y `s` = +2 o −2 | Dirección del retorno 01:00 → 15:00 | 1,0 | 21:00 |
| **NFP** | T + 60 min (T = hora del NFP en el calendario), si el movimiento entre el open de T−15 y el precio de T+60 ≠ 0 | Dirección de ese movimiento | 1,0 | 24 h de mercado después de la entrada (si es viernes, termina el lunes) |

**Descartado y fuera del diseño:**
- FOMC e IPC como satélites;
- entradas en retrocesos (operaciones cortas): empeoran, R 0,021 frente a 0,040;
- subasta LBMA: en observación;
- otros símbolos;
- filtros macro y SMC.

## 3. Gestión de cada operación

**Escalera:** cada entrada abre **3 posiciones iguales** (tercios):

| Tercio | Salida |
|---|---|
| 1 | Por hora |
| 2 | Objetivo +2 × ATR15 desde el precio de entrada; si no llega, por hora |
| 3 | Objetivo +3 × ATR15; si no llega, por hora |

**Candado** (Hedge Lock, sin stop): cuando el precio llega a **−1 × ATR_D** en contra de la entrada, se abre **una orden opuesta** por el volumen de los tercios que sigan abiertos. Desde ahí la pérdida queda congelada.

**Cierre a la hora de salida:** se cierran juntos los tercios abiertos y su candado. ⚠️ **Decisión que necesita aprobación explícita (D1):** esto realiza la pérdida congelada a la hora de salida aunque el neto sea negativo.
- La simulación lo supone así.
- La regla vigente del M15 («la cobertura solo se cierra con neto positivo», [[bot-design-constraints]]) **no aplica** a este bot.
- Si se mantuviera, el par quedaría abierto días, pagando swap neto (≈ −45 $/lote/noche) y bloqueando el riesgo.

**Sin** Healer, Profit Banking, recovery, Op2–Op4 ni cierre de emergencia.

## 4. Tamaño

**Riesgo por operación:**
- `riesgo_pct = 8 %` por defecto. Alternativa conservadora: 5 %.
- El freno por caída sigue siendo opcional (D3, ver §11).

**Fórmula:** `lote_total = balance × riesgo_pct × peso / (ATR_D × 100)`. Cada tercio = `floor(lote_total / 3, 0,01)`, con mínimo 0,01.
- Se usa el **balance** (cerrado) al momento de entrar.
- Las patas pueden solaparse (por ejemplo, NFP con Momentum).

**Verificaciones antes de abrir:**
- el margen libre alcanza (con 1:500 sobra);
- `lote_total ≤ volume_max` (100). Si se supera, se reparte en varias órdenes.
- Se registra el **riesgo efectivo** (lote real × ATR_D × 100 / balance) para auditar el redondeo.

## 5. Arquitectura

| Pieza | Qué hace |
|---|---|
| `bot/sessions.py` | Funciones puras y testeables: `trend_state`, `atr_d`, `atr15`, `signal_bigone`, `signal_momentum`, `signal_nfp`, `size_ladder` y `lock_price`. Sin MT5. |
| `bot/strategy_e2.py` | Clase `SessionEngine` con la misma interfaz que `SentinelEngine` y `M5Engine` (para `main.run(engine_cls=...)`). Hace el ciclo por tick: programar las entradas, vigilar objetivos y candado, y cerrar a la hora de salida. |
| Calendario | Reutiliza el `NewsGuard` existente (`bot/news.py`) y el archivo que genera `scripts/news_exporter.py` para la hora del NFP y para marcar días de NFP, IPC y FOMC (el ×0,5 de la Big One). |
| Identidad | `BOT_ID = e2`, magic **100300** (fijo en código, como los demás). Comentarios MT5: `E2 BigOne T1/T2/T3`, `E2 MomUS T1..`, `E2 NFP T1..`, `E2 Lock`. |
| Configuración | Tabla `bot_config` por instancia: `riesgo_pct`, patas activas, multiplicadores (lock 1,0 ATR_D; TP 2 y 3 ATR15), umbral de momentum 0,232 % y el peso en días no alcistas. Los valores por defecto son exactamente los de este documento. |
| Arranque | `run_instance.ps1 -BotId e2` y `start_all.ps1`: solo en las cuentas nuevas. En ellas no se arrancan los motores M15 ni M5. |
| Registro | Mismo logger/CSV/Supabase. Por operación: pata, tercio, precio esperado y real, deslizamiento, spread al entrar, ATR_D, ATR15, `s`, riesgo efectivo y si saltó el candado. |
| Persistencia | Estado mínimo en disco (`instances/e2_state_<id>.json`): tickets de cada pata, hora de salida y candado. Así un reinicio retoma las salidas pendientes sin duplicar entradas. |

**Robustez:**
- Si a la hora de entrada no hay tick en los primeros 60 s, se omite esa pata ese día y queda registrado.
- Si falla la orden del candado, se reintenta cada tick. La entrada queda marcada «desnuda», con alerta.
- Nunca se reabre una pata que ya entró ese día.

## 6. Qué no cambia

- Las 3 cuentas demo actuales y sus bots M15/M5 no se modifican.
- El colector de ticks semanal (`SentinelTickCollector`) sigue igual.
- El reporte diario se amplía para leer el magic 100300. Es un cambio menor, en la misma implementación.

## 7. Pruebas antes de la demo

1. **Pruebas unitarias de `sessions.py`**, contra valores calculados con los scripts del simulador (`broker_rule`, `broker_accounts`) en 10 días conocidos:
   - `s`, `ATR_D` y señales;
   - lotes y redondeo por tercio;
   - precio del candado y de los objetivos.
2. **Reproducción:** un arnés que alimente `SessionEngine` con las velas M15 del broker de 2025-11 → 2026-10. Debe dar las mismas operaciones que el simulador (entradas, lados, salidas, candados), con diferencias de precio menores al 1 %.
3. **Prueba en seco en una cuenta demo:** un día con lote mínimo, para validar la apertura, el candado y el cierre por hora.

## 8. Plan de demo y criterios

**Cuentas nuevas** (RAW, 1:500): **3 000, 10 000 y 25 000**, las tres con la misma configuración (8 %, escalera). Así se ve solo el efecto del capital.

**Duración:** mínimo **10 semanas** (≈ 300 operaciones entre las tres patas).

**Se miden semanalmente** (con el colector de ticks y el log):

| Medida | Umbral |
|---|---|
| Spread real a la entrada | ≤ 0,20 $/oz a las 01:00 |
| Deslizamiento | ≤ 0,10 $/oz de media |
| Tasa de candados por pata | Dentro de ±50 % de la simulación |
| R medio por pata | Dentro del intervalo del 80 % de la simulación para ese número de operaciones |
| Riesgo efectivo (sobre todo en la de 3 000) | Registrado en cada operación, para auditar el redondeo |

**Tras la demo**, si se cumplen los criterios, se propone pasar a real con el capital que el usuario decida. Si una pata falla, se apaga esa pata (configuración), no el bot.

## 9. Proyección de las cuentas demo

`projection.py`: escalera, lotes reales, precios del broker.

| Cuenta | Riesgo | Camino real 2022-10 → 2026-10 | Últimos 12 meses | Próximos 12 meses: pesimista (p10) / típico (p50) / optimista (p90) | P(perder en el año) | P(duplicar en el año) |
|---|---|---|---|---|---|---|
| 3 000 | 8 % | ×50 (~8,3 %/mes) | ×2,06 | 4 984 / 7 754 / 12 003 | < 1 % | 77 % |
| 10 000 | 8 % | ×57 (~8,6 %/mes) | ×2,08 | 16 833 / 26 673 / 42 086 | < 1 % | 79 % |
| 25 000 | 8 % | ×60 (~8,7 %/mes) | ×2,08 | 42 509 / 67 429 / 106 888 | < 1 % | 80 % |
| 3 000 | 5 % | ×10 (~4,8 %/mes) | ×1,50 | 4 098 / 5 266 / 6 764 | < 1 % | 26 % |
| 10 000 | 5 % | ×13 (~5,4 %/mes) | ×1,58 | 14 072 / 18 640 / 24 640 | < 1 % | 38 % |
| 25 000 | 5 % | ×14 (~5,5 %/mes) | ×1,61 | 35 347 / 47 241 / 62 789 | < 1 % | 40 % |

**Caídas esperadas:**
- Al 8 %: hasta **~30 %**, medida operación a operación (las de cierre de mes son menores, ~17 %).
- Al 5 %: hasta **~19 %**.
- Peor mes: −12 % al 8 % y −7 % al 5 %. Hubo 9–10 meses negativos de 49.

**Cautelas:**
- 2023–2026 fue un mercado alcista para el oro, y la Big One depende en parte de eso.
- La proyección remuestrea meses reales y no inventa regímenes nuevos.
- Un mercado bajista y lateral prolongado rendiría menos. La Big One baja a medio riesgo y el Momentum opera también con tendencia bajista, pero no está probado en un bajista largo.

## 10. Lo que queda para el implementador

- Cómo programar las entradas dentro del bucle existente (temporizador o comprobación por tick).
- La forma exacta del archivo de estado.
- Los mensajes del log.
- La reutilización de `broker.market_order` y `close_position`.

## 11. Decisiones que debe tomar el usuario

| # | Decisión | Opciones |
|---|---|---|
| **D1** | Cerrar candado y tercios juntos a la hora de salida, realizando la pérdida congelada | **Sí, recomendado: es lo que se simuló** / no |
| **D2** | Riesgo por operación | **8 %** (caída ~30 %) / 5 % (caída ~19 %) |
| **D3** | Freno opcional por caída: el riesgo baja en proporción a la caída, sin cerrar nada | Activado / **desactivado (no simulado con escalera)** |
| **D4** | Qué hacer con las 3 demo actuales y sus bots M15/M5 | Dejarlos como están / detenerlos (requiere tu permiso explícito) |
| **D5** | Capitales de las demo nuevas | **3 000 / 10 000 / 25 000** u otros |

## 12. Implementación

Estado: **implementado, pendiente de prueba en demo.**

- Plan: [`docs/superpowers/plans/2026-10-25-bot-tres-patas-e2.md`](../superpowers/plans/2026-10-25-bot-tres-patas-e2.md).
- Motor: `bot/strategy_e2.py` (`SessionEngine`), reglas puras en `bot/sessions.py`, estado en `bot/e2_state.py`, entrada `bot/main_e2.py`.
- Pruebas: `tests/test_e2_*.py`, `tests/test_daily_report_e2.py`.
- Reporte diario: `scripts/daily_report.py` (sección e2 por pata).
- Memoria: `docs/memory/e2-motor-tres-patas.md`.
