---
name: e2-motor-tres-patas
description: Motor e2 (bot/strategy_e2.py, SessionEngine): tres patas Big One / Momentum US / NFP en XAUUSD+, magic 100300, BOT_ID e2; implementado, pendiente de prueba en demo
metadata:
  type: project
---

**Qué es:** el motor del Experimento 2 (rama `experimento-2-rediseno`). Opera tres patas de sesión con escalera de tercios y candado: Big One, Momentum US y NFP. Clase `SessionEngine` en `bot/strategy_e2.py`; reglas puras en `bot/sessions.py`; entrada `bot/main_e2.py` (variante `bot.lite_e2`).

- **Identidad:** `BOT_ID=e2`, magic **100300** (`MAGIC_E2`). Comentarios: `E2 BigOne T1..T3`, `E2 MomUS T1..T3`, `E2 NFP T1..T3`; candado `E2 Lock <Pata>`; cierres `E2 TP <Pata> T<n>` y `E2 Salida <Pata>`.
- **Archivo de estado:** `instances/e2_state_<USER_ID>.json` (no se versiona).
- **Estado:** implementado, pendiente de prueba en demo (cuentas nuevas de 3 000 / 10 000 / 25 000, solo e2).
- **Diseño y plan:** `docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md` y `docs/superpowers/plans/2026-10-25-bot-tres-patas-e2.md`.
- **Reporte diario:** `scripts/daily_report.py` muestra e2 (abiertas, flotante, realizado 24 h y desglose por pata).

**Why:** el diseño simulado mostró ventaja en estas tres sesiones; el motor se probó contra un simulador del broker, pero no con dinero demo real.

**How to apply:**
- Arrancar: en el `.env` de la instancia `BOTS=e2` (BOT_ID/magic los valida `config.validate_identity`), luego `scripts/start_all.ps1`.
- Apagar una pata: en `bot_config`, `e2_legs` (por defecto `bigone,mom,nfp`); quitar el nombre de la lista.
- Seguridad: al salir se cierran el candado y los tercios juntos (se realiza la pérdida congelada); un ticket ausente sin confirmar en el historial espera (no se da por cerrado antes de N lecturas y 15 min); una posición con magic 100300 que el estado no reconoce genera un WARNING y no se toca.
- Colector de ticks: cuando exista una cuenta nueva, apuntarlo con `--login` a ella ([[tick-collector]]); hoy usa el terminal de 26275221.
