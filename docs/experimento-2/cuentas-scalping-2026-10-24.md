# Cuentas mes a mes, patas nuevas y banco de scalping (24-oct, noche)

Todo con **precios reales del broker** (M15 desde 2022-08; M5 desde 2025-05; ticks desde 2026-01).

## Lección de método: salida fijada de antemano

Al corregir un error del simulador cambiaron los resultados. Con pandas 3 las salidas «por hora» y «por objetivo» quedaban sin nombre, así que la validación móvil solo elegía entre trailings. Con más salidas disponibles, el momentum EE. UU. y la FOMC se volvieron inestables. **Elegir entre ~30 salidas sobreajusta.**

Desde aquí, todas las patas usan **una salida fija decidida antes de mirar**: salida por hora + candado a 1 ATR diario.

| Pata (salida fija) | R por operación | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| Big One, días alcistas | +0,041 | +0,04 | +0,01 | +0,03 | +0,05 | +0,10 |
| Big One, días neutros (peso 0,5) | +0,02 | +0,15 | +0,03 | +0,02 | +0,05 | −0,01 |
| Momentum EE. UU. (umbral 0,5; tendencia +2) | +0,047 | +0,15 | +0,05 | +0,09 | +0,01 | +0,01 |
| Momentum EE. UU., tendencia −2 | +0,05 | — | +0,03 | +0,20 | +0,11 | +0,05 |
| NFP, seguir el salto 24 h | +0,28 | +0,14 | +0,51 | +0,09 | +0,36 | +0,20 |
| FOMC | −0,04 (1/5 años) | | | | | ← descartada |
| IPC | mezclado (2/5) | | | | | ← descartado |

## Cuentas mes a mes: Big One (todos los días) + momentum EE. UU. (+2/−2) + NFP

`broker_accounts.py`:
- lote redondeado a 0,01 con mínimo 0,01;
- operaciones superpuestas;
- margen de 800 $/lote (1:500).

**Últimos 12 meses** (cuenta nueva el 2025-11-01, hasta el 2026-10-16):

| Cuenta | Tamaño | Final | × | Caída máx. | Riesgo medio real |
|---|---|---|---|---|---|
| 1 000 | cualquiera (manda el lote mínimo) | 2 591 | 2,6 | 24 % | **6 % (hasta 16 %)** |
| 5 000 | 3 % fijo | 6 755 | 1,35 | 8 % | 2,1 % |
| 5 000 | 5 % fijo | 8 934 | 1,79 | 13 % | 3,3 % |
| 5 000 | 8 % fijo | 11 518 | 2,30 | 24 % | 5,8 % |
| 5 000 | piso G-Z 50 %, 10 % | 11 088 | 2,22 | 28 % | 6,3 % |
| 10 000 | 3 % / 5 % / 8 % | 14 055 / 17 832 / 24 090 | 1,41 / 1,78 / 2,41 | 8 / 15 / 25 % | |

**Equity a fin de mes, 5 % fijo:**

| Mes | 1 000 | 5 000 | 10 000 | % (5 000) | Operaciones |
|---|---|---|---|---|---|
| 2025-11 | 1 187 | 5 331 | 10 649 | +6,6 | 29 |
| 2025-12 | 1 232 | 5 394 | 10 881 | +1,2 | 40 |
| 2026-01 | 1 829 | 7 045 | 14 359 | +30,6 | 42 |
| 2026-02 | 2 248 | 7 543 | 15 150 | +7,1 | 38 |
| 2026-03 | 2 306 | 7 658 | 15 549 | +1,5 | 31 |
| 2026-04 | 2 353 | 7 801 | 15 688 | +1,9 | 23 |
| 2026-05 | 2 003 | 7 084 | 13 966 | −9,2 | 42 |
| 2026-06 | 1 995 | 7 364 | 14 314 | +3,9 | 38 |
| 2026-07 | 2 288 | 8 252 | 16 343 | +12,1 | 38 |
| 2026-08 | 2 485 | 8 733 | 17 496 | +5,8 | 29 |
| 2026-09 | 2 565 | 9 068 | 18 013 | +3,8 | 27 |
| 2026-10 (16 días) | 2 591 | 8 934 | 17 832 | −1,5 | 15 |

**Desde 2022-10 (49 meses):**

