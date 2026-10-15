-- ==================================================================
-- 012_healer_perdedor_real.sql  |  Healer: bolsa solo con perdedor real
-- ==================================================================
-- Contexto:
--   * El Healer solo amputa un PERDEDOR REAL: pata amputable con perdida
--     (profit + swap) >= healer_min_move_usd por onza. Una recovery roja
--     solo por spread ya no se amputa (14-oct: se cerraba la recien abierta).
--   * La bolsa (90 % de lo ganado) solo se llena mientras hay perdedor real;
--     sin el, lo ganado queda como ganancia. Logica en codigo, sin columna.
--   * healer_min_move_usd = 0 vuelve al comportamiento anterior del umbral.
-- Spec: docs/superpowers/specs/2026-10-16-healer-patas-frescas-design.md
--
-- ESTADO: APLICADA en Supabase el 2026-10-15 (SQL Editor). Idempotente.
-- Sin aplicarla, el bot usa el DEFAULT 2.0 de bot/strategy.py.
-- ==================================================================

ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS healer_min_move_usd DOUBLE PRECISION DEFAULT 2.0;

-- ---- ROLLBACK (comentado) ------------------------------------------
-- [PROSA - NO DESCOMENTAR] Umbral apagado; la bolsa con perdedor real sigue en codigo.
-- UPDATE public.bot_config SET healer_min_move_usd = 0;
