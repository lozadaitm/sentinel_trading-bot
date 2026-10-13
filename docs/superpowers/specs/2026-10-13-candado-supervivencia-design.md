# Diseño — Tope de supervivencia, candado de cesta y umbrales en movimiento de precio

Fecha: 2026-10-13 · Rama: `experimento-2-rediseno` · Estado: **borrador para aprobación**
Bot afectado: `bot/strategy.py` (M15, magic 100100), `bot/ledger.py`, `bot/budget.py`,
`bot/strategy_m5.py` (M5, magic 100200), `bot/notify.py`, `bot/main.py`, migración nueva.

Evidencia: [informe de las 3 cuentas](../../experimento-2/audit/informe-3-cuentas.md),
[sesiones y AMD](../../experimento-2/analisis/informe-sesiones-amd.md) y el análisis de esta
sesión, resumido en §2.

---

## 1. Intención

Dos de las tres cuentas demo se liquidaron en agosto. **No fue por falta de stops, sino por
exceso de exposición neta:**

- el tope `max_net_lots = 1.0` es un lote fijo para cualquier cuenta;
- las Op3/Op4 no tienen cobertura propia;
- el Unwind las cobraba una por una y dejaba patas desnudas.

Además, varios umbrales en dólares fijos hacían que cuentas de distinto tamaño se comportaran
distinto ante el mismo movimiento del precio.

El usuario **rechaza stops y cierres de emergencia**, y su filosofía es "la Op2 congela la
pérdida". Este diseño extiende esa filosofía a toda la cesta:

1. **No añadir** exposición que la cuenta no pueda aguantar (tope de supervivencia).
2. **Congelar** la cesta entera si, aun así, el precio se acerca a la liquidación (candado).
3. **Volver a exponerse solo con un rebote confirmado**, nunca a favor de la tendencia que
   está dañando.
4. **Medir todo en movimiento del precio**, para que todas las cuentas hagan lo mismo ante el
   mismo precio, sin importar su capital.

Nada en este diseño cierra posiciones en pérdida para "frenar". Las únicas formas de realizar
pérdida son las que ya existen:

- las amputaciones del Healer;
- el cierre total en positivo;
- la nueva disolución por parejas (§5.5), que no cambia el equity.

## 2. Evidencia que lo justifica (resumen)

| Hallazgo | Dato |
|---|---|
| Movimiento en contra que liquidaba a 25912766 (6 000 $, 0,79 lotes netos) | ~61 $ |
| Movimiento en contra que liquidaba a la base (12 538 $, 0,84 lotes netos) | ~119 $ |
| Lo que se mueve el oro en contra (máx. excursión en un sentido), ene–jun 2026 | 8 h: p50 50 $ / p90 125 $ · 24 h: p50 94 / p90 217 / p99 583 · 48 h: p50 144 / p90 332 |
| Quiebra de 25912766 | El ciclo nació el 17-ago 07:38 UTC; 14 Recovery + 9 Op4; murió el 19-ago 01:02 UTC. 48 h después el precio estaba **+126 $ a favor** |
| Quiebra de la base | 19-ago 12:57–13:11 UTC: **14 Op4 de 0,44** abiertas y cobradas en segundos (bucle). Quedaron 2 ventas desnudas, que se liquidaron el 21-ago tras **165 $ en contra** sin rebote |
| Op2 tras el ledger por roles (11-ago) | Ya congela: el lock estuvo puesto 17 h de mediana (antes: 0,3 h). El par Op1–Op2 es atómico. **El hueco son las Op3/Op4** |
| 174 Hedge Locks reales | En ~50 % de los casos el precio volvió a la entrada de la Op1 (mediana 4–6 h). Lo que siguió en contra ≈ lo que rebotó (p50 ~30 $). Sin sesgo direccional |
| Swap medido | BUY −53 $/lote/noche, SELL +30 $/lote/noche → una cesta cubierta paga ~23 $/lote/noche |
| Noticias (Fase 1, observación) | 10 rojas USD, 13-ago → 30-sep. El log funcionó en las 3 cuentas. Un ciclo malo nació de una noticia (Core PPI 13-ago: 20 patas, −660 $). **Ninguna quiebra coincidió con noticia** |
| Horas violentas | 01 UTC y 13–15 UTC (perfil horario ene–jun). El bucle de Op4 de la base fue a las 13 UTC |

