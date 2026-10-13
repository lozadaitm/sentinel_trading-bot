---
name: ideas-experimento-2
description: Backlog de ideas externas (videos, repos, APIs, carrusel) recogidas el 2026-10-13 para evaluar en el brainstorming de experimento-2; ninguna está verificada
metadata:
  type: project
---

Ideas que el usuario trajo el 2026-10-13 para potenciar el bot. **Ninguna está
validada**: el objetivo del brainstorming es investigar viabilidad, no implementarlas.

**A. Auditoría de las 3 cuentas (2 meses, ago-oct 2026).** Exportar historial de deals
de cada instancia MT5 (3 clones: 25924397, 25912766, 34087418; más la base) y comparar:
cantidad de operaciones por ciclo, puntos de entrada/salida, lotaje vs equity
(`equity_weight`, `lot_per_1k` o equivalente). Hipótesis: misma lógica, comportamiento
distinto. Cruzar con `bot_logs` en Supabase ([[logging-taxonomy-and-ticket]]).

**B. Modelo de predicción open source tipo "Bloomberg".** Candidato citado en un
comentario: https://github.com/shiyu-coder/Kronos (foundation model para velas K-line).
Evaluar: licencia, tamaño, inferencia en CPU del VPS, si predice XAUUSD M15 mejor que
azar, y cómo se integraría (filtro de dirección para OP1, veto de ruptura, etc.).
Buscar alternativas si Kronos no aplica.

**C. Alpha decay.** El riesgo nº1 del trading algorítmico: el edge se erosiona. Dos
métricas propuestas como monitor de salud de la estrategia: (1) racha de ciclos que
llegan a OP4/rescate (análogo a racha de pérdidas consecutivas), (2) Sharpe ratio
rodante. Idea: un "kill-switch suave" o reducción de riesgo cuando ambas se degradan.
Ojo: el usuario no quiere emergency-stops duros ([[bot-design-constraints]]).

**D. Sesiones.** Asia consolida (rango, 20-30 pips), Londres rompe estructura y define
tendencia (40-100 pips), Nueva York confirma o revierte con máxima liquidez (100-350
pips). Verificar con los datos propios de XAUUSD M5/M15 antes de parametrizar nada por
sesión (el bot ya tiene régimen de rango en M5, ver [[m5-range-regime-v2]]).

**E. APILayer** (https://apilayer.com, ~1400 APIs). Revisar si alguna sirve: calendario
económico, sentimiento, precios alternativos. Hoy el calendario viene de Forex Factory
([[news-exporter-python]]).

**F. MiroFish.** "Motor de predicción" que se podría usar como agentes del arnés de IA
que falta construir. Investigar qué es realmente (repo, paper, licencia).

**G. Estrategia AMD** (Acumulación, Manipulación, Distribución; conceptos ICT/Smart
Money, Power of 3). Citada como "nº1 del top 10". Evaluar si encaja con el grid de
ciclos o si solo sirve como filtro de entrada de OP1.

**H. Carrusel "Construí un trader IA 24/7"** (@giraldofinanzas, 7 de 8 slides; fotos en
Downloads del VPS, 2026-10-13). Es marketing, sin código, pero el esqueleto sirve como
referencia para el **arnés de agentes de IA**:
1. Escáner de mercado 24/7: acción del precio, volumen, tendencia, noticias, watchlist →
   setups detectados.
2. Motor de señales: ruptura, pullback, momentum, continuación, reversión; escanea,
   detecta, puntúa (ranking por probabilidad).
3. Planificador de trades: zona de entrada, objetivo, stop, invalidación, R:B,
   dirección, temporalidad, confianza.
4. Módulo de riesgo con 5 checks bloqueantes: tamaño de posición, límite de exposición,
   drawdown, volatilidad, pérdida máxima → pasa/bloquea.
5. Loop de monitoreo: watchlist, alertas, estado, revisión activa.
6. Memo de decisión final con ID y fecha: resumen del setup, fuerza de señal, nivel de
   riesgo, plan, estado → revisión humana: aprobado / watchlist / rechazado.
Lo aprovechable: la separación escáner → señal → plan → riesgo → memo, y el memo
auditable con aprobación humana. Lo que no aplica: stops duros y R:B fijo chocan con
el diseño de ciclos/hedge del bot.

**Estado al 2026-10-13 (sesión de brainstorming):**
- A → hecho: `docs/experimento-2/audit/informe-3-cuentas.md`. 2 cuentas quemadas por patas
  de recovery/rescate sin cobertura, churn OP4↔Unwind y umbrales en $ fijos que desincronizan
  cuentas de distinto tamaño. Vantage eliminó 25912766 y 25556247.
- B Kronos → investigar más (solo un test offline; evidencia débil en oro y bug de cuelgue en Windows).
- C Alpha decay → se diseña junto a los arreglos (los bots estuvieron 50 días "RUNNING" sobre cuentas quemadas).
- D Sesiones → descartada la parametrización tipo video; útil el perfil horario (01 UTC y 13–15 UTC más violentas).
  `docs/experimento-2/analisis/informe-sesiones-amd.md`.
- E APILayer → descartada. F MiroFish → descartada como señal.
- G AMD → descartada como reversión (MFE/MAE < 1); "continuación" sin significancia, prioridad baja.
- H Arnés de agentes → pospuesto hasta estabilizar el bot.

**Cómo aplicar:** en experimento-2, invocar `brainstorming` (plugin Superpowers) con
este backlog como insumo; cada idea termina en "descartada", "investigar más" o
"diseño aprobado" antes de tocar código. Ver [[pendientes-pre-experimento-2]].
