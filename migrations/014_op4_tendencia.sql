-- ==================================================================
-- 014_op4_tendencia.sql  |  Op4 a favor del movimiento
-- ==================================================================
-- Contexto:
--   * La Op4 copiaba la ultima pata (martingala) y el tope de supervivencia la
--     bloqueaba justo en los movimientos grandes (14-oct).
--   * Modo 'trend': con una recovery/rescue a >= rescue_trend_k_atr x ATR M15 en
--     contra (cierre de vela), abre CONTRA ella, tamano <= |neto del ciclo|.
--     Trailing propio (rescue_trend_trail_*_atr), sin stop. Sus ganancias
--     alimentan al Healer, que recorta la perdedora. Cupo por ciclo.
-- Spec: docs/superpowers/specs/2026-10-16-op4-tendencia-design.md
-- Evidencia: docs/experimento-2/analisis-op4-direccion-2026-10-16.md
--
-- ESTADO: APLICADA en Supabase el 2026-10-16 (SQL Editor). Idempotente.
-- Sin aplicarla, el bot usa los DEFAULT de bot/strategy.py (modo 'trend').
-- ==================================================================

ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS rescue_mode                  TEXT             DEFAULT 'trend',
    ADD COLUMN IF NOT EXISTS rescue_trend_k_atr           DOUBLE PRECISION DEFAULT 2.0,
    ADD COLUMN IF NOT EXISTS rescue_trend_max_legs        INTEGER          DEFAULT 6,
    ADD COLUMN IF NOT EXISTS rescue_trend_trail_start_atr DOUBLE PRECISION DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS rescue_trend_trail_dist_atr  DOUBLE PRECISION DEFAULT 0.5;

-- ---- ROLLBACK (comentado) ------------------------------------------
-- [PROSA - NO DESCOMENTAR] Vuelve a la Op4 de copia, sin tocar codigo ni reiniciar.
-- UPDATE public.bot_config SET rescue_mode = 'copy' WHERE bot_id = 'm15';