Limitación: para ago–sep solo hay precios dispersos de `bot_logs`. Las velas siguen bloqueadas
por el error `-6` de MT5 (D9 del informe), así que las cifras posteriores a la quiebra son
aproximadas.

## 3. Objetivos, no-objetivos y anti-objetivos

**Objetivos**
- Que ninguna cuenta pueda liquidarse por un movimiento menor que `survival_move_usd`
  (350 $ de oro) **por exposición que el bot añadió**.
- Que, si el precio se acerca a la liquidación, la cesta quede congelada (exposición neta ≈ 0)
  antes de que ocurra.
- Que cuentas de 1 000 $, 5 000 $ o 50 000 $ tomen las mismas decisiones en el mismo momento
  ante el mismo precio.
- Que la rentabilidad porcentual no caiga al crecer la cuenta: ningún tope en lotes fijos.
- Que el operador se entere por correo cuando algo va mal.

**No-objetivos**
- No se cambia la lógica de entrada de la Op1 ni las señales de Op3/Op4 (salvo los gates
  nuevos).
- No se rediseña el M5 más allá del tope compartido.
- No entran el arnés de agentes IA (Fase 2), Kronos/AMD/sesiones como señal ni NewsGuard
  Fase 2.

**Anti-objetivos (sería un fracaso aunque "funcione")**
- Que algo cierre posiciones en pérdida para cortar el riesgo (stop o cierre de emergencia
  encubierto).
- Que el candado se quite porque "su pata está en verde": eso solo re-expone a favor de la
  tendencia dañina (ver §5.4).
- Que el Unwind, el Healer o cualquier trailing desmonten el candado por su cuenta y vuelvan
  a dejar patas desnudas.
- Que un candado que no entra (por margen) genere miles de errores en el log, como los 12 970
  `retcode 10019` de 25912766.

## 4. Restricciones (no negociables)

- Sin cierre de emergencia, sin stop de cesta por drawdown y sin SL catastrófico
  ([`bot-design-constraints`](../../memory/bot-design-constraints.md)).
- La Op2 congela. El Healer cura con el 90 % del presupuesto del ciclo y solo con `core >= 3`.
  El freeze del Unwind usa `cycle_realized + basket_net`.
- Las órdenes **protectoras** (Hedge Lock y ahora el candado) nunca se bloquean por presupuesto,
  tope ni filtro. Se intentan siempre y decide el bróker.
- Los magics siguen hardcodeados. La config vive en columnas de `bot_config` (una fila por
  usuario y bot), con fallback a `DEFAULTS`.
- No correr backtests salvo que el usuario lo pida.
- Ciclo de pruebas: implementar → commit → push → `restart_all` → días en demo → revisar → decidir.
  Rollback: checkout de `experimento-1-grinder` + `restart_all`.
- No reiniciar bots hasta que el usuario apruebe el código.

## 5. El diseño

### 5.1 Medida central: "aguante" de la cuenta (S)

S es cuántos dólares de movimiento del oro en contra soporta la cuenta antes del stop-out, con
la exposición actual:

```
S = (equity − stop_out% × margen / 100) / (|neto_lotes| × contract_size)
```

- `equity`, `margen` y `stop_out%` son los de la **cuenta entera**, vía
  `account_info().margin_so_so` (`broker.stop_out_levels()`).
- `neto_lotes` = compras − ventas de **todas** las posiciones del símbolo en la cuenta, de los
  dos magics. M15 y M5 comparten el stop-out.
- `contract_size` = `symbol_info().trade_contract_size` (100 en XAUUSD+).
- Si `|neto_lotes| < volume_step`, S = ∞.
- Para evaluar una orden hipotética, se suma su volumen al neto y su margen
  (`order_calc_margin`) al margen actual. Esto ignora el descuento por cobertura, así que
  queda del lado conservador.

Los parámetros nuevos van en "$ de movimiento del oro". En la documentación y la UI se puede
mostrar su equivalente en pips (1 pip = 0,10 $).

### 5.2 Tope de supervivencia (sustituye a `max_net_lots`)

Toda orden **aditiva** (Op1, Op3, Op4 y scalp del M5) solo se abre si, después de abrirla,
`S >= survival_move_usd` (default **350**).

