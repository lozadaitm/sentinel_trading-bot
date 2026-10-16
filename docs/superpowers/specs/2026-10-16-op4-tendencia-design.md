# Diseño: Op4 a favor del movimiento («Op4 tendencia»)

**Estado:** APROBADO por el usuario el 2026-10-16. Implementado (código, tests, migración 014).
- Sin modo observación, a petición del usuario.
- Se aplica también al ciclo abierto del 14-oct: el usuario lo decidió porque ese ciclo llevaba días bloqueado.

**Rama:** `experimento-2-rediseno`.

**Origen:** `docs/experimento-2/analisis-op4-direccion-2026-10-16.md` y `analisis-recoveries-2026-10-16.md`.

## 1. Por qué

**Lo que hace hoy la Op4** (`_check_rescue`):
- copia la última pata del ciclo, la recovery: misma dirección y mismo volumen;
- en L3 la abre al instante.

Es una martingala, con dos problemas:
1. **Cuando el movimiento es grande, el tope de supervivencia la bloquea**, porque aumenta la exposición. Justo cuando más falta haría (14-oct), no puede actuar.
2. **Si pudiera abrir, empeoraría los desastres:** en la simulación, −5 a −82 $/oz en el 14-oct.

**Lo que haría la Op4 tendencia en la simulación** (245 recoveries reales, 46 episodios):
- **14-oct, cuenta de 10 000 $:** la pérdida de la recovery pasa de unos −2 080 $ a unos −370 $;
- **total del historial:** +394 $/oz frente a −226;
- **es un seguro:** gana mucho en 3 episodios de tendencia fuerte y pierde un poco en la mayoría de los demás (peor episodio −43 $/oz).

**Por qué funciona:**
- abre en la dirección contraria a la pata que pierde, y por eso **reduce** la exposición neta; el tope de supervivencia la deja pasar siempre;
- cada ganancia que cobra va al curador (90 %), que recorta la recovery perdedora.

## 2. Objetivos y no-objetivos

**Objetivos:**
- Sustituir la Op4 de copia por una Op4 que opera en la dirección contraria a la pata del ciclo que más pierde (es decir, a favor del mercado).
- Que se cobre con trailing por ATR, sin stop.
- Que sus ganancias alimenten al curador con las reglas actuales (90 %, perdedor real ≥ 2 $/oz, core ≥ 3).

**No-objetivos:**
- **Order blocks / ruptura de estructura como confirmación:** en la simulación no mejoraron a la entrada al cierre de vela. Quedan fuera; se pueden añadir después con datos de 1 minuto.
- **Cambios en recovery, cobertura, curador, Unwind, candado o tope de supervivencia.**
- **Stop o cierre de emergencia:** no hay ninguno (reglas del usuario).

## 3. Comportamiento

### 3.1 Interruptor

- **Nuevo parámetro:** `rescue_mode`, con los valores `trend` (nuevo, DEFAULT) o `copy` (el de hoy, intacto).
- **En modo `trend`,** el bot no abre ninguna Op4 de copia. Las que ya estuvieran abiertas siguen gestionándose como hoy.

### 3.2 Cuándo abre (modo `trend`)

Se evalúa **una vez por vela M15 cerrada**, en ESTADO 3+ (dentro de `_check_rescue`). Abre si se cumple todo lo siguiente.

**Puertas que se mantienen:**
- `use_rescue_mode`;
- sin spread alto, freno de volatilidad, close-only ni ventana de noticia;
- candado `LIBRE`: con candado vivo no hay Op4 tendencia, porque el candado ya neutraliza y el trailing de la Op3 se desactiva;
- cuenta no muerta (`_open_additive`).

**Puerta que se quita:**
- las horas de riesgo.
- *Decisión mía:* la Op4 tendencia no promedia, sino que reduce la exposición, y los movimientos fuertes de la sesión de NY son justo donde rinde.

