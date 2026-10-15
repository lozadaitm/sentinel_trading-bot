# Análisis de las notas del usuario (2026-10-15)

Solo análisis: no se tocó el código ni los bots. Cuatro preguntas.

## 1. ¿Detecta el bot quiebres de estructura?

**Sí, en una versión básica** (`bot/indicators.py`):
- **Estructura H4** (`get_h4_structure`): compara los dos últimos fractales confirmados (máximos y mínimos más altos = alcista, más bajos = bajista).
  - Se usa para filtrar la entrada OP1, para el gate de recovery y para decidir la dirección de OP3.
- **Ruptura M15** (`check_m15_breakout`): la vela cerrada termina por encima o por debajo del último fractal confirmado.
  - Es un BOS ("break of structure") simple y es el disparador de OP1.

**Limitaciones:**
- **Retraso:** un fractal necesita 2 velas posteriores para confirmarse. En H4 eso son ≥ 8 h y en M15 ≥ 30 min.
- **No distingue CHoCH** (el primer quiebre en contra de la tendencia, que marca un posible giro) de un BOS a favor.
- **No filtra rupturas falsas ni barridas de liquidez:** basta un cierre por encima, sin pedir fuerza de la vela ni retesteo.
- **Solo mira un fractal**, sin tener en cuenta el ATR ni la importancia del swing.

**Es viable mejorarlo** con:
- swings por ATR (zigzag);
- detección de CHoCH en M15/H1;
- filtro de ruptura con cuerpo mínimo, o confirmación por retesteo.

Como el quiebre se decide con la vela cerrada, el arnés bar-close sí sirve para medirlo. Antes de implementar nada habría que medir qué parte de las OP1 que acabaron en hedge fueron rupturas falsas.

## 2. Mantenimientos programados de Vantage

- **Dónde se anuncian:** en la página de notificaciones de Vantage (vantagemarkets.com/en-au/notifications).
- **Cuándo caen:** los avisos encontrados son en **sábado**, con el mercado cerrado (8-nov-2025, 11-abr-2026).
- **Excepción:** una migración del 24-ene-2026 afectó solo a servidores demo.
- **Cómo se podría leer:** la librería Python de MT5 no da acceso al correo ni a las noticias del broker. Las opciones serían:
  - leer esa web (frágil, porque depende de su HTML);
  - cargar la ventana a mano.

Para cargarla a mano, la vía natural es reutilizar el NewsGuard (`bot/news.py`), que ya bloquea aperturas en ventanas [T−pre, T+post] leídas de un archivo: añadir "eventos manuales" de mantenimiento.

**Matiz:** bloquear aperturas no protege una cesta ya abierta. Durante el mantenimiento no se puede gestionar nada; la protección es el hedge o el candado.

**Prioridad baja**, porque:
- los mantenimientos suelen caer en fin de semana;
- el bot ya no abre en domingo ni el lunes antes de las 10 h;
- el viernes desde las 20 h solo cierra, si la cesta está en verde.

## 3. ¿La OP2 (hedge) entra demasiado pronto?

**Datos analizados:** 41 primeros hedges sobre una OP1 en las deals de MT5, cruzados con precio M1/M5.
- Unos 38 son eventos independientes.
- Casi todos son de la cuenta base, entre junio y agosto, con versiones anteriores del bot.

**Distancia:**
- Siempre decidió la regla de 2×ATR(M15); el mínimo de 3,50 $ nunca mandó.
- Movimiento en contra al abrir el hedge: mediana 16 $ (de 11 a 41 $).
- Mediana de 49 min desde la OP1.

**¿El precio vuelve a la entrada de OP1 después del hedge?**
- Vuelve en 29 % de los casos en 1 h, 49 % en 4 h y 73 % en 24 h.
- Pero en 29 de 41 casos el precio siguió antes otra distancia igual o mayor en contra. Lo normal es que primero vaya más en contra y luego vuelva.

**Hedge más ancho (simulado):**

| Distancia | Hedges evitados | Pérdida congelada extra en los que sí llegan | Balance |
|---|---|---|---|
| ×1,5 | 18 | ≈ 2 900 $ | aprox. empate |
| ×2 | 21 | ≈ 4 700 $ | aprox. empate |

En ambos casos el peor escenario queda congelado mucho más lejos.

**Idea de cerrar el hedge en verde cuando el precio gira:**
- La ganancia del hedge antes de girar es pequeña: 2,2 $/oz de mediana.
- Regla probada: cerrarlo al perder el 50 % de esa ganancia. Sale bien en 10 casos y mal en 30, porque la OP1 queda desnuda y el precio vuelve a superar el extremo.
- Pérdida máxima de la OP1 desnuda en 24 h: 56 $/oz de mediana, frente a 16 $ congelados con el hedge.
- Para que funcione haría falta una confirmación de giro mucho mejor que la actual (ver punto 1).

**Lo que más pesa:** los **re-locks**.
- Son 50 casos en que el Unwind cobra el hedge y el bot vuelve a cubrir la OP1 más lejos (42 $ de mediana).
- La regla de cerrar el hedge sale mal en 41 de los 50.
- Es el mismo patrón que la idea propuesta (quitar la cobertura esperando el giro), y es lo que más dinero costó.

**Conclusión:** no hay evidencia de que la OP2 entre apresurada. No se recomienda cambiarla ahora. Sí conviene revisar los re-locks en la versión actual durante la revisión del experimento 2.

**Limitaciones:**
- La muestra es pequeña.
- No se tiene en cuenta el spread.
- No se resimulan Recovery, Healer, Unwind ni el trail de la cesta.
- Un solo ciclo (17-jun, −10 637 $) domina el grupo "no volvió".

## 4. Nota "Filtro de minoría" del Smart Healer

**Ya está cubierto, y con una regla más fuerte.** En `_check_healing` / `_apply_healing`:
- **Profundidad mínima:** el Healer solo actúa con core ≥ 3 y nunca con el candado congelado.
- **Par intacto:** mientras el ciclo (realizado + flotante) esté en rojo, la OP1 y su hedge no se pueden amputar.
- **Exposición:** se excluye cualquier pata cuyo cierre **aumente la exposición neta**, que es la definición estructural de cobertura. En el ejemplo de 3 ventas y 1 compra, la compra queda protegida.
- **Patas LOCK:** son intocables siempre.

La regla del filtro de minoría sería más débil:
- con 2 compras y 3 ventas, permitiría amputar una compra aunque eso aumente la exposición;
- la regla actual lo impide.

**Origen:** el problema descrito en la nota se vio en producción (16 de 21 amputaciones mordieron un Hedge Lock) y se corrigió entonces. Ver la memoria `healer-unwind-hedge-cascade`.

**Conclusión:** no hace falta cambio.