- **Tamaño dinámico:** se abre `min(lote_pedido, lote_máximo_que_cabe)`, redondeado hacia
  abajo a `volume_step`. Si lo que cabe es menor que `volume_min`, no se abre.
- **No se espera** a que quepa entera. La pata siguiente vuelve a pedir su tamaño normal.
- Una orden que **reduce** `|neto|` siempre está permitida, igual que hoy en `_net_cap_ok`.
- **Log** de cada recorte y cada bloqueo: *"Op3 reducida 0,20 → 0,15 por tope de
  supervivencia (S=…)"* / *"Op4 bloqueada: no cabe 0,01"*. Con dedupe por motivo, como
  `MarginGovernor._block`.
- `max_net_lots` queda obsoleto (default 0 = desactivado).
- **Decisión mía:** `max_entry_lots` (1,0), `max_recovery_lots` (2,0) y `m5_max_lot_cap`
  (0,50) también pasan a 0 = desactivados. Son topes en lotes fijos que frenarían la
  rentabilidad porcentual de cuentas grandes. El tope de supervivencia ya gobierna el riesgo.
  `volume_max` del bróker sigue aplicando.
- El cálculo es de cuenta, así que el M5 usa la **misma** comprobación (helper común,
  p. ej. en `budget.py`).
- **Reparto entre bots (decisión mía; mantiene que el M15 es el senior de `budget.py`):** sea
  `N_max` el neto de cuenta que deja S = 350. Cada bot puede sostener como mucho
  `equity_weight × N_max` de neto **propio**: M15 0,8 y M5 0,2 con la config actual. Además debe
  cumplirse la comprobación de cuenta (S ≥ 350 tras la orden). Así el M5 no puede comerse el
  espacio que necesita el M15.

Ejemplos con 350 $ (aprox., sin margen): 1 000 $ → ~0,02 lotes netos; 5 000 $ → ~0,11;
12 500 $ → ~0,28; 50 000 $ → ~1,1. El tope crece en proporción al capital.

### 5.3 Candado de cesta (nuevo rol `LOCK`)

**Cuándo se pone:** cuando `S < lock_trigger_usd` (default **150**) y el neto del M15 no es
cero.

**Qué hace:**
- abre una orden **protectora** en sentido contrario al neto **del M15** (magic 100100), por
  `|neto_M15|`, con comment `"Basket Lock"`;
- la registra en el ledger con rol `ROLE_LOCK`, que persiste en el JSON y se rehidrata por
  comment;
- el neto del M15 queda en 0.
- **Decisión mía:** el M5 no se cubre. Lleva SL y sus scalps son pequeños, pero su exposición
  sí cuenta en S.

**Si ya hay candado y S vuelve a bajar de 150** (por ejemplo, tras un aflojado), se añade otra
pata `LOCK` por el neto restante. Puede haber varias patas `LOCK`. Se tratan como un bloque.

**Margen:**
- Antes de enviar el candado se hace `order_check`. Si el bróker lo rechaza, se reintenta cada
  tick, pero el **log se deduplica**: un mensaje al primer fallo y luego uno cada 10 min con
  el mismo motivo. Además se envía una alerta por correo (§5.9).
- Al arrancar se loguea `margin_hedged` del símbolo (`broker.hedged_margin_rate()`), para
  confirmar cuánto margen cobra Vantage por posiciones cubiertas.

**Estados (decisión mía).** Hay tres estados, según las patas `LOCK` vivas y el neto del M15:

- **LIBRE:** no hay patas `LOCK`. Operativa normal, con los gates nuevos.
- **CONGELADO:** hay patas `LOCK` y `|neto_M15| < volume_step`. Aplica la tabla de abajo.
- **AFLOJADO:** hay patas `LOCK`, pero el neto ya no es cero porque se aflojó en parte (§5.4).
  - Funciona como LIBRE: Op3/Op4 con tope y horas de riesgo; Unwind con la comprobación de S
    (§5.6); Healer.
  - Excepción: las patas `LOCK` son **intocables** para el Unwind y el Healer (igual que un
    par Op1–Op2).
  - El trailing de Op3 sigue desactivado mientras viva alguna pata `LOCK`.
  - Solo se cierran por un nuevo aflojado (§5.4), por la disolución (§5.5) o por un cierre
    total.

**En estado CONGELADO:**

