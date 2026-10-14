"""Alertas por correo con dedupe y deteccion de cuenta muerta. Best-effort: nunca tumba el motor."""

import inspect
import time

from . import config, notify

DEAD_LOG_EVERY_S = 600      # un ERROR de cuenta muerta cada 10 min como maximo (hora servidor)
RETRY_AFTER_FAIL_S = 60     # tras un envio fallido, no reintentar antes (evita un intento por tick)
ZERO_EQUITY_CONFIRM = 2     # lecturas equity <= 0 en ticks distintos para declarar la cuenta muerta
DEAD_ALERT_CONFIRM_S = 30   # la CRITICA "cuenta muerta" solo sale si dura >= 30 s (hora servidor)


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
        self._retry_at = {}
        self._warned_no_to = False
        try:   # solo el sender real (send_async) acepta el callback de fallo
            self._sender_has_on_fail = "on_fail" in inspect.signature(sender).parameters
        except (TypeError, ValueError):
            self._sender_has_on_fail = False

    def notify(self, kind, severity, subject, body):
        """True si envio; False si dedupe, sin destinatario o fallo del sender.

        Un envio fallido (excepcion o sender que devuelve False) NO consume la espera
        del dedupe: se restaura el `_last` previo para poder reintentar (tras una
        pausa corta, para no martillar en cada tick). El sender real (send_async)
        manda en un hilo y devuelve None: sus fallos transitorios (HTTP, timeout) los avisa llamando a `on_fail` desde ese hilo; el callback
        solo asigna en dos dicts (sin tocar el logger).
        """
        if not self.to_addr:
            if not self._warned_no_to:
                self._warned_no_to = True
                self.log.write("SYSTEM", "ALERT_EMAIL_TO sin configurar: las alertas por correo quedan desactivadas.")
            return False
        now = self.clock()
        last = self._last.get(kind)
        if last is not None and now - last < self.cooldown_s:
            return False
        if now < self._retry_at.get(kind, 0.0):
            return False   # reintento tras fallo: aun en pausa corta
        self._last[kind] = now
        failed = [False]

        def restore():
            # No consume la espera: restaura el estado previo y pausa el reintento.
            # Idempotente y apta para el hilo del sender (solo asignaciones a dict).
            if self._last.get(kind) == now:
                if last is None:
                    self._last.pop(kind, None)
                else:
                    self._last[kind] = last
            self._retry_at[kind] = now + RETRY_AFTER_FAIL_S
            failed[0] = True

        kw = {"on_fail": restore} if self._sender_has_on_fail else {}
        try:
            ok = self.sender(self.to_addr, f"[Sentinel {severity}] {self.label}: {subject}", body, self.log, **kw)
        except Exception as e:  # noqa: BLE001
            self.log.write("ERROR", f"Fallo al enviar alerta '{kind}': {e}")
            ok = False
        if ok is False or failed[0]:
            restore()
            return False
        self._retry_at.pop(kind, None)
        return True


def account_dead(broker, engine=None):
    """(True, motivo) si equity <= 0 o el terminal no permite operar.

    Con `engine`, equity <= 0 solo cuenta tras ZERO_EQUITY_CONFIRM lecturas en ticks
    distintos (engine.now), igual que el guard `_empty_reads`: un 0 pasajero no manda
    CRITICA. Sin `engine` (llamada directa) se evalua al instante.

    Equity desconocido (None: account_info fallo) NO es cuenta muerta: esa
    parte no se puede evaluar y no se declara (ni ERROR ni CRITICA por una
    lectura fallida). El permiso del terminal se sigue comprobando.
    """
    try:
        equity = broker.account_equity()
        if engine is not None:
            if equity is not None and equity <= 0:
                now = getattr(engine, "now", None)
                if now != getattr(engine, "_zero_equity_now", None):
                    engine._zero_equity_now = now
                    engine._zero_equity_reads = getattr(engine, "_zero_equity_reads", 0) + 1
                if engine._zero_equity_reads >= ZERO_EQUITY_CONFIRM:
                    return True, "equity <= 0"
            else:
                engine._zero_equity_reads = 0   # positiva o desconocida: se corta la racha
                engine._zero_equity_now = None
        elif equity is not None and equity <= 0:
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
    aditivas. Se libera sola cuando la condicion desaparece. La marca es inmediata;
    la CRITICA por correo solo si la condicion dura DEAD_ALERT_CONFIRM_S seguidos.
    """
    dead, motivo = account_dead(engine.b, engine)
    if not dead:
        if engine.dead:
            engine.log.write("SYSTEM", "Cuenta operativa de nuevo: se reanudan las aperturas aditivas.")
        engine.dead = False
        engine._dead_since = None
        return
    engine.dead = True   # el bloqueo de aperturas es inmediato
    if getattr(engine, "_dead_since", None) is None:
        engine._dead_since = engine.now
    if engine.now - engine._dead_last_log >= DEAD_LOG_EVERY_S:
        engine._dead_last_log = engine.now
        engine.log.write("ERROR", f"CUENTA MUERTA ({motivo}): aperturas aditivas suspendidas.")
    # El correo espera a que la condicion dure DEAD_ALERT_CONFIRM_S: un "trading
    # deshabilitado" de 1-2 s al iniciar sesion la cuenta no manda CRITICA (2026-10-14).
    if engine.now - engine._dead_since < DEAD_ALERT_CONFIRM_S:
        return
    engine.alerts.notify(
        "cuenta_muerta", "CRITICA", "cuenta muerta",
        f"La cuenta {engine.alerts.label} no puede operar: {motivo}.\n"
        f"Se suspenden las aperturas aditivas; la gestion y las protectoras siguen activas.")
