"""SentinelEngine: motor M15, derivado del EA MQL5 'M15 Gold Sentinel HyperGrinder v20.0'.

Maquina de estados derivada de los ROLES del CycleLedger (bot/ledger.py):
cada posicion tiene identidad (ENTRY/HEDGE/RECOVERY/RESCUE/ORPHAN) y el par
OP1<->OP2 es atomico. El conteo (0/1/2/3+) del MQL5 original se conserva como
profundidad del CICLO (cycle_legs: excluye huerfanos), no del magic entero:
contar posiciones sin identidad re-etiquetaba hedges huerfanos como OP1 y
construia ciclos sobre bases falsas (ver docs/memory/
unwind-orphans-hedge-count-state). on_tick() replica OnTick del MQL5.
Los parametros se reciben en self.cfg (cargados de bot_config).

El scalper M5 que el EA original llevaba embebido ("Bio-Reactor / Smart
Grinder") YA NO VIVE AQUI: se extrajo a su propio proceso y su propio magic
(bot/strategy_m5.py). Consecuencia directa: todas las posiciones que este
motor ve por su magic son cesta core, sin excepciones ni filtros de identidad.

Indexacion: ver bot/indicators.py. MQL5 [0]==.iloc[-1], [1]==.iloc[-2].
Tiempos: se usa el epoch del servidor (tick.time) para todas las comparaciones
de tiempo, consistente con position.time.
"""

import datetime
import math

import MetaTrader5 as mt5
import pandas as pd

from . import alerts, budget, config, indicators, ledger, news, survival

# Defaults = valores input del MQL5 (fallback si falta la columna en bot_config)
DEFAULTS = {
    "inp_max_spread": 350,
    "base_risk": 5000.0, "base_lots": 0.12, "max_entry_lots": 0.0, "max_recovery_lots": 0.0,  # 0 = sin tope fijo (manda el de supervivencia)
    "use_basket_close": True, "basket_percent": 0.15, "commission_per_lot": 6.0,
    "use_dynamic_retrace": True, "retrace_atr_mult": 0.1, "fixed_retrace": 2.0,
    "use_dynamic_hedge": True, "hedge_dist": 800, "hedge_atr_mult": 2.0,  # suelo 800 pt = 8 $ (spec 2026-10-15)
    "use_healer": True, "healer_balance_bias": True, "healer_min_core": 3, "use_unwind_mode": True,
    "healer_min_move_usd": 2.0,       # perdedor real: >= N $/oz en contra (spec 2026-10-16; 0 = cualquier rojo)
    "unwind_atr_mult": 2.0, "unwind_money_floor": 30.0,
    "use_pullback": True, "atr_entry_distance": 2.5, "use_h4_struct": True,
    "entry_rsi_max": 75, "entry_rsi_min": 25,
    "use_smart_trail": True, "trail_activate": 1.0, "trail_dist_atr": 1.5,
    "use_op3_trail": True, "op3_start_atr": 0.60, "op3_base_dist_atr": 0.40,
    "op3_turbo_trigger_atr": 3.0, "op3_turbo_dist_atr": 1.2,
    "use_m5_confirm": True, "min_tech_wait": 60,
    "use_rescue_mode": True, "rescue_atr_mult": 4.0, "rescue_rsi": 70,
    "rescue_target_pct": 0.10, "dd_percent_l2": 3.0, "dd_percent_l3": 8.0,
    "fast_ma": 9, "atr_period": 14, "close_friday": True, "friday_hour": 20,
    "monday_start_hour": 10, "cooldown_seconds": 10,
    # --- Nuevos (optimizaciones de esta revision) ---
    "recovery_min_spacing_atr": 1.0,  # OP3 anti-espera v2: separacion minima por ATR del ultimo leg
    "rescue_cooldown": 30,            # OP4: segundos minimos entre rescates (anti-spam de L3)
    "min_green_profit": 3.0,          # OP12: piso verde del trail en OP1 sola; bajo esto se desarma a hedge (no cierra rojo)
    # --- Fork A: respiro/supervivencia ante volatilidad anomala (noticia/manipulacion) ---
    "use_vol_breaker": True,          # VCB: circuit breaker de volatilidad (bloquea aperturas, no la gestion)
    "vcb_atr_mult": 2.8,              # VCB: dispara si el rango de la vela M15 en curso >= ATR * este mult
    "max_net_lots": 0.0,              # OBSOLETO (rollback): ya nadie lo lee; manda el tope de supervivencia
    "max_rescue_legs": 3,             # cap de legs de Op4 por ciclo (acota el martingala)
    "use_recovery_h4_gate": True,     # no promediar (recovery/rescue) contra la estructura H4 confirmada
    # --- NewsGuard Fase 1 (bloqueo duro por noticias rojas; ver bot/news.py) ---
    "news_enforce": True,             # True = ENFORCEMENT: bloquea aperturas en ventana roja (False = solo observacion)
    "news_pre_seconds": 7200,         # ventana previa: T-2h (una OP1 abierta despues llega al dato sin colchon)
    "news_post_seconds": 3600,        # ventana posterior: T+1h (clusters se funden por solape de ventanas)
    "news_currencies": "USD",         # divisas cuyas rojas cuentan (coma-separado); el oro es un trade de USD
    # --- Gobierno de margen (convivencia con el bot M5; ver bot/budget.py) ---
    "equity_weight": 0.80,            # fraccion del equity que dimensiona el lote de ESTE bot
    "margin_cap_pct": 60.0,           # techo de margen propio, en % del equity
    "ml_no_add": 200.0,               # bajo este margin level no se abren aditivas (el hedge sigue)
    "ml_flatten": 0.0,                # el senior nunca se auto-liquida: lo hace el M5
    # --- Re-entradas sobre la misma ruptura (spec 2026-10-15-reentrada-y-suelo-hedge) ---
    "reentry_max_atr": 1.0,           # re-entrada "lejana" si el precio esta a > N*ATR del nivel roto (0 = apagado)
    "reentry_enforce": False,         # False = solo observacion (abre y loguea); True = no abre la lejana
    # --- Op4 a favor del movimiento (spec 2026-10-16-op4-tendencia) ---
    "rescue_mode": "trend",           # 'trend' = contra la pata que pierde (reduce el neto); 'copy' = martingala vieja
    "rescue_trend_k_atr": 2.0,        # dispara con la recovery/rescue a >= K*ATR M15 en contra (cierre de vela)
    "rescue_trend_max_legs": 6,       # cupo de Op4 por ciclo en modo trend (cuenta rescue_opened)
    "rescue_trend_trail_start_atr": 1.0,  # trailing propio de la Op4 (T): arranque en ATR
    "rescue_trend_trail_dist_atr": 0.5,   # y distancia en ATR (sin turbo)
}
# Tope de supervivencia y umbrales en movimiento (bot/survival.py): solo se
# anaden las claves que este motor no define (equity_weight mantiene su 0.80).
for _k, _v in survival.DEFAULTS.items():
    DEFAULTS.setdefault(_k, _v)

OP4_TREND_COMMENT = "Sentinel Op 4 (T)"   # prefijo "Sentinel Op 4" => rol RESCUE en el ledger

# Estados del candado de cesta (spec §5.3)
LOCK_FREE = "LIBRE"        # sin patas LOCK
LOCK_FROZEN = "CONGELADO"  # patas LOCK y neto propio 0: nada cambia el neto
LOCK_LOOSE = "AFLOJADO"    # patas LOCK con neto residual: operativa normal, LOCK intocable
LOCK_FAIL_LOG_EVERY_S = 600
DISSOLVE_RETRY_S = 60       # backoff de reintento de la disolucion por parejas (R14)

def _struct_txt(v):
    return {1: "Alcista (+1)", -1: "Bajista (-1)"}.get(v, "Neutral (0)")


def _sig_txt(v):
    return {1: "Ruptura alza (+1)", -1: "Ruptura baja (-1)"}.get(v, "Sin ruptura (0)")


