# Revisión de las 3 cuentas nuevas (14-oct → 15-oct 2026)

**Alcance:** las tres cuentas demo dadas de alta el 14-oct (1 000 $, 5 000 $ y 10 000 $), desde el alta hasta el 15-oct 21:24 UTC (pausa diaria del mercado).

**Fuentes:** historial de MT5 leído en modo solo lectura contra los terminales abiertos, y `bot_logs` de Supabase. Solo cifras agregadas.

## Resultado

| Cuenta | Balance | Equity | Flotante del ciclo M15 | M5 cerrado |
|---|---|---|---|---|
| 1 000 $ | 1 042 $ | 867 $ | −175 $ | +15,5 $ (solo el 15-oct) |
| 5 000 $ | 5 121 $ | 4 109 $ | −1 012 $ | −5,4 $ |
| 10 000 $ | 10 280 $ | 8 239 $ | −2 040 $ | +35,7 $ |

**M15:** las tres cuentas llevan el mismo ciclo, abierto el 14-oct a las 09:01 de servidor:
- venta de entrada a 4 147;
- cobertura de compra a 4 161;
- 5 o 6 recoveries de venta. Las primeras se cobraron, y entre las tres cuentas suman unos +400 $ realizados.

La última recovery se abrió a las 21:13 de servidor, a 4 090, en el mínimo del día. El oro rebotó hasta 4 170, unos 80 $.

Casi todo el flotante viene de esa pata. En la cuenta de 10 000 $:
- recovery: −1 769 $;
- par entrada + cobertura: unos −270 $, congelado.

## Hallazgos

### 1. El Healer amputa la recovery que acaba de abrir (raro, coste pequeño)

**Dónde:** en las cuentas de 5 000 $ y 10 000 $, dos veces en cada una (13:27 y 21:13 de servidor).

**Qué pasa, en el mismo segundo:**
1. Se abre una recovery.
2. El Healer la cierra entera con una «Amputación Táctica». Pierde solo el spread (−1,8 a −6,2 $).
3. Se vuelve a abrir otra recovery idéntica.

**Coste:** unos 19 $ en total, contando spread y comisión.

**Causa:**
- El Healer solo actúa con 3 o más patas (`healer_min_core`), y esa condición se cumple justo al abrir la recovery.
- Para entonces ya tiene presupuesto: lo que ganó la recovery anterior al cerrarse con beneficio.
- Además, el par entrada + cobertura está protegido mientras el ciclo va en rojo, así que la única pata que puede amputar es la recovery recién abierta. Esa pata va en rojo por el spread.

**Consecuencia:** el presupuesto de curación se gasta en nada, y el bot paga el spread dos veces.

**Posible arreglo (pendiente de diseño):** que el Healer ignore las patas cuya pérdida no supere el spread, o que tengan menos de N minutos abiertas.

### 2. El M5 de la cuenta de 1 000 $ solo puede operar a la contra del M15 (estructural)

**Qué pasa:**
- El 14-oct, el M5 de esa cuenta no abrió nada.
- El 15-oct abrió 41 operaciones, todas compras.

**Por qué:**
- El tope de supervivencia da al M5 el 20 % del aguante (`equity_weight` 0,2).
- Con unos 1 000 $ y 350 $/oz, eso son unos 0,006 lotes, por debajo del mínimo de 0,01.
- Por eso el M5 solo puede abrir cuando su orden reduce la exposición neta de la cuenta. Con el M15 corto, solo puede comprar.

No es un error: es el tope funcionando como se diseñó. Pero en esa cuenta el M5 queda limitado a operar en contra de la dirección del M15.

### 3. «Trading deshabilitado» cada 6 horas, a las :42 UTC (broker, inofensivo)

**Cuándo:** a las 01:42, 07:42, 13:42 y 19:42 UTC, durante unos segundos.
- Aparece en distintas cuentas cada vez.
- El filtro de 30 s ya evita que mande correo.

Parece una reconexión periódica del servidor de Vantage. No hay nada que hacer.

### 4. La cola del ciclo: la recovery a favor no tiene protección (diseño, a vigilar)

**Qué pasó:**
- La recovery «V-Shape» suma lotes en la dirección de la entrada. Con un rebote de 80 $ queda sola contra el precio.
- La cobertura solo cubre la entrada.

**Qué funcionó:**
- El tope de supervivencia bloqueó la «Sentinel Op 4», que habría sido una capa más de venta. S pasó de 491 a 409 $.
- El candado no saltó porque S sigue por encima de 150 $. Es lo esperado.

No es un fallo, pero es justo la cola que hay que vigilar en la revisión del candado.

### 5. Menores

- **M5 antes de la pausa diaria:** el M5 abre hasta las 23:59 de servidor (`m5_end_hour` 23 incluida). Las compras de las 23:45–23:50 pasan la pausa y pagan swap. Es poco dinero.
- **Swap de la cobertura:** −59 $ en dos noches en la cuenta de 10 000 $, compensado en parte por el swap positivo de las ventas.
- **Avisos:** el «bot inactivo 72 h» falso solo llegó una vez por cuenta, el 14-oct. Tras el reinicio del 15-oct no ha vuelto. Lo de «ALERT_EMAIL_TO sin configurar» solo pasó en el primer arranque.

## Lo que funciona bien

- La cobertura entró a tiempo.
- Las recoveries se cobraron con trailing.
- El tope de supervivencia frenó las capas extra.
- Las noticias y el freno de volatilidad bloquearon y liberaron a su hora.
- El reinicio del 15-oct retomó el ciclo sin incidencias.
