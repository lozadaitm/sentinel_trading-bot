"""Recorte por parejas del Healer: recovery primero, parejas despues.

Spec: docs/superpowers/specs/2026-10-19-recorte-por-parejas-design.md
Correr:  python -m tests.test_pair_cut
"""

import MetaTrader5 as mt5

from bot import strategy, survival
from tests.test_healer import _cycle as _healer_cycle, _heal
from tests.test_supervivencia import _pos, _rec_alerts, check

BUY, SELL = mt5.POSITION_TYPE_BUY, mt5.POSITION_TYPE_SELL


def _cycle(rec_profit, rec_vol=0.10, cfg=None):
    return _healer_cycle(rec_profit, rec_vol, {"healer_pair_cut": True, **(cfg or {})})


def _net(b):
    return survival.net_lots(b.positions())


def _pc(b):
    return [(x["ticket"], round(x["lots"], 8)) for x in b.partials if x["comment"] == strategy.PAIR_CUT_COMMENT]


def _with_op4(rec_profit=-50.0, op4_profit=-5.0, op4_vol=0.10, cfg=None):
    """Entry SELL -300 + Hedge BUY +10 (par), recovery SELL y Op4 (T) BUY: neto 0."""
    e, b, log, rec, d = _cycle(rec_profit=rec_profit, cfg=cfg)
    op4 = _pos(b, 4, BUY, op4_vol, 4170.0, strategy.OP4_TREND_COMMENT, profit=op4_profit)
    e.cycle.sync(b.positions())
    return e, b, log, rec, op4, d


def test_cover_pair_when_recovery_green():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)   # recovery en verde: sin perdedor amputable
    net0 = _net(b)
    d.win(100.0)                                    # bolsa 90; par entry/hedge = 2900 $/lote
    e._check_healing()
    check(_pc(b) == [(1, 0.03), (2, 0.03)], f"paga 0.03 de la entrada (roja, primero) y 0.03 de la cobertura (got {_pc(b)})")
    check(abs(_net(b) - net0) < 1e-9, "el neto no cambia")
    check(abs(e.healer_budget - (90.0 - 87.0)) < 1e-6, f"la bolsa baja lo realizado (got {e.healer_budget})")
    check(abs(e.cycle_realized + 87.0) < 1e-6, "cycle_realized registra la perdida realizada")
    check(any("Recorte por parejas: 0.03 lotes de #1 + #2" in m for m in _heal(log)), "log HEALER")


def test_recovery_op4_pair():
    e, b, log, rec, op4, d = _with_op4(cfg={"healer_pair_order": "recovery_first"})
    net0 = _net(b)
    d.win(50.0)                                     # bolsa 45; recovery+Op4 = 550 $/lote
    e._check_healing()
    check(_pc(b) == [(3, 0.08), (4, 0.08)],
          f"recovery primero: paga recovery+Op4 aunque la Op1+Op2 pierda mas por lote (got {_pc(b)})")
    check(abs(_net(b) - net0) < 1e-9, "el neto no cambia")


def test_cover_first_default():
    e, b, log, rec, op4, d = _with_op4()
    net0 = _net(b)
    d.win(50.0)                                     # bolsa 45; Op1+Op2 = 2900 $/lote => 0.01
    e._check_healing()
    check(_pc(b) == [(1, 0.01), (2, 0.01)],
          f"por defecto paga primero la Op1+Op2 aunque haya recovery+Op4 valida (got {_pc(b)})")
    check(abs(_net(b) - net0) < 1e-9, "el neto no cambia")


def test_cover_first_falls_back_at_anchor():
    e, b, log, rec, op4, d = _with_op4()
    for p in b._pos[:2]:                            # Op1 y Op2 ya en el lote minimo (ancla)
        p.profit = p.profit / p.volume * 0.01
        p.volume = 0.01
    d.win(50.0)                                     # bolsa 45 => recovery+Op4 a 550 $/lote: 0.08
    e._check_healing()
    check(_pc(b) == [(3, 0.08), (4, 0.08)],
          f"con la Op1+Op2 en el ancla, la bolsa pasa a recovery+Op4 (got {_pc(b)})")
    check({p.ticket: round(p.volume, 8) for p in b.positions()}.get(1) == 0.01, "el ancla queda intacta")


def test_amputation_has_priority():
    e, b, log, rec, d = _cycle(rec_profit=-50.0)   # recovery perdedora real y amputable
    d.win(50.0)
    e._check_healing()
    check(not _pc(b) and b.partials and b.partials[0]["comment"] == "Healer Amputacion",
          f"con recovery amputable manda la amputacion (got {b.partials})")
    e, b, log, rec, d = _cycle(rec_profit=-50.0, rec_vol=0.01)
    d.win(10.0)                                     # 9 $ < 50 $ del lote minimo de recovery
    e._check_healing()
    check(not b.partials and abs(e.healer_budget - 9.0) < 1e-9,
          "la bolsa espera a la recovery; no se gasta en la pareja Op1+Op2")


def test_never_mixes_types():
    e, b, log, rec, op4, d = _with_op4(rec_profit=+30.0, op4_profit=-30.0)   # rec+Op4 sin perdida real
    d.win(100.0)
    e._check_healing()
    check(_pc(b) == [(1, 0.03), (2, 0.03)],
          f"paga la pareja de cobertura; recovery y Op4 intactas: nunca Op1 con Op4 (got {_pc(b)})")


