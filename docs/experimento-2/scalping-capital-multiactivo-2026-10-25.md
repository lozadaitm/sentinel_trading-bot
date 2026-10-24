# Último intento de operaciones cortas, capital por cuenta y otros símbolos (25-oct)

## 1. Operaciones cortas alineadas con las ventajas (`gold_bias_scalp.py`)

Scalping solo dentro de las ventanas con ventaja probada:
- Asia (01:15–09:45) con tendencia alcista, comprando.
- EE. UU. (15:00–20:45) en la dirección de Asia.

Disparadores: cada vela / retroceso / ruptura / control en contra. Mantener 3, 6 o 12 velas, en M15 (2022–26, por año), M5 (2025–26) y M1 (ticks 2026). Costo 0,17 $/oz.

- **Control en contra del sesgo:** pierde en todos los años y escalas. Confirma que el sesgo es real.
- **EE. UU., retroceso, 12 velas M15 (3 h):** +0,01 / +0,43 / +1,33 / +1,36 / +4,15 $/oz por año (5/5). En M5 a 1 h: A +0,45, B +1,38.
- **Asia:** más débil (2–4 de 5 años). En M1 nada sobrevive en la segunda mitad.
- **En dólares por día no es una ventaja nueva:** entrar en retrocesos (~1,5 operaciones de 3 h por día) da 2,81 $/oz/día, frente a 2,63 de la entrada fija a las 15:00. Correlación 0,67. Queda como **variante de entrada** del momentum EE. UU.

## 2. Capital mínimo, ideal y máximo (`capital_analysis.py`)

Cartera Big One + momentum EE. UU. + NFP con escalera, 2022-10 → 2026-10.

**Eficiencia** = resultado con lotes reales (cada tercio redondeado a 0,01, mínimo 0,01) dividido por el resultado con lotes continuos.

| Capital | Eficiencia al 5 % | Riesgo máx. real (plan 5 %) | Eficiencia al 8 % | Lote mediano por operación (inicio) |
|---|---|---|---|---|
| 1 000 | 75 % | 10,9 % | 57 % | 0,03 (forzado) |
| 2 000 | 64 % | 6 % | 68 % | 0,03–0,06 |
| 3 000 | 72 % | 5 % | 81 % | 0,05–0,09 |
| 5 000 | 82 % | 5 % | 88 % | 0,09–0,15 |
| 10 000 | 91 % | 5 % | 93 % | 0,18–0,33 |
| 25 000 | 96 % | 5 % | 98 % | 0,5–0,8 |
| 50 000+ | ≥ 98 % | 5 % | ≥ 99 % | ≥ 1 |

**Lecturas:**
- **Mínimo: 3 000.** La escalera necesita 3 × 0,01 lote. Por debajo, el lote mínimo fuerza más riesgo del planeado (hasta 11 % con 1 000).
- **Ideal: 10 000–25 000.** Más del 90 % de eficiencia, con el riesgo exactamente el planeado.
- **Máximo práctico:** al 8 % de riesgo, cada 100 000 $ de equity son ~1 lote por operación.
  - El broker admite hasta 100 lotes por orden y el margen a 1:500 no limita.
  - El límite real es la **liquidez de la reapertura de la 01:00**: hasta ~20–50 lotes por entrada, es decir unos 2–5 M$ de equity, no debería haber gran deslizamiento. Hay que verificarlo en vivo.
  - Pasado ese tamaño, conviene repartir la entrada en varios minutos o retirar ganancias.

## 3. Otros símbolos (`multi_bank.py`, M15 del broker, 37 símbolos)

**Datos:** cripto desde 2023-12; el resto, ~4 años.

**Símbolos:**
- Cripto: BTC, ETH.
- 9 pares de divisas.
- Plata y platino.
- Petróleo (WTI, Brent, CL) y gas natural.
- Cobre.
- Índices: S&P, Nasdaq, Dow, DAX, FTSE, CAC, Euro Stoxx, Nikkei, Hang Seng, China A50, ASX, Russell.
- USDX y VIX.
- Agrícolas: café, cacao, azúcar, trigo, soja.

**Pruebas:**
- mapa horario (hora × duración × lado × tendencia, BH en la primera mitad y confirmación en la segunda);
- momentum intradía al estilo de «Asia → EE. UU.».

**Costos:** spread real por hora más comisión RAW. Sin entradas cerca del rollover.

**Resultado:**
- **Ningún símbolo pasa el filtro estricto.** El oro tampoco lo pasa en este mismo banco: es la calibración.
- **Con la vara del oro** (regla fijada de antemano, positiva todos los años) solo hay dos candidatos débiles:

| Regla (momentum intradía, \|retorno desde las 02:00\| > 0,5 desv.) | 2022 | 2023 | 2024 | 2025 | 2026 | t |
|---|---|---|---|---|---|---|
| Nasdaq 13:00 → 18:00 (tendencia ≠ 0) | +0,23 % | +0,01 | +0,05 | +0,07 | +0,01 | 1,38 |
| USDJPY 10:00 → 15:00 | +0,06 % | +0,02 | +0,03 | +0,01 | +0,01 | 1,52 |
| Oro, misma regla 13:00 (referencia) | +0,03 % | +0,04 | +0,08 | +0,02 | +0,23 | 2,38 |

- **BTC, ETH, petróleo, gas, índices europeos y asiáticos, agrícolas y resto de divisas:** nada.
- **Recomendación:** no crear bots para otros símbolos todavía. Nasdaq y USDJPY no alcanzan la certeza pedida («muy certeros, como el oro»). Se pueden seguir en observación con datos que se acumulen.
