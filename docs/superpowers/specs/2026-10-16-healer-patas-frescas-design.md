# Diseño: el Healer no amputa patas recién abiertas; bolsa solo con perdedor real

**Estado:** PROPUESTA v2, pendiente de aprobación del usuario.
- v1: bolsa del ciclo que espera aunque no haya a quién curar.
- v2, acordada con el usuario el 2026-10-16: la bolsa **solo existe mientras haya un perdedor real amputable**. Lo ganado sin perdedor queda como ganancia.

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
- Que el Healer **solo use ganancias obtenidas mientras existe un perdedor real** que se pueda curar. Lo que se gana sin perdedor queda como ganancia del ciclo y nunca se gasta después en curar.
- **Respetar las reglas del usuario:**
  - el Healer cura con el **90 %** de esas ganancias;
  - solo con **core ≥ 3**;
  - el par entrada + cobertura y las patas LOCK siguen intocables.

**No-objetivos:**
- Cambiar qué patas se protegen.
- Cambiar el Unwind.
- Cambiar cuándo se abren las recoveries.

## 3. Comportamiento

### 3.1 Perdedor real

Una pata es **perdedor real** si cumple las dos condiciones:
- **es amputable:** no pertenece a un par congelado ni es pata LOCK, y no la excluye la protección de cobertura (las mismas reglas que hoy);
- **su pérdida, medida en movimiento de precio por onza, alcanza `healer_min_move_usd`:**

```
perdida_por_onza = -(profit + swap) / (volumen × tamaño_contrato)
perdedor real  <=>  amputable  y  perdida_por_onza >= healer_min_move_usd
```

- **Nuevo parámetro:** `healer_min_move_usd`, DEFAULT **2.0** $/oz.
  - Se expresa en movimiento de precio, como los demás umbrales del candado.
  - Valor 0 = cualquier pata amputable en rojo cuenta, que es el comportamiento actual.
- **Por qué 2 $** (*decisión mía*):
  - el spread del oro ronda 0,2–0,35 $, así que 2 $ deja fuera el spread con mucho margen;
  - y sigue siendo menos de un tercio del ATR(M15) típico, así que una pata de verdad perdedora entra enseguida.

### 3.2 La bolsa solo existe mientras haya un perdedor real

En cada pasada del Healer:

1. **Se leen los deals ganadores nuevos del magic**, con el cursor de siempre. El cursor avanza siempre.
2. **Si ahora no hay ningún perdedor real:**
   - esas ganancias quedan como ganancia del ciclo y **no** entran en la bolsa;
   - si la bolsa tenía algo, por ejemplo porque el perdedor se recuperó por debajo de 2 $ o se cerró, **se libera**: vuelve a 0 y lo que quedaba es ganancia normal.
3. **Si hay perdedor real:**
   - cada ganancia nueva suma `0,90 × beneficio` a la bolsa;
   - el Healer amputa **una parte** del peor perdedor real.

**Cuánto se amputa:**
- `lotes = floor(bolsa / pérdida_por_lote)`, en pasos del broker y con tope en el volumen de la pata.
- Si no cabe ni el lote mínimo, no se amputa y la bolsa espera, mientras siga habiendo perdedor real.
- La bolsa baja exactamente lo realizado (`−money × fracción`).

Así, cada ganancia que llega mientras la pata pierde le recorta un trozo, y la pata se va cerrando poco a poco. Si no llegan ganancias suficientes, la pata no se elimina del todo por esta vía. La cierra el resto del ciclo: Unwind, cierre de cesta o candado.

**Core < 3:** el Healer sigue sin actuar.
- Al cerrarse una recovery con ganancia quedan 2 patas.
- Esa ganancia se ve en la siguiente pasada con core ≥ 3. En ese momento solo entra en la bolsa si ya hay un perdedor real; una recovery recién abierta no lo es.
- *Decisión mía:* lo dejo así. Con core < 3 solo queda el par protegido, así que en ese momento tampoco había a quién curar. Es coherente con la regla.

