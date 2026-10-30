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
   Walmart Supercenter/Express…). Los conteos de tiendas excluyen los que no son tienda.
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
  franquicias de Otras cadenas; selector Juntos/Separados propio) · Mapa dividido por ciudad (selector de cadena,
  tarjetas, puntos, top 5 clicable) · Tendencias por franquicia (una gráfica por ciudad) · Productos (top propio por
  ciudad y reparto del 100% del revenue por cadena) · Franquicias (sumadas; Juntos/Separados propio).
- **Excel** (`cadenas_excel.py`): Resumen (tiendas, sin estados, Por territorio + Top 10 municipios) · Por territorio ·
  Comparativo (horizontal, bandas de color, diferencias resaltadas) · Detalle PdV (columnas del Excel de referencia y
  luego las nuevas) · Por zona · Por municipio · Tendencia mensual (hasta el último mes completo de todos) · Productos ·
  Producto × cadena (100% de lo que compra cada franquicia, con TOTAL por bloque y "Resto de …" < 1%) · Top por ciudad.

## Corrida de referencia (2026-10-30, hydration, OXXO · Costco · Walmart · Otras cadenas)

Mérida (Bepensa) 568 tiendas vs CDMX (Femsa) 2,215: CDMX 3.9× más tiendas, pero cada tienda compradora de Mérida vende
$35.2K vs $21.3K; compran hydration ~94% en ambas; revenue 12m cae en las dos (Mérida −13.7%, CDMX −22.0%). Costco no
tiene venta de hydration en las ventas NSR (compra directo). OXXO vende casi solo Flashlyte (Powerade < 1%).
