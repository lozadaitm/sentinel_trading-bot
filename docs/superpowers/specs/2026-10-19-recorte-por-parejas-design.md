# Diseño: recorte por parejas en el curador (Healer)

**Estado:** PROPUESTA, pendiente de aprobación del usuario.

**Rama:** `experimento-2-rediseno`.

**Origen:**
- `docs/experimento-2/analisis-ciclo-paralelo-2026-10-19.md`
- `docs/experimento-2/analisis-limite-op4-y-entrada-op1-2026-10-19.md`

## 1. Por qué

**El problema:** hoy el curador solo puede recortar patas cuyo cierre **reduce** la exposición neta, en la práctica la recovery. Hay dos pérdidas congeladas que no puede tocar nunca:
- **La pareja Op1 + su cobertura (Op2):** está congelada mientras el ciclo vaya en rojo. Cerrar una sola de las dos dejaría a la otra desnuda.
- **La recovery + una Op4 (T) abierta:** se anulan entre sí, así que cerrar cualquiera de las dos sube el neto.

Si la bolsa tiene dinero pero solo quedan pérdidas de este tipo, hoy pasa una de dos cosas:
- se libera como ganancia;
- o espera, si hay una Op4 (T) abierta.

Mientras tanto, la pareja congelada sigue pagando swap: unos 2 300 $ en 7 meses en la simulación de 10k.

**La idea:** cerrar **a la vez la misma cantidad de lotes de dos patas opuestas**. El neto no cambia y se paga un trozo de la pérdida congelada con la bolsa.

**Lo que dijo la simulación** (ciclo completo con el motor real, del 1-mar al 16-oct, ya con Op4 sin límite):

| Cuenta | Sin recorte por parejas | Con recorte por parejas |
|---|---|---|
| 10k | 6 445 (−36 %, caída máx. −37 %) | **7 061 (−29 %, −30 %)** |
| 5k | 3 261 (−35 %, −36 %) | **3 674 (−27 %, −28 %)** |
| 1k | 651 (−35 %) | 651 (−35 %): con 0,01 lotes la bolsa casi nunca llega |

No empeoró en ninguna cuenta.

## 2. Objetivos y no-objetivos

**Objetivos:**
- Que la bolsa del curador pueda pagar partes iguales de dos patas opuestas cuando no hay ningún perdedor que recortar por la vía actual.
- Que el neto no cambie nunca, tampoco si una de las dos órdenes falla.

**No-objetivos:**
- **No cambia la amputación actual de la recovery,** que mantiene la prioridad.
- **No toca las patas LOCK del candado:** esas las gestiona la disolución.
- **No hay cierres de emergencia ni stops** (reglas del usuario).
- **Las ganancias del M5 no alimentan la bolsa,** porque son de otro bot.

## 3. Comportamiento

### 3.1 Cuándo

Dentro de `_check_healing` / `_heal_with`, en el punto en que hoy **no hay perdedor real amputable** (`_healer_target` devuelve `None`).

Orden nuevo en ese caso:
1. La ganancia nueva (90 %) se suma a la bolsa.
2. Si hay una **pareja válida** con pérdida real, se intenta el recorte por parejas (3.3).
3. Si no hay pareja y hay una Op4 (T) abierta, la bolsa espera (como hoy).
4. Si no hay pareja ni Op4 (T), la bolsa se libera como ganancia (como hoy).

**Cuándo no se hace:**
- con candado CONGELADO, porque el curador ya no corre;
- con el freno de volatilidad activo;
- con una deuda de pareja pendiente (3.4).

### 3.2 Parejas válidas

Una pareja son dos patas de lados opuestos, del mismo magic, sin ninguna pata LOCK. Hay dos tipos:
- **(a) Pareja de cobertura:** un HEDGE y la pata que cubre, según el ledger (`CycleLedger.pairs()`). Normalmente es Op1 + Op2.
- **(b) Pareja suelta:** una pata RECOVERY o RESCUE de cada lado, que no pertenezcan a ninguna pareja de cobertura. Normalmente es recovery + Op4 (T).

No se mezclan tipos: por ejemplo, la Op1 nunca se empareja con una Op4. En la simulación, mezclarlos hacía que el bot reajustara después el tamaño de la cobertura y cambiaba el neto.

**Pérdida de la pareja por lote:** `coste = −(dinero_a / vol_a + dinero_b / vol_b)`, con `dinero = profit + swap`.
- La pareja es válida si `coste / tamaño_contrato ≥ healer_min_move_usd` (2 $/oz, la misma regla de «perdedor real»).
- Si hay varias, se elige la de **mayor coste por lote**.

### 3.3 Recorte

1. `lotes = floor(bolsa / coste / paso) · paso`, sin pasar de `min(vol_a, vol_b)`.
2. Si `lotes < lote mínimo`, no se cierra nada y **la bolsa espera**: no se libera mientras exista la pareja.
3. Se cierra **primero el miembro rojo** y luego el verde, con los mismos lotes.
   - Se reutiliza `_dissolve_close`, con el comentario de orden parametrizado: `Healer Pair Cut`.
   - Si falla el primero, no se cierra nada y se reintenta en `DISSOLVE_RETRY_S`.
