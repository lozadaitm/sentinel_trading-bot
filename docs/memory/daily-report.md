---
name: daily-report
description: Reporte diario por correo (scripts/daily_report.py, solo lectura), tarea SentinelDailyReport de lunes a viernes a las 22:15 UTC; estado en instances/daily_report_state.json
metadata:
  type: reference
---

**Qué hace:** `scripts/daily_report.py` envía un correo por Resend a `ALERT_EMAIL_TO` (el `.env` de la raíz) con, por cuenta:
- equity, balance y cambio frente al reporte anterior;
- lo realizado en 24 h por M15 y por M5;
- el swap de las posiciones abiertas;
- el estado del ciclo M15 (si está CONGELADO);
- la bolsa del curador, los recortes y amputaciones del día;
- latidos y errores agrupados por tipo.

Si algo va mal, el asunto termina en «REVISAR».

**Solo lectura:** MT5 con lecturas ligeras contra los terminales abiertos, Supabase (GET) y el ledger.

**Programación:** tarea de Windows `SentinelDailyReport`, a las 22:15 UTC de lunes a viernes, justo después del rollover del swap.
- El servidor está en hora de Israel. El trigger está en UTC (StartBoundary con offset) y los días de la tarea van de martes a sábado en hora local.
- La salida se guarda en `instances/daily_report.log`.
- **Revisar tras el cambio de horario de Israel (25-oct-2026)** que siga llegando a las 22:15 UTC.

**Uso manual:** `python -m scripts.daily_report --dry-run` imprime el reporte sin enviar ni guardar.

Relacionado: [[fullsim-simulator]].
