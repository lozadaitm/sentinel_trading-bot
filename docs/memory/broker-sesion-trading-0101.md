---
name: broker-sesion-trading-0101
description: XAUUSD+ cotiza desde 01:00 pero solo acepta ordenes desde 01:01 (servidor); la Big One entra al primer minuto operable y pierde ~14 % de la ventaja simulada
metadata:
  type: project
---

Especificacion del simbolo XAUUSD+ en el broker (vista en MT5 el 2026-10-26): sesion de
cotizaciones lunes-jueves 01:00-23:58 (viernes -23:57), sesion de **trading 01:01**-23:58.
El primer intento real del bot e2 (lunes 2026-10-26, 01:00:06) fue rechazado en las 3
cuentas con retcode 10018 (mercado cerrado) y la Big One del dia se perdio.

Arreglo (bot/strategy_e2.py): si la primera orden de una pata vuelve con 10018 se deshace
el registro 'opening' y se reintenta cada 5 s hasta 10 min (MARKET_CLOSED_RETRY_S).
Ademas la antiguedad del calendario se mide en horas de mercado (sessions.market_seconds):
el exportador sella con la hora del ultimo tick y el lunes a las 01:00 marcaba 49 h.

Costo medido con ticks del broker (123 dias, 2026-01 a 2026-10, ida 01:0x -> 10:00, neto
de spread, sin comision): entrada 01:00:00 +4.63 $/oz, 01:01:00 +3.99, 01:02 +3.54,
01:05 +2.78 (error estandar ~5). La simulacion de la Big One usaba el open de las 01:00,
que no es operable: la ventaja real es ~14 % menor que la proyectada.

**Why:** cualquier entrada temporal a la apertura diaria debe usar el primer precio
operable (01:01), no el primer precio cotizado.
**How to apply:** al re-simular o proyectar la Big One, entrar a las 01:01 con ticks;
la demo de 10 semanas mide el valor real. Ver [[e2-motor-tres-patas]], [[decision-bigone-combo]].
