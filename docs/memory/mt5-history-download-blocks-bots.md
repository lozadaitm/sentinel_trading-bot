---
name: mt5-history-download-blocks-bots
description: Pedir histórico profundo (copy_rates_from con 50 000 barras en bucle) a un terminal vivo bloquea su IPC y deja colgados a sus bots; solo lecturas ligeras con el mercado abierto
metadata:
  type: feedback
---

**Qué pasó:** el 19-oct-2026 (00:57–01:10 UTC), una descarga de histórico M15/M5/H4 en bucles de 50 000 barras contra el terminal de la cuenta de 10k obligó al terminal a bajarse historial antiguo del servidor.
- Mientras tanto, las llamadas IPC de sus bots (M15 y M5) se quedaron colgadas unos 13 minutos, sin heartbeat.
- Los bots se recuperaron solos al matar la descarga. No hubo órdenes ni errores.

**Regla:**
- Con el mercado abierto, contra los terminales vivos solo se hacen **lecturas ligeras**: posiciones, deals recientes, tick, o unos cientos de velas.
- Nunca `copy_rates_from` / `copy_rates_range` profundos en bucle.
- El histórico largo se baja con el mercado cerrado (fin de semana), o se reutiliza lo ya guardado (`bot_backtesting/data/*.csv` y los pickles de análisis).

**Why:** el terminal sirve el IPC de los bots y de los scripts por el mismo canal. Una sincronización de historial lo monopoliza.

**How to apply:**
- Antes de cualquier script de lectura de MT5, estimar cuántas barras pide.
- Si son miles de barras o más, esperar al cierre del mercado o usar datos guardados.
- Tras cualquier lectura, comprobar los heartbeats en `bot_state`.

Relacionado: [[mt5-updates-and-onboarding]].
