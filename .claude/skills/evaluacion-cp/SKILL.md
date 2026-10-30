---
name: evaluacion-cp
description: "Evalúa Customer Potential de un análisis (p. ej. hydration) para uno o varios embotelladores con los datos del datawarehouse — clientes que compran (silver), ventas (bronze) y potencial del modelo (gold, si existe) — y entrega a un tomador de decisiones un mapa.html (hexágonos H3, sin coordenadas de PDV) y un Excel con resumen, hallazgos, tendencia, estado, municipio, subcanal, segmentos y listas de acción (recuperar y crecer). Solo lectura en Azure. Usar cuando pidan evaluar, comparar o analizar clientes de Customer Potential, hydration de Femsa o Bepensa, mapa y Excel para gerencia, o 'qué hacer con estos clientes'."
---

# Receta: evaluación de Customer Potential (usuario, 2026-10-30)

Se apoya en **`dwh-navegacion`** (dónde están los datos) y **`pitch-hook-kin`** (cómo presentarlo). Herramienta:
`uv run python -m src.main evaluar --pais mx --analisis hydration --embotelladores femsa,bepensa`.

## Reglas

- **Nunca se sube nada a Azure** (usuario, 2026-10-30): solo `list_blobs` y descargas a `data/` (espejo local; no
  baja de nuevo lo que ya está con el mismo tamaño). El hook `src/runtime/sandbox.py` pide OK si algo intenta escribir.
- **Solo paths del datawarehouse** (SPEC §8.1), la corrida (fecha) más reciente de cada uno:
  `silver/ko/{pais}/{emb}/clients/{analisis}_modern/`, `bronze/ko/{pais}/{emb}/sales/{analisis}/`,
  `bronze/…/product_mapping/{analisis}/`, `gold/ko/{pais}/{emb}/customer_potencial/{analisis}/`.
  Sin silver o sin ventas → para (regla 13). Sin gold → potencial **POR VERIFICAR** (no se estima, regla 9).
- **Salida**: `outputs/{AAAAMMDD}_cp_{analisis}_{pais}/` en la raíz del repo (fuera de git):
  `cp_{analisis}_{pais}.xlsx`, `cp_{analisis}_{pais}_mapa.html`, `evaluacion_metadata.json`.
- **Periodo**: últimos 12 meses contra **los mismos meses** del año anterior. Si el último mes trae < 70% de la
  mediana de los 12 anteriores, es un corte del extracto: queda fuera y se avisa (Bepensa 202609 = 51%).
- **Segmentos** (`evaluacion.SEGMENTO_QUE_ES`): Frecuente (≥ 75% de los meses desde su 1.ª compra) · Ocasional ·
  Nuevo (1.ª compra en los últimos 6 meses) · En riesgo (3+ meses sin comprar; gana sobre los demás).
- **Mapa**: H3 res 6/7/8 agregado en Python; el HTML lleva IDs de hexágono y sumas, nunca lat/lon (se aborta si
  aparece una). OpenFreeMap + MapLibre en Leaflet; la capa GL se agrega en `load`, después de dimensionar y
  encuadrar (antes: `Invalid LatLng (NaN, NaN)` y mapa base en blanco). Ver: servidor `entregables` de
  `.claude/launch.json` (puerto 8772, sirve `outputs/`).
- **Marca Kin** (skill `brand-guidelines-kin`, vía `src/tools/marca.py`): fuentes embebidas, logo oficial desde
  archivo, rampa de grises con el tramo más alto en amarillo; Excel con el mismo pitch que el de cadenas.
- Solo se baja el archivo que se usa de cada ruta (`dwh.bajar`), y solo de bronze/silver/gold.
- **QA**: un cliente por fila; la suma por estado = el total del embotellador.

## Al terminar

Mostrar los hallazgos (los imprime el comando), las rutas del Excel y el mapa, y lo POR VERIFICAR.

## Corrida de referencia (2026-10-30, mx · hydration · moderno)

Femsa: 38,688 clientes, revenue 12m $847.1M (−17.4% vs año anterior), 24% en riesgo, potencial del modelo
78.7K cajas/mes (+17.9%), 7,686 clientes Very High/High. Bepensa: 3,192 clientes, $139.1M en 11 meses (−11.8%),
4% en riesgo, sin gold (potencial POR VERIFICAR). Los territorios no se cruzan (Bepensa: península de Yucatán).
