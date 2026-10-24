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
- Seguridad: al salir se cierran el candado y los tercios juntos (se realiza la pérdida congelada); un ticket ausente sin confirmar en el historial espera (no se da por cerrado antes de N lecturas no vacías y 15 min). Una posición con comentario e2 que el estado no reconoce (archivo perdido/corrupto) se **adopta** (ERROR "adoptada"; salida por la regla de la pata, candado/objetivos solo si hay ATR) y antes de entrar se verifica que la pata de hoy no esté ya en MT5; con el estado ilegible no hay entradas ese día. Otras posiciones del magic sin comentario e2: WARNING y no se tocan.
- Salvaguardas: sin cuenta hedging no entra; calendario > 6 h o que no cubre hoy → sin NFP y Big One a peso de evento (ERROR); feriados de EE. UU. (federales con fecha observada, viernes tras Thanksgiving, 24 y 31-dic) → sin Momentum ni NFP; sin tick nuevo 60 s en horario de mercado → ERROR.
- Supabase: `migrations/017_e2_engine.sql` (columnas `e2_*` + SQL comentado de las filas e2) está **escrita pero sin aplicar**; sin la fila de `bot_config` el motor corre con DEFAULTS (`runs_without_cfg`), y abrir depende de `bot_instances.is_active`.
- Colector de ticks: cuando exista una cuenta nueva, apuntarlo con `--login` a ella ([[tick-collector]]); hoy usa el terminal de la demo vieja de 5k (ver [[demos-viejas-desactivadas]]).
