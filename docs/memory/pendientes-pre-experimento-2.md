---
name: pendientes-pre-experimento-2
description: Pendientes abiertos en experimento-1-grinder al congelarla como producción (2026-10-13) antes de abrir experimento-2-rediseno; se reevalúan dentro del brainstorming, no se implementan a ciegas
metadata:
  type: project
---

El 2026-10-13 se congeló `experimento-1-grinder` como rama de producción (`main` se
actualizó por fast-forward a ella, tag `prod-v20-2026-10-13`) y se abrió
`experimento-2-rediseno` en un worktree aparte (`sentinel_trading_exp2`). Esta carpeta
(`sentinel_trading`) es la que corre en el VPS: 3 bots M15 + 2 M5 en modo Lite y la
tarea `SentinelRestart` apunta aquí. **Nunca cambiar de rama en esta carpeta.**

**Pendientes heredados (decidir en el brainstorming de experimento-2):**

1. NewsGuard Fase 2 (NRI 0-1): diseñado en [[newsguard-phase2-nri]]; solo si los logs
   de Fase 1 (`news_enforce=false`, modo observación) lo justifican. Nadie ha revisado
   esos logs todavía.
2. Migración `004_profit_target.sql`: [[profit-target-and-force-close]] la marca como
   "pendiente de aplicar", pero existen 005..009 posteriores. Casi seguro ya aplicada;
   confirmar en Supabase y corregir esa memoria.
3. Cascada Healer+Unwind ([[healer-unwind-hedge-cascade]]): vías (a) Unwind no banca el
   hedge con perdedor core desnudo y (d) floor del Healer quedaron sin implementar
   porque chocan con "no stops duros" ([[bot-design-constraints]]). Decisión abierta.
4. Paridad de indicadores pandas vs nativos MT5 ([[bot-760-root-cause]]).
5. Apagar `use_grinder` en la fila m15 por gobierno de margen
   ([[multi-bot-margin-governance]]), decisión sin confirmar.
6. Archivos locales sin trackear en producción: `Gold_*.csv`, `bot_backtesting/data/`,
   `bot_backtesting/results/`, `instances/cycle_ledger_m15_*.json`, y
   `experimento_1_logs.csv` borrado. Decidir `.gitignore`.
7. Sospecha del usuario (sin verificar): las 3 cuentas con la misma lógica se
   comportaban distinto (número de operaciones, entradas/salidas, cálculo de lotaje).
   Requiere exportar el historial MT5 de cada instancia y compararlo. Ver
   [[ideas-experimento-2]].

**Cómo aplicar:** cualquier hotfix que entre en `experimento-1-grinder` se mergea a
`experimento-2-rediseno` el mismo día ([[workflow-implement-then-commit]]).