**Cierre del ciclo:** la bolsa vuelve a 0, como hoy el rebase del cursor.

**Reinicio del bot:** la bolsa vive en memoria y vuelve a 0, como hoy el cursor.
- *Decisión mía:* lo dejo así porque los reinicios son raros.
- Si es un error, el coste es curar algo menos en un ciclo que cruce un reinicio.

### 3.3 Log

- **En cada amputación,** `HEALER` sigue igual y añade la bolsa restante: `... Lotes amputados: X. Bolsa restante: Y $`.
- **Una vez por ganancia que no entra en la bolsa porque no hay perdedor real:**
  `Healer: ganancia X $ sin perdedor real (>= 2.00 $/oz): queda como ganancia.`
- **Cuando se libera una bolsa con saldo:**
  `Healer: bolsa Y $ liberada (ya no hay perdedor real).`

## 4. Configuración

- **Nueva columna:** `bot_config.healer_min_move_usd` DOUBLE PRECISION, DEFAULT 2.0.
  - Va en `DEFAULTS` de `bot/strategy.py`, en `schema.sql` y en `supabase_schema.sql`.
- **Migración** `migrations/012_healer_min_move.sql`, idempotente: `ADD COLUMN IF NOT EXISTS`, más un ROLLBACK comentado (`healer_min_move_usd = 0`).
- **Sin la migración** el bot usa el DEFAULT 2.0 del código, porque recarga `bot_config` en caliente.

## 5. Tests (script-style, `python -m tests.test_healer`)

1. **Recovery recién abierta:** un ganador de 57 $ con solo una recovery a −0,3 $/oz no amputa nada. La bolsa queda en 0 y se escribe el log de ganancia libre.
2. **Perdedor real:** una recovery a −5 $/oz y un ganador nuevo de 50 $. La bolsa sube a 45 $ y se amputan `floor(45 / pérdida_por_lote)` lotes. La bolsa baja exactamente lo realizado.
3. **Poco a poco:** tres ganadores sucesivos con el mismo perdedor real. Cada uno recorta un trozo y el volumen de la pata baja en cada pasada.
4. **Liberación:** con la bolsa en 10 $ (no cabe el lote mínimo), el perdedor vuelve a −1 $/oz. La bolsa pasa a 0 y se escribe el log de liberación.
5. **Ganancia previa al perdedor:** un ganador sin perdedor real, y luego la pata cae a −5 $/oz sin ganadores nuevos. No hay amputación: la ganancia anterior no se usa.
6. **Regla del 90 %:** un ganador de 100 $ con perdedor real suma 90 $ a la bolsa.
7. **Cierre de ciclo:** la bolsa vuelve a 0.
8. **Interruptor:** con `healer_min_move_usd = 0`, una recovery en rojo por spread vuelve a ser perdedor real (referencia del comportamiento actual).
9. **Protecciones intactas:** la entrada en rojo de un par congelado y las patas LOCK no cuentan como perdedor real, ni abren la bolsa ni se amputan.
10. **Suites existentes en verde:** `test_supervivencia`, `test_ledger`, `test_m5_and_budget`, `test_mt5_prep` y `test_reentrada`. Si algún test de `test_m5_and_budget` [13–14] asumía el comportamiento antiguo, se ajusta y se explica en el commit.

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

- **El Healer curará menos que hoy.** Las ganancias obtenidas antes de que aparezca un perdedor real ya no sirven para curar. Es intencionado: protege lo ganado. A cambio, una pata que se vuelve perdedora tarde, como la venta de 4 090 del 14-oct, solo se cura si después llegan ganancias nuevas.
- **Umbral fijo de 2 $** en mercados muy quietos: una pata de verdad perdedora puede tardar en contar. El efecto es solo esperar un poco más.
