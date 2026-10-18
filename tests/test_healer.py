"""Healer: solo perdedores reales y bolsa solo mientras exista uno.

Spec: docs/superpowers/specs/2026-10-16-healer-patas-frescas-design.md
Correr:  python -m tests.test_healer
"""

from types import SimpleNamespace

import MetaTrader5 as mt5

from tests.test_supervivencia import _eng, _pos, check

BUY, SELL = mt5.POSITION_TYPE_BUY, mt5.POSITION_TYPE_SELL
M15 = 100200   # magic de _eng (SurvBroker)


class _Deals:
    """history_deals controlable: cada win() agrega un deal OUT ganador del magic."""
    def __init__(self, b):
        self.items, self.next = [], 9000
        b.history_deals = lambda a, z: list(self.items)

    def win(self, profit):
        self.next += 1
        self.items.append(SimpleNamespace(ticket=self.next, magic=M15,
                                          entry=mt5.DEAL_ENTRY_OUT, profit=profit))


def _cycle(rec_profit, rec_vol=0.10, cfg=None):
    """Ciclo real del 14-oct: SELL entry + Hedge BUY (par congelado) + recovery SELL."""
    c = {"equity_weight": 1.0}
    c.update(cfg or {})
    e, b, log = _eng(equity=10000.0, cfg=c)
    e.now = 1_790_000_000
    _pos(b, 1, SELL, 0.10, 4147.0, "SMC Sell Entry", profit=-300.0)
    _pos(b, 2, BUY, 0.10, 4161.0, "Hedge Lock", profit=+10.0)
    rec = _pos(b, 3, SELL, rec_vol, 4090.0, "Recovery Sell (V-Shape)", profit=rec_profit)
    e.cycle.sync(b.positions())
    e._healer_needs_rebaseline = False
    return e, b, log, rec, _Deals(b)


def _heal(log):
    return [m for t, m in log.events if t == "HEALER"]


def test_fresh_recovery_not_amputated():
    e, b, log, rec, d = _cycle(rec_profit=-3.0)        # 0.3 $/oz: spread
    d.win(57.0)
    e._check_healing()
    check(rec.volume == 0.10 and not b.partials, "recovery recien abierta: no se amputa")
    check(e.healer_budget == 0.0, "bolsa en 0")
    check(any("ganancia 57.00 $ sin perdedor real" in m for m in _heal(log)), "log de ganancia libre")


def test_real_loser_amputated():
    e, b, log, rec, d = _cycle(rec_profit=-50.0)       # 5 $/oz => 500 $/lote
    d.win(50.0)
    e._check_healing()                                   # bolsa 45 => floor(45 / 500 $/lote) = 0.09 lotes
    check(b.partials and abs(b.partials[0]["lots"] - 0.09) < 1e-9, f"amputa 0.09 (got {b.partials})")
    spent = 50.0 * 0.09 / 0.10
    check(abs(e.healer_budget - (45.0 - spent)) < 1e-6, f"bolsa baja lo realizado (got {e.healer_budget})")
    check(any("Bolsa restante" in m for m in _heal(log)), "log con bolsa restante")
    check(abs(e.cycle_realized + spent) < 1e-6, "cycle_realized registra la perdida")


def test_little_by_little():
    e, b, log, rec, d = _cycle(rec_profit=-500.0, rec_vol=1.0)   # 5 $/oz, 500 $/lote
    vols = []
    for _ in range(3):
        d.win(20.0)                                      # 18 $ => 0.03 lotes
        e._check_healing()
        vols.append(rec.volume)
        rec.profit = -500.0 * rec.volume                 # mismo precio: P&L escala con el volumen
    check(vols[0] > vols[1] > vols[2], f"cada ganancia recorta un trozo ({vols})")


def test_budget_released():
    e, b, log, rec, d = _cycle(rec_profit=-50.0, rec_vol=0.01)   # 0.01 lote = 50 $ > bolsa
    d.win(10.0)
    e._check_healing()
    check(not b.partials and abs(e.healer_budget - 9.0) < 1e-9, "no cabe el lote minimo: la bolsa espera")
    rec.profit = -1.0                                    # se recupera a 1 $/oz
    e._check_healing()
    check(e.healer_budget == 0.0, "sin perdedor real: bolsa liberada")
    check(any("bolsa 9.00 $ liberada" in m for m in _heal(log)), "log de liberacion")


def test_gain_before_loser_not_used():
    e, b, log, rec, d = _cycle(rec_profit=-3.0)
    d.win(200.0)
    e._check_healing()
    rec.profit = -50.0                                   # ahora si es perdedor real
    e._check_healing()                                   # sin ganadores nuevos
    check(not b.partials and e.healer_budget == 0.0, "la ganancia previa al perdedor no cura")


def test_ninety_percent():
    e, b, log, rec, d = _cycle(rec_profit=-5000.0)       # 500 $/oz: 0.01 = 500 $ > 90
    d.win(100.0)
    e._check_healing()
    check(abs(e.healer_budget - 90.0) < 1e-9, f"ganador 100 => bolsa 90 (got {e.healer_budget})")


def test_cycle_close_resets():
    e, b, log, rec, d = _cycle(rec_profit=-5000.0)
    d.win(100.0)
    e._check_healing()
    e._close_all("test")
    check(e.healer_budget == 0.0, "cierre de ciclo: bolsa en 0")


