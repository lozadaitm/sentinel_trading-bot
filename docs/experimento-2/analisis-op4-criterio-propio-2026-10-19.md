# Op4 con criterio propio de mercado, Op5 direccional y orden de los recortes (19-oct)

**Pregunta del usuario:**
- ¿La Op4 debería tener su propio criterio de mercado en vez de abrir siempre contra la recovery?
- ¿Se podría abrir una venta cuando el mercado va a bajar, para recortar la pérdida de la Op3, aunque aumente la exposición?
- Objetivo: «que me haga millonario y dormir tranquilo».

**Método:** ciclo completo con el motor real (`bot/strategy.py`) sobre velas M15, del 1-mar al 16-oct.
- Swap real, Op4 sin cupo, recorte por parejas activo.
- Dos pruebas:
  - el periodo completo (en la práctica es **un solo ciclo** congelado desde el 2-mar);
  - 15 ventanas de 30 días que empiezan cada 14 días, todas sin posiciones al inicio. Es la prueba más informativa.
- Arnés: `fullsim/op4lab.py` y `op4lab2.py` en el scratchpad de la sesión (no está en el repo).

## 1. Variantes de la Op4

**Señales:**
- `dc20` / `dc48`: ruptura del máximo o mínimo de 20 o 48 velas M15 (una «ruptura de estructura»).
- `ema`: EMA20 frente a EMA50 en M15.
- `h4`: estructura H4 del bot.

**Modos:**
- **suave:** la Op4 solo abre con una señal a su favor.
- **completa:** como suave, y además cierra la Op4 cuando la señal se da vuelta.
- **dir f:** como completa, y además, con la señal a favor de la recovery, abre una «Op5» del mismo lado que la recovery, de tamaño f × su volumen.
  - Usa el trailing de la Op4 y se cierra si la señal se da vuelta.
  - Aumenta la exposición: es la idea del usuario.

### Resultados en la cuenta de 10k

| Variante | Periodo completo | Media por ventana de 30 d | Peor ventana | Peor caída | Ventanas mejor / peor que hoy |
|---|---|---|---|---|---|
| **actual** | −31,9 % | −4,5 % | −20 % | 20 % | — |
| suave dc20 | −38,1 % | −4,2 % | −25 % | 28 % | 4 / 8 |
| suave dc48 | −44,0 % | −3,9 % | −31 % | 32 % | 4 / 11 |
| suave ema | −31,9 % | −3,5 % | −20 % | 24 % | 2 / 1 |
| suave h4 | −70,3 % | −0,6 % | −54 % | 60 % | 7 / 7 |
| completa dc20 | −11,3 % (caída 45 %) | −0,7 % | −43 % | 52 % | 9 / 6 |
| completa dc48 | −50,6 % | −1,8 % | −34 % | 40 % | 7 / 8 |
| completa ema | −45,4 % | +0,3 % | −43 % | 45 % | 8 / 7 |
| completa h4 | −71,9 % | +6,5 % | −57 % | 63 % | 9 / 6 |
| dir dc20 0,5 | −33,5 % | −3,5 % | −45 % | 55 % | 7 / 8 |
| dir dc20 1,0 | −83,4 % | +3,7 % | −50 % | 58 % | 9 / 6 |
| dir dc48 0,5 | −34,0 % | −4,3 % | −30 % | 48 % | 4 / 9 |
| dir dc48 1,0 | −47,7 % | −2,3 % | −35 % | 55 % | 6 / 9 |
| dir ema 0,5 | −86,9 % | −8,5 % | −74 % | 75 % | 7 / 8 |
| dir ema 1,0 | −69,8 % | +4,7 % | −37 % | 49 % | 7 / 7 |
| dir h4 0,5 | **−94,7 % (cuenta quemada)** | −9,6 % | −95 % | 95 % | 6 / 9 |
| dir h4 1,0 | −75,7 % | −3,5 % | −52 % | 73 % | 5 / 10 |

**Lectura:**
- **Ninguna señal tiene ventaja robusta.** Las variantes ganan en más o menos la mitad de las ventanas y pierden en la otra mitad: es una moneda al aire.
- **Lo único que cambia de verdad es la variación:**
  - la peor ventana pasa de −20 % a entre −40 % y −95 %;
  - la peor caída, de 20 % a entre 45 % y 95 %.
- **Las clasificaciones se invierten entre pruebas.** `completa h4` es la mejor en las ventanas (+6,5 %) y de las peores en el periodo completo (−72 %). `completa dc20` es al revés.
- **La Op5 direccional** (abrir del lado de la recovery cuando «el mercado va a bajar») es lo peor de todo. Con la estructura H4 quemó la cuenta.
- **Conclusión:** dar a la Op4 un criterio de mercado convierte una pérdida lenta y acotada en una apuesta de mucha variación sin esperanza positiva. Para «dormir tranquilo», **no se implementa ninguna**.

## 2. Freno de re-entradas (`reentry_enforce = true`)

| | Periodo completo | Media por ventana | Ventanas mejor / peor |
|---|---|---|---|
| actual | −31,9 % | −4,5 % | — |
| `reentry_enforce` | −31,9 % | −5,3 % | 2 / 3 |

No mejora. Se descarta activarlo.

## 3. Recortar primero la pareja Op1 + Op2 («coverfirst»)

