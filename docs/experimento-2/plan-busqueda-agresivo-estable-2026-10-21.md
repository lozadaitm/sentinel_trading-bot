# Búsqueda "agresivo pero estable" — plan y banco de ideas (2026-10-21)

Herramienta: `bot_backtesting/fullsim/race.py` con el bot de esta rama (motor real, swap,
comisión, spread). Cuentas de 1 000 $ y de 5 000 $ (con 5 000 $ el aguante deja más lote, el comportamiento cambia). Métrica: % que duplica antes de 120 días, % que se quema
(≤ 300 $ o stop-out), equity final media y mediana.

## Punto de partida (143 arranques, 2021-03 → 2026-08)

| Bot | Duplica | Se quema | Final medio |
|---|---|---|---|
| Viejo (main) | 21 % | 65 % | 756 $ |
| Viejo + candado externo (5 versiones) | 10–14 % | 34–55 % | 660–743 $ |
| Nuevo, aguante 350 $ | 1 % | 0 % | 910 $ |

## Método (contra el sobreajuste)

1. Elegir SOLO con arranques 2021-03 → 2023-12 (entrenamiento).
2. Validar lo elegido en 2024-01 → 2026-08 (nunca usado para elegir) y luego en la serie completa.
3. Etapas:
   - E1 lote × aguante: `base_lots` {0,12; 0,24; 0,36} × `survival_move_usd` {350, 150, 80}
     (candado y aflojado escalados en proporción).
   - E2 una idea por vez sobre la mejor base de E1, por operación (bancos abajo).
   - E3 combinar lo mejor de cada banco y validar.

## Banco Op2 (Hedge Lock)

Con parámetros existentes:
- `hedge_dist` 350 / 800 / 1500; `hedge_atr_mult` 1,5 / 2 / 3.
- `lock_trigger_usd` (candado de cesta) más temprano o más tarde.

Requieren código (solo en el simulador hasta aprobar diseño):
- Cobertura parcial (50–75 % del neto) en vez de total.
- Cobertura en dos escalones (½ a X, ½ a 2X).
- Cobertura solo si la tendencia diaria va en contra de la Op1.

## Banco Op3 (Recovery)

Con parámetros existentes:
- `recovery_min_spacing_atr` 0,5 / 1 / 2.
- `op3_start_atr`, `op3_base_dist_atr` (trailing de la Op3).
- `use_recovery_h4_gate` sí / no.

Requieren código:
- Op3 solo a favor de la tendencia diaria (tsmom).
- Lote de la Op3 fijo en vez de creciente.

## Banco Op4 (Rescate)

Con parámetros existentes:
- `rescue_mode` trend vs copia; `rescue_trend_k_atr` 1 / 2 / 3.
- `max_rescue_legs` 1 / 3 / 6.
- `rescue_trend_trail_start_atr` / `rescue_trend_trail_dist_atr`.

Requieren código:
- Op4 con lote mayor solo si coincide con la tendencia diaria (idea Big One).
- Op4 que cierra la peor pata con su ganancia (pareja inmediata).

## Criterio de elección

Máximo % de duplicar con % de quema ≤ 10 % y final medio > 1 000 $.

## Resultados E1 (2026-10-22) — entrenamiento 2021-03 → 2023-12, 74 arranques, 120 días

Final medio / mediana (% sobre el saldo inicial); ninguna variante duplica.

| Cuenta | Lote base | Aguante 350 | Aguante 150 | Aguante 80 |
|---|---|---|---|---|
| 1k | 0,12 | −10,7 % | −10,2 % | (= 150) |
| 1k | 0,24 | −11,6 % | −16,3 % | −18,4 % |
| 1k | 0,36 | −11,6 % | −19,9 % | −26,5 % (1 % quema) |
| 5k | 0,12 | −7,6 % | −8,9 % | −8,9 % |
| 5k | 0,24 | −8,4 % | −16,3 % | −19,9 % |
| 5k | 0,36 | −8,4 % | −22,1 % | −28,6 % (4 % quema) |

- Más lote = más pérdida, casi en proporción: escalar una ventaja negativa.
- El percentil 90 es negativo en todas: en 9 de cada 10 ventanas de 120 días el bot pierde.
- Por qué: en TODOS los arranques el bot entra en un ciclo de 4 patas (Op1 + Op2 congeladas
  + recovery + Op4) a los pocos días y no sale en los 120 días. Antes de congelarse gana
  rápido (traza 5k 2021-03: 16 ciclos verdes, +8 % en 4 días). Congelado, no abre Op1 y la
  pareja Op1+Op2 paga swap (≈ −41 $/lote/noche): el swap explica casi toda la pérdida medida.
- Prueba de salida del congelado (`--unfreeze 72`, cerrar la cesta congelada tras 72 h): en el
  arranque de la traza, 95 ciclos, 18 salidas que realizan −2 973 $ contra +2 055 $ de ciclos
  verdes. El congelado no es solo swap: cada ciclo que se congela pierde ~6 veces lo que gana
  uno verde y pasa ~1 de cada 5 veces. Para ganar hay que cambiar esa proporción.

Siguiente: E2 con `--unfreeze 72` como instrumento de medida (muchos ciclos por arranque):
tamaño de la ganancia (trailing de cesta), distancia de la cobertura (Op2), separación de la
Op3 y distancia de la Op4, en cuenta de 5k.
