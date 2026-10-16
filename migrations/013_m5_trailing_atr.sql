-- ==================================================================
-- 013_m5_trailing_atr.sql  |  M5: trailing proporcional al ATR
-- ==================================================================
-- Contexto:
--   * El trailing del M5 era en puntos fijos (arranca +100 pt, sigue a 50 pt,
--     turbo 300/150): cobraba ~1,3 $/oz y perdia ~8,5 $/oz por operacion.
--   * Modo 'atr': arranca a m5_trail_start_atr x ATR, sigue a m5_trail_dist_atr
--     x ATR y desde m5_turbo_trigger_atr x ATR se aprieta a m5_turbo_dist_atr
--     x ATR. ATR(14) M5 de la vela cerrada previa a la apertura, fijo.
--   * Los parametros en puntos (m5_trail_start, ...) siguen para el modo 'points'.
-- Spec: docs/superpowers/specs/2026-10-16-m5-trailing-atr-design.md
-- Evidencia: docs/experimento-2/auditoria-m5-2026-10-16.md (secciones 6 y 7)
--
-- ESTADO: APLICADA en Supabase el 2026-10-16 (SQL Editor). Idempotente.
-- Sin aplicarla, el bot usa los DEFAULT de bot/strategy_m5.py (modo 'atr').
-- ADD COLUMN ... DEFAULT rellena las filas existentes (M15 y M5); el M15 no
-- lee estas columnas.
-- ==================================================================

ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS m5_trail_mode        TEXT             DEFAULT 'atr',
    ADD COLUMN IF NOT EXISTS m5_trail_start_atr   DOUBLE PRECISION DEFAULT 0.50,
    ADD COLUMN IF NOT EXISTS m5_trail_dist_atr    DOUBLE PRECISION DEFAULT 0.30,
    ADD COLUMN IF NOT EXISTS m5_turbo_trigger_atr DOUBLE PRECISION DEFAULT 1.25,
    ADD COLUMN IF NOT EXISTS m5_turbo_dist_atr    DOUBLE PRECISION DEFAULT 0.15;

-- ---- ROLLBACK (comentado) ------------------------------------------
-- [PROSA - NO DESCOMENTAR] Vuelve al trailing en puntos fijos, sin tocar codigo.
-- UPDATE public.bot_config SET m5_trail_mode = 'points' WHERE bot_id = 'm5';
