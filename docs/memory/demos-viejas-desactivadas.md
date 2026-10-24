---
name: demos-viejas-desactivadas
description: El 25-oct se desactivaron las 3 demos del Experimento 2 (logins 26275217/21/22): .env renombrados con «_» y bots M15/M5 detenidos; posiciones abiertas sin tocar
metadata:
  type: project
---

**2026-10-25, a pedido del usuario** («quitemos las demos actuales»).

Instancias desactivadas:

| Cuenta | Login | Instancia |
|---|---|---|
| 1k | 26275217 | `8d3501a8` |
| 5k | 26275221 | `cde65472` |
| 10k | 26275222 | `f9cbf02f` |

- Sus `.env` pasaron a `instances/_<id>.env`. `start_all.ps1`, `provision.py` y `daily_report.py` ignoran los archivos con `_`.
- Se detuvieron sus 12 procesos (`bot.lite` y `bot.lite_m5`).
- **No se cerraron sus posiciones abiertas.**
- `news_exporter` sigue activo.
- El colector de ticks sigue usando el terminal MT5 de 26275221. Cuando haya cuentas nuevas, conviene apuntarlo a una de ellas (`--login`).

**Why:** el bot pasa al diseño de tres patas ([[decision-bigone-combo]]) en tres demos nuevas (3 000 / 10 000 / 25 000).

**How to apply:**
- Para reactivar una, quitar el `_` del nombre del archivo y arrancarla, siempre con permiso del usuario.
- No arrancar los motores M15/M5 en las cuentas nuevas.