| Subsistema | Comportamiento |
|---|---|
| Op1 / Op3 / Op4 nuevas | **Bloqueadas** |
| Hedge monitor de la Op1 y watchdog de huérfanos | **No abren** hedges: el candado ya cubre todo. `_resize_hedge` tampoco actúa |
| Unwind (Profit Banking) | **Desactivado**: no cobra ninguna pata suelta ni par |
| Healer | Desactivado, salvo la disolución por parejas (§5.5) |
| Trailing de Op3 (SL dinámico) y smart trail | **Desactivados**: un SL que salte cambiaría el neto |
| Trailing de cesta, cierre de viernes en positivo, `force_close` del usuario | **Siguen**: cierran **todo** a la vez, sin dejar nada desnudo |
| Scalps del M5 | Siguen, con el tope de supervivencia |

Fuera del candado, todo funciona como hoy, más los gates nuevos de §5.2, §5.6 y §5.7.

### 5.4 Aflojar el candado: solo con rebote confirmado

**Principio:** con el candado puesto, el equity es el mismo cierres la pata que cierres. "Verde"
o "rojo" en la pata del candado es contabilidad, no dinero. Lo único que se decide es
**cuándo y en qué dirección volver a exponerse**. Si se esperara a que la pata del candado
estuviera en verde, solo se aflojaría cuando el precio siguió en contra, es decir, promediando
contra la tendencia (lo que quemó las cuentas), y nunca en un giro a favor. Esa regla queda
prohibida.

**Condiciones para aflojar (todas):**
1. el precio se movió **a favor** del neto original al menos `unlock_rebound_usd`
   (default **50**), medido **desde el precio medio de apertura de las patas `LOCK`**.
   Decisión mía: se mide desde el precio del candado, no desde el extremo posterior, para no
   aflojar en rebotes intermedios de una tendencia;
2. VCB apagado, spread normal y fuera de ventana de noticia;
3. fuera de las horas de riesgo (§5.7).

**Cuánto se afloja:** se cierra la parte de las patas `LOCK` necesaria para que el neto
resultante deje `S >= survival_move_usd` (350). No se quita más.
- Si lo que cabe es menor que `volume_min`, no se afloja.
- Lo realizado entra en `cycle_realized`.
- Log: *"Candado aflojado: cerrados X lotes (rebote +Y $). S=…"*.

**Histéresis:** el candado se pone a 150 y se afloja hasta 350. Si el rebote era falso y el
precio vuelve a caer, se recongela a 150. La pérdida máxima de un rebote falso queda acotada
desde el diseño: la exposición de 350 $ menos la de 150 $.

**Aflojados sucesivos:** en estado AFLOJADO se sigue evaluando. Cada nuevo aflojado exige otro
rebote de `unlock_rebound_usd` medido **desde el precio del aflojado anterior**, y cierra solo
lo que deje S ≥ 350 (S crece si el rebote sube el equity). Cuando se cierra la última pata
`LOCK`, el estado pasa a LIBRE.

### 5.5 Disolución por parejas (si el precio no rebota)

Si el precio sigue en contra, el candado no se afloja. Una cesta congelada **paga swap y no deja
abrir ciclos nuevos**, así que debe disolverse sin re-exponerse:

- **Disparo:** el candado lleva al menos `lock_dissolve_after_h` (default **24 h**) sin
  aflojarse.
- **Cuándo actúa:** una vez al día, en la hora más tranquila (default 03:00–04:59 UTC), con VCB
  apagado.
- **Qué hace:** cierra a la vez **X lotes de las patas `LOCK`** y **X lotes de la pata perdedora
  más cara del lado contrario**, el peor dinero por lote (`profit + swap`). El neto no cambia y
  el equity tampoco, salvo la comisión.
- **Contrapartes válidas:** solo patas Recovery u Op4 (`ROLE_RECOVERY`, `ROLE_RESCUE`).
  - **El par Op1–Op2 nunca se toca:** su neto ya es cero por sí solo y el candado no lo cubre;
    cubre el desequilibrio de las Op3/Op4.
  - Los huérfanos y sus coberturas también quedan fuera.
- **Tamaño de X:** `max(volume_min, redondeo_abajo(lock_dissolve_fraction × volumen LOCK
  inicial))`, con fracción default **0,34**. Así la cesta se disuelve en ~3 días.
