# Diseño: bolsa del curador sin doble conteo y recorte de la Op1 + Op2 primero

**Estado:** APROBADO por el usuario el 2026-10-20 («Si procede»), sobre la descripción en el chat. Este archivo la deja por escrito.

**Rama:** `experimento-2-rediseno`.

**Origen:** `docs/experimento-2/analisis-op4-criterio-propio-2026-10-19.md`, secciones 3 y 4.

## Cambio 1: la bolsa no cuenta los cierres del propio curador

**Problema:** `_check_healing` suma a la bolsa el 90 % de todo deal de salida del magic con `profit > 0`. Eso incluye las órdenes del propio curador y de la disolución:
- **Recorte por parejas:** lo realizado (rojo + verde) ya se descontó de la bolsa en el momento. Si el miembro verde cerró con ganancia, se vuelve a contar como «ganador nuevo».
- **Disolución del candado** (`Basket Dissolve`): no toca la bolsa, pero su miembro verde se cuenta como ganancia mientras que su miembro rojo no resta. Es dinero que el ciclo no ganó.
- **Amputación:** solo cierra perdedores, así que no aporta deals con ganancia. Se incluye por coherencia.

**Arreglo:**
- Al acumular, se ignoran los deals cuyo comentario sea `Healer Pair Cut`, `Healer Amputacion` o `Basket Dissolve` (constante `HEALER_OWN_COMMENTS`).
- El cursor sí avanza sobre ellos.
- La ganancia del miembro verde queda en la cuenta como ganancia: el balance no cambia y la bolsa deja de inflarse.

**Fuera de alcance:** el Unwind (`Unwind Profit Banking`) cierra parejas con dinero conjunto positivo. Se deja como está.

## Cambio 2: orden de las parejas, configurable, con la Op1 + Op2 primero por defecto

- **Nuevo parámetro `healer_pair_order`:**
  - `'cover_first'` (por defecto): primero la pareja de cobertura (Op1 + Op2), después las parejas sueltas (recovery + Op4).
  - `'recovery_first'`: el comportamiento del 19-oct.
- **Lo que se mantiene:**
  - La amputación de una recovery con perdedor real sigue teniendo prioridad sobre cualquier pareja.
  - El ancla: con recovery u Op4 vivas, la Op1 y la Op2 no bajan del lote mínimo. Una pareja de cobertura que ya no puede recortar al menos el lote mínimo sin romper el ancla **no cuenta como candidata**, así que la bolsa pasa a la pareja siguiente en vez de quedarse esperando.
- **Por qué:** con el mismo dinero de la bolsa, la Op1 + Op2 (≈15 $/oz) frena el mismo swap que la recovery + Op4 (≈93 $/oz).
  - En la simulación, 10k pasa de −31,9 % a −21,5 % y 5k de −29,9 % a −20,2 %. 1k queda igual.
  - Ninguna cuenta empeora en las ventanas de 30 días, salvo 1 de 15 en 5k.
- **Migración 016:** `healer_pair_order TEXT DEFAULT 'cover_first'`. Para volver atrás: `UPDATE bot_config SET healer_pair_order = 'recovery_first' WHERE bot_id = 'm15';`. Se recarga en caliente.

## Tests

En `tests/test_pair_cut.py` y `tests/test_healer.py`:
1. Un deal `Healer Pair Cut` con ganancia **no** suma a la bolsa. Un ganador normal sí.
2. Un deal `Basket Dissolve` con ganancia no suma a la bolsa.
3. Con `cover_first`, la bolsa paga la Op1 + Op2 aunque haya una pareja recovery + Op4 válida.
4. Con `cover_first` y la Op1 + Op2 ya en el lote mínimo (con otras patas vivas), la bolsa pasa a la recovery + Op4.
5. Con `recovery_first`, el comportamiento es idéntico al de antes (tests existentes).
6. Las suites existentes siguen en verde.
