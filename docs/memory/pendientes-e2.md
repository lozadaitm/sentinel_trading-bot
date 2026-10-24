---
name: pendientes-e2
description: Pendientes del bot e2 «tres patas» a resolver según cómo salga la demo (registro por defecto en e2, feriados, guardas menores, tamaño del archivo, soporte del dashboard)
metadata:
  type: project
---

Pendientes abiertos del motor e2 ([[e2-motor-tres-patas]]). Se deciden según cómo salga la demo de 10 semanas ([[e2-demos-nuevas]]).

1. **Si el bot funciona, el registro debe crear las cuentas con e2 por defecto.**
   - Hoy el formulario o `provision_requests` usa `bots=m15,m5` y hay que cambiarlo a `e2` a mano antes de que corra el provisionador.
   - A cambiar: el default del registro y del panel, `provision.py` (`req.get("bots") or "m15,m5"`) y la siembra de `bot_config`/`bot_instances` de la migración 008, para que se creen las filas e2 en vez de m15/m5. Pedido por el usuario el 25-oct.
2. **Feriados:** hoy se saltan todos los feriados federales de EE. UU. Columbus Day y Veterans Day se podrían recuperar (unas 2 entradas de momentum al año), porque el oro opera normal esos días.
3. **Guarda adicional:** al reiniciar sin archivo de estado dentro de los 60 s de una entrada, una lectura vacía de MT5 podría dejar pasar una segunda escalera. Hoy la reconciliación la adopta y la salida la cierra. Opción: contar la lectura vacía solo si la cuenta está plana (margen 0).
4. **Archivo:** `bot/strategy_e2.py` tiene unas 1 200 líneas. Conviene dividirlo, por ejemplo en entradas, gestión y reconciliación.
5. **Dashboard:** no conoce el `bot_id` e2. Hoy la instancia se activa por base de datos.
6. **Colector de ticks:** apuntarlo (`--login`) a una cuenta nueva y cerrar los terminales de las demos viejas.
