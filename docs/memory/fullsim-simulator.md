---
name: fullsim-simulator
description: Simulador de ciclo completo con el motor real versionado en bot_backtesting/fullsim (lab, signals, meta_label); datos en data/ fuera de git; medir variantes antes de proponerlas
metadata:
  type: reference
---

**Dónde:** `bot_backtesting/fullsim/`. El `README.md` de esa carpeta tiene el uso y los límites.
- `lab.py`: variantes del bot sobre el ciclo completo o en ventanas de 30 días (`--ms`). Con `--set` cambia cualquier parámetro de DEFAULTS.
- `signals.py`: señales de la Op1 y si acabaron en ganancia o en cobertura.
- `meta_label.py`: filtro de machine learning.

**Datos:** en `data/`, que no se versiona.
- `frames.pkl`: velas del broker de 2026.
- `frames_duka.pkl`: Dukascopy, 2021-2026.

Si faltan, se regeneran con `fetch_dukascopy.py` (sin MT5) o con `fetch_broker.py`, este último **solo con el mercado cerrado** (ver [[mt5-history-download-blocks-bots]]).

**Why:** hasta el 20-oct vivía en el scratchpad de la sesión y se perdía al cerrarla. Toda la evidencia del experimento 2 (Op4, recorte por parejas, filtro ML) sale de aquí.

**How to apply:**
- Medir cualquier idea nueva con `lab.py actual --ms` frente al bot de hoy antes de proponerla.
- Las corridas largas, con prioridad Idle para no frenar los bots en vivo.

Relacionado: [[healer-pair-cut]], [[op4-trend]].
