# Op4 tendencia: límite por ciclo y Op4 secundaria contraria (19-oct-2026)

**Preguntas del usuario:**
1. Tras un hueco de precio, la Op4 se puso en negativo. ¿Debería poder abrirse una Op4 secundaria en sentido contrario (SELL) que corte a la primera?
2. ¿El límite de 6 Op4 por ciclo puede dejar el ciclo bloqueado en negativo? ¿Habría que quitarlo?

**Respuesta corta:**
- El límite no bloquea nada: al llegar a 6, la recovery que queda sigue como antes de que existiera la Op4.
- Subirlo a 10 mejora muy poco; quitarlo empeora.
- La Op4 secundaria contraria empeora el total y se dispara en número de operaciones: hasta 165 Op4 en una sola recovery.
- El recorte por parejas recovery + Op4 no cambia nada en la simulación, porque el curador ya recorta la recovery en cuanto la Op4 cierra con ganancia. Se queda fuera del diseño del recorte por parejas.

## Qué se simuló

- **Modelo:** el mismo que en `analisis-op4-direccion-2026-10-16.md`.
  - 245 recoveries y velas M15, con orden conservador.
  - Op4 con K = 2 ATR y trailing 1,0/0,5 ATR (solo la Op4 más reciente, como en vivo).
  - Curador al 90 %.
  - Spread de 0,3 $/oz por apertura.
- **Op4 secundaria:** si la Op4 más reciente va X ATR en contra (y aún no ha armado el trailing), se abre otra del mismo tamaño en dirección contraria.
- **Recorte por parejas:** con bolsa y sin recovery recortable, se cierran partes iguales de dos patas opuestas.

## Resultados ($/oz, mejora frente a la recovery sola)

| Variante | Mejora | Sin los 3 mejores episodios | 14-oct | Peor episodio | Episodios + / − | Op4 en total | Máx. Op4 en una recovery |
|---|---|---|---|---|---|---|---|
| **Actual (límite 6)** | **+374** | −83 | +77 | −44 | 6 / 15 | 106 | 6 |
| Límite 10 | +403 | −79 | +82 | −44 | 6 / 15 | 138 | 10 |
| Límite 20 | +398 | −82 | +82 | −44 | 6 / 15 | 163 | 20 |
| Sin límite | +339 | −118 | +82 | −44 | 6 / 15 | 165 | 22 |
| Límite 6 + parejas | +374 | −83 | +77 | −44 | 6 / 15 | 106 | 6 |
| Secundaria a 1 ATR + parejas | +332 | −122 | +88 | −37 | 7 / 13 | 530 | 165 |
| Secundaria a 2 ATR + parejas | +307 | −169 | +84 | −52 | 6 / 15 | 323 | 95 |
| Secundaria a 2 ATR sin parejas | +323 | −154 | +85 | −52 | 6 / 15 | 323 | 95 |

## Lectura

- **El límite:**
  - Pasar de 6 a 10 da +29 $/oz, casi todo del 14-oct. Sin los 3 mejores episodios la diferencia es de +4, así que entra en el ruido.
  - Sin límite empeora, porque en mercado lateral la Op4 se reabre una y otra vez pagando spread y pequeñas pérdidas.
  - Al agotarse el límite, el ciclo no se bloquea: la recovery que queda espera, como antes de la Op4.
  - El «bloqueo» real ocurre cuando la Op4 está en rojo y abierta. Con la exposición neta en cero, el ciclo se queda congelado hasta que el precio vuelve a favor de la Op4, y eso no depende del límite.
- **La Op4 secundaria contraria:**
  - mejora el 14-oct (+84 a +88 frente a +77), pero empeora el total y el resto de episodios;
  - en mercado lateral se encadena: cada giro abre otra Op4 y deja otra pérdida congelada;
  - a 1 ATR recorta un poco el peor episodio (−37 frente a −44), pero lo paga con 5 veces más operaciones y peor resultado fuera de las tendencias.
- **Parejas recovery + Op4:** no aportan nada medible. El curador ya recorta la recovery directamente en cuanto la Op4 cierra en verde.

## Decisión

Sin cambios:
- se mantiene el límite de 6;
- no se añade Op4 secundaria;
- el diseño del recorte por parejas se limita al par Op1 + Op2.

Subir el límite a 10 es un cambio solo de configuración (`rescue_trend_max_legs`), por si el usuario lo quiere; su efecto está dentro del ruido.
