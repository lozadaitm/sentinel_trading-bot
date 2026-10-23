---
name: tick-collector
description: scripts/tick_collector.py guarda los ticks del broker (XAUUSD+) por día en bot_backtesting/fullsim/data/ticks (fuera de git); tarea SentinelTickCollector los sábados 10:00 hora local
metadata:
  type: project
---

**Desde el 2026-10-24**, `scripts/tick_collector.py` baja en solo lectura los ticks (bid/ask) de XAUUSD+.

- **Terminal:** el de la cuenta 26275221 (5k), por defecto.
- **Salida:** `bot_backtesting/fullsim/data/ticks/<SÍMBOLO>/<AAAA-MM-DD>.pkl.gz` (~2 MB por día), más `spread_<SÍMBOLO>.csv` con el spread por minuto.
- **Relleno inicial:** desde 2026-01-12, que es lo que guarda el broker.
- **Tarea programada:** `SentinelTickCollector`, sábados a las 10:00 hora local, con `--days 9`.

**Why:** las simulaciones con velas de Dukascopy se equivocaron en la reapertura ([[data-dukascopy-rollover-artifact]]). Los ticks del broker son la fuente de verdad para el costo y la ejecución.

**How to apply:**
- Correrlo solo con el mercado cerrado ([[mt5-history-download-blocks-bots]]).
- Para relleno: `python scripts/tick_collector.py --since AAAA-MM-DD`.
- Para quitar la tarea: `schtasks /delete /tn SentinelTickCollector /f`.
