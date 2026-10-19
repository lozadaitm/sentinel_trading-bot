---
name: op4-trend
description: Decisión firme (16-oct-2026): la Op4 deja de copiar la recovery (martingala) y abre CONTRA la pata que pierde, a favor del movimiento; sus ganancias alimentan al Healer; rescue_mode='copy' revierte
metadata:
  type: project
---

**Problema:**
- La Op4 de copia (martingala) promediaba contra el movimiento.
- El tope de supervivencia la bloqueaba justo en los movimientos grandes. El 14-oct, el ciclo quedó días bloqueado con la recovery a −82 $/oz.

**Regla actual (`bot/strategy.py`: `_check_rescue_trend`, `_op3_trail_params`):**
- **Modo:** `rescue_mode = 'trend'` (DEFAULT).
- **Cuándo abre:** se evalúa una vez por vela M15 cerrada, en ESTADO 3+.
  - Hay una pata RECOVERY/RESCUE, fuera del par congelado y de las LOCK, a `rescue_trend_k_atr` (2,0) × ATR M15 o más en contra.
  - En ese caso abre **contra** ella, con comentario `Sentinel Op 4 (T)`.
- **Tamaño:** `min(volumen de la pata, |neto del ciclo|)`. Reduce el neto, así que el tope de supervivencia la deja pasar.
- **Límites:**
  - una abierta a la vez;
  - cupo de `rescue_trend_max_legs` (6) por ciclo, contado con `rescue_opened`.
- **Puertas:**
  - se mantienen noticia, freno de volatilidad, spread, close-only y candado `LIBRE`;
  - no se aplican la hora de riesgo ni el gate H4 (no promedia).
- **Salida:** el trailing de la Op3 sobre la última pata, con parámetros propios 1,0/0,5 ATR y sin turbo. Sin stop.
- **Curador:** sin cambios.
  - Mientras la Op4 (T) está viva, la recovery no se amputa: su cierre aumentaría la exposición.
  - Cuando la Op4 (T) cierra con ganancia, el siguiente tick amputa la recovery con el 90 %.
  - La siguiente vela abre otra Op4 (T) con el volumen restante.
- **Log:** `RESCATE` «Op4 tendencia: BUY X lotes @ P contra la recovery #T (−Y $/oz, Z ATR). Op4 n/6 del ciclo.» y «cupo del ciclo agotado».
- **Vuelta atrás sin código:** `rescue_mode = 'copy'`.

**Why:**
- **Simulación** con las 245 recoveries reales (`docs/experimento-2/analisis-op4-direccion-2026-10-16.md`):
  - total +394 $/oz frente a −226;
  - el 14-oct, de unos −2 080 $ a unos −370 $ en la cuenta de 10 000 $.
- **Es un seguro:**
  - gana mucho en 3 episodios de tendencia fuerte;
  - pierde poco en muchos de los demás (peor episodio, unos −43 $/oz).
- **Descartado con datos:** confirmación por order block o ruptura de estructura (no mejoró con velas M15), Op4 híbrida (la copia se atasca) y candado/stop en la recovery (peor).

**How to apply:**
- **Decisión del usuario:** puesta en marcha sin modo observación, y también para el ciclo abierto del 14-oct (llevaba días bloqueado).
- **Evaluación:** los ciclos con la recovery a −2 ATR deben acabar mejor que la recovery sola, y ningún ciclo debe empeorar más de unos 45 $/oz por la Op4.
- **Tests:** `python -m tests.test_op4_trend`; las pruebas de la Op4 de copia fijan `rescue_mode='copy'`.
- **Referencias:** migración 014; spec `docs/superpowers/specs/2026-10-16-op4-tendencia-design.md`.
- Ver [[healer-real-loser-bag]] y [[survival-cap-basket-lock]].

**Despliegue:** migración 014 aplicada y `restart_all` el 2026-10-16 ~20:33 UTC (viernes, ~25 min antes del cierre semanal). En el primer tick las 3 cuentas abrieron `Sentinel Op 4 (T)` BUY (0,02 / 0,11 / 0,22) a ~4 168,5 contra la recovery del 14-oct (−79 $/oz, 14 ATR). Neto M15 = 0 en las tres: la pérdida queda congelada en el fin de semana. Evaluar desde el lunes 19-oct (trailing 1,0/0,5 ATR, amputaciones «Bolsa restante»).

**Límite subido a 20 (19-oct-2026, a petición del usuario):** `rescue_trend_max_legs = 20` en `bot_config` (las 7 filas M15), recarga en caliente. Simulación: 20 → +398 $/oz frente a +374 con 6 y +339 sin límite; ver `docs/experimento-2/analisis-op4-limite-y-secundaria-2026-10-19.md`. La Op4 secundaria contraria («bolsa secundaria») se descartó con datos (equivale a cerrar la principal con pérdida; peor total y más ciclos congelados).

**Límite quitado (19-oct-2026, aprobado por el usuario):** `rescue_trend_max_legs = 1000` (sin límite en la práctica). La simulación de ciclo completo (1-mar → 16-oct) mejora las 3 cuentas frente a 20 (10k −40 → −36 %, 1k −55 → −35 %); ver `docs/experimento-2/analisis-limite-op4-y-entrada-op1-2026-10-19.md`.
