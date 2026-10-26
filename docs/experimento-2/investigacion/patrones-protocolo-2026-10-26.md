# Protocolo común — banco de patrones de velas (M15 / M5 / M1), 2026-10-26

Pregunta del usuario: ¿hay patrones de velas (V, W, M, HCH, banderas, velas japonesas, formas
sin nombre) que se cumplan «siempre o casi siempre» en el oro, como para que el bot e2 los
opere con vigilancia tick a tick? Fase A: solo análisis; no se toca el bot.

## Datos (todos del broker, hora de servidor = NY+7; no usar Dukascopy)

| Marco | Archivo (bot_backtesting/fullsim/data/) | Desde | Notas |
|---|---|---|---|
| M15 | broker_m15_full.pkl | 2022-08 | columnas time (epoch s), open, high, low, close, tick_volume, spread (puntos, x0.01 = $/oz) |
| M5 | broker_m5_full.pkl | 2025-05 | mismas columnas |
| M1 | broker_m1_ticks.pkl | 2026-01-12 | open/high/low/close (bid), ticks, spread_mean, spread_max ($/oz); construido desde ticks |
| Ticks | ticks/XAUUSD+/AAAA-MM-DD.pkl.gz | 2026-01-12 | time_msc, bid, ask; para simular entrada/salida exacta |

Tendencia diaria (la de la Big One): s = sign(C - C[-21]) + sign(C - C[-63]) sobre cierres diarios, desplazada un día.

## Reglas del broker y costos

- XAUUSD+ cotiza 01:00-23:58 pero **solo opera desde 01:01**. Sin entradas de 23:45 a 01:05
  (rollover: spread ancho, precios que mienten). Viernes sin entradas después de 22:00.
- Costo por operación ida y vuelta: spread real (de la vela o del tick) + comisión 0,06 $/oz.
  Sin ticks, usar 0,23 $/oz fijo (COST_OZ de broker_map.py). Compra al ask, venta al bid.
- Cuenta RAW hedging 1:500. 1 lote = 100 oz.

## Simulación

- La entrada se decide solo con velas CERRADAS. Se entra en la apertura de la vela siguiente
  (M15/M5) o, cuando haya ticks, en el primer tick que cruza el nivel de confirmación.
- Salidas fijadas ANTES de mirar resultados (no elegir la mejor de muchas):
  E1 objetivo 1 ATR / freno 1 ATR del marco; E2 objetivo 2 ATR / freno 1 ATR;
  E3 salida por tiempo a N velas (N = 4, 12); E4 escalera de la Big One (tercios: tiempo /
  2 ATR / 3 ATR). Si objetivo y freno caen en la misma vela, asumir el freno (conservador)
  salvo que se resuelva con ticks.
- Métrica principal: **expectativa neta en $/oz y en R por operación**. La tasa de acierto
  se reporta, pero NO es criterio (90 % de acierto con pérdidas grandes es perdedor).

## Filtro (todo patrón candidato debe pasar TODO)

1. Mitad A (primera mitad cronológica) = descubrimiento; mitad B = validación, sin tocar.
2. En A: corrección Benjamini-Hochberg al 10 % sobre TODAS las variantes probadas
   (patrón x marco x contexto x salida x lado); contar y reportar cuántas se probaron.
3. En B: neto > 0 con t > 2.
4. Años (o trimestres en M5/M1) positivos: todos menos uno como máximo.
5. Al menos 100 operaciones en total (M1/M5: reportar igual si son menos, marcado «muestra corta»).
6. Remuestreo por bloques o permutación de fechas para estimar la probabilidad de que sea suerte.

## Restricciones

- Prioridad baja (BelowNormal), como máximo 1 proceso pesado por equipo. Hay 3 bots en vivo
  en esta máquina: NO abrir MT5, NO usar MetaTrader5.initialize, NO tocar bot/ ni instances/.
- Código nuevo en bot_backtesting/fullsim/pat_<equipo>.py; resultados en
  docs/experimento-2/investigacion/patrones-<equipo>-2026-10-26.md (en español, con tabla de
  lo probado, lo que pasó cada filtro y la conclusión honesta).
- Repo público: no commitear datos (.pkl), ni .env, ni instances/, ni correos.
- Commit solo de los propios archivos (git add <rutas>, nunca -A), en la rama
  experimento-2-rediseno, con el trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, y push.
