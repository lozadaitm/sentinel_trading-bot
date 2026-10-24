---
name: e2-demos-nuevas
description: 25-oct, las 3 demos nuevas del bot e2 (3k/10k/25k) quedaron provisionadas con BOTS=e2, instancias e2 apagadas y riesgo 0,0001 para la prueba en seco; el provisionador necesita credenciales de un .env activo
metadata:
  type: project
---

**2026-10-25: las 3 cuentas demo nuevas del bot e2 quedaron provisionadas** a mano, sin reinicio automático.

- Instancias `392d37a5`, `a487a7c8`, `c9499865` (USER_ID en `instances/<id>.env`).
- Cada `.env` tiene `BOTS=e2` y `MAGIC_E2=100300`.
- En Supabase:
  - `bot_instances` e2 con `is_active=false`;
  - `bot_config` e2 con `e2_risk_pct=0.0001`, para la prueba en seco.
- Sus filas m15/m5 del registro siguen ahí, apagadas. No se usan porque `BOTS=e2`.
- Antes de provisionar, las solicitudes pendientes venían con `bots=m15,m5` (el valor por defecto del registro) y se cambiaron a `e2`.

**Trampa descubierta:** `scripts/provision.py` saca `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` del entorno, del `.env` raíz o de algún `instances/*.env` activo (sin `_`).
- Al desactivar las demos viejas ([[demos-viejas-desactivadas]]), el provisionador se quedó sin credenciales y paró.
- Ahora las vuelve a encontrar en las instancias nuevas.

**Why:** si el provisionador hubiera corrido con `bots=m15,m5`, habría disparado `SentinelRestart` y arrancado el motor viejo en las cuentas nuevas ([[e2-motor-tres-patas]]).

**How to apply:**
- Para el paso 4 (prueba en seco), con permiso del usuario: arrancar una sola cuenta y activar su instancia e2.
- Después, `e2_risk_pct=0.08` en las tres.
- Al registrar perfiles nuevos para e2, cambiar `bots` a `e2` **antes** de que corra el provisionador.
- Conviene que el formulario de registro permita elegir `e2`.
