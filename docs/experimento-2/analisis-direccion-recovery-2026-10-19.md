# Dirección de la recovery: estructura H4 o a favor del movimiento Op1 → Op2 (19-oct-2026)

**Pregunta del usuario:** ¿se puede usar lo que pasó entre la Op1 y la Op2 para decidir mejor si la recovery compra o vende?

**Respuesta corta:** no como regla fija, ahora que la Op4 tendencia está activa.
- Sin la Op4, poner la recovery a favor del movimiento que rompió la Op1 (el lado de la cobertura) mejora mucho y reduce los desastres.
- Con la Op4, la mejora sale casi entera de los mismos 2–3 episodios de tendencia que la Op4 ya cubre. Además, la recovery pasa a acertar solo el 40 % de las veces, frente al 80 %.

**Recomendación:** no cambiar la dirección de la recovery. Revisarlo cuando la Op4 lleve semanas de datos reales.

## Qué se simuló

**Datos:** las 245 recoveries reales y velas M15.

**Reglas comparadas:**
- **H4 (actual):** la dirección que eligió el bot.
- **A favor Op1 → Op2:** siempre el lado de la cobertura, es decir, contrario a la Op1.
- **Siempre como la Op1.**

**Misma salida modelada para todas:** no se puede usar la salida real del lado contrario, porque no existió. Se probaron tres salidas:
- **aguantar:** valor al cierre real;
- **trailing de la Op3** (0,6/0,4 ATR);
- **aguantar + Op4 tendencia** (K = 2, 1,0/0,5 ATR, curador al 90 %).

**Coste:** spread de 0,3 $/oz por operación.

## Resultados ($/oz por unidad de recovery, sumando las 245)

| Salida | Regla | Total | Sin los 3 mejores episodios | Acierto | Desastres (< −20) | Peor episodio |
|---|---|---|---|---|---|---|
| Aguantar | H4 (actual) | −300 | −533 | 83 % | 11 | −285 |
| Aguantar | A favor Op1 → Op2 | +255 | −244 | 40 % | 3 | −135 |
| Trailing Op3 | H4 (actual) | −424 | −533 | 85 % | 10 | −285 |
| Trailing Op3 | A favor Op1 → Op2 | +11 | −92 | 50 % | 1 | −144 |
| **Aguantar + Op4** | **H4 (actual)** | **+78** | **−156** | **82 %** | 14 | **−66** |
| Aguantar + Op4 | A favor Op1 → Op2 | +363 | −136 | 38 % | 5 | −52 |

**Diferencia por mes** (a favor Op1 → Op2 menos H4):

| Salida | Junio | Julio | Agosto | Octubre | Episodios mejor / peor |
|---|---|---|---|---|---|
| Trailing Op3 | +208 | +46 | −49 | +229 | 17 / 17 |
| Aguantar + Op4 | −37 | −15 | +76 | +261 | 16 / 20 |

*Septiembre no tuvo recoveries.*

## Lectura

- **Sin la Op4, el cambio sería bueno:**
  - de 10 desastres se pasaría a 1;
  - el peor episodio bajaría de −285 a −144 $/oz.
- **Con la Op4, el cambio no es robusto:**
  - quitando los 3 mejores episodios, las dos reglas quedan igual (−136 frente a −156);
  - empeora en más episodios de los que mejora (20 frente a 16);
  - casi toda la ventaja viene del 14-oct (+337 $/oz, sumando las 3 cuentas).
- **Las dos ideas apuestan por lo mismo,** que la tendencia sigue. La Op4 lo hace solo cuando la recovery ya va 2 ATR en contra. Cambiar la dirección de la recovery lo haría siempre, y acertaría en el 40 % de los casos en vez del 80 %. Eso alargaría los ciclos (más swap y más tiempo expuestos), algo que esta simulación no mide.

## Limitaciones

- La salida es un modelo, no el Unwind real. La hora del cierre real depende de la dirección que se tomó de verdad.
- Muestra pequeña: 46 episodios, muy influida por el 14-oct, que cuenta 3 veces (una por cuenta).
