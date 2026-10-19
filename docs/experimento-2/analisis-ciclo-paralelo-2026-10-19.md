# Ciclo paralelo del M15 mientras el ciclo principal está congelado (19-oct-2026)

**Pregunta del usuario:** cuando el ciclo está congelado (neto 0, Op4 en rojo), ¿puede abrirse un ciclo nuevo cuyas ganancias paguen la pérdida congelada? «Mídelo bien, analizando cada posible escenario».

**Respuesta corta:** **no.**
- El ciclo paralelo empeora mucho en las tres cuentas: 10k de −40 % a −75 %, 5k de −39 % a −81 %, y la de 1k se funde por stop-out el 23-mar.
- **El recorte por parejas** (Op1 + Op2 y recovery + Op4, pagado con la bolsa del propio ciclo) **sí mejora**: de −40 % a −31 % en 10k y de −39 % a −31 % en 5k.
- **El hallazgo más importante no era la pregunta:** con el bot actual, un solo ciclo abierto el 2-mar sigue abierto el 16-oct. Lleva 7 meses sin operar mientras el swap se come la cuenta.

## Cómo se midió

- **Simulación de ciclo completo con el código real del bot** (`SentinelEngine` de `bot/strategy.py`, sin cambios) sobre velas M15.
  - Del 1-mar al 16-oct de 2026; los datos van del 12-ene al 16-oct.
  - Cuentas de 1 000, 5 000 y 10 000 $, con la configuración de Supabase (idéntica a DEFAULTS, salvo el límite de Op4 en 20).
- **Arnés propio** (no versionado), basado en `bot_backtesting`:
  - broker con varios magics que comparten cuenta, margen y stop-out (50 %);
  - swap diario sacado de los deals reales del 14 al 19-oct (largo −77,4, corto +36,7 $/lote/noche, triple el miércoles);
  - spread fijo de 0,2 $ y comisión de 6 $/lote/lado.
- **Variantes:**
  - **base:** el bot de hoy;
  - **parejas:** la bolsa paga a la vez partes iguales de dos patas opuestas (Op1 + su cobertura, o recovery + Op4) cuando no hay recovery recortable;
  - **paralelo:** parejas + un segundo motor M15 (otro magic) que solo **abre** mientras el ciclo A está congelado (neto 0, ≥ 3 patas, en rojo). Cuando B cierra su ciclo en verde, el 90 % va a la bolsa de A.
- **Limitaciones:**
  - decisión solo al cierre de cada vela M15;
  - sin filtro de noticias (no hay calendario histórico) y sin el M5;
  - del 17-jun al 7-jul las velas M5 son sintéticas (el M15 solo usa el color de la última M5);
  - es **un solo camino de precios**: el orden de los hechos cambia mucho el resultado.

## Resultados

| Cuenta | Variante | Saldo final | Caída máxima | Margen mínimo | Días con A congelado | Ciclos B (ganados / perdidos) |
|---|---|---|---|---|---|---|
| 10k | base | 5 973 (−40 %) | −43 % | 238 % | 13 | — |
| 10k | parejas | **6 858 (−31 %)** | **−33 %** | 291 % | 13 | — |
| 10k | paralelo | 2 465 (−75 %) | −83 % | 165 % | 90 | 7 (5 / 2) |
| 5k | base | 3 058 (−39 %) | −42 % | 256 % | 13 | — |
| 5k | parejas | **3 471 (−31 %)** | **−33 %** | 310 % | 13 | — |
| 5k | paralelo | 943 (−81 %) | −92 % | 82 % | 88 | 16 (14 / 2) |
| 1k | base | 447 (−55 %) | −75 % | 282 % | 13 | — |
| 1k | parejas | 447 (−55 %) | −75 % | 281 % | 13 | — |
| 1k | paralelo | **102: stop-out el 23-mar** | −90 % | 48 % | 12 | 11 (11 / 0) |

## Qué pasó en cada escenario

### 1. Base: un ciclo de marzo congelado 7 meses

- **2-mar:** Op1 BUY 0,19 en 5 408. La cobertura entra en 5 334 (la distancia va en ATR, y el ATR era de unos 20 $).
- **3 al 23-mar:** caída del oro de 5 400 a 4 130 (−1 286 $).
  - La Op4 tendencia funciona muy bien: 20 Op4 cobran +3 958 $ y el curador recorta la recovery de 0,19 a 0,02 lotes.
  - **El 23-mar se agota el límite de 20 Op4.**
- **23-mar al 16-oct:** ni una operación más.
  - Quedan la pareja Op1 + Op2 congelada y 0,02 de recovery, que sigue perdiendo con la tendencia bajista.
  - El swap de la pareja (−77 + 37 $/lote/noche) cuesta unos **2 300 $** en 7 meses en la cuenta de 10k.
  - En todo el periodo el bot solo hace 29 operaciones.

### 2. Paralelo: los casos buenos existen, pero los malos dominan

- **Escenario bueno, mercado normal:** B cierra ciclos cortos en verde.
  - 30 de 34 ciclos B ganaron en las tres cuentas, y pasaron 842 $ (10k), 895 $ (5k) y 118 $ (1k) a la bolsa de A.
- **Escenario malo 1: B abre en el mismo mercado que congeló a A.**
  - En la caída de marzo, las señales de B también eran compras.
  - B queda atrapado igual que A: en 10k, del 26-mar al 31-ago y otra vez desde el 1-sep.
- **Escenario malo 2: el doble de exposición dispara las protecciones.**
  - Con dos ciclos abiertos baja la resistencia de la cuenta. Salta el candado de cesta, y sus disoluciones realizan pérdidas: −5 817 $ en 10k, −2 698 $ en 5k.
- **Escenario malo 3: la cuenta pequeña no aguanta dos ciclos.**
  - La de 1k llega a stop-out el 23-mar, con el margen en el 48 %.
- **Escenario malo 4: liberar A en mal momento.**
  - Cuando B y las parejas descongelan A en plena tendencia, A vuelve a abrir compras en la caída.
  - En 10k, las recoveries de A pierden −16 562 $, frente a −2 198 $ en la variante base.

### 3. Parejas sin ciclo paralelo

- Mejora en 10k y 5k (+9 puntos), sin cambiar casi nada más: mismos días congelado, más margen libre.
- En 1k no cambia: con 0,01 lotes la bolsa casi nunca llega a pagar una pareja.

## Conclusiones

1. **Descartar el ciclo paralelo.** Abre justo en el mercado que congeló al principal, duplica la exposición y en las cuentas pequeñas lleva al stop-out.
2. **El recorte por parejas merece diseño.** Mejora 9 puntos en 10k y 5k, y nunca empeora.
3. **El problema de fondo son los ciclos congelados durante meses:**
   - el bot deja de operar;
   - el swap de la pareja Op1 + Op2 desangra la cuenta;
   - la Op4 se queda sin cupo (20 en 3 semanas).

   Siguiente análisis propuesto: medir en esta misma simulación el límite de Op4 (20, 50, sin límite) y cómo salir de una pareja congelada antigua, por ejemplo con disolución por parejas pagada con lo que gana la Op4.