| Tamaño | Resultado (×) | Equivalente mensual | Caída máx. | Peor mes |
|---|---|---|---|---|
| 3 % | ×6,2 | ~3,8 %/mes | 18 % | −9 % |
| 5 % | ×20 | ~6,4 %/mes | 30 % | −16 % |
| 8 % | ×100 | ~9,9 %/mes | 46 % | −25 % |

Hubo 10 meses negativos de 49.

**Cautelas:**
- 2026 trae un enero excepcional (+30 % al 5 %). Sin él, los últimos 12 meses rinden ~2,5 %/mes al 5 %.
- 2023–2026 fue un mercado alcista.
- **Cuenta de 1 000:** el candado amplio (~80 $/oz) hace que 0,01 lote ya sea ~8 % de riesgo, así que la cuenta no puede bajar de ahí. Para operar al 3–5 %, la cuenta mínima razonable es de ~3 000–5 000.
- **Riesgo alto por operación:** con el candado amplio, perder 1R entero es raro (desvío por operación ≈ 0,33 R). Eso permite 5–8 % por operación. Kelly ≈ R / var ≈ 0,04 / 0,11 ≈ 35 %, aunque con ventajas tan chicas conviene usar una fracción baja.

## ¿Varias Big One a la vez? (`broker_legs.py`, A)

Varias posiciones iguales en la misma dirección equivalen a un lote mayor: mismo riesgo, nada nuevo.

| Variante | R medio por día | Desvío | Razón |
|---|---|---|---|
| Una a la 01:00 | +0,032 | 0,332 | 0,095 |
| Escalonada 01:00 / 01:15 / 01:30 / 01:45 (¼ cada una) | +0,023 | 0,318 | 0,072 (peor: pierde los primeros minutos) |
| **Escalera de salidas (⅓ a TP2, ⅓ a TP3, ⅓ por hora)** | +0,028 | **0,240** | **0,115** (menos variación) |

## Otras patas probadas (broker)

| Idea | Resultado |
|---|---|
| Rebote asiático tras caída de EE. UU. el día anterior | ❌ Sin patrón estable por año |
| Londres 10:00 → 15:00 siguiendo a Asia | ❌ Inestable (−2,5 a +2,2 $/oz según el año) |
| Big One por día de la semana | ❌ Ruido (el lunes no es especial) |
| Peticiones de desempleo (jueves 08:30 NY), seguir 24 h | ❌ −0,08 R |
| ISM manufacturero, seguir 24 h | ❌ −0,01 R |

## Banco de scalping sobre ticks reales (`econ_scalp.py`, rejilla de 5 s, 2026; A = ene–may, B = jun–oct)

Ejecución: bloque siguiente a la señal, al ask/bid reales, más comisión.

| # | Idea | Resultado |
|---|---|---|
| SC1 | Razón de varianzas del mid a 5 s, 1 min y 5 min | VR 0,95–1,02: paseo aleatorio, nada que explotar |
| SC2 | Desequilibrio de ticks (decil extremo) → seguir o revertir 5–15 min | ❌ −0,14 a −0,52 $/oz |
| SC3 | Salto no programado en 1 min → seguir 15 min | + en A y B (+1,7 $/oz), pero t < 1 y n = 26–73 |
| SC4 | Noticia programada, seguir T−1 → T+2 min | ❌ A negativo |
| SC5 | Números redondos de 25 $, rebote | + en A y B, pero los placebos (+7 / +13 $) también dan +: no es el número |
| SC6 | Barrida del máximo/mínimo de 60 min que vuelve | ❌ −0,3 a −0,4 $/oz |
| SC7 | Franjas de 5 min (546) | 66 positivas en A y B (menos que el azar). Destaca **12:20 venta 15 min**: subasta LBMA de la mañana |
| SC8 | Ruptura tras compresión de 15 min | ❌ |

**Subasta LBMA de la mañana** (10:30 Londres = 12:30 servidor): **vender a las 12:20, salir a las 12:35.**
- M5 del broker desde 2025-05: +1,35 $/oz neto, t 5,8, positiva los 7 trimestres.
- M15 desde 2022: **negativa en 2022–2024** y positiva desde 2025.
- Es un efecto **reciente**. Se vigila en vivo y no entra en la cartera todavía.

**Lectura del scalping:** con un costo de ~0,23–0,29 $/oz, las señales de segundos a pocos minutos no lo cubren, como anticipaba la literatura (`investigacion/scalping-microestructura-2026-10-24.md`). Lo único con forma de ventaja está atado a un evento: la subasta LBMA, reciente, y los saltos no programados, con muestra mínima.

