"""Auditoria de la cuenta para el motor e2 (tres patas). READ-ONLY, no envia ordenes.

Lo que responde antes de arrancar un e2 (start_all.ps1, fase 3):
  - Se llega al terminal MT5 de la instancia (si no, sale con error).
  - La cuenta es HEDGING: los tercios y el candado (orden opuesta) deben convivir.
    Si no, imprime "REQUIERE cuenta hedging" y start_all aborta.
  - Posiciones vivas del magic e2 (por comentario).
  - Margen de una escalera completa de la Big One a peso 1 con los DEFAULTS del
    motor (riesgo 8 %, ATR_D de los 14 dias previos), y del peor caso de dos
    escaleras a la vez (Momentum + NFP), contra el equity de HOY.

Uso:  scripts\\run_instance.ps1 instances\\<usuario>.env -BotId e2 -Module scripts.audit_e2
  o:  python -m scripts.audit_e2      (usa el terminal MT5 por defecto)
"""

import os
import sys

import MetaTrader5 as mt5

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import config, sessions  # noqa: E402
from bot.strategy_e2 import DEFAULTS  # noqa: E402


def main():
    if not mt5.initialize(**config.mt5_init_kwargs()):
        raise SystemExit(f"No se pudo inicializar MT5: {mt5.last_error()}")
    try:
        if not mt5.symbol_select(config.SYMBOL, True):
            print(f"[ALERTA] no se pudo seleccionar {config.SYMBOL}")
        acc = mt5.account_info()
        sym = mt5.symbol_info(config.SYMBOL)
        tick = mt5.symbol_info_tick(config.SYMBOL)
        if acc is None or sym is None or tick is None:
            raise SystemExit("MT5 no devolvio account_info / symbol_info / tick.")

        hedging = acc.margin_mode == mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
        print("=" * 70)
        print(f"CUENTA e2  ({acc.company} / {acc.server})")
        print("=" * 70)
        print(f"  balance / equity  : {acc.balance:.2f} / {acc.equity:.2f} {acc.currency}")
        print(f"  margen libre      : {acc.margin_free:.2f}")
        print(f"  apalancamiento    : 1:{acc.leverage}")
        print(f"  stop out          : {acc.margin_so_so:.1f} %")
        print(f"  modo de cuenta    : {'HEDGING' if hedging else 'NETTING/EXCHANGE'}")
        if not hedging:
            print("  *** AVISO: el e2 REQUIERE cuenta hedging (tercios + candado opuesto). ***")
        print(f"  bid / ask         : {tick.bid:.{sym.digits}f} / {tick.ask:.{sym.digits}f}")
        print(f"  volumen min/step  : {sym.volume_min} / {sym.volume_step}")

        pos = [p for p in (mt5.positions_get(symbol=config.SYMBOL) or [])
               if p.magic == config.MAGIC_E2]
        print(f"\n  posiciones del magic {config.MAGIC_E2}: {len(pos)}")
        for p in pos:
            print(f"     #{p.ticket} '{p.comment}' {p.volume:.2f} P&L {p.profit + p.swap:+.2f}")

        d1 = mt5.copy_rates_from_pos(config.SYMBOL, mt5.TIMEFRAME_D1, 0, 120)
        if d1 is None or len(d1) < 15:
            print("\n  ATR_D: sin velas D1 suficientes; no se estima el margen.")
            return 0
        today = int(tick.time) // 86400
        prev = [r for r in d1 if int(r["time"]) // 86400 < today]
        atr_d = sessions.atr_daily([r["high"] for r in prev], [r["low"] for r in prev])
        lots = sessions.ladder_lots(acc.balance, float(DEFAULTS["e2_risk_pct"]), 1.0, atr_d,
                                    sym.volume_step or 0.01, sym.volume_min, sym.volume_max)
        total = round(sum(lots), 2)
        m1 = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, config.SYMBOL, total, tick.ask) if total else 0
        m1 = float(m1 or 0.0)
        worst = 2 * m1
        pct = worst / acc.equity * 100.0 if acc.equity else 0.0
        veredicto = "CABE" if worst < acc.equity * 0.6 else ("JUSTO" if worst < acc.equity else "NO CABE")
        print(f"\n  ATR_D (14 dias)   : {atr_d:.2f}")
        print(f"  escalera completa : {total:.2f} lotes ({'/'.join(f'{x:.2f}' for x in lots)}) "
              f"-> margen {m1:.2f}")
        print(f"  dos escaleras     : margen {worst:.2f} ({pct:.1f}% del equity)")
        print(f"  VEREDICTO: {veredicto}")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
