---
name: healer-deal-window-lag
description: Fix (19-oct-2026): la ventana de history_deals del M15 iba 3 h atrasada (naive datetime = hora local del PC); el Healer veía cada cierre 3 h tarde. Ahora + 1 día, cursor y bolsa persisten en el meta del ciclo y la bolsa espera con una Op4 (T) abierta
metadata:
  type: project
---

**Qué pasó (19-oct-2026):**
- La primera Op4 (T) cerró por trailing con +149 $ (cuenta de 10k), pero el Healer no recortó la recovery.
- `_deal_window_end()` devolvía hora de servidor + 5 min. La librería de MT5 interpreta el datetime naive como hora local del PC (UTC+3), y los deals llevan la hora de servidor (UTC+3) metida en el epoch. Resultado: la ventana terminaba ~3 h antes del último deal.
- Afectaba desde siempre al Healer, al aviso de stop-out y a la alerta de inactividad del M15. Comprobado leyendo el terminal en solo lectura.

**Arreglo (aprobado por el usuario):**
1. `_deal_window_end()` del M15 = hora de servidor + 1 día. Los consumidores filtran por ticket o solo preguntan si hay alguno, así que no duplica nada.
2. Si no hay perdedor amputable pero hay una Op4 (T) abierta, la bolsa **espera** (log «bolsa X $ en espera») en vez de liberarse. Cuando la Op4 cierra, recorta la recovery con todo lo acumulado.
3. Cursor y bolsa del Healer persisten en el meta del ciclo (`healer_cursor`, `healer_budget`). El arranque los restaura si hay posiciones; el cierre del ciclo los borra.
4. Una sola vez, al desplegar, se sembró `healer_cursor` en los 3 ledgers con el ticket del deal de apertura de la Op4 (T) del viernes 16-oct, para que cuente el +149 $ (y lo equivalente en 1k/5k).

**Pendiente:** el M5 (`strategy_m5.py`, `_refresh_last_trade_result`) tiene el mismo retraso de 3 h para saber si su última operación fue ganadora. No se tocó: cambia entradas del M5 en plena evaluación del trailing ATR; decidir con el usuario.

Relacionado: [[op4-trend]], [[healer-real-loser-bag]].

**Despliegue (19-oct-2026, ~00:05 UTC):** el primer arreglo (4c28e9d) no bastó porque `_check_healing` calculaba su propia ventana; corregido en 2dfec24. Tras el reinicio, el Healer restauró el cursor sembrado y dejó en espera la bolsa de las dos primeras Op4 (T) (237 $ en 10k, 119 $ en 5k, 21 $ en 1k) mientras la 3.ª Op4 sigue abierta.
