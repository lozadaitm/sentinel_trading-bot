# Análisis de las recoveries «V-Shape» (16-oct-2026)

**Pregunta:** ¿las recoveries que acaban en desastre entran en un sitio reconocible (vendiendo mínimos, comprando máximos, tras un movimiento largo) que un filtro de entrada pudiera evitar?

**Respuesta corta:** no. No hay un rasgo de entrada que separe las recoveries catastróficas, y poner un candado o stop a la recovery sale peor en todos los niveles probados. El problema es la asimetría: muchas ganancias pequeñas y unos pocos desastres. Se parece al del M5, pero solo se puede atacar con una simulación del ciclo completo.

## 1. Datos

- **Recoveries:** 245 en total.
  - 228 del experimento 1 (3 cuentas, junio–septiembre, 91 días), sacadas de `audit/mt5_positions_*.csv`;
  - 17 de las cuentas actuales, del historial de MT5 en solo lectura.
- **Precios:** velas M15 del terminal desde el 8-jun.
- **Medidas en ATR(14) M15 de la entrada,** cuya mediana es 7,2 $.
- **Resultado por recovery,** en $/oz: beneficio + swap + comisión, dividido entre volumen × 100.

**Cómo entra una recovery** (`bot/strategy.py`, ESTADO 2):
- con el ciclo en entrada + cobertura;
- pasado `min_tech_wait`;
- a 1 ATR o más de la última pata;
- con el ATR M15 subiendo;
- en la dirección de la estructura H4;
- fuera de las horas de riesgo (desde el experimento 2).

## 2. El patrón: muchas ganancias pequeñas y pocos desastres

| | Recoveries | Acierto | Mediana | Suma $/oz |
|---|---|---|---|---|
| Todas | 245 | 84 % | +1,2 $/oz | −195 |
| Peores que −20 $/oz | 11 | 0 % | −80 $/oz | −844 |
| El resto | 234 | 88 % | +1,2 $/oz | +649 |

- **Los 11 desastres son 8 episodios independientes en 4 meses.** El del 14-oct cuenta 3 veces, una por cuenta; el 29-jun y el 18-ago, 2 veces cada uno.
- **En dinero real:**

| Cuenta | Resultado de las recoveries | De ello, los desastres |
|---|---|---|
| Base del experimento 1 | −10 692 $ | −21 193 $ (6 recoveries) |
| Segunda cuenta del experimento 1 | −2 185 $ | −2 790 $ (2) |
| Tercera cuenta del experimento 1 | +372 $ | — |
| Cuentas actuales (las 3) | −2 434 $ | −2 826 $ (solo el 14-oct) |

- **Cómo se cierran** (experimento 1):
  - 156 solas, sin trailing (sobre todo «Unwind Profit Banking»);
  - 44 junto con otras patas;
  - solo 28 por el trailing de la Op3.

  Lo que cobran las ganadoras lo decide sobre todo el Unwind, no el trailing.

## 3. Rasgos de entrada probados: ninguno separa los desastres

Cada rasgo se partió en tramos. Los desastres aparecen repartidos en casi todos.

| Rasgo en la entrada | Resultado |
|---|---|
| Distancia al extremo de las últimas 2 h (¿vende el mínimo?) | Las que entran a menos de 0,25 ATR del extremo aciertan menos (62 %), pero solo 2 de los 8 episodios están ahí. |
| Momento de las últimas 1–2 h (¿a favor o en contra?) | Hay desastres tanto a favor como en contra del movimiento. |
| Rebote desde el extremo de 2 h | Hay desastres en todos los tramos, de 0 a 6,5 ATR. |
| Posición en el rango de 24 h | 3 episodios entre el 10 y el 25 % del rango, 4 en la mitad alta. |
| Distancia a la entrada del ciclo | El tramo de más de 6 ATR suma −307 $/oz, pero son solo 2 episodios (17-jul y 14-oct). |
| Misma dirección que la entrada del ciclo | 10 de 11 desastres, pero también 169 de las 233 recoveries con dato. |
| Horas de riesgo (UTC 1, NY 9–11) | Las recoveries en esas horas fueron **mejores** (+183 $/oz). Ampliarlas no ayuda. |

**Con 8 episodios, cualquier filtro que los «atrape» estaría hecho a medida y no sería fiable.**

**Corrección sobre el 14-oct:** la recovery **no** vendió el mínimo.
- El mínimo fue 4 073,5 a las 19:00 de servidor.
- Vendió a las 21:13 en 4 090, tras un rebote de 17 $ (1,9 ATR).
- Estaba a 6,5 ATR de la entrada del ciclo.
- Después nunca fue más de 0,28 $ a favor.

## 4. Candado o stop a la recovery: peor en todos los niveles

**Simulación aproximada:** si la recovery llega a −k ATR, la pérdida se congela en k ATR. Es optimista, porque ignora el coste de deshacer un candado.

| k (ATR) | Recoveries que lo tocan | De ellas, acabaron mejor | Suma hoy → con candado ($/oz) |
|---|---|---|---|
| 1,5 | 61 | 49 | −195 → −761 |
| 2 | 47 | 35 | −195 → −685 |
| 3 | 31 | 20 | −195 → −649 |
| 4 | 24 | 14 | −195 → −583 |
| 5 | 20 | 11 | −195 → −543 |

**Por qué empeora:** la mayoría de las recoveries que se van muy en contra vuelven. Es lo mismo que mostró la sección 8 de la auditoría del M5 para la Op2: el 72 % vuelve a la entrada en 24 h. Encaja con la regla del usuario de no poner SL catastrófico.

## 5. Conclusión y siguiente paso posible

- **Sin cambios en la recovery por ahora:**
  - no hay un filtro de entrada con base estadística;
  - un stop o candado propio empeora el resultado.
- **La palanca real es el ciclo completo:**
  - cuánto se cobra (Unwind y trailing de la Op3);
  - cuánto se arriesga en la cola: tamaño de la recovery (2× la base) frente al tope de supervivencia.

  Eso no se puede medir recovery a recovery: la Healer, el Unwind y la cesta se influyen entre sí. Hace falta el arnés de simulación del ciclo completo (Fase 2, pendiente), como ya se concluyó para el trailing de la Op1.
- **En las cuentas actuales,** el tope de supervivencia ya limita el tamaño: en el 14-oct la recovery fue de 0,22 en la cuenta de 10 000 $, frente a los 0,4–0,5 lotes del experimento 1 en la base. Por eso el episodio cuesta un 20 % y no más.
