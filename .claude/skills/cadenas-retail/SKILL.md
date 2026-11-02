---
name: cadenas-retail
description: "Receta de retail por cadena (OXXO, Walmart, Costco, Soriana, 7-Eleven…) en el canal moderno con el datawarehouse — clientes validados, catálogo validado, ventas y potencial — con limpieza de nombres para inferir la franquicia; entrega UN Excel con fórmulas y un tablero HTML; compara territorios o embotelladores (p. ej. Mérida de Bepensa vs CDMX de Femsa) juntos y separados con mapa dividido, tendencias por franquicia y qué vende cada cadena. Usar cuando pidan cadenas, OXXO, Walmart, franquicias, canal moderno, comparar ciudades o embotelladores, o un tablero/Excel de retail."
---

# Receta: cadenas de retail (usuario, 2026-10-30)

Se apoya en **`dwh-navegacion`** (dónde están los datos) y **`pitch-hook-kin`** (cómo presentarlo; ahí están todas las
reglas de UX). Herramienta: `uv run python -m src.main cadenas …` (ver `--help`).

## Qué hace (`src/tools/cadenas.py`)

1. **Clientes validados** de bronze, todos (compren o no).
2. **Franquicia** (`clasificar`, reglas en `src/config/cadenas.py`): regex sobre el nombre → alias sobre el **nombre
   limpio** (sin acentos ni signos; letras sueltas unidas: "O X X O" → OXXO; palabras que **empiezan** con el alias:
   "OXXO12605", "SAM S CLUB", no "BOX XOLALPA") → **aproximado** (similitud ≥ 0.88, alerta "verificar").
   Exclusiones (`no`): KK WALMART, SUPER CENTRO, FARMA, COSCO (Coscomatepec). Columnas `Franquicia`, `Nombre limpio`,
   `Método franquicia`. Para un país/cadena nueva: agregar la cadena y sus alias en config, correr y revisar los
   "aproximado (verificar)".
3. **Tipo de punto** (comedor, corporativo, CEDIS, vending, restaurante, accesos/cajas) y **formato** (OXXO Gas/Tienda,
   Walmart Supercenter/Express…). **Se cuentan TODOS los PdV** (tiendas, comedores, cajas, oficinas) en todo — KPIs,
   mapa, Nunca compraron, hallazgos — para que todo cuadre con "# PdV" (usuario, 2026-11-02); el tipo de punto queda como
   columna de detalle y alerta "no es tienda".
4. **INEGI**: estado, municipio, CVEGEO y población.
5. **Ventas** (periodo comparable, mes incompleto fuera), estatus (Activo, Nuevo, Perdido 3+ meses, Nunca compró),
   catálogo validado (segmento, marca, presentación) y potencial de gold si existe.
6. **Alertas** (no se borra nada): no es tienda, fuera de polígono, nombre repetido, franquicia aproximada, sin venta
   del mes, venta del mes atípica vs su formato (z robusto > 3.5).

## Modos

- Nacional: `cadenas --cadenas oxxo,walmart,costco` → `cadenas_{analisis}_{pais}.xlsx` + `tablero_cadenas.html`.
- `--otras`: cadenas fuera de `--cadenas` → "Otras cadenas" (la franquicia queda en su columna).
  `--independientes`: suma el canal moderno que no es cadena (por defecto NO).
- Territorios (comparar ciudades/embotelladores): `--territorios "Nombre=emb:Estado INEGI[/Municipio INEGI];…"`.
  Referencia: `cadenas --cadenas oxxo,costco,walmart --otras --territorios "Mérida=bepensa:Yucatán/Mérida;CDMX=femsa:Ciudad de México"`.

## Entregables en modo territorios

- **Tablero** (`comparativo.py`): Resumen (hook en frases-dato, KPIs, cara a cara, mezcla, crecimiento, consumo,
  franquicias de Otras cadenas; tarjetas del hook en vertical por ciudad, crecimiento verde/rojo, Nunca compraron; selector "Ver: Territorio de operación | Por ciudad" propio) · Mapa dividido por ciudad (selector de cadena,
  tarjetas, puntos, top 5 clicable) · Tendencias por franquicia (una gráfica por ciudad) · Productos (top propio por
  ciudad y reparto del 100% del revenue por cadena) · Franquicias (sumadas; selector "Ver" propio) · **Nunca
  compraron** (tiendas sin ninguna compra del análisis en 24 meses: X de Y por franquicia y ciudad, % de su franquicia,
  municipios, mapa dividido con esas tiendas en amarillo, lista, y oportunidad de **referencia** = tiendas × revenue
  promedio de las que sí compran de su franquicia en su ciudad; franquicias con 0 compradores (Costco, Sam's Club) se
  avisan aparte como POR VERIFICAR "¿compran por otro canal?").
- **Excel** (`cadenas_excel.py`): Resumen (tiendas, banda "PdV que nunca compraron" total y por ciudad arriba a la derecha, sin estados, Por territorio + Top 10 municipios) · Por territorio ·
  Comparativo (horizontal, bandas de color, diferencias resaltadas) · Detalle PdV (columnas del Excel de referencia y
  luego las nuevas) · Por zona · Por municipio · Tendencia mensual (hasta el último mes completo de todos) · Productos ·
  Nunca compraron (resumen por franquicia + lista de tiendas) · Producto × cadena (100% de lo que compra cada
  franquicia, con TOTAL por bloque y "Resto de …" < 1%) · Top por ciudad.

## Corrida de referencia (2026-11-02, hydration, OXXO · Costco · Walmart · Otras cadenas)

Mérida (Bepensa) 575 PdV vs CDMX (Femsa) 2,236: CDMX 3.9× más PdV, pero cada tienda compradora de Mérida vende
$35.2K vs $21.2K; compran hydration ~93% en ambas; revenue 12m cae en las dos (Mérida −13.7%, CDMX −22.0%). Costco no
tiene venta de hydration en las ventas NSR (compra directo). OXXO vende casi solo Flashlyte (Powerade < 1%).
Contando todos los PdV (2,811: Mérida 575, CDMX 2,236), nunca compraron hydration 191 (6.8% en ambas ciudades: Mérida 39,
CDMX 152); por cadena OXXO 12 (0.7%), Walmart 56 (40.6%), Otras cadenas 114 (13.3%), Costco 9 de 9 (100%, POR VERIFICAR
otro canal; 7 tiendas + 1 comedor + 1 punto de cajas).

## Pendiente conocido (no corregido, usuario 2026-11-02)

Con un mes incompleto en un solo lado (Mérida 202609), su "Revenue 12m" suma 11 meses y el otro 12: el revenue por tienda
compradora no es comparable entre ciudades (el crecimiento vs PY sí). Decírselo al usuario al presentar; no se corrigió.
