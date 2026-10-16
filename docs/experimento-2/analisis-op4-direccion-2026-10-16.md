# Op4: ¿copiar la recovery u operar a favor del movimiento? (16-oct-2026)

**Pregunta del usuario:** en vez de copiar la última pata (la recovery), ¿y si la Op4 leyera el mercado (qué hicieron mal las patas abiertas, order blocks…) y operara en la dirección buena? Sus ganancias podrían curar a las perdedoras y liberar el ciclo.

**Respuesta corta:**
- **En el 14-oct, sí.** Una Op4 a favor del movimiento habría recortado la pérdida de la recovery de unos −2 080 $ a unos −370 $ en la cuenta de 10 000 $.
- **En el historial funciona como un seguro.** Gana mucho en los pocos episodios de tendencia fuerte, que son los que hunden las cuentas, y pierde poco en muchos de los normales.
- **La confirmación** por ruptura de estructura o por retroceso a order block no mejoró a la entrada directa, al menos en la versión que se puede medir con velas M15.

Análisis, no backtest del ciclo completo. Las limitaciones están en la sección 5.

## 1. Cómo es hoy la Op4

`_check_rescue` (`bot/strategy.py`):
- copia la última pata del ciclo (misma dirección y volumen) cuando el ciclo está en rojo;
- en L3 (más de 44,4 $/oz) la abre al momento, sin señal.

Es una martingala: promedia contra el movimiento. Con el tope de supervivencia queda bloqueada justo cuando el movimiento es grande (14-oct), porque **aumenta** la exposición neta.

Una Op4 en la dirección contraria a la recovery **reduce** la exposición neta, así que el tope la deja pasar siempre.

## 2. Qué se simuló

**Datos:**
- las 245 recoveries reales (experimento 1 + actuales), agrupadas en 46 episodios;
- velas M15, con orden conservador dentro de la vela.

**Disparo:** la recovery lleva K ATR en contra (K = 1, 2 o 3).

**Dirección:**
- `copia`: la de hoy;
- `tendencia`: la contraria a la recovery, es decir, a favor del movimiento.

**Confirmación** (solo en `tendencia`):
- `ya`: al cierre de la vela;
- `bos`: cierre que rompe el extremo de 8 velas;
- `ob`: retroceso de 0,5 ATR o más y vela que retoma, como aproximación a la vuelta a un order block.

**Tamaño:** el volumen que le queda a la recovery. Así la Op4 nunca deja la cuenta más expuesta que antes.

**Salida:**
- trailing por ATR (arranque/distancia: 0,6/0,4, 1,0/0,5 o 1,5/1,0);
- sin stop, como pide el usuario;
- hasta 6 Op4 por recovery.

**Curador:**
- cada ganancia de la Op4 suma el 90 % a la bolsa;
- la bolsa amputa la recovery si su pérdida es de 2 $/oz o más (reglas de la spec del Healer v2).

**Al cerrarse la recovery real,** lo que siga abierto se valora a ese precio.

## 3. Resultados

| Variante | Suma total (base −226 $/oz) | Desastres | Resto | Sin los 3 mejores episodios | Episodios +/− |
|---|---|---|---|---|---|
| tendencia K=1 ya 1,0/0,5 | **+456** | +675 | −219 | −20 | 8 / 17 |
| tendencia K=2 ob 1,0/0,5 | +403 | +639 | −236 | −70 | 8 / 11 |
| tendencia K=2 bos 1,0/0,5 | +370 | +575 | −205 | −66 | 9 / 8 |
| tendencia K=3 ob 1,0/0,5 | +383 | +571 | −188 | −34 | 8 / 7 |
| copia K=2 ya 0,6/0,4 *(sin tope de supervivencia)* | +327 | +229 | +98 | +112 | 19 / 2 |
| híbrido (copia hasta 4 ATR, luego tendencia) K=2 bos 0,6/0,4 | +440 | — | — | +153 | 19 / 2 |

*Suma = mejora frente a lo real, en $/oz por unidad de recovery, sumando las 245.*

**Lectura:**
- **La tendencia es un seguro.** Casi toda la mejora viene de 3 episodios de tendencia fuerte: el 14-oct, junio y agosto. Sin ellos queda en torno a cero o algo negativa, y pierde en más episodios de los que gana.
- **La copia es lo contrario.** Gana a menudo y poco (el precio vuelve), y en el 14-oct empeora.
  - Además, en las cuentas actuales casi nunca podría abrirse, porque la frena el tope de supervivencia.
  - Esta simulación no la frena, así que su +327 está inflado.
- **El híbrido** sale bien en el total, pero en el 14-oct falla (−5 $/oz).
  - La Op4 de copia se abre primero, queda atascada sin stop y ya no deja entrar a la de tendencia.
  - Para que sirviera, haría falta una regla de qué hacer con esa copia atascada.
- **Order block / ruptura de estructura:** no mejoran de forma clara a la entrada directa. Con velas M15 la aproximación es tosca; una versión más fina necesita datos M1 o ticks.

## 4. El 14-oct paso a paso (cuenta de 10 000 $, tendencia K=2 ya 1,0/0,5)

| Hora servidor | Qué hace |
|---|---|
| 15-oct 01:15 | Abre Op4 BUY en 4 107,9 (recovery a −2 ATR), tamaño 100 % de la recovery |
| 15-oct 03:30 | Cierra en 4 140,4 (+32,5 $/oz). El curador amputa el 58 % de la recovery |
| 03:30–23:00 | Cuatro Op4 más, con ganancias de +1,7 a +5,6 $/oz. Cada una amputa del 3 al 8 % |
| 16-oct 06:00 | Sexta y última Op4. A la recovery le queda el 23 % |

**Resultado:**
- −94,5 → −16,6 $/oz;
- en dinero, de unos −2 080 $ a unos −370 $.
- La cuenta habría seguido con solo 0,05 lotes de recovery en vez de 0,22.

## 5. Limitaciones

- **Velas M15:** sin spread, sin swap, sin deslizamiento.
- **Una recovery cada vez:** el resto del ciclo (Unwind, cesta, candado) no se simula. Amputar la recovery cambia cuándo cierra el ciclo, y eso no está medido.
- **Muestra pequeña:** 46 episodios y 8 desastres. Que la tendencia gane depende de que vuelvan a darse episodios así. Es lo esperable, pero no está garantizado.
- **Sin stop en la Op4 de tendencia:** si el precio se da la vuelta, la Op4 pierde, pero la recovery gana a la vez. Como mucho actúa como un candado parcial; el peor episodio simulado fue de −33 a −44 $/oz.

## 6. Si se quisiera avanzar

Un diseño tendría que decidir:
1. **El disparo** (K en ATR), y si sustituye a la Op4 de copia o convive con ella. Con la copia atascada, el híbrido falla.
2. **El tamaño:** el volumen de la recovery que queda (lo simulado) o el neto de la cuenta.
3. **El trailing por ATR,** y cuántas Op4 por ciclo.
4. **Cómo convive con el candado y el Unwind.**

**Antes de activarlo:** una simulación del ciclo completo, o al menos una pasada en M1 con spread, y empezar en modo observación (solo log), como se hizo con el freno de reentrada.