def test_cover_pair_keeps_anchor():
    # recovery + Op4 casi empatadas (pareja sin perdida real): la bolsa va a Op1+Op2,
    # pero con recovery/Op4 vivas nunca las cierra del todo (no deja un ciclo sin ENTRY).
    e, b, log, rec, op4, d = _with_op4(rec_profit=+30.0, op4_profit=-30.0)
    d.win(5000.0)
    e._check_healing()
    alive = {p.ticket: round(p.volume, 8) for p in b.positions()}
    check(alive == {1: 0.01, 2: 0.01, 3: 0.10, 4: 0.10},
          f"Op1+Op2 recortadas hasta el lote minimo; recovery y Op4 intactas (got {alive})")
    e.now += 61
    e._check_healing()
    check({p.ticket: round(p.volume, 8) for p in b.positions()} == alive, "no baja del minimo en ticks siguientes")


def test_cover_pair_closes_when_alone():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)
    b._pos.remove(rec)                              # sin recovery: el ciclo es solo Op1 + Op2
    e.cycle.sync(b.positions())
    e.cfg["healer_min_core"] = 2
    d.win(5000.0)
    e._check_healing()
    check(not b.positions(), f"sin otras patas, la pareja se paga entera (got {[(p.ticket, p.volume) for p in b.positions()]})")


def test_budget_waits_below_min_lot():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)
    d.win(20.0)                                     # 18 $ < 29 $ de 0.01 de pareja
    e._check_healing()
    check(not b.partials and abs(e.healer_budget - 18.0) < 1e-9, "no cierra y la bolsa NO se libera")
    d.win(20.0)                                     # 36 $ => 0.01
    e._check_healing()
    check(_pc(b) == [(1, 0.01), (2, 0.01)], f"al llegar, paga 0.01 (got {_pc(b)})")


def test_pair_without_real_loss_released():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)
    b._pos[0].profit = -5.0                         # par entry/hedge: (5-10)/0.1 => ganancia neta
    d.win(100.0)
    e._check_healing()
    check(not b.partials and e.healer_budget == 0.0, "sin pareja con perdida real: la bolsa se libera como hoy")


def test_lock_legs_excluded():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)
    _pos(b, 5, SELL, 0.10, 4100.0, "Basket Lock", profit=-400.0)
    _pos(b, 6, BUY, 0.10, 4100.0, "Recovery Buy (V-Shape)", profit=-400.0)
    e.cycle.sync(b.positions())
    d.win(5000.0)
    e._check_healing()
    check(5 not in {t for t, _ in _pc(b)}, f"la pata LOCK nunca entra en una pareja (got {_pc(b)})")


def test_first_close_rejected():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)
    orig = b.close_partial
    b.close_partial = lambda p, lots, comment="Partial": type("R", (), {"retcode": 10006})()
    d.win(100.0)
    e._check_healing()
    check(not b.partials and abs(_net(b) - (-0.10)) < 1e-9, "primer cierre rechazado: nada cerrado, neto intacto")
    check(e.cycle.get_meta("pair_cut_pending") is None, "sin deuda")
    b.close_partial = orig
    e._check_healing()
    check(not _pc(b), "backoff: el mismo instante no reintenta")
    e.now += 61
    e._check_healing()
    check(_pc(b) == [(1, 0.03), (2, 0.03)], f"tras el backoff paga la pareja (got {_pc(b)})")


def test_second_close_rejected_debt():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)
    sent = _rec_alerts(e, log)
    orig = b.close_partial
    st = {"fail": True}

    def failing(p, lots, comment="Partial"):
        if p.ticket == 2 and st["fail"]:
            return type("R", (), {"retcode": 10006})()
        return orig(p, lots, comment)
    b.close_partial = failing
    net0 = _net(b)
    d.win(100.0)
    e._check_healing()
    pend = e.cycle.get_meta("pair_cut_pending")
    check(_pc(b) == [(1, 0.03)] and pend and pend["tickets"] == [2] and abs(pend["lots"] - 0.03) < 1e-9,
          f"deuda pendiente 0.03 de #2 (got {_pc(b)}, {pend})")
    check(len(sent) == 1 and "CRITICA" in sent[0], "alerta CRITICA")
    d.win(100.0)
    e.now += 61
    e._check_healing()
    check(_pc(b) == [(1, 0.03)], "con deuda: ni otra pareja ni amputacion, solo reintento")
    st["fail"] = False
    e.now += 61
    e._check_healing()
    check(_pc(b) == [(1, 0.03), (2, 0.03)] and e.cycle.get_meta("pair_cut_pending") is None,
          f"deuda cerrada (got {_pc(b)})")
    check(abs(_net(b) - net0) < 1e-9, "neto de vuelta al previo")


def test_vol_breaker_blocks():
    e, b, log, rec, d = _cycle(rec_profit=+20.0)
    e.vol_breaker = True
    d.win(100.0)
    e._check_healing()
    check(not b.partials and abs(e.healer_budget - 90.0) < 1e-9, "VCB activo: no recorta y la bolsa espera")


def test_switch_off():
    e, b, log, rec, d = _cycle(rec_profit=+20.0, cfg={"healer_pair_cut": False})
    d.win(100.0)
    e._check_healing()
    check(not b.partials and e.healer_budget == 0.0, "healer_pair_cut=false: comportamiento de hoy (bolsa liberada)")


def main():
    for t in (test_cover_pair_when_recovery_green, test_recovery_op4_pair, test_cover_first_default,
              test_cover_first_falls_back_at_anchor, test_amputation_has_priority,
              test_never_mixes_types, test_cover_pair_keeps_anchor, test_cover_pair_closes_when_alone,
              test_budget_waits_below_min_lot, test_pair_without_real_loss_released,
              test_lock_legs_excluded, test_first_close_rejected, test_second_close_rejected_debt,
              test_vol_breaker_blocks, test_switch_off):
        print(t.__name__)
        t()
    print("\ntest_pair_cut: TODO OK")


if __name__ == "__main__":
    main()