4. Contabilidad:
   - lo realizado (suma de las dos partes) va a `cycle_realized`;
   - la bolsa baja exactamente en la pérdida realizada.
5. Log `HEALER`: «Recorte por parejas: X lotes de #A + #B (−Y $). Bolsa restante Z $.»
6. Como mucho una pareja por tick. La siguiente se hace en el tick siguiente, si la bolsa alcanza.

### 3.4 Fallo del segundo cierre

Se hace igual que la deuda de la disolución (R14):
- Se persiste en el meta del ciclo `pair_cut_pending = {side, lots, tickets, net_before}`.
- Mientras exista, solo se reintenta cerrar ese resto, con espera de 60 s, sin pasarse del neto previo, y no se empieza otra pareja.
- Si las patas desaparecen o el neto ya volvió a su valor previo, la deuda se descarta y queda en el log.
- Alerta `CRITICA` (como `disolucion_fallida`), porque mientras tanto el neto está desviado.

### 3.5 Relación con lo demás

- **Recovery con perdedor real:** sigue mandando la amputación actual. El recorte por parejas solo actúa cuando ella no puede.
- **Unwind / cierre de cesta:** sin cambios. Si el ciclo pasa a verde, `protect_cover` se apaga y el Unwind desarma los pares como hoy.
- **Ajuste del tamaño de la cobertura (`_resize_hedge`):** al recortar la Op1 y la Op2 a la vez, la cobertura nunca queda mayor que la entrada, así que no se dispara.
- **Persistencia:** la bolsa y el cursor ya se guardan en el meta del ciclo (arreglo del 19-oct).

## 4. Configuración

- **Migración `migrations/015_recorte_parejas.sql`:** `healer_pair_cut BOOLEAN DEFAULT true`. Idempotente.
- **Vuelta atrás comentada:** `UPDATE bot_config SET healer_pair_cut = false WHERE bot_id = 'm15';`, con recarga en caliente.
- El DEFAULT del código es `true`. También va en `schema.sql` y `supabase_schema.sql`.

## 5. Tests (`python -m tests.test_pair_cut`, estilo script)

1. **Op1 + Op2 congeladas,** recovery en verde y bolsa suficiente: recorta X lotes de las dos. El neto no cambia y la bolsa baja en lo realizado.
2. **Recovery SELL + Op4 (T) BUY:** recorta las dos por igual.
3. **Nunca mezcla tipos:** la Op1 no se empareja con una Op4 ni con una recovery.
4. **Bolsa por debajo del lote mínimo:** no cierra y la bolsa **no** se libera.
5. **Pareja con pérdida < 2 $/oz:** no es válida. La bolsa se libera, salvo que haya Op4 (T).
6. **Recovery con perdedor real:** manda la amputación; no hay recorte por parejas.
7. **Patas LOCK:** nunca entran en una pareja.
8. **Primer cierre rechazado:** no se cierra nada y se reintenta tras la espera.
9. **Segundo cierre rechazado:** queda la deuda `pair_cut_pending`. El tick siguiente solo reintenta la deuda y no empieza otra pareja. Al cerrarla, el neto vuelve al previo.
10. **Freno de volatilidad activo:** no recorta.
11. **`healer_pair_cut = false`:** comportamiento idéntico al de hoy.
12. **Suites existentes en verde.**

## 6. Despliegue y evaluación

**Pasos:**
1. implementar, commit y push;
2. el usuario aplica la migración 015;
3. reinicio con su aprobación.

**Ciclo abierto del 14-oct:** con la Op4 (T) abierta, la pareja recovery + Op4 será válida en cuanto su pérdida conjunta llegue a 2 $/oz. Ya la supera: unos −93 $/oz. Por tanto, la bolsa en espera (237 $ en 10k, 119 $ en 5k) se usará en el primer tick:
- **10k:** 237 $ / ~9 300 $ por lote ≈ 0,02 lotes de recovery + 0,02 de Op4;
- **5k:** 0,01 + 0,01;
- **1k:** espera.

**Qué mirar:**
- los logs «Recorte por parejas»;
- que no aparezca ninguna deuda pendiente;
- que el neto quede igual tras cada recorte;
- el swap acumulado de las parejas.

**Vuelta atrás:** `healer_pair_cut = false`.

## 7. Riesgos

- **Dos órdenes en vez de una:** el riesgo de quedar a medias se cubre con la deuda persistida (3.4), igual que en la disolución.
- **Realiza pérdidas:** cada recorte pasa pérdida flotante a realizada. El equity no cambia, pero el balance baja.
- **Simulación aproximada:** velas M15, sin noticias ni M5, y un solo camino de precios. La mejora (+7–8 puntos) es de una simulación, no una garantía.