def test_switch_off():
    e, b, log, rec, d = _cycle(rec_profit=-3.0, cfg={"healer_min_move_usd": 0})
    d.win(57.0)
    e._check_healing()
    check(b.partials, "umbral 0: la recovery roja por spread vuelve a amputarse (comportamiento viejo)")


def test_protections_intact():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)         # recovery en verde; entry -300 en par
    d.win(500.0)
    e._check_healing()
    check(not b.partials and e.healer_budget == 0.0,
          "la entrada roja del par congelado no es perdedor real ni abre la bolsa")
    e, b, log, rec, d = _cycle(rec_profit=+20.0)
    lock = _pos(b, 4, BUY, 0.10, 4170.0, "Basket Lock", profit=-200.0)
    e.cycle.sync(b.positions())
    d.win(500.0)
    e._check_healing()
    check(lock.volume == 0.10 and not b.partials, "pata LOCK intocable")


def test_window_not_lagged():
    import datetime
    e, b, log, rec, d = _cycle(rec_profit=-50.0)
    end = e._deal_window_end()
    check(end >= e._server_dt() + datetime.timedelta(hours=12),
          f"la ventana llega >= 12 h por delante de la hora de servidor (got {end})")
    calls = []
    b.history_deals = lambda a, z: (calls.append((a, z)), list(d.items))[1]
    d.win(50.0)
    e._check_healing()
    check(calls and calls[0][1] >= e._server_dt() + datetime.timedelta(hours=12),
          f"el Healer usa esa misma ventana (got {calls})")


def test_op4_open_budget_waits():
    from bot import strategy
    e, b, log, rec, d = _cycle(rec_profit=-50.0)        # 5 $/oz, 500 $/lote
    op4 = _pos(b, 4, BUY, 0.10, 4170.0, strategy.OP4_TREND_COMMENT, profit=-5.0)
    e.cycle.sync(b.positions())
    d.win(50.0)
    e._check_healing()
    check(not b.partials and abs(e.healer_budget - 45.0) < 1e-9,
          f"Op4 (T) viva: la bolsa espera, no se libera (got {e.healer_budget})")
    check(any("en espera" in m for m in _heal(log)), "log de bolsa en espera")
    b._pos.remove(op4)                                   # cierra la Op4 (T)
    e._check_healing()
    check(b.partials and abs(b.partials[0]["lots"] - 0.09) < 1e-9,
          f"al cerrar la Op4, la bolsa acumulada recorta la recovery (got {b.partials})")


def test_state_survives_restart():
    from bot import ledger
    from bot.strategy import SentinelEngine
    e, b, log, rec, d = _cycle(rec_profit=-5000.0)       # 0.01 = 500 $ > bolsa
    d.win(100.0)
    e._check_healing()
    check(e.cycle.get_meta("healer_cursor") == 9001 and abs(e.cycle.get_meta("healer_budget") - 90.0) < 1e-9,
          f"cursor y bolsa persistidos en el meta (got {e.cycle.meta})")
    e2 = SentinelEngine(b, log)                           # "reinicio": mismo broker y archivo de ledger
    e2.cycle = ledger.CycleLedger(e.cycle.path, log)
    e2.cfg = e.cfg
    e2.now = e.now
    d.win(200.0)                                          # ganador ya existente al arrancar
    e2.init_history_cursor()
    check(e2.last_healed_ticket == 9001 and abs(e2.healer_budget - 90.0) < 1e-9
          and not e2._healer_needs_rebaseline, "el arranque restaura cursor y bolsa del ciclo abierto")
    e2._check_healing()
    check(abs(e2.healer_budget - 270.0) < 1e-9, f"el ganador previo al arranque si cuenta (got {e2.healer_budget})")


def test_restart_without_positions_ignores_meta():
    from bot import ledger
    from bot.strategy import SentinelEngine
    e, b, log, rec, d = _cycle(rec_profit=-5000.0)
    d.win(100.0)
    e._check_healing()
    b._pos.clear()
    e2 = SentinelEngine(b, log)
    e2.cycle = ledger.CycleLedger(e.cycle.path, log)
    e2.cfg, e2.now = e.cfg, e.now
    e2.init_history_cursor()
    check(e2._healer_needs_rebaseline and e2.healer_budget == 0.0, "sin posiciones: meta viejo ignorado")


def test_cycle_close_clears_persisted():
    e, b, log, rec, d = _cycle(rec_profit=-5000.0)
    d.win(100.0)
    e._check_healing()
    e._close_all("test")
    check(e.cycle.get_meta("healer_cursor") is None and e.cycle.get_meta("healer_budget") is None,
          "cierre de ciclo: estado persistido borrado")


def main():
    for t in (test_fresh_recovery_not_amputated, test_real_loser_amputated, test_little_by_little,
              test_budget_released, test_gain_before_loser_not_used, test_ninety_percent,
              test_cycle_close_resets, test_switch_off, test_protections_intact, test_window_not_lagged,
              test_op4_open_budget_waits, test_state_survives_restart,
              test_restart_without_positions_ignores_meta, test_cycle_close_clears_persisted):
        print(t.__name__)
        t()
    print("\ntest_healer: TODO OK")


if __name__ == "__main__":
    main()
