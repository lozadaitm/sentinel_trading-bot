# Revisión del 16-oct (tarde): primeras horas del trailing ATR y estado del ciclo M15

**Ventana:** desde el reinicio (16-oct 01:02 UTC) hasta las 13:40 UTC.

**Fuentes:** historial de MT5 en solo lectura de las 3 cuentas y `bot_logs`. Precio al cierre de la revisión: 4 172.

## 1. M5 con el trailing ATR: funciona como se diseñó, muestra mínima

Desde el reinicio, cada cuenta hizo solo **2 operaciones del M5**, las mismas en las tres:

| Hora UTC | Entrada | Salida | $/oz | Qué pasó |
|---|---|---|---|---|
| 02:25 | 4 159,77 | 4 161,07–4 161,29 | +1,3 a +1,5 | El trailing ATR se armó a +1,75 $ (ATR 3,49 $ × 0,5) con SL 4 160,47 (0,3 ATR). Salió por SL en verde. |
| 04:30 | 4 178,7 | 4 172,3–4 172,5 | −6,3 a −6,5 | TimeStop a los 45 min. Nunca avanzó lo bastante para armar el trailing. |

- **Log y cálculo correctos:** «Trailing ATR armado» salió una vez por ticket, con ATR, avance y SL que cuadran con la fórmula.
- **La entrada de las 04:30** es la primera vela tras liberarse la ventana de noticia (comparecencia del presidente de la Fed). Compró tras una subida de unos 19 $ durante la ventana y el precio se dio la vuelta. Es un solo caso; queda anotado para mirarlo cuando haya más muestra.
- **Desde las 05:15 UTC el M5 no opera:** cambió de régimen a `scalper` (ADX 23,4). En la práctica el M5 solo opera en `surfer` (939 de 944 operaciones del historial), así que en mercado lateral se queda parado. Es lo esperado.
- **Sin conclusión todavía:** con 2 operaciones no se puede evaluar. El criterio sigue siendo 2 semanas o 100 operaciones.

## 2. Ciclo M15 del 14-oct: es el riesgo dominante

Las tres cuentas siguen con las mismas 3 patas (entrada venta 4 147, cobertura compra 4 161, recovery venta 4 090). No ha habido aperturas ni cierres del M15 desde el reinicio.

| Cuenta | Neto | Flotante | % del balance | S | Candado saltaría hacia | Ciclo en empate hacia |
|---|---|---|---|---|---|---|
| 1 000 $ | −0,02 | −177 $ | −17 % | 422 $ | 4 444 | 4 083 |
| 5 000 $ | −0,11 | −1 030 $ | −20 % | 367 $ | 4 389 | 4 078 |
| 10 000 $ | −0,22 | −2 076 $ | −20 % | 367 $ | 4 389 | 4 078 |

*(S y precio del candado con stop-out supuesto del 50 %; el margen es pequeño y casi no influye.)*

**Lectura:**
- **La recovery «V-Shape» es casi toda la pérdida:** unos −82 $/oz, el 85–90 % del flotante. El par entrada + cobertura está congelado en unos −15 $/oz, swaps incluidos.
- **Entró tras un rebote, no en el mínimo** *(corregido tras el análisis de recoveries)*: el mínimo fue 4 073,5 a las 19:00 de servidor; la venta entró a las 21:13 en 4 090, con el precio ya 17 $ por encima. Después nunca fue más de 0,28 $ a favor, así que ningún trailing la habría salvado. Ver `analisis-recoveries-2026-10-16.md`.
- **Las protecciones funcionan como se diseñaron:**
  - el tope de supervivencia bloqueó otra vez la Sentinel Op 4 (L3) a las 04:30 UTC (S 364–421 $ frente a 350 $ exigidos);
  - el candado (S < 150 $) queda unos 215–270 $ por encima del precio actual.
- **El Healer no puede curar:** no hay ganancias nuevas del M15 mientras el ciclo esté abierto, y las del M5 no cuentan (otra magic).
- **Salida natural:** que el oro vuelva a unos 4 078–4 083, o el candado si sigue subiendo. Las reglas del usuario excluyen el cierre de emergencia y el SL catastrófico.

## 3. Avisos

- **«CUENTA MUERTA»** a las 01:42 y 07:42–07:44 UTC, de 3 a 20 s. Es la reconexión de Vantage cada 6 h ya conocida (hallazgo 3 de la revisión anterior). No llega correo: el filtro exige 30 s.
- **Circuit breaker de volatilidad** a las 02:59 (M15) y 03:48 (M5), liberado en 1–2 min.
- **Sin errores de órdenes** ni excepciones.

## 4. Propuesta de siguiente paso (solo análisis) — hecho, ver `analisis-recoveries-2026-10-16.md`

Medir en todo el historial (experimento 1 y actual) **dónde entran las recoveries «V-Shape»** respecto al extremo del movimiento: cuántas venden mínimos o compran máximos, y qué les pasa después. Si el patrón se repite, el siguiente diseño sería un filtro de entrada para la recovery, no un stop.