**Condiciones nuevas:**
1. **No hay otra Op4 tendencia abierta en el ciclo.** Solo una cada vez; así el curador puede recortar entre una y otra (ver 3.5).
2. **Hay una pata objetivo:** la pata RECOVERY o RESCUE del ciclo con peor $/oz que esté a `rescue_trend_k_atr` (DEFAULT **2,0**) × ATR M15 o más en contra.
   - Se mide con el cierre de la última vela M15 cerrada.
   - Quedan excluidas las patas de un par entrada + cobertura y las patas LOCK, igual que en el curador.
3. **Cupo:** `rescue_opened` < `rescue_trend_max_legs` (DEFAULT **6** por ciclo).
4. **Cooldown:** el `rescue_cooldown` de siempre (30 s).

**Dirección:** la contraria a la pata objetivo.

**Tamaño:** `min(volumen de la pata objetivo, |neto del ciclo|)`, redondeado al paso del broker.
- Así la Op4 nunca da la vuelta a la exposición: como mucho la deja en cero.
- Si no llega al lote mínimo, no abre.

**Apertura:**
- por `_open_additive` (rol RESCUE, tope de supervivencia y gobierno de margen como hoy);
- comentario `Sentinel Op 4 (T)`. El ledger lo reconoce como RESCUE por el prefijo «Sentinel Op 4».

### 3.3 Cómo sale

Usa el trailing de la Op3 ya existente, que trailea la última pata del ciclo, que será la Op4. Cuando esa pata es una Op4 tendencia, se aplican parámetros propios:
- arranque a `rescue_trend_trail_start_atr` (DEFAULT **1,0**) × ATR;
- distancia de `rescue_trend_trail_dist_atr` (DEFAULT **0,5**) × ATR;
- sin turbo;
- con el mismo ATR M15 actual (`_effective_atr`) que usa la Op3.

**Sin stop.** Si el precio se da la vuelta, la Op4 pierde, pero la pata objetivo gana lo mismo: actúa como un candado parcial.
- El curador no la toca: cerrarla aumentaría la exposición, y está protegida por la regla de cobertura existente.
- La cierra el cierre de cesta del ciclo, o el Unwind si el ciclo pasa a verde.

### 3.4 Cierre del ciclo

Sin cambios: la cesta cierra todo al llegar a su objetivo, como hoy con profundidad ≥ 4.

### 3.5 Curador

Sin cambios de código. Funciona así:
- el curador corre en cada tick **antes** de la máquina de estados;
- cuando el broker cierra la Op4 por trailing, en el siguiente tick el curador ve la ganancia y la Op4 ya no está;
- la recovery vuelve a ser recortable (cerrarla reduce la exposición) y se amputa un trozo con el 90 %;
- después, en la siguiente vela cerrada, puede abrirse otra Op4, del tamaño de lo que queda de la recovery.

*Riesgo conocido:* si queda un resto de bolsa que no llega al lote mínimo y se abre la siguiente Op4, la recovery deja de ser recortable en ese momento. El curador lo trata como «sin perdedor real» y libera ese resto como ganancia. Es poco dinero, y lo acepto para no tocar el curador.

### 3.6 Log

- **Al abrir,** con el mismo tipo de log que usa hoy la Op4:
  `Op4 tendencia: BUY X lotes @ P contra la recovery #T (−Y $/oz, Z ATR). Op4 n/6 del ciclo.`
- **Una vez por ciclo,** si el cupo de 6 se agota: `Op4 tendencia: cupo del ciclo agotado.`
- El trailing y las amputaciones ya tienen sus logs.

## 4. Configuración

- **Migración** `migrations/014_op4_tendencia.sql`, idempotente:

| Columna | Tipo | DEFAULT |
|---|---|---|
| `rescue_mode` | TEXT | `'trend'` |
| `rescue_trend_k_atr` | DOUBLE PRECISION | 2.0 |
| `rescue_trend_max_legs` | INTEGER | 6 |
| `rescue_trend_trail_start_atr` | DOUBLE PRECISION | 1.0 |
| `rescue_trend_trail_dist_atr` | DOUBLE PRECISION | 0.5 |

- **ROLLBACK** comentado: `UPDATE bot_config SET rescue_mode = 'copy' WHERE bot_id = 'm15';`. Se recarga en caliente, sin reinicio.
- **Sin la migración,** valen los DEFAULT del código (modo `trend`).
- Los DEFAULT también van en `DEFAULTS` de `bot/strategy.py`, en `schema.sql` y en `supabase_schema.sql`.

