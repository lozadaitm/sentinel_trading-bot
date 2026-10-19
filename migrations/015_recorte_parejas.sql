-- ==================================================================
-- 015_recorte_parejas.sql  |  Recorte por parejas del Healer + Op4 sin cupo
-- ==================================================================
-- Contexto:
--   * Sin recovery recortable (o con la recovery cubierta por una Op4 (T)), la
--     bolsa del Healer paga lotes iguales de dos patas opuestas: primero
--     recovery + Op4 (T), despues Op1 + su cobertura. El neto no cambia.
--     Recovery primero: con perdedor real amputable manda la amputacion.
--   * El cupo de Op4 (T) por ciclo pasa a 1000 (sin limite en la practica);
--     ya estaba en 1000 en las filas M15 desde el 19-oct (UPDATE manual).
-- Spec: docs/superpowers/specs/2026-10-19-recorte-por-parejas-design.md
-- Evidencia: docs/experimento-2/analisis-ciclo-paralelo-2026-10-19.md
--            docs/experimento-2/analisis-limite-op4-y-entrada-op1-2026-10-19.md
--
-- ESTADO: APLICADA en Supabase el 2026-10-19 (SQL Editor). Idempotente.
-- Sin aplicarla, el bot usa los DEFAULT de bot/strategy.py (recorte activo).
-- ==================================================================

ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS healer_pair_cut BOOLEAN DEFAULT true;

ALTER TABLE public.bot_config
    ALTER COLUMN rescue_trend_max_legs SET DEFAULT 1000;

-- ---- ROLLBACK (comentado) ------------------------------------------
-- [PROSA - NO DESCOMENTAR] Apaga el recorte por parejas, sin tocar codigo ni reiniciar.
-- UPDATE public.bot_config SET healer_pair_cut = false WHERE bot_id = 'm15';
