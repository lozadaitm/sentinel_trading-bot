# Carrera hasta duplicar del bot de antes de esta rama (main, ed49958) — 2026-10-20

Herramienta: `bot_backtesting/fullsim/race.py` (motor REAL de `main`, swap, comisión, spread).
Cuenta de 1 000 $, DEFAULTS de `main`, 285 arranques semanales 2021-03 → 2026-08.
Cada arranque corre hasta duplicar (≥ 2 000 $), quemarse (≤ 300 $ o stop-out) o 120 días.

## Resultado

| Plazo | Duplica | Se quema |
|---|---|---|
| 14 días | 4,6 % | 16,8 % |
| 30 días | 9,5 % | 35,4 % |
| 60 días | 14,0 % | 54,4 % |
| 120 días | 21,1 % | 67,4 % |

- Días hasta duplicar (cuando duplica): mediana 40, cuartiles 15–78.
- Valor medio al final por cada 1 000 $: 734 $ (mediana 295 $). Esperanza negativa.
- El "2x en dos semanas" ocurre en ~1 de cada 20 arranques.

## Qué quema la cuenta

3 630 ciclos; 192 son el ciclo que quema su arranque (116 distintos).

- Casi todos llegan al tope de patas (6 = Op1 + cobertura + Op3 + 3 Op4).
  De los ciclos de 6 patas, ~30 % queman la cuenta; el resto gana de media +11 % de golpe.
  Los ciclos de 1–4 patas casi nunca hacen daño.
- Ciclo asesino (medianas): 6 patas, 0,19 lotes brutos / 0,16 netos, 3 ATR diarios en contra,
  ~10 días abierto. Ciclos profundos que sobreviven: < 1 ATR en contra.
- Reparto de la pérdida de los 192 ciclos asesinos (re-simulados con atribución):
  - 99,7 % con exposición neta abierta; 0,4 % con neto 0 / candado; swap 0,9 %.
  - 10 % antes de llegar al tope de patas, **90 % después** (mediana: tope a las 30 h,
    luego 178 h abierto perdiendo ~843 $).

Conclusión: la cuenta muere por la exposición que queda abierta tras agotar el rescate, no
por la entrada ni por el swap. Siguiente paso: candado externo (`--guard cap,k,u`) que cubre
el neto si el precio sigue k ATR en contra tras el tope y lo suelta si vuelve u ATR.
