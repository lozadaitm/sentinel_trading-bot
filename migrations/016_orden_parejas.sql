-- ==================================================================
-- 016_orden_parejas.sql  |  Orden del recorte por parejas del Healer
-- ==================================================================
-- Contexto:
--   * La bolsa del Healer paga primero la pareja Op1 + su cobertura (Op2) y
--     despues recovery + Op4 (T): por el mismo dinero frena el mismo swap
--     (~15 $/oz frente a ~93 $/oz en el ciclo del 14-oct). Se mantienen la
--     prioridad de la amputacion de la recovery y el ancla de la Op1 + Op2.
--   * 'recovery_first' vuelve al orden del 19-oct.
--   * (El arreglo del doble conteo de la bolsa no necesita configuracion.)
-- Spec: docs/superpowers/specs/2026-10-20-bolsa-sin-doble-conteo-y-op1op2-primero-design.md
-- Evidencia: docs/experimento-2/analisis-op4-criterio-propio-2026-10-19.md (secc. 3)
--
-- ESTADO: PENDIENTE de aplicar en Supabase (SQL Editor). Idempotente.
-- Sin aplicarla, el bot usa el DEFAULT de bot/strategy.py ('cover_first').
-- ==================================================================

ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS healer_pair_order TEXT DEFAULT 'cover_first';

-- ---- ROLLBACK (comentado) ------------------------------------------
-- [PROSA - NO DESCOMENTAR] Vuelve al orden "recovery primero", sin tocar codigo ni reiniciar.
-- UPDATE public.bot_config SET healer_pair_order = 'recovery_first' WHERE bot_id = 'm15';