## Ronda 3 (25-oct): comisión real RAW, escalera de salidas y scalping ronda 2

**Comisión real de la cuenta RAW** (Vantage, 1:500):
- 3 $ por lote **por lado**, medido en 380 operaciones de octubre. Son 0,06 $/oz ida y vuelta.
- Las simulaciones anteriores usaban 0,12 y eran conservadoras en 0,06 $/oz por operación.
- Corregido en `bigone_broker.py` (y con él en `broker_rule`), `econ_scalp.py` y `broker_map.py`. Costo total: 0,23 $/oz a la 01:00 y ~0,17 en el resto del día.

**Escalera de salidas:** la misma entrada en 3 tercios (salida por hora, TP 2 y TP 3 ATR M15) con el mismo candado. Datos del broker 2022-10 → 2026-10:

| Pata | R una salida (desvío) | R escalera (desvío) | Razón una → escalera |
|---|---|---|---|
| Big One | +0,033 (0,33) | +0,029 (0,24) | 0,100 → 0,122 |
| Momentum EE. UU. | +0,049 (0,45) | +0,040 (0,32) | 0,108 → 0,124 |
| NFP | +0,283 (0,80) | +0,191 (0,54) | 0,353 → 0,355 |

**Cuenta de 5 000, 49 meses:**

| Tamaño | Una salida: × / caída / peor mes | Escalera: × / caída / peor mes |
|---|---|---|
| 3 % | ×6,6 / 18 % / −8,7 % | ×4,7 / 11 % / −4,4 % |
| 5 % | ×23 / 30 % / −15 % | ×13 / 19 % / −7,6 % |
| 8 % | ×122 / 45 % / −24 % | **×59 / 30 % / −12 %** |
| 10 % | ×332 / 54 % / −30 % | ×147 / 37 % / −15 % |

**Lectura:** al mismo riesgo por operación, la escalera gana menos. A **igual caída** gana bastante más: con 30 % de caída, ×59 frente a ×23. Escalera al 8 % equivale a ~8,7 %/mes compuesto en 49 meses, con 10 meses negativos y peor mes −12 %.

**Últimos 12 meses** (escalera, cuenta nueva el 2025-11-01):

| Cuenta | 5 % fijo | 8 % fijo | Piso G-Z 50 %, 10 % |
|---|---|---|---|
| 5 000 | ×1,55 (caída 7 %) | ×1,84 (15 %) | ×1,96 (16 %) |
| 10 000 | ×1,56 | ×2,02 | ×2,05 |
| 1 000 | ×2,36 (forzada a ~7 % por el lote mínimo; hasta 20 %) | | |

**Scalping, ronda 2** (`econ_scalp2.py`, con costo real):

| # | Idea | Resultado |
|---|---|---|
| SC9 | Ejecución pasiva: órdenes límite a 1,5 / 2 / 3 desv. del promedio de 15 min, objetivo el promedio | ❌ −0,85 a −4,4 $/oz. Selección adversa: se llenan cuando el precio sigue de largo |
| SC12 | Aperturas Londres 10:00 / COMEX 15:20 / NY 16:30 con ticks (ruptura del rango de 5 min) | ❌ t < 0,8 en todas |
| SC13 | Modelo lineal con todo a 1 min (retornos, desequilibrio, spread, volatilidad, hora) | ❌ correlación fuera de muestra 0,000 |
| SC14 | Saltos no programados de 5 min, 2021–2026 (3 314 y 696 casos) | Seguirlos pierde todos los años. Revertir los grandes gana solo en 2025–26 |
| SC15 | Subasta LBMA de la mañana (venta 12:20 → 12:35), 2021–2026 | −0,04 / −0,27 / −0,34 / −0,06 / **+0,56 / +1,75**: régimen nuevo desde 2025. Tarde: ≈ 0 |
| SC10 | Plata (XAGUSD) al minuto: movimiento > 3 o 5 desv. → oro en la misma dirección 1/5 min | ❌ B negativo (−0,18 a −0,44 $/oz). El broker no guarda historia de ticks del índice del dólar (USDX); su versión M5 con Dukascopy ya había fallado |
| SC11 | Triángulo XAUEUR+ × EURUSD+ vs XAUUSD+ | ❌ Desvío medio de 0,07 $ (p99 0,47 $). Los desvíos grandes no se corrigen a favor: −0,07 a −0,27 $/oz en A |
