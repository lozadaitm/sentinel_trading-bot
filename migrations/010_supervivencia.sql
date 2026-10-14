-- ==================================================================
-- 010_supervivencia.sql  |  Tope de supervivencia + candado de cesta
-- ==================================================================
-- Contexto: los topes de lotes fijos (max_net_lots, max_entry_lots,
-- max_recovery_lots, m5_max_lot_cap) se sustituyen por un tope de
-- SUPERVIVENCIA: la cuenta debe aguantar survival_move_usd (350 $ por onza)
-- de movimiento adverso antes del stop-out. Bajo lock_trigger_usd (150 $)
-- se pone el candado de cesta; solo se afloja con un rebote favorable
-- >= unlock_rebound_usd (50 $), nunca por continuacion; tras
-- lock_dissolve_after_h horas se disuelve por parejas. Los umbrales de
-- cesta/rescate pasan a ser movimiento de precio (USD por onza).
-- Spec: docs/superpowers/specs/2026-10-13-candado-supervivencia-design.md (§5.11)
--
-- Secciones:
--   1. Columnas nuevas (DOUBLE PRECISION salvo las dos TEXT y news_enforce BOOLEAN).
--   2. Topes de lotes fijos desactivados (0 = sin tope) y news_enforce = true.
--   3. Drift de config en vivo corregido (m15 y m5).
--   4. Bloque ROLLBACK (comentado).
--
-- ESTADO: PENDIENTE de aplicar en Supabase (SQL Editor). Idempotente.
-- ==================================================================

-- ---- 1. Columnas nuevas ------------------------------------------
-- Garantiza las columnas del drift (ya creadas en 002_bot_id.sql; no-op si existen).
ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS margin_cap_pct DOUBLE PRECISION DEFAULT 60.0,
    ADD COLUMN IF NOT EXISTS ml_no_add      DOUBLE PRECISION DEFAULT 200.0,
    ADD COLUMN IF NOT EXISTS ml_flatten     DOUBLE PRECISION DEFAULT 0.0;

ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS survival_move_usd        DOUBLE PRECISION DEFAULT 350.0,
    ADD COLUMN IF NOT EXISTS lock_trigger_usd         DOUBLE PRECISION DEFAULT 150.0,
    ADD COLUMN IF NOT EXISTS unlock_rebound_usd       DOUBLE PRECISION DEFAULT 50.0,
    ADD COLUMN IF NOT EXISTS risk_hours_utc           TEXT             DEFAULT '1,13,14,15',
    ADD COLUMN IF NOT EXISTS lock_dissolve_after_h    DOUBLE PRECISION DEFAULT 24,
    ADD COLUMN IF NOT EXISTS lock_dissolve_fraction   DOUBLE PRECISION DEFAULT 0.34,
    ADD COLUMN IF NOT EXISTS lock_dissolve_hours_utc  TEXT             DEFAULT '3,4',
    ADD COLUMN IF NOT EXISTS basket_arm_move_usd      DOUBLE PRECISION DEFAULT 0.83,
    ADD COLUMN IF NOT EXISTS rescue_arm_move_usd      DOUBLE PRECISION DEFAULT 0.56,
    ADD COLUMN IF NOT EXISTS min_green_move_usd       DOUBLE PRECISION DEFAULT 0.33,
    ADD COLUMN IF NOT EXISTS retrace_min_move_usd     DOUBLE PRECISION DEFAULT 0.11,
    ADD COLUMN IF NOT EXISTS retrace_max_move_usd     DOUBLE PRECISION DEFAULT 5.6,
    ADD COLUMN IF NOT EXISTS fixed_retrace_move_usd   DOUBLE PRECISION DEFAULT 0.22,
    ADD COLUMN IF NOT EXISTS unwind_floor_move_usd    DOUBLE PRECISION DEFAULT 3.33,
    ADD COLUMN IF NOT EXISTS rescue_l2_move_usd       DOUBLE PRECISION DEFAULT 16.7,
    ADD COLUMN IF NOT EXISTS rescue_l3_move_usd       DOUBLE PRECISION DEFAULT 44.4;

ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS news_enforce BOOLEAN DEFAULT true;

-- ---- 2. Topes de lotes fijos desactivados -------------------------
UPDATE public.bot_config
   SET news_enforce      = true,
       max_net_lots      = 0,
       max_entry_lots    = 0,
       max_recovery_lots = 0,
       m5_max_lot_cap    = 0;

-- ---- 3. Drift de config en vivo -----------------------------------
UPDATE public.bot_config
   SET margin_cap_pct = 60,
       ml_no_add      = 200,
       ml_flatten     = 0,
       inp_max_spread = 350
 WHERE bot_id = 'm15';

UPDATE public.bot_config
   SET margin_cap_pct = 60,
       ml_no_add      = 200,
       ml_flatten     = 0
 WHERE bot_id = 'm5';

-- ---- 4. ROLLBACK (comentado) --------------------------------------
-- [PROSA - NO DESCOMENTAR] ANTES de aplicar esta migracion, ejecuta este
-- [PROSA - NO DESCOMENTAR] SELECT y guarda la salida EN LOCAL (no en el repo;
-- [PROSA - NO DESCOMENTAR] el repo es publico):
--
--   SELECT user_id, bot_id, margin_cap_pct, ml_no_add, ml_flatten, inp_max_spread
--     FROM public.bot_config;
--
-- [PROSA - NO DESCOMENTAR] Para revertir: descomenta solo las lineas de SQL.
-- [PROSA - NO DESCOMENTAR] Las columnas nuevas se conservan a proposito (el codigo viejo las ignora).
--
-- UPDATE public.bot_config
--    SET max_net_lots      = 1,
--        max_entry_lots    = 1,
--        max_recovery_lots = 2,
--        m5_max_lot_cap    = 0.5,
--        news_enforce      = false;
--
-- [PROSA - NO DESCOMENTAR] ATENCION: los dos UPDATE siguientes DEBEN
-- [PROSA - NO DESCOMENTAR] restringirse a la UNICA fila identificada en el
-- [PROSA - NO DESCOMENTAR] SELECT guardado en local (solo una fila de cada bot
-- [PROSA - NO DESCOMENTAR] tenia esos valores). Sin el filtro por user_id se
-- [PROSA - NO DESCOMENTAR] aplicarian a TODAS las filas.
--
-- [PROSA - NO DESCOMENTAR] La fila m5 que tenia 10 / 400 / 250 (margin_cap_pct / ml_no_add / ml_flatten):
-- UPDATE public.bot_config
--    SET margin_cap_pct = 10, ml_no_add = 400, ml_flatten = 250
--  WHERE bot_id = 'm5'
--    AND user_id = '<UUID de la fila, tomado del SELECT guardado>';
--
-- [PROSA - NO DESCOMENTAR] La fila m15 que tenia inp_max_spread 300. Sus
-- [PROSA - NO DESCOMENTAR] margin_cap_pct / ml_no_add / ml_flatten ya eran
-- [PROSA - NO DESCOMENTAR] 60 / 200 / 0 (iguales a los nuevos): no requieren cambio.
-- UPDATE public.bot_config
--    SET inp_max_spread = 300
--  WHERE bot_id = 'm15'
--    AND user_id = '<UUID de la fila, tomado del SELECT guardado>';