- Lo realizado entra en `cycle_realized`. Log tipo `HEALER` con los dos tickets.
- **Fin de la disolución (decisión mía):** se para cuando se agotan las patas `LOCK` o las
  Op3/Op4 del lado contrario.
  - Lo normal es que quede el par Op1–Op2, congelado. Es el estado que ya existe hoy: con
    `cycle_count == 2` vuelven las Op3 (con tope) y el trailing de cesta cierra todo cuando el
    flotante arma.
  - Si quedan Op3/Op4 de ambos lados con neto ≈ 0, también se disuelven entre sí por parejas,
    con la misma cadencia diaria, hasta que el neto de lo que queda deje de ser ≈ 0 o no queden.
  - Las Op4 no se reabren: el contador de abiertas por ciclo (§5.6) ya alcanzó el tope en
    casi todos los casos, y si no, el tope de supervivencia las recorta.

**Decisión mía** (el usuario aprobó "cierre por parejas" para bajar el swap; la cadencia
diaria y el plazo de 24 h son elección mía):

- **24 h** porque el 50 % de los rebotes en los Hedge Lock ocurrió en 4–6 h; a las 24 h la
  probabilidad de rebote ya es baja.
- **03–04 UTC** porque es la franja más tranquila del perfil horario.

### 5.6 Fin del bucle de Op4 y del Unwind que deja patas desnudas

1. **`max_rescue_legs` cuenta las Op4 abiertas en el ciclo, no las vivas.** El contador se
   persiste con el ciclo y se reinicia con `cycle_realized`. En la base se abrieron 14 Op4 con
   tope 3 porque cada una se cobraba en segundos y el contador de vivas nunca llegaba a 3.
2. **El Unwind solo cobra una pata suelta si, después del cierre, `S >= survival_move_usd`.**
   Cerrar una pata que agranda `|neto|` equivale a añadir exposición. Los pares Op1–Op2 siguen
   como hoy (atómicos).
3. Se mantiene `rescue_cooldown`.

### 5.7 Horas de riesgo

`risk_hours_utc` (default **"1,13,14,15"**: cada hora cubre HH:00–HH:59 UTC). Durante esas
horas:
- no se abren Op3/Op4 nuevas (el hedge y la gestión siguen);
- no se afloja el candado.

La Op1 no se toca: no es parte de lo acordado.

### 5.8 Noticias

- **Decisión del usuario:** `news_enforce = true`. Bloquea aperturas aditivas en la ventana
  (T−2 h / T+1 h de rojas USD). Ya está implementado en modo observación y el log se verificó.
