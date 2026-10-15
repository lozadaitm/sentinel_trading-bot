---
name: mt5-updates-and-onboarding
description: Lecciones del alta del 2026-10-14 — autoupdate de MT5 tumba el IPC, provisioner como SYSTEM no siembra el perfil, Algo Trading se pierde; arreglos y procedimiento
metadata:
  type: project
---

Alta de 3 cuentas demo nuevas el 2026-10-14 (26275217, 26275221, 26275222). Fallaron tres
cosas a la vez y los 12 bots quedaron caídos ~45 min (sin daño: las cuentas estaban FLAT).

**1. Autoactualización de MT5 → IPC timeout (-10005).**
- MT5 descargó la build 6230 y pidió "reiniciar ahora / después".
- Con la actualización a medias, los clones dejaron de atender a Python, incluso los que funcionaban desde hacía meses.
- La librería `MetaTrader5` de Python era la 6090.
- Se resolvió cerrando todos los terminales y relanzando: la actualización se aplicó sola al abrir.
- **Regla:** las actualizaciones de MT5 se aplican **el fin de semana** (mercado cerrado): parar bots → actualizar → `pip install MetaTrader5==<build>` alineada → `restart_all`.
- Entre semana, al aviso de actualización se responde "Después".
- `scripts/mt5_prep.py` (lo llama `start_all`) avisa si la build del terminal no casa con la librería.

**2. El provisioner corre como SYSTEM y no encontraba el perfil maduro del base.**
- Lo busca en `%APPDATA%`, pero el perfil vive en el `%APPDATA%` del operador (`C:\Users\Administrator\...`).
- Como no lo encontraba, los clones nuevos nacían sin sembrar → IPC timeout.
- Además, la marca de "ya sembrado" era `settings.ini`, que la copia del base ya podía traer.
- **Arreglo en `scripts/provision.py`:**
  - recorre `C:\Users\*\AppData\Roaming\MetaQuotes\Terminal` (`MT5_USERS_ROOT`);
  - acepta `MT5_BASE_PROFILE` como override;
  - usa la marca propia `config\sentinel_seeded.txt`.
- **Arreglo manual de urgencia:** copiar el `config` del perfil del base (sin `accounts.dat` ni `common.ini`) al clon, con los terminales cerrados.

**3. Algo Trading apagado.**
- El provisioner escribía `[Experts] Enabled=1` solo si `common.ini` no existía; el terminal lo reescribía sin esa sección.
- El bot lo detecta (CUENTA MUERTA / APERTURAS BLOQUEADAS) pero no opera.
- **Arreglo:** `scripts/mt5_prep.ensure_algo_trading` lo fuerza en **cada** arranque (`start_all`, con los terminales ya cerrados por `restart_all`) y en el provisioner.

**Otros datos del día:**
- **Cuentas retiradas:** 25924397 (credencial rechazada `-6`, muy probablemente demo caducada por inactividad), 25912766 y 25556247 (quemadas). Sus `.env` llevan prefijo `_`.
- **Avisos por correo:** `ALERT_EMAIL_TO` va en el `.env` de la raíz (default para todas las instancias, incluidas las nuevas).
- **El provisioner dispara `SentinelRestart` solo al crear instancias.** Renombrar con `_` los `.env` retirados ANTES de las altas, o el reinicio los relanza.
- **La contraseña MT5 solo vive en el `.env` de la instancia** (no está en git ni en la DB). Si se pierde, hay que restablecerla en el portal del broker.

**Why:** que la próxima alta sea automática de principio a fin (invitación → signup → bot operando), sin pasos manuales en el VPS.

**How to apply:** ante un IPC timeout, sospechar primero de una actualización de MT5 a medias o de un clon sin sembrar. Ver [[mt5-clone-ipc-profile-seed]] y [[private-signup-provisioning]].

**Pendiente de mantenimiento (fin de semana tras el 2026-10-14):**
- `pip install MetaTrader5` de la build de los terminales (6230 → librería 6231; hoy está la 6090).
- `restart_all` tras actualizar la librería; verificar en Supabase que 26275217/21/22 vuelven a RUNNING.
  (El fix de inactividad a2f07d7 ya se cargó con el reinicio del 2026-10-15.)
- Luego, revisión de los primeros días del candado (tiempo CONGELADO, re-candados, coste de rebotes falsos, avisos).
