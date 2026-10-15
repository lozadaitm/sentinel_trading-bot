-- ==================================================================
-- 011_reentrada_suelo_hedge.sql  |  Re-entradas, suelo del hedge, horas NY
-- ==================================================================
-- Contexto:
--   * Re-entradas sobre la misma ruptura M15: se OBSERVAN (reentry_enforce =
--     false) las que entran a > reentry_max_atr * ATR del nivel roto. Con
--     reentry_enforce = true no se abren. reentry_max_atr = 0 apaga todo.
--   * Suelo del hedge: hedge_dist 350 -> 800 puntos (8 $ de precio). Manda
--     max(hedge_dist, 2*ATR), asi que hoy casi nunca cambia nada.
--   * Horas de riesgo: las de Nueva York (9-11 h NY) pasan a risk_hours_ny
--     y siguen solas su cambio de hora; risk_hours_utc queda en '1' (Asia).
-- Spec: docs/superpowers/specs/2026-10-15-reentrada-y-suelo-hedge-design.md
--
-- Secciones:
--   1. Columnas nuevas.
--   2. Defaults de columna (filas nuevas de futuras altas).
--   3. Valores vigentes (solo filas con el valor viejo; no pisa personalizados).
--   4. Bloque ROLLBACK (comentado).
--
-- ESTADO: APLICADA en Supabase el 2026-10-15 (SQL Editor). Idempotente.
-- ==================================================================

-- ---- 1. Columnas nuevas ------------------------------------------
ALTER TABLE public.bot_config
    ADD COLUMN IF NOT EXISTS risk_hours_ny    TEXT             DEFAULT '9,10,11',
    ADD COLUMN IF NOT EXISTS reentry_max_atr  DOUBLE PRECISION DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS reentry_enforce  BOOLEAN          DEFAULT false;

-- ---- 2. Defaults de columna ----------------------------------------
ALTER TABLE public.bot_config ALTER COLUMN hedge_dist     SET DEFAULT 800;
ALTER TABLE public.bot_config ALTER COLUMN risk_hours_utc SET DEFAULT '1';

-- ---- 3. Valores vigentes -------------------------------------------
UPDATE public.bot_config
   SET hedge_dist = 800
 WHERE bot_id = 'm15'
   AND hedge_dist = 350;

UPDATE public.bot_config
   SET risk_hours_utc = '1',
       risk_hours_ny  = '9,10,11'
 WHERE risk_hours_utc = '1,13,14,15';

-- ---- 4. ROLLBACK (comentado) --------------------------------------
-- [PROSA - NO DESCOMENTAR] Para revertir: descomenta solo las lineas de SQL.
-- [PROSA - NO DESCOMENTAR] Las columnas nuevas se conservan a proposito (el codigo viejo las ignora).
-- ALTER TABLE public.bot_config ALTER COLUMN hedge_dist     SET DEFAULT 350;
-- ALTER TABLE public.bot_config ALTER COLUMN risk_hours_utc SET DEFAULT '1,13,14,15';
-- UPDATE public.bot_config SET hedge_dist = 350 WHERE bot_id = 'm15' AND hedge_dist = 800;
-- UPDATE public.bot_config SET risk_hours_utc = '1,13,14,15', risk_hours_ny = ''
--  WHERE risk_hours_utc = '1' AND risk_hours_ny = '9,10,11';
-- UPDATE public.bot_config SET reentry_enforce = false, reentry_max_atr = 0;