## 5. Tests (script-style, `python -m tests.test_op4_trend`)

1. **Dispara:** recovery SELL a −2,1 ATR → abre BUY. A −1,9 ATR no abre.
2. **Tamaño:** recovery 0,22 con neto −0,22 → 0,22. Con neto −0,10 → 0,10. Con neto < mínimo → no abre.
3. **Dirección:** recovery BUY perdiendo → abre SELL.
4. **Una sola abierta:** con una Op4 (T) viva no se abre otra.
5. **Cupo:** con `rescue_opened` = 6 no abre y escribe el log del cupo una sola vez.
6. **Puertas:**
   - no abre con noticia, freno de volatilidad, spread alto o candado vivo;
   - sí abre en hora de riesgo.
7. **Pares y LOCK:** una entrada perdedora de un par congelado no es objetivo.
8. **Una vez por vela:** dos ticks en la misma vela cerrada no evalúan dos veces.
9. **Trailing propio:** la Op4 (T) como última pata usa 1,0/0,5 ATR. Una recovery como última pata sigue usando 0,6/0,4.
10. **Curador encadenado:** la Op4 (T) cierra con +X → el siguiente tick amputa la recovery con 0,9X → la siguiente vela abre una Op4 del volumen restante.
11. **Interruptor:** con `rescue_mode = 'copy'`, el comportamiento es idéntico al de hoy (misma Op4 L1/L2/L3).
12. **Tope de supervivencia:** la Op4 (T) pasa con S por debajo de 350, porque reduce el neto.
13. **Suites existentes en verde:** `test_supervivencia`, `test_ledger`, `test_m5_and_budget`, `test_mt5_prep`, `test_reentrada`, `test_healer` y `test_m5_trailing`. Si alguna asumía la Op4 de copia, se fija `rescue_mode = 'copy'` en ese test y se explica en el commit.

## 6. Despliegue y evaluación

**Ciclo acordado** (sin modo observación, a petición del usuario):
1. implementar, commit y push;
2. el usuario aplica la migración 014;
3. `restart_all`, con su aprobación;
4. dejar correr.

**Ciclo abierto del 14-oct (decisión del usuario):**
- Si el modo `trend` le aplica, en la primera vela M15 cerrada tras el reinicio comprará el volumen de la recovery (0,22 en la cuenta de 10 000 $) cerca de 4 175–4 185.
  - Eso congela la pérdida actual, unos −2 080 $ en esa cuenta.
  - Solo cobra si el oro sigue subiendo.
  - Si el oro vuelve hacia 4 078, la recovery mejora pero la Op4 pierde lo mismo: se pierde la salida «esperar a que vuelva».
- La alternativa es aplicarlo solo a los ciclos que empiecen después del reinicio. Se haría con un parámetro `rescue_trend_since` (hora de servidor) y una comprobación sobre la hora de la entrada del ciclo.

**Qué mirar:**
- los logs «Op4 tendencia»;
- las amputaciones encadenadas («Bolsa restante»);
- el volumen de recovery que queda;
- el P&L de cada ciclo con Op4.

**Criterio de evaluación:**
- los ciclos que llegan a recovery −2 ATR deben acabar mejor que la recovery sola;
- ningún ciclo debe empeorar más de ~45 $/oz por la Op4, que fue el peor episodio simulado.

**Vuelta atrás:**
- sin código: `rescue_mode = 'copy'`;
- completa: revertir el commit + `restart_all`.

## 7. Riesgos

- **Muestra pequeña:** 8 episodios graves en 4 meses. Si no vuelven tendencias así, la Op4 tendencia cuesta un poco en muchos ciclos.
- **Simulación con velas M15,** sin spread ni swap, y sin modelar el resto del ciclo (Unwind, cesta, candado). En vivo el resultado puede ser algo peor.
- **Exposición neta cerca de cero** mientras la Op4 está abierta: el ciclo deja de beneficiarse de una vuelta del precio hasta que la Op4 se cierra.
- **Swap:** la Op4 paga o cobra swap como cualquier pata. En holds largos puede pesar.
