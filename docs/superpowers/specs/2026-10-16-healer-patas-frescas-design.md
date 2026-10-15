# Diseño: el Healer no amputa patas recién abiertas y no pierde su presupuesto

**Estado:** PROPUESTA, pendiente de aprobación del usuario.

**Rama:** `experimento-2-rediseno`.

**Origen:** `docs/experimento-2/revision-cuentas-2026-10-16.md`, hallazgo 1.

## 1. Por qué

### Lo que se vio (14-oct, cuentas de 5 000 $ y 10 000 $)

Dos veces en cada cuenta, en el mismo segundo:
1. se abre una `Recovery Sell (V-Shape)`;
2. el Healer la cierra entera («Amputación Táctica»), perdiendo solo el spread (−1,8 a −6,2 $);
3. se abre otra recovery idéntica.

**Coste directo:** unos 19 $ entre spread y comisiones.

**Coste real:** el presupuesto de curación. Lo que ganó la recovery anterior (≈ 57 $ y 111 $) se gasta en cerrar una pata que no tenía pérdida de verdad.

### Causa (código actual, `bot/strategy.py`)

1. **El Healer solo actúa con 3 o más patas** (`healer_min_core = 3`).
   - Cuando una recovery se cierra con beneficio por su trailing, quedan 2 patas y el Healer espera.
   - El presupuesto (ese beneficio) queda pendiente.
2. **Se abre la siguiente recovery y vuelve a haber 3 patas**, así que el Healer se activa con el presupuesto pendiente.
3. **Elige la peor pata amputable.**
   - El par entrada + cobertura está protegido mientras el ciclo va en rojo, así que la única candidata es la recovery recién abierta.
   - Esa recovery va en rojo solo por el spread.
   - Como su pérdida por lote es mínima, el presupuesto alcanza para cerrarla entera.
4. **El presupuesto se pierde aunque no se use.**
   - El cursor de deals avanza en cada pasada, haya amputación o no.
   - Si en ese momento no hay pata amputable, porque la nueva recovery ya iba en verde, el beneficio de la recovery anterior desaparece del presupuesto.
   - Probablemente es lo que pasó a las 11:24 de servidor del 14-oct: no hubo amputación y el presupuesto de la recovery anterior se esfumó.
   - Lo mismo ocurre con el 10 % que nunca se gasta y con el sobrante cuando la pata elegida es más pequeña que el presupuesto.

## 2. Objetivos

- Que el Healer **solo ampute patas con pérdida real**, no ruido de spread.
- Que el **presupuesto del ciclo no se pierda**: lo que no se gasta hoy queda para la pata que de verdad lo necesite.
- **Respetar las reglas del usuario:**
  - el Healer cura con el **90 % del presupuesto del ciclo**;
  - solo con **core ≥ 3**;
  - el par entrada + cobertura y las patas LOCK siguen intocables.

**No-objetivos:**
- Cambiar qué patas se protegen.
- Cambiar el Unwind.
- Cambiar cuándo se abren las recoveries.

## 3. Comportamiento

### 3.1 Patas elegibles: pérdida real mínima

Una pata solo es amputable si su pérdida, medida en **movimiento de precio por onza**, alcanza `healer_min_move_usd`:

```
perdida_por_onza = -(profit + swap) / (volumen × tamaño_contrato)
elegible  <=>  perdida_por_onza >= healer_min_move_usd
```

- **Nuevo parámetro:** `healer_min_move_usd`, DEFAULT **2.0** $/oz.
  - Se expresa en movimiento de precio, como los demás umbrales del candado.
  - Valor 0 = comportamiento actual.
- **Por qué 2 $** (*decisión mía*):
  - el spread del oro ronda 0,2–0,35 $, así que 2 $ deja fuera el spread con mucho margen;
  - y sigue siendo menos de un tercio del ATR(M15) típico, así que una pata de verdad perdedora entra enseguida.
- Una pata que no llega al umbral **no se toca**, y el presupuesto **espera**.

### 3.2 Presupuesto del ciclo que no se pierde

El presupuesto pasa a ser una **bolsa del ciclo**, `healer_budget`, en $:

