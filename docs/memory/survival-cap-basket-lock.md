---
name: survival-cap-basket-lock
description: Decisión firme (13-oct-2026): tope de supervivencia 350 $, candado de cesta a 150 $, desbloqueo solo con rebote >= 50 $, disolución por parejas tras 24 h
metadata:
  node_type: memory
  type: project
---

Decisión firme de experimento-2 (13-oct-2026). Lo que el bot hace ahora:

- **Tope de supervivencia:** ninguna orden nueva se acepta si la cuenta dejaría de aguantar **350 $ por onza** de movimiento adverso antes del stop-out. Sustituye a los topes de lotes fijos (`max_net_lots`, `max_entry_lots`, `max_recovery_lots`, `m5_max_lot_cap` quedan en 0 = sin tope).
- **Candado de cesta a 150 $:** si el aguante S cae bajo `lock_trigger_usd`, se pone el candado (cesta neutra, congelada).
- **Desbloqueo solo con rebote favorable >= 50 $**, nunca por continuación del movimiento adverso; se afloja hasta recuperar S >= 350 $.
- **Disolución por parejas tras 24 h** (fracción 0.34, ventana 3-4 UTC), sin re-exponer y con deuda persistente: sin parejas nuevas hasta cerrar la anterior.
- **Umbrales en movimiento de precio** (USD por onza, no en dinero): cesta 0.83, rescate 0.56, verde mínimo 0.33, retroceso 0.11-5.6 (fijo 0.22), unwind 3.33, rescates L2 16.7 / L3 44.4.
- **`news_enforce` activado:** el NewsGuard bloquea de verdad. Horas de riesgo `1` UTC + `9,10,11` hora de Nueva York desde la migración 011 (antes `1,13,14,15` UTC); ver [[reentry-observation-hedge-floor]].
- **Alertas** por email (`ALERT_EMAIL_TO`) en los eventos de protección.

Migración: `migrations/010_supervivencia.sql` (pendiente de aplicar hasta el OK del usuario). Spec: `docs/superpowers/specs/2026-10-13-candado-supervivencia-design.md`.

**Why:** los topes de lotes fijos no reflejan el riesgo real (depende de equity y margen); el oro se mueve cientos de dólares y liquida cuentas con lotes "pequeños". Medir el aguante en dólares de precio da un límite honesto, y el candado evita el stop-out sin recurrir a un stop.

**How to apply:** cualquier mecanismo que añada exposición debe pasar por el tope de supervivencia; los umbrales nuevos se expresan en movimiento de precio. El candado congela, no cierra: coherente con [[bot-design-constraints]] (nada de stops duros; la cobertura se respeta). Detalle y migración en el spec `docs/superpowers/specs/2026-10-13-candado-supervivencia-design.md` (§5.11).