class SentinelEngine:
    def __init__(self, broker, logger):
        self.b = broker
        self.log = logger
        self.cfg = {}
        self.hud = {}  # snapshot read-only publicado cada tick para la TUI

        # Gobierno de margen. Rol SENIOR: este motor no reserva margen para
        # nadie y sus protectoras (Hedge Lock) son inbloqueables. Es el bot M5
        # quien cede. Lee la config vigente por referencia (main la refresca).
        self.gov = budget.MarginGovernor(
            broker, lambda: self.cfg, budget.ROLE_SENIOR,
            peer_magics=config.PEER_MAGICS, logger=logger)

        # Tope de supervivencia de la cuenta (bot/survival.py). El cfg_provider
        # mezcla los DEFAULTS del motor con la config vigente (esta gana).
        self.surv = survival.SurvivalGuard(
            broker, lambda: {**DEFAULTS, **(self.cfg or {})}, logger, config.MAGIC_NUMBER)

        # Identidad por ROL de cada posicion del ciclo (persistida por
        # instancia; rehidratable desde los comments de MT5 tras un restart).
        self.cycle = ledger.CycleLedger(config.LEDGER_PATH, logger)

        # NewsGuard (Fase 1): ventana dura alrededor de noticias rojas.
        # Complementa al VCB: el VCB es reactivo (la vela ya exploto), este es
        # predictivo (la vela va a explotar y esta agendada).
        self.news = news.NewsGuard(config.NEWS_CALENDAR_PATH, logger)
        self.news_active = False      # dentro de una ventana de noticia este tick
        self.news_block = False       # ventana activa Y news_enforce=True
        self.news_reason = None       # texto del evento que manda (HUD/logs)

        # Estado (globals del MQL5)
        self.last_recovery_close_time = 0
        self.last_healed_ticket = 0
        self.cycle_realized = 0.0            # B: P&L realizado del ciclo en curso (para el freeze del Unwind)
        self._healer_needs_rebaseline = True  # C: al iniciar ciclo, rebasa el cursor del Healer (presupuesto por ciclo)
        self._cover_protect_logged = False    # dedupe del aviso de cobertura protegida (1 por ciclo)
        self.healer_budget = 0.0             # bolsa del Healer: 90% de lo ganado CON perdedor real (spec 2026-10-16)
        self.max_cycle_peak = 0.0
        self.cycle_armed = False      # trailing de cesta armado (OP8/OP9)
        self.spread_high = False      # cache del filtro de spread del tick actual
        self.close_only = False       # modo wind-down: bloquea aperturas, deja gestion/cierres (bot_instances.is_active=false)
        self.is_active = False         # espejo de bot_instances.is_active (Supabase) para la UI; lo setea main.trading_loop
        self.user_email = None         # email del usuario (auth.users) para identificar la instancia en la UI
        self.last_rescue_time = 0     # cooldown de rescate (OP4)
        self._last_additive_sent = False  # _open_additive llego a enviar orden
        self.alerts = alerts.make_manager(logger)
        self.dead = False             # cuenta muerta: salta aperturas aditivas (se libera sola)
        self._dead_last_log = 0
        self._last_so_ticket = 0
        self._so_primed = False       # primer chequeo: solo fija el ancla, sin alertar
        self._next_chk_err_log = 0
        self._next_so_check = 0
        self._next_idle_check = 0
        self._idle_ref = None         # desde cuando cuenta la inactividad (arranque/encendido)
        self.lock_state = LOCK_FREE   # estado del candado de cesta en el tick (spec §5.3)
        self._lock_fail_next_log = 0  # throttle del ERROR de candado fallido
        self._lock_sl_err_next = 0    # throttle del ERROR de SL no limpiado con candado
        self._unlock_err_next = 0     # throttle del ERROR/SHADOW del aflojado del candado
        self._dissolve_err_next = 0   # throttle del ERROR/SHADOW de la disolucion por parejas
        self._dissolve_retry_next = 0 # backoff (60 s) de reintentos de la disolucion
        self._hedge_fail_next = {}    # ticket -> proximo ERROR de "Hedge Lock FALLIDO"
        self._surv_unknown_next_log = 0  # throttle del aviso "cuenta no evaluable" del candado
        self._empty_reads = 0         # lecturas vacias CONFIRMADAS seguidas (reset de meta a la 2.a)
        self._pos_fail_next_log = 0   # throttle del aviso de positions_get fallido
        self._guard_err_next = {}     # subsistema -> proximo ERROR por excepcion (600 s)
        self.vol_breaker = False      # VCB activo este tick (Fork A)
        self.vol_breaker_prev = False # para loguear solo las transiciones del VCB
        self.struct_h4 = 0            # estructura H4 del tick (cache para gates de recovery/rescue)
        self._last_entry_signal = None    # (lado, nivel roto, ordinal) de la ultima OP1 confirmada
        self._reentry_block_logged = None # (lado, nivel) ya logueado como frenado (1 vez por senal)
        self._last_open_ticket = 0        # ticket de la ultima apertura confirmada (_register_open)

        # Buffers del tick actual (rellenados por _compute_buffers)
        self.now = 0
        self.atr0 = self.atr1 = 0.0
        self.ema0 = self.rsi0 = 0.0
        self.m5_open1 = self.m5_close1 = 0.0
        self.df_h4 = None
        self.df_m15 = None
        self._op4t_bar = None             # ultima vela M15 cerrada evaluada por la Op4 tendencia

    # ==============================================================
    # Helpers de parametros
    # ==============================================================
    def _p(self, key):
        return self.cfg.get(key, DEFAULTS[key])

    def init_history_cursor(self):
        """Init lastHealedTicket al mayor ticket existente (baseline del healer).

        El cursor es por numero de ticket (independiente de zona horaria), por lo
        que basta una ventana amplia. Se usa max(ticket) en vez de deals[-1] para
        no depender del orden de retorno del broker.
        """
        if not self.now:   # aun sin tick (arranque): hora de servidor del ultimo tick
            tick = self._fetch_tick()
            if tick is not None:
                self.now = tick.time
        to_dt = self._deal_window_end()   # hora de servidor (R9), no la del PC
        from_dt = to_dt - datetime.timedelta(days=7)
        deals = self.b.history_deals(from_dt, to_dt)
        if deals:
            self.last_healed_ticket = max(d.ticket for d in deals)
        # Cursor y bolsa del Healer persistidos en el meta del ciclo: un reinicio
        # con el ciclo abierto ya no pone la bolsa a cero ni salta los ganadores
        # que aun no se habian contado. Sin posiciones el meta es de un ciclo muerto.
        cursor = self.cycle.get_meta("healer_cursor")
        if cursor is not None and self.b.positions():
            self.last_healed_ticket = int(cursor)
            self.healer_budget = float(self.cycle.get_meta("healer_budget") or 0.0)
            self._healer_needs_rebaseline = False
            self.log.write("HEALER", f"Healer: cursor #{self.last_healed_ticket} y bolsa "
                                     f"{self.healer_budget:.2f} $ restaurados del ciclo abierto.")

    # ==============================================================
    # Utils numericas (UTILS MQL5)
    # ==============================================================
    def _ref_lot(self):
        """Lote de referencia del ciclo (meta ref_lot fijado en la ENTRY); si no hay
        ciclo, el lote de entrada que dimensionaria hoy."""
        ref = self.cycle.get_meta("ref_lot")
        if ref:
            return float(ref)
        return float(self._calculate_lots(False))

    def _move_money(self, move_usd):
        """Dinero que vale un movimiento del oro (USD/oz) con el lote de referencia."""
        return float(move_usd) * self._ref_lot() * self.b.contract_size()

    def _rescue_level(self, abs_dd):
        """Nivel de rescate (1, 2 o 3) segun el DD medido en movimiento del precio."""
        if abs_dd > self._move_money(float(self._p("rescue_l3_move_usd"))):
            return 3
        if abs_dd > self._move_money(float(self._p("rescue_l2_move_usd"))):
            return 2
        return 1

    def _effective_atr(self):
        return max(self.atr0, self.b.point() * 150)

    # ==============================================================
    # Fork A: respiro/supervivencia (VCB + tope neto + gate H4)
    # ==============================================================
    def _vol_breaker_active(self):
        """Circuit breaker de volatilidad. True si la vela M15 EN CURSO es anomala
        (rango high-low >= ATR * vcb_atr_mult). Mientras este activo se bloquean
        SOLO las aperturas que ANADEN riesgo (entry, recovery, rescate), igual que
        spread_high: el Hedge (proteccion), cierres, trailing y healer siguen
        corriendo. Captura noticia, manipulacion o spikes fuera de calendario.
        """
        if not self._p("use_vol_breaker"):
            return False
        if self.df_m15 is None:
            return False
        bar_range = float(self.df_m15["high"].iloc[-1]) - float(self.df_m15["low"].iloc[-1])
        atr = self._effective_atr()
        if atr <= 0:
            return False
        return bar_range >= atr * float(self._p("vcb_atr_mult"))

    def _net_exposure(self):
        """Lotes netos de la cesta (long - short)."""
        net = 0.0
        for p in self.b.positions():
            net += p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume
        return net

    def _h4_gate_ok(self, order_type):
        """Bloquea promediar CONTRA la estructura H4 confirmada: no comprar si H4
        es bajista, no vender si es alcista. El martingala vive en rangos y muere
        en tendencias; este gate corta el apilado contra una tendencia macro.
        """
        if not self._p("use_recovery_h4_gate"):
            return True
        if order_type == mt5.ORDER_TYPE_BUY:
            return self.struct_h4 >= 0
        return self.struct_h4 <= 0

    def _risk_hour(self):
        """True si la hora actual esta en `risk_hours_utc` (hora UTC) o en
        `risk_hours_ny` (hora de Nueva York, sigue su cambio de hora). En hora de
        riesgo se bloquean recovery/rescate y el aflojado; hedge y gestion no."""
        utc = survival.parse_hours(str(self._p("risk_hours_utc")))
        ny = survival.parse_hours(str(self._p("risk_hours_ny")))
        return (survival.utc_hour_from_server(self.now) in utc
                or survival.ny_hour_from_server(self.now) in ny)

    # ==============================================================
    # Lotaje y cierre total
    # ==============================================================
    def _calculate_lots(self, is_recovery):
        # Equity PONDERADO por el peso de este bot: con dos motores sobre la
        # misma cuenta, dimensionar contra el equity completo haria que ambos
        # escalasen sobre el mismo capital (doble conteo). Ver bot/budget.py.
        equity = self.gov.sizing_equity()
        base_risk = float(self._p("base_risk"))
        ratio = equity / base_risk if base_risk else 0.0
        lots = ratio * float(self._p("base_lots"))

        vol_step = self.b.volume_step()
        import math
        lots = math.floor(lots / vol_step) * vol_step
        min_lot = self.b.volume_min()
        max_lot = self.b.volume_max()

        if lots < min_lot:
            lots = min_lot
        if lots > max_lot:
            lots = max_lot

        cap = float(self._p("max_recovery_lots")) if is_recovery else float(self._p("max_entry_lots"))
        if cap > 0 and lots > cap:
            lots = cap
        return lots

    def close_all(self, reason):
        """Cierre inmediato de toda la cesta por comando externo (force_close
        del dashboard). El usuario asume el flotante actual; NO es un stop
        automatico (esos siguen vetados por diseño).

        A diferencia de _close_all (cierre de ciclo por TP, best-effort), aqui
        se verifica el retcode de CADA orden y al final se re-consulta MT5:
        devuelve True solo si la instancia quedo PLANA. Si el terminal rechaza
        (AutoTrading off, requote, mercado cerrado) se loguea ERROR con el
        retcode y el caller NO consume el comando: reintenta en ~3 s.
        """
        if self.b.shadow:
            self.log.write("SHADOW", f"CLOSE ALL ({reason}): sin ordenes reales en modo sombra.")
            return True
        total = 0.0
        for p in self.b.positions():
            leg_pl = p.profit + p.swap
            res = self.b.close_position(p, "Close: Forzado (usuario)")
            rc = getattr(res, "retcode", None)
            if rc not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL):
                self.log.write("ERROR", f"Cierre forzado RECHAZADO (retcode {rc}).",
                               p.price_current, p.volume, self.b.account_balance(),
                               ticket=p.ticket)
                continue
            total += leg_pl
            self.log.write("CIERRE", f"Leg cerrado ({reason}). PnL: {leg_pl:.2f}",
                           p.price_current, p.volume, self.b.account_balance(),
                           ticket=p.ticket)
        if self.b.positions():
            return False  # quedo algo vivo (rechazo o cierre parcial): reintentar
        # Plano: cerrar el ciclo igual que un cierre normal de cesta.
        self.log.write("EXITO", f"Cierre CICLO ({reason}). PnL: {total:.2f}",
                       balance=self.b.account_balance())
        self.last_recovery_close_time = self.now
        self.max_cycle_peak = 0.0
        self.cycle_armed = False
        self.cycle_realized = 0.0
        self._healer_needs_rebaseline = True
        self._cover_protect_logged = False
        self.healer_budget = 0.0
        self._save_healer_state(clear=True)
        return True

    def _close_all(self, reason):
        total_profit = 0.0
        for p in self.b.positions():
            leg_pl = p.profit + p.swap
            total_profit += leg_pl
            self.b.close_position(p, f"Close: {reason}")
            # Traza por-leg con ticket (verbose): permite reconstruir el cierre de
            # cesta pos-a-pos en bot_logs sin depender del reporte de MT5.
            self.log.write("CIERRE", f"Leg cerrado ({reason}). PnL: {leg_pl:.2f}",
                           p.price_current, p.volume, self.b.account_balance(), ticket=p.ticket)
        self.log.write("EXITO", f"Cierre CICLO ({reason}). PnL: {total_profit:.2f}",
                       balance=self.b.account_balance())
        self.last_recovery_close_time = self.now
        self.max_cycle_peak = 0.0
        self.cycle_armed = False
        self.cycle_realized = 0.0             # B: cierra el ciclo -> reinicia el realizado
        self._healer_needs_rebaseline = True  # C: el proximo ciclo rebasa el cursor del Healer
        self._cover_protect_logged = False
        self.healer_budget = 0.0              # la bolsa es del ciclo
        self._save_healer_state(clear=True)

    # ==============================================================
    # Filtros de entrada
    # ==============================================================
    def _is_price_good_entry(self, order_type):
        if not self._p("use_pullback"):
            return True
        price = self.b.ask() if order_type == mt5.ORDER_TYPE_BUY else self.b.bid()
        ema = self.ema0
        current_atr = self._effective_atr()
        if abs(price - ema) > (current_atr * float(self._p("atr_entry_distance"))):
            return False
        return True

    def _m5_momentum(self, order_type):
        if not self._p("use_m5_confirm"):
            return True
        if order_type == mt5.ORDER_TYPE_BUY:
            return self.m5_close1 > self.m5_open1
        if order_type == mt5.ORDER_TYPE_SELL:
            return self.m5_close1 < self.m5_open1
        return True

    # ==============================================================
    # HEDGE LOCK (orden protectora)
    # ==============================================================
    def _open_hedge(self, p):
        """Abre el Hedge Lock y SOLO limpia el SL si el hedge quedo confirmado.

        El orden es critico. Antes se hacia `modify_sl(p, 0)` ANTES de intentar
        cubrir, de modo que un rechazo (margen insuficiente, retcode del broker)
        dejaba la posicion DESNUDA: sin SL y sin cobertura, en silencio. El M15
        no lleva SL catastrofico por diseño (ver docs/memory/bot-design-constraints),
        asi que el hedge es la unica red que congela la perdida: si no entra, el
        SL previo debe sobrevivir y hay que avisar.

        Es una orden PROTECTORA: no se pre-filtra por margen ni por ningun tope
        de presupuesto. Se intenta siempre y manda el broker; si rechaza, se
        loguea el retcode real y el bucle reintenta en el siguiente tick.
        """
        hedge_type = (mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY
                      else mt5.ORDER_TYPE_BUY)
        res = self.b.market_order(hedge_type, p.volume, "Hedge Lock")

        # En SHADOW_MODE market_order devuelve None a proposito (no envia nada):
        # se trata como exito para no ensuciar el log con errores fantasma.
        ok = self.b.shadow or (
            res is not None and getattr(res, "retcode", None) == mt5.TRADE_RETCODE_DONE
        )
        if not ok:
            rc = getattr(res, "retcode", "sin respuesta del broker")
            # Se reintenta cada tick, pero el ERROR sale como mucho cada 600 s por ticket.
            if self.now < self._hedge_fail_next.get(p.ticket, 0):
                return False
            self._hedge_fail_next[p.ticket] = self.now + LOCK_FAIL_LOG_EVERY_S
            self.log.write(
                "ERROR",
                f"Hedge Lock FALLIDO sobre ticket #{p.ticket} ({p.volume:.2f} lotes). "
                f"retcode={rc}. Margen libre: {self.b.margin_free():.2f}. "
                f"SL preservado; se reintenta en el proximo tick.",
                p.price_current, p.volume, self.b.account_balance(), ticket=p.ticket)
            return False

        self._hedge_fail_next.pop(p.ticket, None)
        # Cobertura confirmada: el par queda registrado en el ledger (quien
        # cubre a quien). Sin este vinculo, un restart re-emparejaria por
        # inferencia y un hedge de un ciclo muerto podria adoptar la OP1 nueva.
        self._register_open(res, ledger.ROLE_HEDGE, covers=p.ticket)

        # Recien ahora es seguro soltar el SL para que el par Op1+Hedge quede
        # congelado y lo gestionen los subsistemas de cesta.
        if p.sl != 0:
            self.b.modify_sl(p, 0)
        return True

    def _register_open(self, res, role, covers=None, accept_partial=False):
        """Registra en el ledger una apertura CONFIRMADA por el broker.

        En SHADOW_MODE res es None (no existe posicion real): no se registra y
        el sync() por comments cubriria cualquier hueco si algo quedo abierto.
        Con accept_partial (solo el candado) un DONE_PARTIAL tambien cuenta:
        la posicion existe aunque con menos volumen.
        Devuelve True si la apertura quedo confirmada y registrada.
        """
        if res is None:
            return False
        ok = (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL) if accept_partial             else (mt5.TRADE_RETCODE_DONE,)
        if getattr(res, "retcode", None) in ok:
            self._last_open_ticket = getattr(res, "order", 0)
            self.cycle.register(self._last_open_ticket, role, covers=covers)
            return True
        return False

    # ==============================================================
    # CANDADO DE CESTA (rol LOCK, spec §5.3)
    # ==============================================================
    def _guarded(self, name, fn):
        """Corre un subsistema del tick aislado: una excepcion se loguea (ERROR,
        como mucho cada 600 s por subsistema) y el tick sigue (hedge monitor, trail)."""
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            if self.now >= self._guard_err_next.get(name, 0):
                self._guard_err_next[name] = self.now + LOCK_FAIL_LOG_EVERY_S
                try:
                    self.log.write("ERROR", f"Subsistema '{name}' fallo y se omite este tick: "
                                            f"{type(e).__name__}: {e}",
                                   balance=self.b.account_balance())
                except Exception:  # noqa: BLE001
                    pass

    def _backfill_lock_since(self, positions):
        """Patas LOCK vivas sin lock_since (adopcion tras IOC parcial, ledger
        perdido/corrupto, instancia movida): se rellena con el time de la pata
        LOCK mas vieja, para que la disolucion no quede bloqueada para siempre."""
        legs = self.cycle.lock_legs(positions)
        if legs and self.cycle.get_meta("lock_since") is None:
            self.cycle.set_meta("lock_since", float(min(p.time for p in legs)))

    def _lock_state(self, positions):
        """LIBRE sin patas LOCK; CONGELADO con LOCK y |neto propio| < step;
        AFLOJADO con LOCK y neto residual."""
        if not self.cycle.lock_legs(positions):
            return LOCK_FREE
        if abs(survival.net_lots(positions)) < self.b.volume_step() - 1e-9:
            return LOCK_FROZEN
        return LOCK_LOOSE

    def _maybe_lock(self):
        """Pone el candado si el aguante S de la cuenta cae bajo lock_trigger_usd
        y el neto PROPIO (M15) no es cero: orden contraria por |neto| con comment
        "Basket Lock", rol LOCK. Orden PROTECTORA: no pasa por _open_additive ni
        por el gobierno de margen; solo el pre-chequeo del broker (order_check).
        Con el neto ya en 0 (candado congelado) no hace nada: nunca candado sobre
        candado. En AFLOJADO cubre solo el neto restante (otra pata LOCK).
        """
        positions = self.b.positions()
        net = survival.net_lots(positions)
        step = self.b.volume_step()
        if abs(net) < step - 1e-9:
            return
        s = self.surv.s_now()
        if s is None:
            # Cuenta no evaluable (account_info/positions_get None): NO es S=0.
            # Se salta el tick; nunca se pone un candado por una lectura fallida.
            if self.now >= self._surv_unknown_next_log:
                self._surv_unknown_next_log = self.now + LOCK_FAIL_LOG_EVERY_S
                self.log.write("SYSTEM", "Candado: cuenta no evaluable (MT5 sin respuesta); "
                                         "se reevalua en el proximo tick.",
                               balance=self.b.account_balance())
            return
        if s >= float(self._p("lock_trigger_usd")):
            return
        otype = mt5.ORDER_TYPE_SELL if net > 0 else mt5.ORDER_TYPE_BUY
        side = "SELL" if otype == mt5.ORDER_TYPE_SELL else "BUY"
        total = round(round(abs(net) / step) * step, 8)

        if self.b.shadow:
            if self.now >= self._lock_fail_next_log:
                self._lock_fail_next_log = self.now + LOCK_FAIL_LOG_EVERY_S
                self.log.write("SHADOW", f"Candado (sombra): se pondria {total:.2f} lotes {side}. "
                                         f"S={survival._s_txt(s)} $", balance=self.b.account_balance())
            return

        # Por encima de volume_max se parte en varias patas LOCK (se tratan como bloque).
        vmax = self.b.volume_max()
        if not vmax or vmax <= 0:
            vmax = total   # sin tope valido: una sola pata
        remaining = total
        locked = 0.0
        fail_rc = None
        while remaining >= step - 1e-9:
            vol = round(min(remaining, vmax), 8)
            ok, rc = self.b.order_check(otype, vol)
            if not ok:
                fail_rc = rc
                break
            res = self.b.market_order(otype, vol, "Basket Lock")
            # Un DONE_PARTIAL (IOC) abrio una pata real: se registra como LOCK y no
            # es un "Candado FALLIDO".
            if not self._register_open(res, ledger.ROLE_LOCK, accept_partial=True):
                fail_rc = getattr(res, "retcode", "sin respuesta del broker")
                break
            # A3: con un fill parcial (IOC) cuenta lo realmente abierto, no lo pedido.
            ticket = getattr(res, "order", 0)
            partial = getattr(res, "retcode", None) == mt5.TRADE_RETCODE_DONE_PARTIAL
            got = self._filled_volume(res, ticket, vol, step, partial)
            if got > 0:
                locked = round(locked + got, 8)
                remaining = round(remaining - got, 8)
                # R13: tras (re)poner el candado, el rebote se mide desde el precio de
                # ESTE candado (en un candado partido, la ultima pata confirmada).
                fill = next((p.price_open for p in self.b.positions() if p.ticket == ticket), None)
                if fill is None:
                    fill = self.b.bid() if otype == mt5.ORDER_TYPE_SELL else self.b.ask()
                self.cycle.set_meta("unlock_ref_price", float(fill))
                # F4: cada pata confirmada (candado o re-candado) reinicia el plazo
                # de 24 h de la disolucion.
                self.cycle.set_meta("lock_ref_ts", self.now)
            if got < vol - 1e-9:
                # Fill parcial (falta liquidez): se corta aqui. El resto solo se cubre
                # en un tick posterior si S sigue bajo lock_trigger_usd.
                break

        if locked > 0:
            if self.cycle.get_meta("lock_since") is None:
                self.cycle.set_meta("lock_since", self.now)
            self.cycle.set_meta("lock_initial_volume",
                                round(float(self.cycle.get_meta("lock_initial_volume", 0.0)) + locked, 8))
            # Un SL que saltara cambiaria el neto congelado: se limpian todos.
            self._clear_lock_sls(self.b.positions())
            msg = f"Candado puesto: {locked:.2f} lotes {side}. S={survival._s_txt(s)} $"
            self.log.write("PROTECCION", msg, lots=locked, balance=self.b.account_balance())
            self.alerts.notify("candado", "INFO", "candado de cesta puesto",
                               f"{msg}. La cesta queda congelada (neto 0) hasta un rebote "
                               f"confirmado o la disolucion.")
            self.lock_state = self._lock_state(self.b.positions())

        if fail_rc is not None and self.now >= self._lock_fail_next_log:
            self._lock_fail_next_log = self.now + LOCK_FAIL_LOG_EVERY_S
            free = self.b.margin_free()
            msg = f"Candado FALLIDO ({fail_rc}). S={survival._s_txt(s)} $. Margen libre {free:.2f}"
            self.log.write("ERROR", msg, balance=self.b.account_balance())
            self.alerts.notify("candado_fallido", "CRITICA", "candado de cesta FALLIDO",
                               f"{msg}. Se reintenta cada tick; la cesta sigue expuesta "
                               f"({total:.2f} lotes netos).")

    def _filled_volume(self, res, ticket, vol, step, partial=False):
        """Lotes realmente abiertos por una orden confirmada (A3): res.volume si
        viene; si no, el volumen vivo releido del ticket. Si no se puede releer,
        lo pedido si la orden vino DONE, o 0 si vino DONE_PARTIAL (lo pedido seria
        falso seguro). Redondeado hacia abajo al step (bajo un step => 0)."""
        got = getattr(res, "volume", None)
        try:
            got = float(got) if got is not None else 0.0
        except (TypeError, ValueError):
            got = 0.0
        if got <= 0:
            cur = self.b.positions_checked()
            live = next((q for q in cur if q.ticket == ticket), None) if cur is not None else None
            if live is not None:
                got = live.volume
            else:
                got = 0.0 if partial else vol
        got = min(got, vol)
        return round(math.floor(got / step + 1e-9) * step, 8)

    def _maybe_unlock(self):
        """Afloja el candado SOLO con rebote confirmado a favor del neto original
        (spec §5.4). Corre en CONGELADO y AFLOJADO, justo despues de _maybe_lock.

        Principio: con candado puesto el equity es el mismo se cierre la pata que
        se cierre; el "verde/rojo" de la pata LOCK es contabilidad, nunca motivo
        para aflojar. Esperar a la pata LOCK en verde seria aflojar cuando el
        precio SIGUIO en contra (promediar contra la tendencia): prohibido. Solo
        se vuelve a exponer tras un rebote >= unlock_rebound_usd medido desde el
        precio medio del candado o desde el aflojado anterior, y solo lo que deje
        S >= survival_move_usd.
        """
        positions = self.b.positions()
        legs = self.cycle.lock_legs(positions)
        if not legs:
            return
        lock_net = survival.net_lots(legs)
        step = self.b.volume_step()
        if abs(lock_net) < step - 1e-9:
            return
        # Patas SELL => el neto original era largo (dir +1); BUY => corto (dir -1).
        dir_orig = 1.0 if lock_net < 0 else -1.0
        lock_type = mt5.POSITION_TYPE_SELL if dir_orig > 0 else mt5.POSITION_TYPE_BUY
        legs = [p for p in legs if p.type == lock_type]
        total = round(sum(p.volume for p in legs), 8)

        # 1. Referencia: precio del aflojado anterior o medio ponderado del candado.
        ref = self.cycle.get_meta("unlock_ref_price")
        if ref is None:
            ref = sum(p.price_open * p.volume for p in legs) / total
        ref = float(ref)
        # 2. Rebote a favor del neto original (nunca la continuacion).
        price = self.b.bid() if dir_orig > 0 else self.b.ask()
        rebound = (price - ref) if dir_orig > 0 else (ref - price)
        # 3. Gates: todos.
        if rebound < float(self._p("unlock_rebound_usd")) - 1e-9:
            return
        if self.vol_breaker or self.spread_high or self.news_active or self._risk_hour():
            return

        # 4. Volumen: el mayor v que deja S >= survival_move_usd y el neto propio en cupo.
        # S cae y |neto propio| crece de forma monotona con v: busqueda binaria
        # sobre k (acota las llamadas a MT5 por tick). Asume que el neto no-LOCK
        # (el de `positions`, sin las coberturas) no se opone a dir_orig: asi
        # sumar v en dir_orig solo puede aumentar |neto| y empeorar S.
        # Una sola foto de la cuenta; si MT5 no responde no se afloja (desconocido).
        snap = self.surv.snapshot()
        if snap is None:
            return
        target = self.surv._target()
        cap = self.surv._f("equity_weight") * self.surv.n_max(snap)
        own = survival.net_lots(positions)
        vmin = self.b.volume_min()

        def fits(k):
            cand = round(k * step, 8)
            return (self.surv.s_with_delta(dir_orig * cand, 0.0, snap) >= target - 1e-9
                    and abs(own + dir_orig * cand) <= cap + 1e-9)

        lo, hi = 0, int(math.floor(total / step + 1e-9))   # invariante: fits(lo) o lo == 0
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fits(mid):
                lo = mid
            else:
                hi = mid - 1
        v = round(lo * step, 8)
        if v < vmin - 1e-9:
            return

        if self.b.shadow:
            if self.now >= self._unlock_err_next:
                self._unlock_err_next = self.now + LOCK_FAIL_LOG_EVERY_S
                self.log.write("SHADOW", f"Candado (sombra): se aflojarian {v:.2f} lotes "
                                         f"(rebote +{rebound:.0f} $).",
                               balance=self.b.account_balance())
            return

        # 5. Cierre: de la pata LOCK mas nueva a la mas vieja; parcial en la ultima.
        legs.sort(key=lambda p: (p.time, p.ticket), reverse=True)
        remaining, closed, realized = v, 0.0, 0.0
        for p in legs:
            if remaining < step - 1e-9:
                break
            lots = round(min(p.volume, remaining), 8)
            vol_before = p.volume
            # antes del cierre (el volumen cambia)
            pl_per_lot = (p.profit + p.swap) / p.volume if p.volume > 0 else 0.0
            if lots >= p.volume - 1e-9:
                res = self.b.close_position(p, "Basket Unlock")
            else:
                res = self.b.close_partial(p, lots, "Basket Unlock")
            rc = getattr(res, "retcode", None)
            if rc == mt5.TRADE_RETCODE_DONE_PARTIAL:
                # A4: igual que la disolucion (F6), cuenta lo REALMENTE cerrado.
                got = self._partial_closed_volume(res, p.ticket, vol_before, lots, step)
                if got >= step - 1e-9:
                    closed = round(closed + got, 8)
                    realized += pl_per_lot * got
                    remaining = round(remaining - got, 8)
                break
            if rc != mt5.TRADE_RETCODE_DONE:
                if self.now >= self._unlock_err_next:
                    self._unlock_err_next = self.now + LOCK_FAIL_LOG_EVERY_S
                    self.log.write("ERROR",
                                   f"Aflojado del candado RECHAZADO en ticket #{p.ticket} "
                                   f"(retcode {getattr(res, 'retcode', 'sin respuesta del broker')}). "
                                   f"Se reevalua en el proximo tick.",
                                   balance=self.b.account_balance(), ticket=p.ticket)
                break
            closed = round(closed + lots, 8)
            realized += pl_per_lot * lots
            remaining = round(remaining - lots, 8)
        if closed <= 0:
            return

        self.cycle_realized += realized
        # 6. Referencia para el siguiente aflojado: este precio. A4: si el cierre
        # quedo a medias (parcial o rechazo tras algun cierre), la referencia no se
        # mueve: lo no cerrado sigue autorizado por el MISMO rebote.
        if remaining < step - 1e-9:
            self.cycle.set_meta("unlock_ref_price", price)
        else:
            self.cycle.set_meta("unlock_ref_price", ref)
        self.cycle.set_meta("last_unlock_ts", self.now)
        s = self.surv.s_now()
        msg = (f"Candado aflojado: cerrados {closed:.2f} lotes (rebote +{rebound:.0f} $). "
               f"S={survival._s_txt(s)} $")
        self.log.write("PROTECCION", msg, lots=closed, balance=self.b.account_balance())
        self.alerts.notify("candado_aflojado", "INFO", "candado de cesta aflojado",
                           f"{msg}. Rebote confirmado a favor del neto original.")
        after = self.b.positions_checked()
        if after is not None and not self.cycle.lock_legs(after):
            # Ultima pata LOCK cerrada: estado LIBRE (se conserva last_unlock_ts).
            for key in ("unlock_ref_price", "lock_since", "lock_initial_volume", "lock_ref_ts"):
                self.cycle.set_meta(key, None)

    def _utc_day(self):
        """Fecha UTC (YYYY-MM-DD) de la hora de servidor self.now."""
        off_h = ((int(self.now) // 3600) - survival.utc_hour_from_server(self.now)) % 24
        utc_ts = int(self.now) - off_h * 3600
        return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=utc_ts)).date().isoformat()

    def _maybe_dissolve(self):
        """Disolucion diaria por parejas del candado sin re-exponer (spec §5.5).

        Corre en CONGELADO, AFLOJADO y en LIBRE (caso "ambos lados"), justo
        despues de _maybe_unlock. Cierra X lotes de las patas LOCK y X lotes de
        la contraparte (Recovery/Op4 del lado contrario con peor dinero por
        lote): lados opuestos y lotes iguales => el neto NO cambia. Nunca toca
        ENTRY, HEDGE, ORPHAN ni sus coberturas. Primero el miembro rojo: si el
        segundo cierre fallara, lo que queda vivo es el verde.

        R14: si el segundo cierre falla, la deuda (lotes del segundo miembro
        aun por cerrar) se persiste en meta "dissolve_pending". Mientras exista,
        aqui SOLO se reintenta cerrar ese resto (backoff 60 s, sin gates de
        hora/dia/24 h; el VCB si bloquea) y nunca se empieza otra pareja.

        A2: una sola pareja por dia UTC. En cuanto se cierra cualquier volumen
        >= step del primer miembro, el dia queda gastado (last_dissolve_day):
        un primer miembro parcial o una deuda descartada/recortada no abren una
        segunda pareja ese dia; el resto espera al dia siguiente.
        """
        ref_ts = self._dissolve_ref_ts()
        if self.cycle.get_meta("dissolve_pending"):
            self._retry_dissolve_pending(ref_ts)
            return

        # 1. Gates: plazo desde el ultimo candado/aflojado, hora UTC, una vez al dia, VCB.
        if ref_ts <= 0:
            return
        if self.now - ref_ts < float(self._p("lock_dissolve_after_h")) * 3600 - 1e-9:
            return
        if survival.utc_hour_from_server(self.now) not in survival.parse_hours(
                self._p("lock_dissolve_hours_utc")):
            return
        day = self._utc_day()
        if self.cycle.get_meta("last_dissolve_day") == day:
            return
        if self.vol_breaker:
            return
        if self.now < self._dissolve_retry_next:
            return   # backoff tras un primer cierre rechazado

        positions = self.b.positions()
        step = self.b.volume_step()
        vmin = self.b.volume_min()
        cp_roles = (ledger.ROLE_RECOVERY, ledger.ROLE_RESCUE)
        cps = [p for p in positions if self.cycle.role_of(p.ticket) in cp_roles]

        def per_lot(p):
            return (p.profit + p.swap) / p.volume if p.volume > 0 else 0.0

        legs = self.cycle.lock_legs(positions)
        lock_case = bool(legs)
        if lock_case:
            # 2. Con patas LOCK: contraparte del lado contrario al neto LOCK.
            lock_net = survival.net_lots(legs)
            if abs(lock_net) < step - 1e-9:
                return
            lock_type = mt5.POSITION_TYPE_SELL if lock_net < 0 else mt5.POSITION_TYPE_BUY
            legs = [p for p in legs if p.type == lock_type]
            opp = [p for p in cps if p.type != lock_type]
            if not opp:
                return
            cp = min(opp, key=per_lot)
            lock_total = round(sum(p.volume for p in legs), 8)
            init = self.cycle.get_meta("lock_initial_volume")
            init = float(init) if init else lock_total
            frac = float(self._p("lock_dissolve_fraction"))
            x = max(vmin, math.floor(frac * init / step + 1e-9) * step)
            x = round(min(x, lock_total, cp.volume), 8)
            # Patas LOCK: de la mas nueva a la mas vieja (igual que el aflojado).
            legs.sort(key=lambda p: (p.time, p.ticket), reverse=True)
            side_a, side_b = legs, [cp]
        else:
            # 3. Sin LOCK: Op3/Op4 de ambos lados con neto propio < step.
            buys = [p for p in cps if p.type == mt5.POSITION_TYPE_BUY]
            sells = [p for p in cps if p.type == mt5.POSITION_TYPE_SELL]
            if not buys or not sells:
                return
            if abs(survival.net_lots(cps)) >= step - 1e-9:
                return
            wb, ws = min(buys, key=per_lot), min(sells, key=per_lot)
            x = round(min(wb.volume, ws.volume), 8)
            side_a, side_b = [wb], [ws]
        if x < vmin - 1e-9 or x < step - 1e-9:
            return

        def portion_pl(member, lots):
            pl, rem = 0.0, lots
            for p in member:
                if rem < step - 1e-9:
                    break
                take = min(p.volume, rem)
                pl += (p.profit + p.swap) * take / p.volume
                rem = round(rem - take, 8)
            return pl

        # 4. Primero el miembro rojo y luego el verde.
        if portion_pl(side_a, x) <= portion_pl(side_b, x):
            first, second = side_a, side_b
        else:
            first, second = side_b, side_a

        if self.b.shadow:
            if self.now >= self._dissolve_err_next:
                self._dissolve_err_next = self.now + LOCK_FAIL_LOG_EVERY_S
                self.log.write("SHADOW", f"Disolucion (sombra): se cerrarian {x:.2f} lotes "
                                         f"de #{first[0].ticket} + #{second[0].ticket}.",
                               balance=self.b.account_balance())
            return

        net_before = survival.net_lots(positions)
        closed1, real1, fail1, tk1 = self._dissolve_close(first, x, step)
        if closed1 <= 0:
            self._dissolve_retry_next = self.now + DISSOLVE_RETRY_S
            self._dissolve_error(f"Disolucion por parejas RECHAZADA en #{fail1} "
                                 f"(nada cerrado). Se reintenta en {DISSOLVE_RETRY_S} s.")
            return
        # A2: ya se cerro volumen de la pareja: el dia queda gastado pase lo que pase.
        self._mark_dissolve_day(day)
        # El segundo miembro cierra exactamente lo que se cerro del primero.
        closed2, real2, fail2, tk2 = self._dissolve_close(second, closed1, step)
        self.cycle_realized += real1 + real2
        remaining = round(closed1 - closed2, 8)
        if remaining >= step - 1e-9:
            # R14: deuda persistida; solo se reintenta este resto del MISMO par.
            side = "BUY" if second[0].type == mt5.POSITION_TYPE_BUY else "SELL"
            self.cycle.set_meta("dissolve_pending", {
                "side": side, "lots": remaining,
                "tickets": [p.ticket for p in second],
                "net_before": net_before, "x": closed1,
                "first_tickets": tk1, "second_tickets": tk2,
                "lock_case": lock_case, "day": day,
            })
            self._dissolve_retry_next = self.now + DISSOLVE_RETRY_S
            msg = (f"Disolucion por parejas INCOMPLETA: cerrados {closed1:.2f} de "
                   f"{self._tickets_txt(tk1)} y {closed2:.2f} de {self._tickets_txt(tk2) or '-'} "
                   f"(rechazo en #{fail2}). Se reintenta cerrar los {remaining:.2f} lotes "
                   f"restantes del mismo par ({side}).")
            self._dissolve_error(msg)
            self.alerts.notify("disolucion_fallida", "CRITICA", "disolucion por parejas FALLIDA",
                               f"{msg} Mientras tanto la cesta queda {remaining:.2f} lotes "
                               f"fuera de neto; no se abre otra pareja hasta cerrarlo.")
            return
        if fail1 is not None:
            # Primer miembro parcial, segundo completo: neto intacto. A2: el dia ya
            # esta gastado; el resto de X espera a la ventana del dia siguiente.
            self._dissolve_error(f"Disolucion por parejas PARCIAL: {closed1:.2f} de {x:.2f} lotes "
                                 f"(rechazo en #{fail1}). Neto sin cambio; el resto espera "
                                 f"al dia siguiente.")
            self._dissolve_cleanup(lock_case, ref_ts)
            return
        self._dissolve_done(closed1, tk1, tk2, lock_case, ref_ts, day)

    def _dissolve_ref_ts(self):
        """Referencia del plazo de 24 h: el ultimo candado/re-candado (lock_ref_ts),
        el ultimo aflojado (last_unlock_ts) o el inicio del candado (lock_since)."""
        return max(float(self.cycle.get_meta("lock_ref_ts") or 0),
                   float(self.cycle.get_meta("last_unlock_ts") or 0),
                   float(self.cycle.get_meta("lock_since") or 0))

    def _retry_dissolve_pending(self, ref_ts):
        """R14: reintenta cerrar el resto del segundo miembro de una pareja a medias."""
        if self.vol_breaker or self.now < self._dissolve_retry_next:
            return
        pend = self.cycle.get_meta("dissolve_pending")
        ptype = mt5.POSITION_TYPE_BUY if pend["side"] == "BUY" else mt5.POSITION_TYPE_SELL
        cur = self.b.positions_checked()
        if cur is None:
            return   # lectura fallida: nunca descartar la deuda por una lista vacia falsa
        by_t = {p.ticket: p for p in cur}
        alive = [by_t[t] for t in pend["tickets"] if t in by_t and by_t[t].type == ptype]
        lock_case = bool(pend.get("lock_case"))
        if not alive:
            self.cycle.set_meta("dissolve_pending", None)
            self.log.write("HEALER", "Disolucion: deuda pendiente descartada (sus patas ya no "
                                     "existen).", balance=self.b.account_balance())
            self._mark_dissolve_day(pend.get("day"))
            self._dissolve_cleanup(lock_case, ref_ts)
            return
        step = self.b.volume_step()
        owed = float(pend["lots"])
        # Nunca pasarse del neto previo a la pareja (p. ej. si otro candado ya lo cubrio).
        net = survival.net_lots(cur)
        gap = (net - float(pend["net_before"])) if ptype == mt5.POSITION_TYPE_BUY \
            else (float(pend["net_before"]) - net)
        lots = round(min(owed, math.floor(max(gap, 0.0) / step + 1e-9) * step), 8)
        capped = lots < owed - 1e-9   # R15: recortada por el neto previo
        if lots < step - 1e-9:
            self.cycle.set_meta("dissolve_pending", None)
            self.log.write("HEALER", "Disolucion: deuda pendiente descartada (el neto ya volvio "
                                     "al valor previo).", balance=self.b.account_balance())
            self._mark_dissolve_day(pend.get("day"))
            self._dissolve_cleanup(lock_case, ref_ts)
            return
        if self.b.shadow:
            return
        closed, real, fail, tk = self._dissolve_close(alive, lots, step)
        self.cycle_realized += real
        tk2 = list(pend.get("second_tickets") or []) + [t for t in tk if t not in
                                                       (pend.get("second_tickets") or [])]
        rest = round(owed - closed, 8)
        if fail is not None and rest >= step - 1e-9:
            pend = dict(pend, lots=rest, second_tickets=tk2)
            self.cycle.set_meta("dissolve_pending", pend)
            self._dissolve_retry_next = self.now + DISSOLVE_RETRY_S
            self._dissolve_error(f"Disolucion por parejas: reintento RECHAZADO en #{fail}. "
                                 f"Quedan {rest:.2f} lotes del mismo par por cerrar.")
            return
        self.cycle.set_meta("dissolve_pending", None)
        if rest >= step - 1e-9:
            if capped and closed >= lots - 1e-9:
                # R15: se cerro todo lo que cabia hasta el neto previo; el resto ya
                # lo cubre el neto (p. ej. un re-candado). No es "cerradas fuera".
                why = (f"recortada a {closed:.2f} lotes por el neto previo (R15); "
                       f"{rest:.2f} lotes ya cubiertos")
            else:
                why = f"descartada con {rest:.2f} lotes sin cerrar (patas cerradas fuera)"
            self.log.write("HEALER", f"Disolucion: deuda pendiente {why}.",
                           lots=closed, balance=self.b.account_balance())
            self._mark_dissolve_day(pend.get("day"))
            self._dissolve_cleanup(lock_case, ref_ts)
            return
        self._dissolve_done(float(pend["x"]), list(pend.get("first_tickets") or []), tk2,
                            lock_case, ref_ts, pend.get("day"))

    def _dissolve_done(self, x, tk1, tk2, lock_case, ref_ts, day=None):
        """Pareja completa: dia marcado, log HEALER y, si se agoto el candado, meta limpia."""
        self._mark_dissolve_day(day)
        self.log.write("HEALER",
                       f"Disolucion por parejas: {x:.2f} lotes de {self._tickets_txt(tk1)} + "
                       f"{self._tickets_txt(tk2)}. Neto sin cambio.",
                       lots=x, balance=self.b.account_balance(), ticket=tk1[0] if tk1 else 0)
        self._dissolve_cleanup(lock_case, ref_ts)

    def _mark_dissolve_day(self, day=None):
        """A2: gasta el dia UTC de la disolucion. `day` es el dia en que empezo la
        pareja (guardado en la deuda); sin el (deuda de antes de A2), el de hoy."""
        self.cycle.set_meta("last_dissolve_day", day or self._utc_day())

    def _dissolve_cleanup(self, lock_case, ref_ts):
        """Si la disolucion agoto las patas LOCK, limpia la meta del candado."""
        after = self.b.positions_checked() if lock_case else None
        if after is not None and not self.cycle.lock_legs(after):
            # Ultima pata LOCK disuelta: estado LIBRE. La referencia del plazo
            # (ultimo candado/aflojado) se conserva en last_unlock_ts para el
            # caso "ambos lados".
            if ref_ts > 0:
                self.cycle.set_meta("last_unlock_ts", ref_ts)
            for key in ("unlock_ref_price", "lock_since", "lock_initial_volume", "lock_ref_ts"):
                self.cycle.set_meta(key, None)

    @staticmethod
    def _tickets_txt(tickets):
        return ", ".join(f"#{t}" for t in tickets)

    def _dissolve_close(self, member, lots, step):
        """Cierra `lots` de las patas de un miembro (en orden). Cuenta lo
        confirmado con retcode DONE y, en un DONE_PARTIAL, el volumen REALMENTE
        cerrado (res.volume o, si no viene, releyendo la posicion), para que el
        segundo miembro / la deuda usen la cifra real. Devuelve (cerrado,
        realizado, ticket_fallido, tickets_cerrados)."""
        remaining, closed, realized, tickets = round(lots, 8), 0.0, 0.0, []
        for p in member:
            if remaining < step - 1e-9:
                break
            take = round(min(p.volume, remaining), 8)
            vol_before = p.volume
            pl_per_lot = (p.profit + p.swap) / p.volume if p.volume > 0 else 0.0
            ticket = p.ticket
            if take >= p.volume - 1e-9:
                res = self.b.close_position(p, "Basket Dissolve")
            else:
                res = self.b.close_partial(p, take, "Basket Dissolve")
            rc = getattr(res, "retcode", None)
            if rc == mt5.TRADE_RETCODE_DONE_PARTIAL:
                got = self._partial_closed_volume(res, ticket, vol_before, take, step)
                if got >= step - 1e-9:
                    closed = round(closed + got, 8)
                    realized += pl_per_lot * got
                    tickets.append(ticket)
                return closed, realized, ticket, tickets
            if rc != mt5.TRADE_RETCODE_DONE:
                return closed, realized, ticket, tickets
            pl = pl_per_lot * take   # antes del cierre (el volumen cambia)
            closed = round(closed + take, 8)
            realized += pl
            remaining = round(remaining - take, 8)
            tickets.append(ticket)
        return closed, realized, None, tickets

    def _partial_closed_volume(self, res, ticket, vol_before, take, step):
        """Lotes realmente cerrados en un DONE_PARTIAL: res.volume si viene; si no,
        volumen previo - volumen vivo releido (posicion desaparecida => `take`).
        Si la relectura falla, 0 (el cierre queda sin contar y se reintenta)."""
        vol = getattr(res, "volume", None)
        try:
            vol = float(vol) if vol is not None else 0.0
        except (TypeError, ValueError):
            vol = 0.0
        if vol <= 0:
            cur = self.b.positions_checked()
            if cur is None:
                return 0.0
            live = next((q for q in cur if q.ticket == ticket), None)
            vol = take if live is None else max(0.0, vol_before - live.volume)
        vol = min(vol, take)
        return round(math.floor(vol / step + 1e-9) * step, 8)

    def _dissolve_error(self, msg):
        """ERROR de la disolucion, como mucho cada 600 s."""
        if self.now >= self._dissolve_err_next:
            self._dissolve_err_next = self.now + LOCK_FAIL_LOG_EVERY_S
            self.log.write("ERROR", msg, balance=self.b.account_balance())

    def _clear_lock_sls(self, positions):
        """Con candado vivo ningun leg propio puede llevar SL (un SL que salte
        cambia el neto). Idempotente: se llama cada tick; si el broker rechaza
        la modificacion, ERROR como mucho cada 600 s y se reintenta."""
        for p in positions:
            if p.sl == 0:
                continue
            res = self.b.modify_sl(p, 0)
            if res is not None and getattr(res, "retcode", None) != mt5.TRADE_RETCODE_DONE:
                if self.now >= self._lock_sl_err_next:
                    self._lock_sl_err_next = self.now + LOCK_FAIL_LOG_EVERY_S
                    self.log.write("ERROR",
                                   f"Candado: no se pudo quitar el SL del ticket #{p.ticket} "
                                   f"(retcode {getattr(res, 'retcode', '?')}). Se reintenta.",
                                   balance=self.b.account_balance(), ticket=p.ticket)

    def _prune_hedge_fail(self, positions):
        """Purga de _hedge_fail_next los tickets que ya no estan abiertos.
        Reutiliza la lista chequeada del tick (cero lecturas MT5 extra); con
        None (lectura fallida) no hace nada, para no olvidar tickets vivos."""
        if positions is None or not self._hedge_fail_next:
            return
        alive = {p.ticket for p in positions}
        for t in [t for t in self._hedge_fail_next if t not in alive]:
            del self._hedge_fail_next[t]

    def _news_note(self, what):
        """Traza de auditoria del NewsGuard: apertura ocurrida DENTRO de una
        ventana de noticia. En modo observacion (news_enforce=False) es el dato
        que calibra los umbrales antes de activar el enforcement. Con
        enforcement activo no deberia ocurrir nunca (el bloqueo no tiene
        excepciones): si aparece, se marca como inesperado."""
        if not self.news_active:
            return
        modo = "bloqueo activo (inesperado)" if self.news_block else "observacion"
        self.log.write("NOTICIAS",
                       f"{what} abierta en ventana de noticia [{modo}]: {self.news_reason}.",
                       balance=self.b.account_balance())

    def _open_additive(self, order_type, lots, comment, role, label):
        """Unica puerta de las aperturas ADITIVAS (entry / recovery / rescue).

        Recorta el lote al mayor que mantiene el aguante S de la cuenta
        (SurvivalGuard.fit; 0 = no cabe ni el minimo => no abre), pasa por el
        gobierno de margen y registra el rol en el ledger. Las protectoras
        (Hedge Lock / Basket Lock) NO pasan por aqui.
        Devuelve True solo si la apertura quedo confirmada y registrada.
        """
        self._last_additive_sent = False
        if self.dead:
            return False
        if self.lock_state == LOCK_FROZEN:
            return False   # candado congelado: nada aditivo puede cambiar el neto
        lots = self.surv.fit(order_type, lots, label)
        if lots <= 0:
            return False
        if not self.gov.can_open(lots, order_type, budget.KIND_ADDITIVE):
            return False
        res = self.b.market_order(order_type, lots, comment)
        self._last_additive_sent = True   # salio al broker (confirmada o rechazada)
        if not self._register_open(res, role):
            return False
        self._news_note(label)
        if role == ledger.ROLE_ENTRY:
            self.cycle.set_meta("ref_lot", lots)
        elif role == ledger.ROLE_RESCUE:
            self.cycle.set_meta("rescue_opened", int(self.cycle.get_meta("rescue_opened", 0)) + 1)
        return True

    def _reentry_info(self, side):
        """(nivel roto, ordinal, distancia en ATR) de una OP1 de `side` (+1/-1).

        Ordinal: 1 si es una ruptura nueva; N+1 si repite (lado, nivel) de la
        ultima OP1 confirmada (re-entrada sobre la misma ruptura). Sin nivel
        identificable (datos cortos o senal distinta) cuenta como ruptura nueva.
        """
        try:
            sig, level = indicators.m15_breakout_level(self.df_m15)
        except Exception:  # noqa: BLE001  (solo identifica; nunca rompe la entrada)
            sig, level = 0, 0.0
        if sig != side or level <= 0:
            return 0.0, 1, 0.0
        prev = self._last_entry_signal
        n = 1
        if prev and prev[0] == side and abs(prev[1] - level) <= self.b.point() / 2:
            n = prev[2] + 1
        dist = (self.b.ask() - level) if side == 1 else (level - self.b.bid())
        return level, n, dist / self._effective_atr()

    def _open_entry(self, order_type, lots, comment, label):
        """Apertura de OP1 con el control de re-entradas sobre la misma ruptura.

        Una re-entrada (misma ruptura que la OP1 anterior) a mas de
        reentry_max_atr * ATR del nivel roto es "lejana": con reentry_enforce
        no se abre (log 1 vez por senal); sin el, se abre igual y se anota con
        su ticket para evaluarla despues (modo observacion).
        """
        side = 1 if order_type == mt5.ORDER_TYPE_BUY else -1
        level, n, dist_atr = self._reentry_info(side)
        max_atr = float(self._p("reentry_max_atr"))
        far = level > 0 and n > 1 and max_atr > 0 and dist_atr > max_atr
        if far and self._p("reentry_enforce"):
            key = (side, round(level, 5))
            if self._reentry_block_logged != key:
                self._reentry_block_logged = key
                self.log.write(
                    "SYSTEM",
                    f"Re-entrada frenada: precio a {dist_atr:.2f} ATR del nivel {level:.2f} "
                    f"(max {max_atr:.2f} ATR).",
                    self.b.ask() if side == 1 else self.b.bid(), lots, self.b.account_balance())
            return False
        if not self._open_additive(order_type, lots, comment, ledger.ROLE_ENTRY, label):
            return False
        if level > 0:
            self._last_entry_signal = (side, level, n)
        if level > 0 and n > 1 and max_atr > 0:
            kind = "lejana" if far else "cercana"
            tail = " Se abre igual." if far else ""
            self.log.write(
                "SYSTEM",
                f"Re-entrada {kind} (observacion): {n}.a entrada sobre el nivel {level:.2f}, "
                f"a {dist_atr:.2f} ATR (umbral {max_atr:.2f}).{tail}",
                self.b.ask() if side == 1 else self.b.bid(), lots, self.b.account_balance(),
                ticket=self._last_open_ticket)
        return True

    def _resize_hedge(self, entry, hedge):
        """Encoge el hedge al volumen remanente de la ENTRY (nunca lo agranda).

        Si el Healer amputo parte de la ENTRY, el exceso del hedge ya no
        congela nada: es exposicion direccional nueva disfrazada de cobertura.
        Lo realizado por el recorte entra a cycle_realized para que el freeze
        del Unwind lo vea (mismo tratamiento que una amputacion del Healer).
        """
        step = self.b.volume_step()
        excess = hedge.volume - entry.volume
        if excess < step - 1e-9:
            return
        import math
        lots = math.floor(excess / step + 1e-9) * step
        frac = lots / hedge.volume
        res = self.b.close_partial(hedge, lots, "Hedge Resize")
        if res is None or getattr(res, "retcode", None) == mt5.TRADE_RETCODE_DONE:
            self.cycle_realized += (hedge.profit + hedge.swap) * frac
            self.log.write(
                "PROTECCION",
                f"Hedge ajustado al remanente de la OP1 (ticket #{entry.ticket}): "
                f"cerrados {lots:.2f} lotes de exceso.",
                hedge.price_current, lots, self.b.account_balance(), ticket=hedge.ticket)

    # ==============================================================
    # HUD (snapshot read-only para la TUI; NO afecta el trading)
    # ==============================================================
    def _build_hud(self, struct_h4, signal_m15, is_friday_mode, is_weekly_start_wait):
        """Construye el panel 'actual vs requerido' de las condiciones de Op1.

        Espejo de lectura de los gates del ESTADO 0. Si la maquina de estados
        cambia, este metodo debe seguirla (no comparte codigo a proposito,
        para no arriesgar la logica de trading).
        """
        point = self.b.point()
        bid = self.b.bid()
        ask = self.b.ask()
        spread = self.b.spread()
        rsi = self.rsi0
        ema = self.ema0
        catr = self._effective_atr()
        my_positions = len(self.b.positions())

        if signal_m15 == 1:
            side = "BUY"
        elif signal_m15 == -1:
            side = "SELL"
        elif struct_h4 > 0:
            side = "BUY?"
        elif struct_h4 < 0:
            side = "SELL?"
        else:
            side = "-"

        gates = []
        max_sp = int(self._p("inp_max_spread"))
        gates.append(("Spread", str(spread), f"<= {max_sp}", spread <= max_sp))
        if self.news_active:
            estado = (self.news_reason or "ventana activa")
            if not self._p("news_enforce"):
                estado += " (obs)"
            gates.append(("Noticias", estado, "fuera de ventana roja", not self.news_block))

        if side.startswith("BUY"):
            gates.append(("Estructura H4", _struct_txt(struct_h4), ">= 0 (alcista)", struct_h4 >= 0))
            gates.append(("Senal M15", _sig_txt(signal_m15), "ruptura alza (+1)", signal_m15 == 1))
            dist = abs(ask - ema)
            maxd = catr * float(self._p("atr_entry_distance"))
            ok_pb = (not self._p("use_pullback")) or dist <= maxd
            gates.append(("Pullback EMA", f"{dist / point:.0f} pt", f"<= {maxd / point:.0f} pt", ok_pb))
            rmax = int(self._p("entry_rsi_max"))
            gates.append(("RSI (M15)", f"{rsi:.1f}", f"< {rmax}", rsi < rmax))
            otype = mt5.ORDER_TYPE_BUY
        elif side.startswith("SELL"):
            gates.append(("Estructura H4", _struct_txt(struct_h4), "<= 0 (bajista)", struct_h4 <= 0))
            gates.append(("Senal M15", _sig_txt(signal_m15), "ruptura baja (-1)", signal_m15 == -1))
            dist = abs(bid - ema)
            maxd = catr * float(self._p("atr_entry_distance"))
            ok_pb = (not self._p("use_pullback")) or dist <= maxd
            gates.append(("Pullback EMA", f"{dist / point:.0f} pt", f"<= {maxd / point:.0f} pt", ok_pb))
            rmin = int(self._p("entry_rsi_min"))
            gates.append(("RSI (M15)", f"{rsi:.1f}", f"> {rmin}", rsi > rmin))
            otype = mt5.ORDER_TYPE_SELL
        else:
            gates.append(("Senal M15", _sig_txt(signal_m15), "ruptura +-1", False))
            gates.append(("Estructura H4", _struct_txt(struct_h4), "definida", struct_h4 != 0))
            gates.append(("RSI (M15)", f"{rsi:.1f}", "25 .. 75", 25 < rsi < 75))
            otype = mt5.ORDER_TYPE_BUY

        if side in ("BUY", "SELL") and float(self._p("reentry_max_atr")) > 0:
            level, n, dist_atr = self._reentry_info(1 if side == "BUY" else -1)
            if level > 0 and n > 1:
                rmax = float(self._p("reentry_max_atr"))
                mode = "ACTIVO" if self._p("reentry_enforce") else "OBS"
                far = dist_atr > rmax
                gates.append((f"Re-entrada ({mode})", f"{n}.a a {dist_atr:.2f} ATR",
                              f"<= {rmax:.2f} ATR", not (far and self._p("reentry_enforce"))))

        lots = self._calculate_lots(False)
        margin_ok = self.gov.probe(lots, otype, budget.KIND_ADDITIVE)
        gates.append(("Presupuesto", self.gov.last_block or f"{self.b.margin_free():.0f} libre",
                      f"req {lots:.2f} lot", margin_ok))

        if is_friday_mode:
            gates.append(("Gate viernes", "ON", "OFF", False))
        if is_weekly_start_wait:
            gates.append(("Apertura semanal", "en espera", "abierto", False))
        if self.last_recovery_close_time > 0:
            elapsed = self.now - self.last_recovery_close_time
            cd = int(self._p("cooldown_seconds"))
            if elapsed < cd:
                gates.append(("Cooldown", f"{cd - elapsed}s", "0s", False))

        ready = (my_positions == 0 and side in ("BUY", "SELL") and all(g[3] for g in gates))
        blockers = sum(1 for g in gates if not g[3])

        self.hud = {
            "status": None,
            "symbol": config.SYMBOL,
            "bid": bid, "ask": ask, "spread": spread,
            "rsi": rsi, "ema": ema, "atr": catr,
            "struct_h4": struct_h4, "signal_m15": signal_m15,
            "balance": self.b.account_balance(),
            "equity": self.b.account_equity(),
            "positions": my_positions,
            "side": side,
            "lots": lots,
            "gates": gates,
            "ready": ready,
            "blockers": blockers,
            "server_time": self._server_dt().strftime("%H:%M:%S"),
        }

    # ==============================================================
    # Calculos de cesta
    # ==============================================================
    def _round_trip_commission(self, volume):
        """RF-F: comision ida+vuelta. commission_per_lot se interpreta por lado."""
        return volume * float(self._p("commission_per_lot")) * 2.0

    def _basket_net_profit(self):
        net = 0.0
        for p in self.b.positions():
            net += p.profit + p.swap
            net -= self._round_trip_commission(p.volume)
        return net

    def _vol_risk_money(self):
        total_lots = sum(p.volume for p in self.b.positions())
        if total_lots <= 0:
            return 1.0
        atr_points = self._effective_atr() / self.b.point()
        return atr_points * total_lots * self.b.tick_value()

    # ==============================================================
    # SMART HEALER
    # ==============================================================
    def _check_healing(self):
        """Healer: ACUMULA el profit de TODOS los deals ganadores nuevos desde el
        cursor (no solo el mas reciente) y aplica una amputacion con ese 90%.

        Cambios vs version previa:
          - RF/bug: ya no se descartan los ganadores intermedios. El cursor avanza
            al mayor ticket visto, pero el presupuesto suma TODOS los ganadores
            nuevos (no salta solo al ultimo).
          - Tiempo: se usa una ventana amplia y se filtra por ticket (el cursor),
            evitando el desfase de zona horaria de datetime.now() vs server time.
          - No se exige que un solo ganador cubra toda la perdida: se va curando
            parcialmente con lo disponible en cada pasada.
        """
        if not self._p("use_healer"):
            return
        if self.lock_state == LOCK_FROZEN:
            return   # candado congelado: el Healer no toca nada

        # Gate de profundidad: el Healer solo ampu­ta en cestas reales (OP3/OP4+).
        # Con OP1 sola (core==1) la cobertura correcta es el Hedge Lock (congela la
        # perdida en ESTADO 1); con OP1+Hedge (core==2) el hedge ya congela. Amputar
        # antes realizaria en rojo una entrada que aun debe cubrirse. Se sale ANTES de
        # tocar el cursor para NO consumir presupuesto: los ganadores nuevos se siguen
        # acumulando y quedan disponibles cuando la cesta llega a OP3+.
        own = self.b.positions()
        if len(own) - len(self.cycle.lock_legs(own)) < int(self._p("healer_min_core")):
            return   # profundidad sin contar las patas LOCK (no son cesta)

        to_dt = self._deal_window_end()   # hora de servidor + 1 dia (antes + 5 min: 3 h atrasada)
        from_dt = to_dt - datetime.timedelta(days=2)
        deals = self.b.history_deals(from_dt, to_dt)
        if not deals:
            return

        budget = 0.0
        max_ticket = self.last_healed_ticket
        for d in deals:
            if d.ticket <= self.last_healed_ticket:
                continue
            if d.ticket > max_ticket:
                max_ticket = d.ticket
            if d.magic == self.b.magic and d.entry == mt5.DEAL_ENTRY_OUT and d.profit > 0:
                budget += d.profit  # acumula los ganadores nuevos DEL CICLO

        # C: presupuesto acotado al ciclo. Al arrancar un ciclo nuevo se rebasa el
        # cursor al ultimo ticket para NO contar verdes de ciclos ya cerrados. Antes
        # se acumulaban cross-ciclo (cursor congelado mientras core<3) y disparaban
        # una amputacion gigante al llegar la primera cesta a OP3+. Ver docs/memory:
        # healer-budget-accumulates-across-cycles.
        if self._healer_needs_rebaseline:
            self.last_healed_ticket = max_ticket
            self._healer_needs_rebaseline = False
            self.healer_budget = 0.0
            self._save_healer_state()
            return  # este pass no amputa: el presupuesto del ciclo arranca en cero

        if max_ticket > self.last_healed_ticket:
            self.last_healed_ticket = max_ticket
        try:
            self._heal_with(budget)
        finally:
            self._save_healer_state()

    def _heal_with(self, budget):
        """Suma `budget` (ganadores nuevos) a la bolsa y amputa, o la libera/aparca."""
        # Bolsa SOLO con perdedor real (spec 2026-10-16). Sin perdedor real, lo
        # ganado queda como ganancia y nunca se gasta despues en curar; si habia
        # bolsa (el perdedor se recupero o se cerro) se libera. El 14-oct se
        # amputaba la recovery recien abierta (roja solo por spread) con lo que
        # habia ganado la anterior.
        positions = self.b.positions()
        no_target = self._healer_target(positions)[0] is None
        if no_target and any(self._is_trend_op4(p) for p in positions):
            # Op4 (T) viva: la recovery esta cubierta por ella (cerrarla subiria la
            # exposicion), no "curada". La bolsa espera a que la Op4 cierre y entonces
            # recorta la recovery con todo lo acumulado (19-oct: se liberaba).
            if budget > 0:
                self.healer_budget += 0.90 * budget
                self.log.write("HEALER", f"Healer: bolsa {self.healer_budget:.2f} $ en espera "
                                         f"(Op4 tendencia abierta; recorta al cerrarse).",
                               balance=self.b.account_balance())
            return
        if no_target:
            thr = float(self._p("healer_min_move_usd"))
            if budget > 0:
                self.log.write("HEALER", f"Healer: ganancia {budget:.2f} $ sin perdedor real "
                                         f"(>= {thr:.2f} $/oz): queda como ganancia.",
                               balance=self.b.account_balance())
            if self.healer_budget > 0:
                self.log.write("HEALER", f"Healer: bolsa {self.healer_budget:.2f} $ liberada "
                                         f"(ya no hay perdedor real).",
                               balance=self.b.account_balance())
            self.healer_budget = 0.0
            return
        self.healer_budget += 0.90 * budget
        if self.healer_budget > 0:
            spent = self._apply_healing(self.healer_budget)
            self.healer_budget = max(0.0, self.healer_budget - spent)

    def _save_healer_state(self, clear=False):
        """Persiste cursor y bolsa del Healer en el meta del ciclo (solo si cambian)."""
        cursor = None if clear else int(self.last_healed_ticket)
        bolsa = None if clear else round(float(self.healer_budget), 6)
        if self.cycle.get_meta("healer_cursor") != cursor or self.cycle.get_meta("healer_budget") != bolsa:
            self.cycle.meta["healer_cursor"] = cursor
            self.cycle.set_meta("healer_budget", bolsa)

    def _closing_increases_exposure(self, p):
        """True si cerrar `p` AUMENTA la exposicion neta absoluta de la cesta.

        Es la definicion estructural de "leg de cobertura": no depende del
        comment ni de quien lo abrio, sino de lo que su cierre le hace al
        riesgo direccional. El Hedge Lock cumple esto por construccion mientras
        siga cubriendo; deja de cumplirlo en cuanto la cesta se equilibra.
        """
        net = self._net_exposure()
        contrib = p.volume if p.type == mt5.POSITION_TYPE_BUY else -p.volume
        return abs(net - contrib) > abs(net)

    def _healer_target(self, positions):
        """Peor PERDEDOR REAL amputable: (pos, money) o (None, 0.0).

        Perdedor real = amputable y con perdida (profit + swap) >= healer_min_move_usd
        por onza; una pata roja solo por spread no lo es (spec 2026-10-16).

        Proteccion de la cobertura: mientras el P&L total del ciclo siga en
        negativo, se excluyen los legs cuyo cierre aumentaria la exposicion neta.

        Por que. `_apply_healing` era un argmin(profit+swap) sin nocion de rol:
        no distinguia entrada, cobertura, recovery ni rescate. Y como recovery y
        rescate abren SIEMPRE del lado de Op1, la cesta acumula N legs de un lado
        y uno solo del otro -> en cuanto la tendencia acompaña, el hedge es el
        peor leg por geometria, no por casualidad. En produccion, 16 de 21
        amputaciones mordieron un Hedge Lock, a 0.01 lotes por vez (el ticket
        #1609321275, 12 veces en 2h30m). Cada mordisco realiza ~90% del verde
        acumulado como perdida, asi que el bot convertia en rojo permanente lo
        que el Unwind acababa de bancar, y de paso desmontaba su unica cobertura.

        El gate replica el freeze del Unwind (cycle_realized + neto flotante):
        con la cesta en positivo la cobertura ya no hace falta y desarmarla es
        trabajo del Unwind, que lo hace ordenadamente. Ver docs/memory:
        healer-unwind-hedge-cascade.
        """
        protect_cover = (self.cycle_realized + self._basket_net_profit()) <= 0

        # Rol: los miembros de un par intacto (ENTRY<->HEDGE, huerfano<->cover)
        # son intocables mientras el ciclo siga en rojo. La regla estructural
        # de abajo no basta sola: con N recoveries del lado de la ENTRY, cerrar
        # la ENTRY (o su hedge) puede REDUCIR |neto| y pasar el filtro, pero
        # huerfana al par igual (asi murio la OP1s del 11-ago: -1,332 de
        # amputacion financiada por el churn). El par se congela completo.
        pair_frozen = self.cycle.pair_members(positions) if protect_cover else set()
        # Patas LOCK: intocables SIEMPRE (solo las cierra un aflojado, la
        # disolucion o un cierre total), independiente de protect_cover.
        pair_frozen |= {p.ticket for p in self.cycle.lock_legs(positions)}

        min_move = float(self._p("healer_min_move_usd"))
        contract = self.b.contract_size()
        # Peor leg por DINERO REAL = profit + swap (antes solo miraba p.profit e
        # ignoraba el swap acumulado, que en holds largos puede ser material).
        worst = None
        worst_money = 0.0
        cover_skipped = 0
        for p in positions:
            if p.ticket in pair_frozen:
                cover_skipped += 1
                continue
            if protect_cover and self._closing_increases_exposure(p):
                cover_skipped += 1
                continue
            money = p.profit + p.swap
            if money >= 0 or p.volume <= 0:
                continue
            if -money / (p.volume * contract) < min_move - 1e-9:
                continue   # rojo de spread/ruido: no es perdedor real
            if worst is None or money < worst_money:
                worst_money = money
                worst = p

        if cover_skipped and not self._cover_protect_logged:
            self.log.write(
                "HEALER",
                f"Cobertura protegida: {cover_skipped} leg(s) excluido(s) de la "
                f"amputacion mientras el ciclo siga en negativo.",
                balance=self.b.account_balance())
            self._cover_protect_logged = True
        return worst, worst_money

    def _apply_healing(self, bolsa):
        """Amputa parcialmente el peor perdedor real con la bolsa (ya al 90%).

        Devuelve lo gastado (la perdida realizada, positiva) o 0.0 si no amputa.
        Cada ganancia que llega mientras la pata pierde le recorta un trozo.
        """
        worst, worst_money = self._healer_target(self.b.positions())
        if worst is None:
            return 0.0

        # Costo real por lote = P&L (precio + swap) prorrateado por volumen. Es exacto
        # porque el P&L de la posicion escala lineal con el volumen (mismo precio de
        # apertura); reemplaza al calculo por diff_points, que no consideraba swap.
        cost_per_lot = -worst_money / worst.volume
        min_lot = self.b.volume_min()
        if cost_per_lot * min_lot > bolsa:
            return 0.0  # ni el lote minimo cabe: la bolsa espera

        import math
        vol_step = self.b.volume_step()
        lots_to_close = math.floor(bolsa / cost_per_lot / vol_step + 1e-9) * vol_step
        lots_to_close = round(min(lots_to_close, worst.volume), 8)  # no cerrar mas de lo abierto
        if lots_to_close < min_lot - 1e-9:
            return 0.0

        vol_before = worst.volume  # captura antes: close_partial puede dejar worst.volume=0
        # Identidad de la operacion amputada, capturada ANTES del cierre para
        # dejar constancia en el log de a que leg se le aplico la amputacion.
        op_side = "BUY" if worst.type == mt5.POSITION_TYPE_BUY else "SELL"
        op_desc = worst.comment or "sin comentario"
        op_ticket = worst.ticket
        op_open = worst.price_open
        res = self.b.close_partial(worst, lots_to_close, "Healer Amputacion")
        if res is not None and getattr(res, "retcode", None) != mt5.TRADE_RETCODE_DONE:
            return 0.0
        # B: registra la perdida realizada (incl. swap, prorrateada por el
        # volumen cerrado) en el acumulado del ciclo, para que el freeze del
        # Unwind la tenga en cuenta y la amputacion NO levante el neto flotante
        # abriendo la cobertura (cascade). Ver docs/memory: healer-unwind-hedge-cascade.
        frac = lots_to_close / vol_before
        self.cycle_realized += worst_money * frac
        spent = -worst_money * frac
        self.log.write(
            "HEALER",
            f"Amputacion Tactica sobre {op_side} '{op_desc}' (ticket #{op_ticket}) "
            f"abierta @ {op_open:.2f}. Lotes amputados: {lots_to_close:.2f}. "
            f"Bolsa restante: {max(0.0, bolsa - spent):.2f} $",
            worst_money, bolsa, self.b.account_balance(), ticket=op_ticket)
        return spent

    # ==============================================================
    # PROFIT BANKING (Unwind)
    # ==============================================================
    def _profit_banking(self):
        """Banca una posicion ganadora SOLO si la cesta total ya es neta positiva.

        Cambio clave: mientras el neto de la cesta sea <= 0 las ganadoras estan
        CUBRIENDO a las perdedoras (hedge lock). Desarmar esa cobertura re-exponia
        al perdedor desnudo (causa del -760 observado). Ahora el unwind respeta el
        congelamiento: el hedge solo se cierra cuando el saldo TOTAL es positivo.

        PARES (rol): los miembros de un par intacto (ENTRY<->HEDGE) NUNCA se
        bancan sueltos, ni siquiera con el freeze abierto. La auditoria 6-11 ago
        mostro los dos modos de fallo: (a) bancar la OP1 verde dejaba el hedge
        rojo huerfano, que la maquina re-etiquetaba como OP1 y cubria de nuevo
        (hedge-sobre-hedge); (b) bancar el hedge verde con la OP1 roja flotando
        lo reabria al tick siguiente en un loop de scalping (12+ vueltas el
        10-ago) mientras el freeze seguia abierto por los verdes del churn. Un
        par solo se desarma COMPLETO: aqui si su P&L conjunto es positivo, o en
        _close_all cuando el TOTAL de la cesta alcanza el target. Bancables
        sueltos quedan RECOVERY/RESCUE y los verdes sin par.

        RF-C corregido: la condicion de dinero y la posicion elegida son la MISMA
        (se banca la ganadora mas rica que cumpla el umbral, no se mezclan).
        RF-F: comision ida+vuelta.
        """
        if not self._p("use_unwind_mode"):
            return
        if self.lock_state == LOCK_FROZEN:
            return   # candado congelado: no se cobra ninguna pata ni par
        positions = self.b.positions()
        if len(positions) < 2:
            return

        # FREEZE (B): no desarmar cobertura si el P&L TOTAL del ciclo (realizado +
        # flotante) sigue en negativo. Antes se miraba SOLO el flotante, y una
        # amputacion del Healer (que realiza rojo y sube el flotante remanente) abria
        # el gate y bancaba el hedge -> cesta desnuda -> stop-out. Al incluir lo ya
        # realizado en el ciclo, la amputacion es NEUTRA para el freeze (mueve dinero
        # de flotante a realizado sin cambiar la suma) y la cascade queda rota.
        if self.cycle_realized + self._basket_net_profit() <= 0:
            return

        current_atr = self._effective_atr()
        atr_mult = float(self._p("unwind_atr_mult"))
        floor = self._move_money(float(self._p("unwind_floor_move_usd")))
        pair_tickets = self.cycle.pair_members(positions)
        lock_tickets = {p.ticket for p in self.cycle.lock_legs(positions)}
        pair_tickets |= lock_tickets   # patas LOCK: intocables para el Unwind

        best_single = None
        best_pair = None
        best_money = -1e18
        for p in positions:
            if p.ticket in pair_tickets:
                continue  # miembro de par intacto: solo se desarma junto
            money = p.profit + p.swap - self._round_trip_commission(p.volume)
            if money <= 0:
                continue
            dist = abs(p.price_current - p.price_open) / current_atr if current_atr else 0.0
            if (dist >= atr_mult or money >= floor) and money > best_money:
                # Aguante: no cobrar una pata suelta si cerrarla AUMENTA el neto y
                # la cuenta quedaria por debajo del movimiento de supervivencia.
                if self._closing_increases_exposure(p):
                    s_after = self.surv.s_after_close(p)
                    # Desconocido (MT5 sin respuesta): no se cobra la pata suelta.
                    if s_after is None or s_after < float(self._p("survival_move_usd")):
                        continue
                best_money = money
                best_single, best_pair = p, None

        for leg, hedge in self.cycle.pairs(positions):
            if leg.ticket in lock_tickets or hedge.ticket in lock_tickets:
                continue
            money = (leg.profit + leg.swap + hedge.profit + hedge.swap
                     - self._round_trip_commission(leg.volume)
                     - self._round_trip_commission(hedge.volume))
            if money <= 0:
                continue  # par congelado en rojo: intocable
            dist = max(abs(leg.price_current - leg.price_open),
                       abs(hedge.price_current - hedge.price_open))
            dist = dist / current_atr if current_atr else 0.0
            if (dist >= atr_mult or money >= floor) and money > best_money:
                best_money = money
                best_single, best_pair = None, (leg, hedge)

        if best_single is not None:
            banked_ticket = best_single.ticket
            self.b.close_position(best_single, "Unwind Profit Banking")
            self.cycle_realized += best_single.profit + best_single.swap  # B: acumula lo realizado del ciclo
            self.log.write("UNWIND", f"Profit Banking. Money: {best_money:.2f}",
                           balance=self.b.account_balance(), ticket=banked_ticket)
        elif best_pair is not None:
            leg, hedge = best_pair
            # Primero el miembro ROJO: si el segundo cierre fallara, lo que
            # queda vivo es un verde desnudo (benigno), nunca un rojo huerfano.
            first, second = ((leg, hedge)
                             if (leg.profit + leg.swap) <= (hedge.profit + hedge.swap)
                             else (hedge, leg))
            for p in (first, second):
                self.b.close_position(p, "Unwind Profit Banking")
                self.cycle_realized += p.profit + p.swap
            self.log.write("UNWIND",
                           f"Profit Banking de PAR completo (tickets #{leg.ticket} + "
                           f"#{hedge.ticket}). Money conjunto: {best_money:.2f}",
                           balance=self.b.account_balance(), ticket=leg.ticket)

    # ==============================================================
    # SENTINEL OP4 (Rescate)
    # ==============================================================
    def _check_rescue(self, positions):
        """OP4. `positions` son los legs del CICLO (cycle_legs): los huerfanos y
        sus coberturas no cuentan profundidad ni pueden ser el 'op3' de anclaje."""
        if not self._p("use_rescue_mode"):
            return
        if str(self._p("rescue_mode")).strip().lower() == "trend":
            self._check_rescue_trend(positions)
            return
        if self.spread_high or self.vol_breaker or self.close_only:
            return  # no abrir martingala con spread alto, vela anomala (VCB) ni en close-only
        if len(positions) < 3:
            return
        if int(self.cycle.get_meta("rescue_opened", 0)) >= int(self._p("max_rescue_legs")):
            return  # cap de Op4 ABIERTAS en el ciclo (no vivas): corta el bucle abrir-cobrar-reabrir
        if self.news_block:
            return  # NewsGuard: sin excepciones, tampoco para el L3
        if self._risk_hour():
            return  # horas de riesgo: no se martingalea
        if self.now - self.last_rescue_time < int(self._p("rescue_cooldown")):
            return  # anti-spam (sobre todo en L3 "abre ahora")

        current_dd = self._basket_net_profit()
        abs_dd = abs(current_dd)
        level = self._rescue_level(abs_dd)

        active_atr_mult = float(self._p("rescue_atr_mult"))
        ignore_rsi = False
        immediate = False
        if level >= 2:
            active_atr_mult = 3.0
            ignore_rsi = True
        if level >= 3:
            active_atr_mult = 2.0
            ignore_rsi = True
            immediate = True  # L3 = ABRE AHORA (sin esperar distancia ni momentum)

        # Op3 = ultima posicion core abierta (por tiempo)
        last_time = 0
        vol_op3 = price_op3 = 0.0
        type_op3 = -1
        for p in positions:
            if p.time > last_time:
                last_time = p.time
                vol_op3 = p.volume
                price_op3 = p.price_open
                type_op3 = p.type

        current_atr = self._effective_atr()
        min_distance = current_atr * active_atr_mult
        rsi = self.rsi0
        rescue_rsi = int(self._p("rescue_rsi"))

        comment = "Sentinel Op 4 (L1)"
        if level >= 2:
            comment = "Sentinel Op 4 (L2)"
        if level >= 3:
            comment = "Sentinel Op 4 (L3-CRITICO)"

        signal = False
        if type_op3 == mt5.POSITION_TYPE_SELL:
            if immediate:
                signal = True  # L3: defensa inmediata
            else:
                dist = self.b.bid() - price_op3
                if dist >= min_distance and (ignore_rsi or rsi > rescue_rsi):
                    signal = True
            if signal and self._h4_gate_ok(mt5.ORDER_TYPE_SELL):
                self._open_additive(mt5.ORDER_TYPE_SELL, vol_op3, comment,
                                    ledger.ROLE_RESCUE, comment)
                if self._last_additive_sent:   # cooldown solo si la orden SALIO al broker
                    self.last_rescue_time = self.now
        elif type_op3 == mt5.POSITION_TYPE_BUY:
            if immediate:
                signal = True  # L3: defensa inmediata
            else:
                dist = price_op3 - self.b.ask()
                if dist >= min_distance and (ignore_rsi or rsi < (100 - rescue_rsi)):
                    signal = True
            if signal and self._h4_gate_ok(mt5.ORDER_TYPE_BUY):
                self._open_additive(mt5.ORDER_TYPE_BUY, vol_op3, comment,
                                    ledger.ROLE_RESCUE, comment)
                if self._last_additive_sent:   # cooldown solo si la orden SALIO al broker
                    self.last_rescue_time = self.now

    def _op3_trail_params(self, leg, pts, current_atr, point):
        """(arranque, distancia) en puntos del trailing de la ultima pata del ciclo.
        La Op4 tendencia usa su trailing propio, sin turbo (spec 2026-10-16)."""
        if self._is_trend_op4(leg):
            return ((current_atr * float(self._p("rescue_trend_trail_start_atr"))) / point,
                    (current_atr * float(self._p("rescue_trend_trail_dist_atr"))) / point)
        start_pts = (current_atr * float(self._p("op3_start_atr"))) / point
        active_dist = (current_atr * float(self._p("op3_base_dist_atr"))) / point
        if pts >= (current_atr * float(self._p("op3_turbo_trigger_atr"))) / point:
            active_dist = (current_atr * float(self._p("op3_turbo_dist_atr"))) / point
        return start_pts, active_dist

    @staticmethod
    def _is_trend_op4(p):
        return (p.comment or "").startswith(OP4_TREND_COMMENT)

    def _check_rescue_trend(self, positions):
        """Op4 tendencia (spec 2026-10-16-op4-tendencia): en vez de copiar la
        ultima pata, abre CONTRA la recovery/rescue que mas pierde (a favor del
        movimiento), con tamano <= |neto del ciclo|. Reduce el neto, asi que el
        tope de supervivencia la deja pasar; sus ganancias alimentan al Healer,
        que recorta la perdedora. Una abierta a la vez; se evalua una vez por
        vela M15 cerrada. Sin hora de riesgo ni gate H4: no promedia.
        """
        if self.spread_high or self.vol_breaker or self.close_only or self.news_block:
            return
        if len(positions) < 3:
            return
        if self.lock_state != LOCK_FREE:
            return   # con candado vivo ya esta neutralizado (y el trailing de Op3 se apaga)
        if self.now - self.last_rescue_time < int(self._p("rescue_cooldown")):
            return
        df = self.df_m15
        if df is None or len(df) < 2:
            return
        bar_t = df["time"].iloc[-2]
        if bar_t == self._op4t_bar:
            return   # esta vela cerrada ya se evaluo
        self._op4t_bar = bar_t
        if any(self._is_trend_op4(p) for p in positions):
            return   # una sola a la vez: el Healer recorta entre una y otra
        opened = int(self.cycle.get_meta("rescue_opened", 0))
        if opened >= int(self._p("rescue_trend_max_legs")):
            if not self.cycle.get_meta("op4t_cap_logged"):
                self.cycle.set_meta("op4t_cap_logged", True)
                self.log.write("RESCATE", "Op4 tendencia: cupo del ciclo agotado.",
                               balance=self.b.account_balance())
            return

        close1 = float(df["close"].iloc[-2])
        atr = self._effective_atr()
        k = float(self._p("rescue_trend_k_atr"))
        frozen = self.cycle.pair_members(positions) | {p.ticket for p in self.cycle.lock_legs(positions)}
        roles = (ledger.ROLE_RECOVERY, ledger.ROLE_RESCUE)
        target, worst = None, 0.0
        for p in positions:
            if p.ticket in frozen or self.cycle.role_of(p.ticket) not in roles:
                continue
            loss = (p.price_open - close1) if p.type == mt5.POSITION_TYPE_BUY else (close1 - p.price_open)
            if loss >= k * atr - 1e-9 and loss > worst:
                target, worst = p, loss
        if target is None:
            return

        net = survival.net_lots(positions)
        if target.type == mt5.POSITION_TYPE_SELL:
            otype, side = mt5.ORDER_TYPE_BUY, "BUY"
            if net >= 0:
                return   # comprar no reduciria el neto
        else:
            otype, side = mt5.ORDER_TYPE_SELL, "SELL"
            if net <= 0:
                return
        step = self.b.volume_step()
        lots = math.floor(min(target.volume, abs(net)) / step + 1e-9) * step
        lots = round(lots, 8)
        if lots < self.b.volume_min() - 1e-9:
            return
        ok = self._open_additive(otype, lots, OP4_TREND_COMMENT, ledger.ROLE_RESCUE, "Op4 tendencia")
        if self._last_additive_sent:
            self.last_rescue_time = self.now
        if ok:
            self.log.write(
                "RESCATE",
                f"Op4 tendencia: {side} {lots:.2f} lotes @ {close1:.2f} contra la recovery "
                f"#{target.ticket} (-{worst:.2f} $/oz, {worst / atr:.1f} ATR). "
                f"Op4 {opened + 1}/{int(self._p('rescue_trend_max_legs'))} del ciclo.",
                balance=self.b.account_balance(), ticket=target.ticket)

    # ==============================================================
    # BUFFERS (equivalente a los CopyBuffer de OnTick)
    # ==============================================================
    def _rates(self, timeframe, count=150, min_bars=60):
        rates = mt5.copy_rates_from_pos(config.SYMBOL, timeframe, 0, count)
        if rates is None or len(rates) < min_bars:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def _fetch_tick(self):
        """Seam de datos: en vivo devuelve el tick de MT5; el backtest lo sobrescribe."""
        return mt5.symbol_info_tick(config.SYMBOL)

    def _compute_buffers(self):
        tick = self._fetch_tick()
        if tick is None:
            return False
        self.now = tick.time

        df15 = self._rates(config.TIMEFRAME_CORE)
        df5 = self._rates(config.TIMEFRAME_M5)
        dfh4 = self._rates(config.TIMEFRAME_STRUCT)
        if df15 is None or df5 is None or dfh4 is None:
            return False

        atr_period = int(self._p("atr_period"))
        atr15 = indicators.atr(df15, atr_period)
        self.atr0 = float(atr15.iloc[-1])
        self.atr1 = float(atr15.iloc[-2])
        self.ema0 = float(indicators.ema(df15["close"], int(self._p("fast_ma"))).iloc[-1])
        self.rsi0 = float(indicators.rsi(df15).iloc[-1])

        # M5 solo para confirmar el momentum de la entrada (_m5_momentum). Los
        # indicadores M5 del grinder (EMA/ADX/RSI) se fueron con el a su proceso.
        self.m5_open1 = float(df5["open"].iloc[-2])
        self.m5_close1 = float(df5["close"].iloc[-2])

        self.df_h4 = dfh4
        self.df_m15 = df15

        # Guarda contra NaN (warmup de indicadores)
        if pd.isna(self.atr0) or pd.isna(self.rsi0) or pd.isna(self.ema0):
            return False
        return True

    def _server_dt(self):
        return datetime.datetime.utcfromtimestamp(self.now)

    def _deal_window_end(self):
        """Fin de la ventana de history_deals: hora de servidor + 1 dia.

        Antes era + 5 min y la ventana iba 3 h atrasada: la libreria de MT5 trata el
        datetime naive como hora LOCAL del PC (UTC+3) y los deals vienen con la hora
        del servidor (UTC+3) ya metida en el epoch, asi que el Healer veia cada cierre
        3 h tarde (19-oct: la Op4 (T) cerro +149 $ y la recovery no se recorto). Con
        + 1 dia el ultimo deal siempre entra; los consumidores filtran por ticket o
        solo preguntan "hay alguno", asi que el margen no duplica nada.
        """
        if not self.now:
            return datetime.datetime.now() + datetime.timedelta(days=1)
        return self._server_dt() + datetime.timedelta(days=1)

    def _check_stop_out(self):
        """Una vez por minuto: deal propio de stop-out ('[so...') nuevo => alerta CRITICA."""
        if self.now < self._next_so_check:
            return
        self._next_so_check = self.now + 60
        try:
            to_dt = self._deal_window_end()
            deals = self.b.history_deals(to_dt - datetime.timedelta(days=1), to_dt)
            magic = getattr(self.b, "magic", config.MAGIC_NUMBER)
            nuevos = [d for d in deals if d.magic == magic
                      and str(getattr(d, "comment", "") or "").startswith("[so")
                      and d.ticket > self._last_so_ticket]
            if not self._so_primed:
                # Tras un reinicio no se re-alerta un stop-out viejo: solo se fija el ancla.
                self._so_primed = True
                if nuevos:
                    self._last_so_ticket = max(d.ticket for d in nuevos)
                return
            if nuevos:
                self._last_so_ticket = max(d.ticket for d in nuevos)
                d = max(nuevos, key=lambda x: x.ticket)
                self.log.write("ERROR", f"STOP-OUT del broker detectado: {d.comment}")
                self.alerts.notify(
                    "stop_out", "CRITICA", "stop-out ejecutado por el broker",
                    f"El broker cerro posiciones por stop-out ({len(nuevos)} deals). "
                    f"Ultimo comentario: {d.comment}. Profit: {getattr(d, 'profit', 0)}.")
        except Exception as e:  # noqa: BLE001  (best-effort; nunca rompe on_tick)
            self._check_failed("stop-out", e)

    def _check_idle(self):
        """Una vez por hora: sin posiciones propias ni deals propios en 72 h => AVISO.

        Las 72 h se cuentan tambien desde que el bot esta RUNNING (_idle_ref): una
        cuenta recien creada o recien encendida no tiene deals y no debe avisar
        hasta llevar de verdad 72 h sin operar (falso aviso del 2026-10-14)."""
        if self.now < self._next_idle_check:
            return
        self._next_idle_check = self.now + 3600
        if self.close_only:   # solo bots RUNNING: uno detenido a proposito no esta "inactivo"
            self._idle_ref = None
            return
        if self._idle_ref is None:
            self._idle_ref = self.now
        if self.now - self._idle_ref < 72 * 3600:
            return
        try:
            if self.b.positions():
                return
            to_dt = self._deal_window_end()
            deals = self.b.history_deals(to_dt - datetime.timedelta(hours=72), to_dt)
            magic = getattr(self.b, "magic", config.MAGIC_NUMBER)
            if any(d.magic == magic for d in deals):
                return
            self.alerts.notify(
                "inactivo", "AVISO", "bot inactivo 72 h",
                "Sin posiciones abiertas ni operaciones propias en las ultimas 72 horas.")
        except Exception as e:  # noqa: BLE001
            self._check_failed("inactividad", e)

    def _check_failed(self, what, exc):
        """Un chequeo de alertas fallo: SYSTEM como mucho una vez por hora."""
        if self.now >= self._next_chk_err_log:
            self._next_chk_err_log = self.now + 3600
            try:
                self.log.write("SYSTEM", f"Chequeo de {what} fallo (se omite): {exc}")
            except Exception:  # noqa: BLE001
                pass

    # ==============================================================
    # ON TICK (CORE)
    # ==============================================================
    def on_tick(self):
        if not self._compute_buffers():
            self.hud = {"status": "Esperando datos de MT5 (warmup de indicadores)..."}
            return

        alerts.update_dead(self)
        self._check_stop_out()
        self._check_idle()

        struct_h4 = indicators.get_h4_structure(self.df_h4, self._p("use_h4_struct"))
        signal_m15 = indicators.check_m15_breakout(self.df_m15)

        dt = self._server_dt()
        dow = (dt.weekday() + 1) % 7  # MQL5: domingo=0 ... sabado=6
        hour = dt.hour
        is_friday_mode = (self._p("close_friday") and dow == 5 and hour >= int(self._p("friday_hour")))
        is_weekly_start_wait = (dow == 0 or (dow == 1 and hour < int(self._p("monday_start_hour"))))

        # NewsGuard (Fase 1): ¿estamos dentro de la ventana dura de una roja?
        # Igual que spread/VCB, SOLO condiciona aperturas aditivas: la gestion
        # (hedge, cierres, trailing, healer, unwind) nunca se congela. Con
        # news_enforce=True (default) bloquea las aditivas en la ventana; con
        # news_enforce=False es pura observacion: loguea y no toca.
        self.news_active, self.news_reason = self.news.check(
            self.now, int(self._p("news_pre_seconds")),
            int(self._p("news_post_seconds")), self._p("news_currencies"))
        self.news_block = self.news_active and bool(self._p("news_enforce"))

        # Snapshot read-only para la TUI (se publica aun si el tick sale temprano).
        self._build_hud(struct_h4, signal_m15, is_friday_mode, is_weekly_start_wait)

        # Spread: NO congela la gestion (RF-A). Solo bloquea aperturas que
        # ANADEN riesgo (entrada, recovery, rescate). Cierres, trailing,
        # healer y profit banking corren igual; el Hedge (proteccion) tambien.
        self.spread_high = self.b.spread() > int(self._p("inp_max_spread"))

        # VCB (Fork A): circuit breaker de volatilidad. Bloquea las aperturas que
        # anaden riesgo durante velas anomalas (noticia/manipulacion/spike); la
        # gestion (hedge, cierres, trailing, healer) sigue. Cachea la estructura H4
        # para los gates de recovery/rescate. Solo se loguea la transicion on/off.
        self.struct_h4 = struct_h4
        self.vol_breaker = self._vol_breaker_active()
        if self.vol_breaker != self.vol_breaker_prev:
            estado = "ACTIVADO" if self.vol_breaker else "liberado"
            self.log.write("VCB", f"Circuit breaker de volatilidad {estado}.",
                           balance=self.b.account_balance())
            self.vol_breaker_prev = self.vol_breaker

        # Identidad por ROL: reconcilia el ledger ANTES de los subsistemas,
        # para que Unwind/Healer conozcan los pares vigentes de este tick
        # (adopcion por comment tras un restart, hedges viudos -> ORPHAN,
        # promocion de huerfano solitario a ENTRY).
        # Lectura CHEQUEADA: si positions_get fallo (None) el tick se salta entero.
        # Una lista vacia falsa haria olvidar roles en el ledger, reiniciar la
        # meta del ciclo (candado, rescue_opened, deuda de disolucion) o abrir
        # una ENTRY sobre una cesta viva.
        _pos_tick = self.b.positions_checked()
        if _pos_tick is None:
            if self.now >= self._pos_fail_next_log:
                self._pos_fail_next_log = self.now + LOCK_FAIL_LOG_EVERY_S
                self.log.write("SYSTEM", "Lectura de posiciones fallida (MT5 sin respuesta): "
                                         "tick omitido, sin decisiones de trading.",
                               balance=self.b.account_balance())
            return
        self.cycle.sync(_pos_tick)
        self._prune_hedge_fail(_pos_tick)
        self._backfill_lock_since(_pos_tick)

        # Candado de cesta (spec §5.3): se evalua ANTES de los subsistemas y el
        # estado se calcula con las posiciones releidas (puede haberse puesto).
        # Cada uno aislado: una excepcion (config/meta corrupta) no aborta el
        # tick antes del hedge monitor y el trailing.
        self._guarded("candado", self._maybe_lock)
        self._guarded("aflojado", self._maybe_unlock)    # §5.4: solo con rebote confirmado
        self._guarded("disolucion", self._maybe_dissolve)  # §5.5: diaria, por parejas, neto intacto
        _pos_now = self.b.positions()
        self.lock_state = self._lock_state(_pos_now)
        frozen = self.lock_state == LOCK_FROZEN
        if self.lock_state != LOCK_FREE:
            self._clear_lock_sls(_pos_now)   # cada tick: tambien tras un reinicio

        # Subsistemas transversales (CONGELADO: ni Healer ni Unwind)
        if not frozen:
            self._check_healing()
            self._profit_banking()

        # Todas las posiciones del magic son cesta core: el grinder salio del
        # Sentinel a su propio proceso (bot/strategy_m5.py), con su propio magic.
        # Se relee DESPUES de los subsistemas (pueden haber cerrado legs).
        core_positions = self.b.positions_checked()
        if core_positions is None:
            return   # lectura fallida a mitad de tick: nada se decide sobre una lista falsa
        my_positions = core_count = len(core_positions)

        # Vistas por ROL. La profundidad de la maquina de estados es la del
        # CICLO (cycle_legs: sin huerfanos ni sus coberturas): un hedge viudo
        # de un ciclo muerto no debe fabricar Recovery/OP4 ni bloquear nada.
        entry = self.cycle.entry_pos(core_positions)
        entry_hedge = (self.cycle.hedge_of(entry.ticket, core_positions)
                       if entry is not None else None)
        cycle_legs = self.cycle.cycle_legs(core_positions)
        cycle_count = len(cycle_legs)
        lock_n = len(self.cycle.lock_legs(core_positions))
        lock_alive = lock_n > 0
        # Profundidad de la cesta SIN patas LOCK: el candado no es un leg de
        # rescate (target ">=4 core" y etiqueta "Rescue Mission Success").
        depth = core_count - lock_n

        # Red de seguridad de ciclo (B/C): si NO hay cesta core (cerro por _close_all,
        # stop-out del broker o SL), reinicia el realizado del ciclo y marca rebaseline
        # del Healer. Cubre los finales de ciclo que no pasan por _close_all.
        # Solo tras DOS lecturas vacias confirmadas seguidas: un vacio espurio no
        # debe borrar la meta (candado, rescue_opened, deuda). Mientras no se
        # confirma, el tick termina aqui (sin ENTRY sobre meta vieja); con la meta
        # ya vacia y sin realizado (arranque limpio) no hay nada que proteger.
        if core_count == 0:
            self._empty_reads += 1
            if self._empty_reads < 2:
                if self.cycle.meta or abs(self.cycle_realized) > 1e-9:
                    return
            else:
                self.cycle_realized = 0.0
                self._healer_needs_rebaseline = True
                self._cover_protect_logged = False
                self.cycle.reset_meta()   # ref_lot / rescue_opened / candado: meta del ciclo muerto
        else:
            self._empty_reads = 0

        current_atr = self._effective_atr()
        point = self.b.point()
        digits = self.b.digits()

        # ============================================================
        # MONITOR DE SALIDA - trailing de cesta (OP8/OP9 unificados)
        # Se ARMA cuando el neto alcanza el target; luego sigue el pico y cierra
        # al retroceder. Deja correr tendencia favorable y asegura lo ganado.
        # ============================================================
        if my_positions > 0:
            net_pl = self._basket_net_profit()
            arm_target = self._move_money(float(self._p("basket_arm_move_usd")))
            # Cesta profunda (>=4 core sin patas LOCK): se arma antes, con el target de rescate.
            if depth >= 4 and self._p("use_rescue_mode"):
                rescue_target = self._move_money(float(self._p("rescue_arm_move_usd")))
                if rescue_target < arm_target:
                    arm_target = rescue_target

            if not self.cycle_armed and net_pl >= arm_target:
                self.cycle_armed = True
                self.max_cycle_peak = net_pl

            if self.cycle_armed:
                if net_pl > self.max_cycle_peak:
                    self.max_cycle_peak = net_pl
                allowed_retrace = self._move_money(float(self._p("fixed_retrace_move_usd")))
                if self._p("use_dynamic_retrace"):
                    vol_money = self._vol_risk_money()
                    allowed_retrace = vol_money * float(self._p("retrace_atr_mult"))
                    allowed_retrace = max(self._move_money(float(self._p("retrace_min_move_usd"))),
                                          min(allowed_retrace, self._move_money(float(self._p("retrace_max_move_usd")))))
                # RF-B: el retroceso se evalua SIEMPRE que este armado, aunque
                # net_pl haya caido por debajo del target entre ticks.
                if self.max_cycle_peak - net_pl >= allowed_retrace:
                    # OP12: piso verde para OP1 SOLA (core_count == 1). Una entrada
                    # desnuda nunca debe cerrarse en rojo por el trail; eso actuaria
                    # como un SL y contradice la filosofia hedge-congela (OP2 congela
                    # la perdida, no hay SL catastrofico). Si el cierre caeria bajo
                    # min_green (reverson veloz que cruza el piso entre ticks), se
                    # DESARMA y la posicion vuelve a ESTADO 1 este mismo tick para que
                    # el Hedge Lock la cubra a hedge_dist. Con >=2 legs la cesta es
                    # real: bankear el neto (con legs rojas individuales) es el
                    # comportamiento deseado y se mantiene intacto.
                    if core_count == 1 and net_pl < self._move_money(float(self._p("min_green_move_usd"))):
                        self.cycle_armed = False
                        self.max_cycle_peak = 0.0
                    else:
                        reason = "Rescue Mission Success" if depth >= 4 else "Basket Profit Trail"
                        self._close_all(reason)
                        return
        else:
            self.cycle_armed = False
            self.max_cycle_peak = 0.0

        # Gate de cierre de viernes (usa flags ya calculados al inicio del tick)
        if is_friday_mode and my_positions > 0 and self._basket_net_profit() > 0:
            self._close_all("Viernes Close")
            return

        # CONGELADO: el trailing de cesta y el viernes (arriba) cierran todo a la
        # vez; nada mas corre. Ni hedge monitor, _resize_hedge, smart trail,
        # watchdog de huerfanos, Op1/Op3/Op4 ni trail de Op3: cualquier orden o
        # SL que salte cambiaria el neto congelado.
        if frozen:
            return

        # Distancia de cobertura vigente (comun al monitor y al watchdog)
        atr_points = current_atr / point
        dynamic_dist = atr_points * float(self._p("hedge_atr_mult"))
        active_hedge_dist = max(float(self._p("hedge_dist")), dynamic_dist)

        # --- HEDGE MONITOR (por ROL: corre a CUALQUIER conteo) ---
        # Antes vivia en el ESTADO 1 (count==1): una OP1 que se quedaba sin
        # cobertura con la cesta ya profunda (op3/op4 abiertas) era imposible
        # de cubrir. Ahora la ENTRY sin hedge vivo se congela a hedge_dist sin
        # importar cuantos legs mas existan.
        if entry is not None:
            if entry.type == mt5.POSITION_TYPE_BUY:
                profit_pts = (entry.price_current - entry.price_open) / point
                loss_pts = (entry.price_open - entry.price_current) / point
            else:
                profit_pts = (entry.price_open - entry.price_current) / point
                loss_pts = (entry.price_current - entry.price_open) / point

            if entry_hedge is None:
                # Con candado vivo no se abren hedges: un Hedge Lock de volumen
                # completo sobre el LOCK residual invertiria el neto. La red en
                # AFLOJADO es el re-candado a S < lock_trigger_usd.
                if loss_pts >= active_hedge_dist and not lock_alive:
                    self._open_hedge(entry)
            else:
                # Invariante del par: el hedge nunca mas grande que la ENTRY
                # (si el Healer amputo parte de la ENTRY, se recorta el exceso).
                self._resize_hedge(entry, entry_hedge)

            # Smart trail: solo con la entrada SOLA (comportamiento original
            # del ESTADO 1; con mas legs la gestiona la cesta).
            if (core_count == 1 and self._p("use_smart_trail")
                    and profit_pts > (current_atr * float(self._p("trail_activate"))) / point):
                trail_dist = current_atr * float(self._p("trail_dist_atr"))
                if entry.type == mt5.POSITION_TYPE_BUY:
                    new_sl = round(entry.price_current - trail_dist, digits)
                    if new_sl > entry.price_open and (entry.sl == 0 or new_sl > entry.sl):
                        self.b.modify_sl(entry, new_sl)
                else:
                    new_sl = round(entry.price_current + trail_dist, digits)
                    if new_sl < entry.price_open and (entry.sl == 0 or new_sl < entry.sl):
                        self.b.modify_sl(entry, new_sl)

        # --- WATCHDOG de exposicion desnuda (huerfanos sin cobertura) ---
        # Red final para lo que el ledger no vio nacer (restarts, cierres
        # manuales): un leg huerfano en rojo mas alla de la distancia de hedge
        # se congela igual que una OP1. Orden protectora: sin pre-filtros.
        for orphan in ([] if lock_alive else self.cycle.naked_orphans(core_positions)):
            if orphan.type == mt5.POSITION_TYPE_BUY:
                orphan_loss = (orphan.price_open - orphan.price_current) / point
            else:
                orphan_loss = (orphan.price_current - orphan.price_open) / point
            if orphan_loss >= active_hedge_dist:
                self._open_hedge(orphan)

        # --- ESTADO 0: ENTRY (sin ciclo activo; huerfanos congelados no bloquean) ---
        if cycle_count == 0:
            if self.spread_high or self.vol_breaker or self.close_only or self.news_block:
                return
            if is_friday_mode or is_weekly_start_wait:
                return
            if (self.last_recovery_close_time > 0
                    and self.now - self.last_recovery_close_time < int(self._p("cooldown_seconds"))):
                return

            lots = self._calculate_lots(False)
            if struct_h4 >= 0 and signal_m15 == 1 and self._is_price_good_entry(mt5.ORDER_TYPE_BUY):
                if self.rsi0 < int(self._p("entry_rsi_max")):
                    self._open_entry(mt5.ORDER_TYPE_BUY, lots, "SMC Buy Entry", "OP1 BUY")
            elif struct_h4 <= 0 and signal_m15 == -1 and self._is_price_good_entry(mt5.ORDER_TYPE_SELL):
                if self.rsi0 > int(self._p("entry_rsi_min")):
                    self._open_entry(mt5.ORDER_TYPE_SELL, lots, "SMC Sell Entry", "OP1 SELL")

        # --- ESTADO 2: RECOVERY (ciclo = OP1 + hedge) ---
        elif cycle_count == 2:
            if self.spread_high or self.vol_breaker or self.close_only or self.news_block:
                return
            if self._risk_hour():
                return  # horas de riesgo: sin recovery (el hedge ya esta puesto)
            # Anti-espera v2 (OP3): tiempo minimo Y separacion por ATR del ultimo
            # leg. Antes era solo un timer fijo de 60s; ahora ademas exige que el
            # precio se haya movido >= ATR*spacing, para no apilar recovery en el
            # mismo nivel (clustering) durante ruido.
            last_leg = max(cycle_legs, key=lambda q: q.time)
            if self.now - last_leg.time < int(self._p("min_tech_wait")):
                return
            ref_price = self.b.ask()
            spacing = self._effective_atr() * float(self._p("recovery_min_spacing_atr"))
            if abs(ref_price - last_leg.price_open) < spacing:
                return

            base_lots = self._calculate_lots(False)
            recovery_lots = base_lots * 2.0
            rec_cap = float(self._p("max_recovery_lots"))
            if rec_cap > 0 and recovery_lots > rec_cap:
                recovery_lots = rec_cap

            if self.atr0 > self.atr1:
                # OP3 (Fork A): direccion anclada a ESTRUCTURA H4, no a ruido M5. Si
                # H4 acompana a la cesta se promedia; si H4 volteo en contra, el add
                # cae al lado opuesto (de-risk con la tendencia) en vez de promediar
                # contra el movimiento. Gateado por el tope de supervivencia (_open_additive).
                if struct_h4 > 0:
                    rtype, label = mt5.ORDER_TYPE_BUY, "Recovery Buy (V-Shape)"
                elif struct_h4 < 0:
                    rtype, label = mt5.ORDER_TYPE_SELL, "Recovery Sell (V-Shape)"
                else:
                    rtype = None
                if rtype is not None:
                    self._open_additive(rtype, recovery_lots, label,
                                        ledger.ROLE_RECOVERY, "Recovery")

        # --- ESTADO 3+: SENTINEL + TRAILING OP3 ---
        elif cycle_count >= 3:
            self._check_rescue(cycle_legs)  # RF-D: corre con >=3 legs de ciclo (no solo ==3)

            if self._p("use_op3_trail") and not lock_alive:  # sin trail de Op3 con candado vivo
                # 'Op3' = ultimo leg DEL CICLO (un huerfano o su cobertura,
                # aunque sean mas recientes, no son el leg a trailear).
                op3 = None
                last_t = 0
                for p in cycle_legs:
                    if p.time > last_t:
                        last_t = p.time
                        op3 = p

                if op3 is not None:
                    current_profit = op3.profit + op3.swap
                    if current_profit > 0:
                        if op3.type == mt5.POSITION_TYPE_BUY:
                            pts = (op3.price_current - op3.price_open) / point
                        else:
                            pts = (op3.price_open - op3.price_current) / point

                        start_pts, active_dist = self._op3_trail_params(op3, pts, current_atr, point)

                        if pts > start_pts:
                            if op3.type == mt5.POSITION_TYPE_BUY:
                                new_sl = round(op3.price_current - active_dist * point, digits)
                                if op3.sl == 0 or new_sl > op3.sl:
                                    self.b.modify_sl(op3, new_sl)
                            else:
                                new_sl = round(op3.price_current + active_dist * point, digits)
                                if op3.sl == 0 or new_sl < op3.sl:
                                    self.b.modify_sl(op3, new_sl)