**Por qué:**
- La pareja Op1 + Op2 cuesta unos 14–16 $/oz en el ciclo de hoy. Quita el mismo swap diario que la pareja recovery + Op4, que cuesta unos 93 $/oz.
- Por cada dólar de la bolsa, recortar Op1 + Op2 frena el swap unas 6 veces más rápido.
- Se mantiene la regla del ancla: la Op1 y la Op2 nunca bajan de 0,01 mientras queden otras patas del ciclo.

| 10k | Periodo completo | Peor caída | Media por ventana | Peor ventana | Ventanas mejor / peor |
|---|---|---|---|---|---|
| actual (recovery primero) | −31,9 % | 32,9 % | −4,5 % | −20,0 % | — |
| **Op1 + Op2 primero** | **−21,5 %** | **22,6 %** | **−3,8 %** | −19,4 % | **7 / 0** |

**Mejora en el periodo completo (+10 puntos) y no empeora ninguna ventana.** No añade exposición. Va en contra de la regla «recovery primero» que puso el usuario, así que decide él.

Validación en 5k y 1k: ver sección 6.

## 4. Fallo encontrado: doble conteo en la bolsa del curador

**El fallo:** cuando el recorte por parejas cierra un miembro **en verde**, MT5 registra un deal con ganancia. En la pasada siguiente, `_check_healing` lo cuenta como «ganador nuevo» y suma el 90 % a la bolsa. Pero ese dinero ya estaba neteado dentro del recorte, así que la bolsa gasta dinero que no existe.

**Afecta a:**
- el recorte por parejas cuando la Op1 o la Op4 están en verde;
- la disolución del candado (`Basket Dissolve`);
- y, en teoría, a la amputación si alguna vez cerrara una pata verde.

**En vivo:** los dos recortes del 19-oct fueron con los dos miembros en rojo, así que no se infló nada.

**Arreglo propuesto:** que el curador ignore los deals con comentario interno (`Healer Pair Cut`, `Healer Amputacion`, `Basket Dissolve`).

**Efecto medido en 10k:**

| | Periodo completo | Media por ventana |
|---|---|---|
| Con el fallo, recovery primero | −29,4 % | −4,8 % |
| Con el fallo, Op1 + Op2 primero | −16,4 % | −7,6 % (peor caída 57 %) |

Con el fallo, el gasto extra a veces ayuda y a veces hunde. Es azar, no ventaja. **Se arregla por corrección:** la bolsa no puede gastar dinero que no existe.

## 5. Lo de fondo: la economía de la Op1

Señales de Op1 del motor real, simulando la Op1 sola en M5 (`op1scan.py`, del 20-feb al 16-oct, 960 señales):
- llega a la distancia de cobertura (Op2) en el **10,5 %** de las veces;
- la distancia media de cobertura es de **18,4 $/oz** (2 ATR, con suelo de 8 $).

Datos reales de `bot_positions` (cuentas anteriores, jul–ago):
- acierto del 86–95 %;
- ganancia mediana por Op1 de 0,9–2,3 $/oz.

**Cuenta:**
- Antes de cada cobertura hay unas 8,5 Op1 ganadoras: entre 8 y 20 $/oz ganados.
- Solo el bloqueo Op1 + Op2 ya cuesta al menos la distancia de cobertura, unos 18 $/oz. Sin contar la recovery, que en el ciclo del 14-oct añadió ~93 $/oz.
- Para empatar, cada ciclo congelado tendría que resolverse costando menos de lo que la Op1 ganó antes. Hoy no pasa: en 14 de las 15 ventanas de 30 días, la cuenta termina con un ciclo de 4 patas congelado durante 17–20 días.
- Media de las cuentas reales anteriores: −15,6 $/oz por Op1 en una cuenta, −0,8 en otra y +0,8 en la tercera.

**Conclusión:** el resultado lo decide **cuánto cuesta salir de cada cobertura**, no la Op4. Ajustar la Op4 solo mueve dónde cae la pérdida. Ganar dinero de verdad exige que el ciclo cubierto se resuelva más barato, o que haya menos coberturas. La mejora de la entrada de la Op1 ya se midió y salió débil (10 % frente a 7 % al azar).

**Límites:**
- son velas M15, sin noticias ni M5;
- el periodo completo es un solo camino;
- la economía de la Op1 sale de una simulación aproximada y de pocas cuentas reales.

## 6. Validación en 5k y 1k (Op1 + Op2 primero)

| Cuenta | Variante | Periodo completo | Media por ventana | Peor ventana | Ventanas mejor / peor |
|---|---|---|---|---|---|
| 10k | recovery primero | −31,9 % | −4,5 % | −20,0 % | — |
| 10k | **Op1 + Op2 primero** | **−21,5 %** | **−3,8 %** | −19,4 % | **7 / 0** |
| 5k | recovery primero | −29,9 % | −5,1 % | −19,8 % | — |
| 5k | **Op1 + Op2 primero** | **−20,2 %** | **−4,4 %** | −18,4 % | **9 / 1** |
| 1k | recovery primero | −34,9 % | −4,5 % | −20,8 % | — |
| 1k | **Op1 + Op2 primero** | −34,9 % | **−4,1 %** | −20,7 % | **5 / 0** |

- **Mejora en las tres cuentas:** en 5k y 10k recupera unos 10 puntos en el periodo completo.
- **En 1k no cambia el periodo completo,** porque con 0,01 lotes el ancla no deja recortar más. Mejora 5 ventanas y no empeora ninguna.
- **Es la única mejora de esta tanda que no añade riesgo.**
