-- ==================================================================
-- 017_e2_engine.sql  |  Motor e2 "tres patas" (Big One, Momentum EE. UU., NFP)
-- ==================================================================
-- Contexto:
--   * El motor e2 (bot/strategy_e2.py, SessionEngine; magic 100300, bot_id 'e2')
--     lee sus parametros de bot_config con los DEFAULT de strategy_e2.DEFAULTS.
--     Sin estas columnas el bot usa los DEFAULTS (mismo resultado), pero el
--     dashboard no puede verlos ni cambiarlos.
--   * NULL en cualquier columna = el DEFAULT del codigo (SessionEngine._p).
--   * e2_tp_atr15_mults es TEXT "m2,m3" (objetivos de T2 y T3 en ATR15); el bot
--     acepta tambien '{2,3}' o '[2,3]'. Un valor invalido cae al default y se
--     registra ERROR (una vez por hora).
--   * ADD COLUMN ... DEFAULT rellena las filas existentes (m15 y m5), que no
--     leen estas columnas.
--   * main.py deja correr el e2 sin fila de bot_config (runs_without_cfg): las
--     salidas se gestionan igual; ABRIR depende de bot_instances.is_active.
-- Spec: docs/experimento-2/diseno-bot-tres-patas-2026-10-25.md
--
-- ESTADO: PENDIENTE de aplicar en Supabase (SQL Editor). Idempotente.
-- ==================================================================

ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS e2_risk_pct               DOUBLE PRECISION DEFAULT 0.08,
    ADD COLUMN IF NOT EXISTS e2_lock_atrd_mult         DOUBLE PRECISION DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS e2_tp_atr15_mults         TEXT             DEFAULT '2.0,3.0',
    ADD COLUMN IF NOT EXISTS e2_mom_threshold_pct      DOUBLE PRECISION DEFAULT 0.232,
    ADD COLUMN IF NOT EXISTS e2_bigone_weight_nontrend DOUBLE PRECISION DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS e2_bigone_event_weight    DOUBLE PRECISION DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS e2_entry_grace_s          INTEGER          DEFAULT 60,
    ADD COLUMN IF NOT EXISTS e2_nfp_hold_bars          INTEGER          DEFAULT 96,
    ADD COLUMN IF NOT EXISTS e2_legs                   TEXT             DEFAULT 'bigone,mom,nfp';

-- ---- FILAS DE UNA INSTANCIA e2 (comentado; una vez por usuario) ------
-- [PROSA - NO DESCOMENTAR TAL CUAL] Sustituir <USER_ID> (auth.users.id, el
-- USER_ID del instances/<usuario>.env) y el simbolo si no es XAUUSD+. La
-- instancia nace APAGADA (is_active=false): el usuario la enciende desde el
-- dashboard cuando el .env tenga BOTS=...,e2 y el bot este corriendo.
--
-- INSERT INTO public.bot_instances (user_id, bot_id, label, is_active)
-- VALUES ('<USER_ID>', 'e2', 'Tres Patas E2', false)
-- ON CONFLICT (user_id, bot_id) DO NOTHING;
--
-- INSERT INTO public.bot_config (user_id, symbol, bot_id, is_active)
-- VALUES ('<USER_ID>', 'XAUUSD+', 'e2', true)
-- ON CONFLICT (user_id, symbol, bot_id) DO NOTHING;
--
-- Comprobacion:
-- SELECT bot_id, is_active, e2_risk_pct, e2_legs FROM public.bot_config
--  WHERE user_id = '<USER_ID>' AND bot_id = 'e2';

-- ---- ROLLBACK (comentado) ------------------------------------------
-- [PROSA - NO DESCOMENTAR] Apaga una pata sin tocar codigo (p.ej. solo Big One):
-- UPDATE public.bot_config SET e2_legs = 'bigone' WHERE bot_id = 'e2';