- **Entra:** cada deal ganador nuevo del magic suma `0,90 × beneficio`. Ahí se aplica la regla del 90 %, una sola vez.
- **Sale:** cada amputación resta lo que de verdad costó, es decir, la pérdida realizada de los lotes cerrados (`−money × fracción`).
- **No se toca:** si no hay pata elegible, la bolsa no cambia y se guarda para la siguiente pasada.
- **Se vacía:** al cerrar el ciclo, igual que hoy con el rebase del cursor.

**Mientras core < 3** el Healer sigue sin amputar. Los beneficios que lleguen en ese tiempo se suman a la bolsa al volver a core ≥ 3; hoy ya funciona así.

**Lotes a cerrar:** `floor(bolsa / coste_por_lote)`, en pasos del broker y con tope en el volumen de la pata. Si no cabe ni el lote mínimo, no se amputa y la bolsa espera.

**Reinicio del bot.** La bolsa vive en memoria; tras un reinicio empieza en 0, como hoy el cursor.
- *Decisión mía:* lo dejo así porque los reinicios son raros.
- Si es un error, el coste es curar menos en un ciclo que cruce un reinicio.

### 3.3 Log

- `HEALER` sigue igual en cada amputación y añade la bolsa restante: `... Lotes amputados: X. Bolsa restante: Y $`.
- **Nuevo:** una sola vez por ciclo, cuando hay bolsa pero ninguna pata alcanza el umbral:
  `Healer en espera: bolsa X $, ninguna pata con perdida >= 2.00 $/oz.`

## 4. Configuración

- **Nueva columna:** `bot_config.healer_min_move_usd` DOUBLE PRECISION, DEFAULT 2.0.
  - Va en `DEFAULTS` de `bot/strategy.py`, en `schema.sql` y en `supabase_schema.sql`.
- **Migración** `migrations/012_healer_min_move.sql`, idempotente: `ADD COLUMN IF NOT EXISTS`, más un ROLLBACK comentado (`healer_min_move_usd = 0`).
- **Sin la migración** el bot usa el DEFAULT 2.0 del código, porque recarga `bot_config` en caliente.

## 5. Tests (script-style, `python -m tests.test_healer`)

1. **Pata recién abierta:** con bolsa de 50 $, una recovery en rojo de 0,3 $/oz no se amputa y la bolsa sigue en 50 $.
2. **Pata con pérdida real:** la misma bolsa y una recovery a −5 $/oz. Se amputan `floor(50 / coste_por_lote)` lotes y la bolsa baja exactamente lo realizado.
3. **Bolsa que espera:**
   - sin pata elegible, un ganador de 40 $ deja la bolsa en 36 $;
   - otro de 20 $ la sube a 54 $;
   - después se amputa con 54 $.
4. **Regla del 90 %:** un ganador de 100 $ suma 90 $, no 100 $.
5. **Cierre de ciclo:** la bolsa se vacía y el ciclo nuevo empieza en 0.
6. **Interruptor:** con `healer_min_move_usd = 0`, la recovery recién abierta vuelve a ser amputable. Es el comportamiento actual, como referencia.
7. **Protecciones intactas:** el par entrada + cobertura y las patas LOCK siguen sin tocarse aunque haya bolsa y superen el umbral.
8. **Suites existentes en verde:** `test_supervivencia`, `test_ledger`, `test_m5_and_budget`, `test_mt5_prep` y `test_reentrada`.

## 6. Despliegue

Según el ciclo acordado:
1. implementar, commit y push;
2. el usuario aplica la migración 012;
3. `restart_all`, solo con su aprobación;
4. dejar correr.

**Qué mirar después:**
- que no haya amputaciones de patas recién abiertas;
- las líneas «Bolsa restante» y «en espera»;
- si la bolsa llega a curar parte de recoveries que de verdad pierden.

**Vuelta atrás:**
- sin código: `healer_min_move_usd = 0`;
- completa: revertir el commit + `restart_all`.

## 7. Riesgos

- **La bolsa puede curar más que hoy.** Al no perderse el presupuesto, la recovery que de verdad pierde recibe amputaciones más grandes. Es justo la intención del Healer, pero realiza más pérdida dentro del ciclo.
  - Lo acota la regla del 90 %: nunca se realiza más del 90 % de lo ganado en el ciclo.
- **Umbral fijo de 2 $** en mercados muy quietos: una pata de verdad perdedora podría tardar en llegar a 2 $. El efecto es solo esperar un poco más.
