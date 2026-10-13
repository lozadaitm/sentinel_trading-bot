"""Alertas por correo con dedupe y deteccion de cuenta muerta. Best-effort: nunca tumba el motor."""

import time

from . import config, notify

DEAD_LOG_EVERY_S = 600      # un ERROR de cuenta muerta cada 10 min como maximo (hora servidor)


class AlertManager:
    """Envia correos de alerta con dedupe por `kind` dentro de `cooldown_s`."""

    def __init__(self, logger, to_addr, account_label, cooldown_s=21600,
                 sender=notify.send_async, clock=time.time):
        self.log = logger
        self.to_addr = to_addr
        self.label = account_label
        self.cooldown_s = cooldown_s
        self.sender = sender
        self.clock = clock
        self._last = {}
        self._warned_no_to = False

    def notify(self, kind, severity, subject, body):
        """True si envio; False si dedupe, sin destinatario o fallo del sender."""
        if not self.to_addr:
            if not self._warned_no_to:
                self._warned_no_to = True
                self.log.write("SYSTEM", "ALERT_EMAIL_TO sin configurar: las alertas por correo quedan desactivadas.")
            return False
        now = self.clock()
        last = self._last.get(kind)
        if last is not None and now - last < self.cooldown_s:
            return False
        self._last[kind] = now
        try:
            self.sender(self.to_addr, f"[Sentinel {severity}] {self.label}: {subject}", body, self.log)
        except Exception as e:  # noqa: BLE001
            self.log.write("ERROR", f"Fallo al enviar alerta '{kind}': {e}")
            return False
        return True


def account_dead(broker):
    """(True, motivo) si equity <= 0 o el terminal no permite operar."""
    try:
        if broker.account_equity() <= 0:
            return True, "equity <= 0"
        allowed, motivo = broker.trade_allowed()
        if not allowed:
            return True, motivo or "trading no permitido"
    except Exception:  # noqa: BLE001  (si no se puede evaluar, no se declara muerta)
        pass
    return False, ""


def make_manager(logger):
    """AlertManager con el destinatario y la etiqueta de la cuenta de este proceso."""
    label = f"{config.MT5_LOGIN or 'cuenta'}/{config.BOT_ID}"
    return AlertManager(logger, config.ALERT_EMAIL_TO, label)


def update_dead(engine):
    """Evalua la cuenta muerta en el tick: fija engine.dead, loguea (throttle) y alerta.

    Nunca cierra nada ni bloquea gestion/protectoras: solo marca para saltar aperturas
    aditivas. Se libera sola cuando la condicion desaparece.
    """
    dead, motivo = account_dead(engine.b)
    if not dead:
        if engine.dead:
            engine.log.write("SYSTEM", "Cuenta operativa de nuevo: se reanudan las aperturas aditivas.")
        engine.dead = False
        return
    engine.dead = True
    if engine.now - engine._dead_last_log >= DEAD_LOG_EVERY_S:
        engine._dead_last_log = engine.now
        engine.log.write("ERROR", f"CUENTA MUERTA ({motivo}): aperturas aditivas suspendidas.")
    engine.alerts.notify(
        "cuenta_muerta", "CRITICA", "cuenta muerta",
        f"La cuenta {engine.alerts.label} no puede operar: {motivo}.\n"
        f"Se suspenden las aperturas aditivas; la gestion y las protectoras siguen activas.")