- **Decisión mía:** también se elimina la excepción del L3-CRÍTICO (`_check_rescue`, "no debe
  morir por calendario"). Con el candado, el L3 ya no es la última línea de defensa. Y en el
  ciclo malo del Core PPI, la Op4 abierta en el minuto del dato era L3.
- No se afloja el candado dentro de una ventana de noticia.

### 5.9 Umbrales en movimiento del precio (pips)

**Regla única:** todo umbral de dinero de la cesta se expresa como movimiento del oro
multiplicado por el **lote de referencia del ciclo**, que es el lote de la Op1 al abrirse el
ciclo. Se persiste con el ciclo. Si no hay Op1, se usa `_calculate_lots(False)` en ese momento.

```
umbral_$ = movimiento_$ × lote_ref × contract_size
```

Como Recovery (2× base) y Op4 (lote de la última pata) escalan con la Op1, el mismo precio
produce las mismas decisiones en cualquier cuenta, aunque los lotes estén redondeados.

Valores nuevos, calibrados para replicar el comportamiento actual de una cuenta de **5 000 $**
(Op1 = 0,09 lotes → 9 $ por cada 1 $ de movimiento):

| Parámetro actual | Hoy | Nuevo parámetro | Default |
|---|---|---|---|
| `basket_percent` (armado del trail) | 0,15 % del balance | `basket_arm_move_usd` | 0,83 |
| `rescue_target_pct` (armado en cesta ≥ 4) | 0,10 % | `rescue_arm_move_usd` | 0,56 |
| piso de armado (2 $ fijos) | 2 $ | se elimina (lo cubren los de arriba) | — |
| `min_green_profit` | 3 $ | `min_green_move_usd` | 0,33 |
| límites del retroceso dinámico | 1–50 $ | `retrace_min_move_usd` / `retrace_max_move_usd` | 0,11 / 5,6 |
| `fixed_retrace` | 2 $ | `fixed_retrace_move_usd` | 0,22 |
| `unwind_money_floor` | 30 $ | `unwind_floor_move_usd` | 3,33 |
| `dd_percent_l2` (Op4 L2) | 3 % | `rescue_l2_move_usd` | 16,7 |
| `dd_percent_l3` (Op4 L3) | 8 % | `rescue_l3_move_usd` | 44,4 |

- El retroceso dinámico (`_vol_risk_money × retrace_atr_mult`) ya está en ATR y lotes y se
  mantiene. Solo sus límites pasan a movimiento.
- Se mantienen:
  - la comisión por lote (costo real del bróker, ya proporcional);
  - el 90 % del Healer;
  - el objetivo de ganancia de la cuenta (%);
  - todo lo del M5 que ya está en puntos o ATR;
  - `hedge_dist` y todo lo que ya está en ATR o puntos.

### 5.10 Monitor de salud y alertas por correo (idea C)

Correo con `bot/notify.py` (Resend, `send_async`) a una dirección de operador en el env
(`ALERT_EMAIL_TO`; decisión mía). Dedupe: un correo por tipo de evento y cuenta cada 6 h.

| Evento | Severidad |
|---|---|
| Candado puesto / aflojado / disuelto | info |
| `S < lock_trigger_usd` y el candado no pudo entrar | **crítica** |
| Equity ≤ 0, stop-out detectado (deal **nuevo** con comment `[so …]`) o `trade_allowed` falso | **crítica**. Mientras la condición **siga vigente** (equity ≤ 0 o `trade_allowed` falso), ese bot no reintenta aperturas y solo loguea cada 10 min (fin del spam D2). **No es un bloqueo permanente:** se libera solo en cuanto la condición desaparece. El stop-out solo dispara la alerta, no bloquea. Cada bot (M15 y M5) lo aplica por su cuenta |
| Bot en RUNNING sin ningún deal propio en 72 h y con la cuenta sin posiciones | aviso |

Ninguna alerta cierra ni bloquea nada por sí misma.

### 5.11 Configuración y despliegue

- **Migración nueva** (`migrations/010_supervivencia.sql`): añade las columnas nuevas a
  `bot_config` con sus defaults y pone `news_enforce = true`, `max_net_lots = 0`,
  `max_entry_lots = 0`, `max_recovery_lots = 0` y `m5_max_lot_cap = 0` (0 = desactivado; el
  código debe tratarlo así). Las columnas viejas se conservan para poder hacer rollback.
- **Misma config para todas las cuentas** (cierra D7). Alcance acotado (decisión mía):
  - la migración **solo** toca las columnas nuevas, las cinco puestas a 0 de arriba,
    `news_enforce` y las cuatro con drift: `margin_cap_pct`, `ml_flatten`, `ml_no_add` (por
    `bot_id`) e `inp_max_spread`;
  - las cuatro con drift se igualan a los valores de `DEFAULTS` de Python del bot
    correspondiente (`strategy.py` para m15, `strategy_m5.py`/`budget.py` para m5), que son
    los que usaban las cuentas sin drift;
  - **no** toca tamaño (`base_lots`, `base_risk`, `equity_weight`), objetivo de ganancia ni
    nada más del usuario;
  - en comentarios de la propia migración se dejan los valores anteriores y el SQL inverso,
    porque un rollback de git no deshace datos.
- Rollout según §4. Las cuentas quemadas se retiran (prefijo `_` en su `.env`) solo con OK del
  usuario. Las cuentas nuevas de ~5 000 $ entran por invitación.

## 6. Pruebas

Tests unitarios (pytest, en `tests/`, sin terminal MT5, con broker falso como en
`test_m5_and_budget.py`):

- cálculo de S, con y sin posiciones, incluyendo el M5;
- tamaño dinámico: pide 0,20 y caben 0,15 → 0,15; caben 0,19 → 0,19; caben 0,35 → 0,20;
  caben 0,004 → bloqueo;
- el candado se pone a S < 150, con volumen = neto M15; el ledger lo persiste y lo rehidrata;
- con candado, Unwind/Healer/trails/hedge monitor no cambian el neto;
- aflojar: no con la pata del candado en verde por continuación; sí con rebote ≥ 50 $ fuera de
  horas de riesgo, de noticia y de VCB; afloja exactamente hasta S ≥ 350;
- disolución por parejas: neto constante y cadencia diaria;
- `max_rescue_legs` por abiertas: reproduce el caso del bucle (abrir → cobrar → abrir) y se
  detiene en 3;
- Unwind no cobra una pata si deja S < 350;
- **paridad entre cuentas:** la misma serie de precios con equity de 5 000 / 10 000 / 20 000 $
  produce la misma secuencia de decisiones (armado, cierre, Op4 L2/L3, Unwind).
  - `lote_ref` es el volumen **real** de la Op1 (redondeado), no el teórico. Como Recovery
    (2 × base redondeado) y Op4 (lote de la última pata) escalan con él, la igualdad es
    exacta.
  - Las cuentas cuyo lote cae en `volume_min` (≈ 1 000 $) quedan fuera del test exacto. Con
    ellas solo se exige que no haya bloqueos ni cierres que no ocurran en las demás. Su
    redondeo a 0,01 es una limitación conocida.
  - El tope de supervivencia se desactiva en este test, porque recorta según el capital por
    diseño.

Sin backtest salvo que el usuario lo pida. La validación real es la demo.

## 7. Qué se deja al builder

- La forma exacta del helper de S y del "lote máximo que cabe" (búsqueda descendente por
  `volume_step` con `order_calc_margin`, o fórmula cerrada).
- Dónde vive el contador de Op4 abiertas y el lote de referencia del ciclo (ledger JSON o
  estado del motor), siempre que sobrevivan a un restart.
- El texto exacto de los logs, respetando la taxonomía
  ([`logging-taxonomy-and-ticket`](../../memory/logging-taxonomy-and-ticket.md)). Se sugiere
  `PROTECCION` para el candado (orden protectora) y `BUDGET` para recortes y bloqueos del tope.
- Mostrar S y el estado del candado en el HUD/TUI (deseable, no obligatorio).

## 8. Riesgos conocidos

- **Recuperación más lenta.** Con 350 $ las Op3/Op4 serán mucho más pequeñas (en la base:
  ~0,27 lotes netos frente a 0,84). Se ganará menos en los días buenos. Esto es intencional.
- **Margen del candado** desconocido hasta leer `margin_hedged` en vivo.
- **Spread del rollover:** golpea según el tamaño total de la cesta. El tope lo acota, pero
  conviene vigilarlo en demo.
- **Datos ago–sep dispersos:** las cifras de rebote tras la quiebra son aproximadas.

## 9. Decisiones tomadas por Claude (a revisar por el usuario)

El usuario decidió: sin stops ni cierres de emergencia; tope de 350 $; candado a 150 $; aflojar
solo con un rebote de ~50 $ y nunca por continuación; cierre por parejas; tamaño dinámico de las
patas (abrir lo que quepa, sin esperar); umbrales en movimiento del precio; activar el bloqueo
de noticias.

Lo siguiente lo decidí yo:

1. Desactivar `max_entry_lots`, `max_recovery_lots` y `m5_max_lot_cap` (topes en lotes fijos).
2. El candado cubre solo el neto del M15; el M5 cuenta en S, pero no se cubre.
3. Reparto del espacio del tope entre bots según `equity_weight` (M15 0,8 / M5 0,2).
4. Tres estados (LIBRE / CONGELADO / AFLOJADO); en AFLOJADO las patas `LOCK` son intocables.
5. El rebote se mide desde el precio del candado (o del aflojado anterior), no desde el extremo.
6. Disolución por parejas: tras 24 h, una vez al día entre las 03 y las 05 UTC, en tercios;
   contrapartes solo Op3/Op4; el par Op1–Op2 nunca se toca.
7. Quitar la excepción del L3-CRÍTICO al bloqueo de noticias.
8. Horas de riesgo "1,13,14,15" UTC: no aplican a la Op1.
9. Calibrar los umbrales en movimiento para que una cuenta de 5 000 $ se comporte como hoy.
10. Alertas a `ALERT_EMAIL_TO`, una por evento y cuenta cada 6 h; el bloqueo por cuenta muerta
    no es permanente.
11. La migración solo toca las columnas nuevas y las cuatro con drift, y deja el SQL inverso.
