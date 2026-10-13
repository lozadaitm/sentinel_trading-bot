# Fase 1 — D (Sesiones) y G (AMD / Power of 3) medidos con nuestros datos

Fecha: 2026-10-13 · Datos: `bot_backtesting/data/XAUUSD+_M5.csv` y `_M15.csv`, del 12-ene al
16-jun-2026 (108 días completos) · Script: [`sesiones_amd.py`](sesiones_amd.py) · Tablas
completas: [`out/resultados.md`](out/resultados.md).

**Hora:** servidor = Nueva York + 7 h (el corte diario 00:00 servidor = 17:00 NY), convertida a
UTC. El perfil horario lo confirma: el pico de volatilidad cae a las 13–15 UTC, con la apertura
de NY y los datos de EE. UU.

**Limitación:** no hay velas de jun–oct 2026 (el historial MT5 está bloqueado por el error
`-6`, ver D9 del [informe de cuentas](../audit/informe-3-cuentas.md)). 5 meses de un oro muy
volátil (~4 500 $) dan una muestra corta para AMD.

## D. Sesiones: lo que dice el video **no se cumple** en el oro de 2026

| Sesión (hora local de cada plaza) | Rango mediano | p25–p75 | Lo que dice el video |
|---|---|---|---|
| Asia (Tokio 09–15 = 00–06 UTC) | **56 $** | 38–82 $ | 20–30 pips, "consolida" |
| Londres (08–13 Londres) | **41 $** | 30–60 $ | 40–100 pips, "rompe" |
| Nueva York (08–17 NY) | **81 $** | 57–119 $ | 100–350 pips, "confirma o revierte" |

- **Asia no es tranquila.** Por hora se mueve igual que Londres y que NY (~9 $/h). Es la sesión
  más estrecha solo el 20 % de los días. Ninguna convención de pips hace encajar las cifras del
  video:
  - con 1 pip = 0,10 $ caen dentro del rango del video el 0 % de los días;
  - con 1 pip = 1 $, Asia supera el rango el 94 % de los días.
- **Londres rompe el rango de Asia el 74 % de los días.** Esto sí se cumple, pero casi siempre
  por un solo lado: por los dos, apenas el 1 %.
- **NY sigue la dirección de Londres el 56 % de los días** y la revierte el 44 %. Es casi lanzar
  una moneda.
- **Las horas más violentas son las 13–15 UTC (NY) y la 01 UTC.** La 01 UTC es la segunda hora
  más volátil del día, y es justo cuando 25912766 sufrió el stop-out (19-ago 01:02 UTC, ver
  informe de cuentas). Las más tranquilas son las 03–04 UTC.

**Veredicto D: descartada** la parametrización por sesión al estilo del video. Lo aprovechable
para el diseño del bot es el **perfil horario de riesgo**: la 01 UTC y las 13–15 UTC son las
ventanas en que una pata sin cobertura sufre más.

## G. AMD: la "reversión tras el barrido" **no funciona**; la continuación tampoco es concluyente

Definición: rango asiático 00–06 UTC. El barrido es una vela M5 que entre las 06 y las 10 UTC
supera el rango en k·R y vuelve a cerrar dentro antes de N velas. Se compara:

- **reversión:** la regla ICT, entrar en contra del barrido;
- **continuación:** entrar a favor del barrido;
- **azar:** misma hora, otro día y lado aleatorio.

Se separó un periodo reservado (desde 1-may) que no se usó para elegir parámetros.

| (k=0,10 · N=6) | Señales | MFE > MAE a 4 h | p contra 50 % |
|---|---|---|---|
| Reversión (regla ICT) | 37 | 43 % | 0,84 |
| Continuación | 37 | 57 % | 0,26 |
| Azar | 37 | 41 % | 0,91 |

- En **todas** las combinaciones de k y N, en desarrollo y en reserva, la reversión tiene un
  MFE/MAE a 4 h **menor que 1** (0,49–0,94): pierde más de lo que gana.
- La continuación queda **por encima de 1** (1,06–2,05).
- Coincide con lo que encontraron la Fed de NY (Osler) y el preprint de SSRN: el barrido de
  stops empuja **a favor** de la ruptura.
- La ventaja de la continuación **no es estadísticamente significativa** (p = 0,26 con 37
  señales). Hace falta más historia.
- El proxy "OP1 en verde antes de OP2" (+1,5 $ antes de −2 ATR) sale ~90 % en todos los grupos y
  no discrimina. 1,5 $ es poco para el oro de 2026. Si se repite, usar umbrales en ATR.

**Veredicto G: descartada como filtro de reversión para OP1.** Usarla haría entrar contra el
movimiento fuerte, que es el peor caso para un ciclo sin stop.

"Continuación tras el barrido" queda como **investigar más (prioridad baja)**: solo con más datos
(jun–oct, cuando se resuelva D9) y como veto ("no abrir OP1 en contra de un barrido reciente"),
no como señal de entrada.
