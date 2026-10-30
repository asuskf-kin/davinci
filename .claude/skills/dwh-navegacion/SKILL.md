---
name: dwh-navegacion
description: "Mapa del datawarehouse de Kin/KO en Azure Blob para saber por dónde moverse: contenedores, capas (bronze, silver, gold), rutas de clientes, catálogo, mapeo, ventas y resultados del modelo Customer Potential, columnas por embotellador, qué archivo responde qué pregunta, qué bajar (y qué no) y trampas conocidas (mes incompleto, mayúsculas, rutas fuera de norma). Usar antes de cualquier análisis sobre datos de clientes, productos, ventas o potencial de un embotellador o país, o cuando pidan explorar, inventariar o ubicar datos en el blob."
---

# Navegar el datawarehouse (usuario, 2026-10-30)

Regla de oro: **la fuente válida es el datawarehouse, de bronze para arriba** (`settings.CAPAS`). Solo lectura:
listar y bajar al espejo `data/`; nunca subir, copiar ni borrar (el hook pide OK). Archivos que mande el usuario
(un Excel, un CSV) son **referencia de formato**, no de cifras: no se cuadra contra ellos.

## Cómo encontrar lo que se necesita (en este orden)

1. **Traducir la pregunta a datos**: ¿quién (embotellador, país, ciudad), qué (clientes, productos, ventas,
   potencial), cuándo (últimos 12 meses comparables)?
2. **Ubicar la ruta** con la tabla de abajo y `blob.ultima_corrida(prefijo)` (toma la carpeta de fecha más reciente).
3. **Bajar solo el archivo principal** con `dwh.bajar(prefijo, terminación)` (no metadata ni QA si no se usan; no
   vuelve a bajar lo que ya está con el mismo tamaño).
4. Si algo no está donde debe: **listar sin bajar** (`blob.contenedor().list_blobs(name_starts_with=…)` o
   `walk_blobs(delimiter="/")`), decirle al usuario qué hay y qué falta. No inventar ni tomar archivos de otro lado
   por cuenta propia (POR VERIFICAR).

## Contenedores

| Contenedor | Qué hay |
|---|---|
| `prospecting-data` | El datawarehouse: `drop_zone/` (crudo, no se usa) · `bronze/` · `silver/` · `gold/` |
| `ko-customer-potential-service` | Resultados del modelo: `processed_data/{pais3}/{emb}[_custom_x \| _bodyarmor]/{AAAAMMDD}/results/conservative_scenario.csv` (+ `json_config.json`). Fuera de la norma del DWH: usar solo si el usuario lo pide |
| `ko-processed-data` | AltScore y procesos del modelo (p. ej. `ko-db/femsa_mx_complete_may_2026/…parquet`) |
| otros (`ko-raw-data`, `ko-cleaned-data`, `dataplorraw`…) | Fuera del alcance del agente salvo pedido explícito |

## Rutas de la norma (minúsculas, `{pais}` ISO-2, `{emb}` en minúsculas)

| Dato | Ruta en `prospecting-data` | Archivo principal | Para qué |
|---|---|---|---|
| Clientes validados | `bronze/ko/{pais}/{emb}/clients/{AAAAMMDD}/` | `…_{canal}_validos.parquet` | universo de PdV del canal (compren o no) |
| Catálogo validado | `bronze/ko/{pais}/{emb}/product_catalog/{analisis}/{AAAAMMDD}/` | `catalogo_….xlsx` (cabecera fila 7; filtrar `¿Es {analisis}? = Sí`) | productos aprobados: segmento, marca, sabor, envase, servicio |
| Mapeo | `bronze/ko/{pais}/{emb}/product_mapping/{analisis}/{AAAAMMDD}/` | `mapeo_….csv` (`;`, cp1252) | lista corta `product_id;Descripción;custom_category` |
| Ventas del análisis | `bronze/ko/{pais}/{emb}/sales/{analisis}/{AAAAMMDD}/` | `….parquet` | PdV × producto × mes (`month_445`), `revenue`, `unit_cases`, `es_outlier` |
| Clientes que compran | `silver/ko/{pais}/{emb}/clients/{analisis}_{modern\|traditional\|all}/{AAAAMMDD}/` | `…_validos_catalog.csv` (UTF-8) | compradores con `estado`, `municipio`, `{analisis}_*` (revenue, cajas, meses, top) |
| Resultado del modelo | `gold/ko/{pais}/{emb}/customer_potencial/{analisis}/{AAAAMMDD}/Results for Bottler/` | `Customer_Potential_Conservative_Scenario.csv` | `Priority Level_CustomCat_{analisis}`, `Monthly Growth Potential (Unit Cases)_…`, `size_class_internal` |
| Metadata de gold | misma carpeta | `customer_potential_metadata.json` | `VTM data` (ventas actuales, aporte, % crecimiento, PdV por GEC) |

**No usar** (crudo o fuera de norma): `drop_zone/…` (incluido `products_nsr` crudo), `bronze/customer_potencial/KO/…`
y `silver|gold/customer_potential/…` (legado, "potential" con t, mayúsculas), `silver/prospection/…`.
Productos = **siempre el catálogo validado**, nunca products_nsr.

## Qué hay hoy (2026-10-30)

- **mx · femsa**: clientes 20261029 (80,187 moderno), catálogo/mapeo/ventas hydration 20261029, silver
  `hydration_modern/20261029` (38,688 compradores), **gold hydration 20261029** (potencial).
- **mx · bepensa**: clientes 20261030 (3,561 moderno; Yucatán, Quintana Roo, Campeche), catálogo/mapeo/ventas hydration
  20261030, silver `hydration_modern/20261030` (3,192). **Sin gold** → potencial POR VERIFICAR.
- **ar** (andina, arca, femsa): solo drop_zone. Muchos países (BR, CL, CO, PE, PY, RD, VE, GT…) con carpetas fuera de
  norma en `bronze/ko/{PAIS}/…`: inventariar antes de prometer un análisis.

## Columnas por embotellador (bronze clients) — `src/config/cadenas.COLUMNAS`

| | Femsa MX | Bepensa MX |
|---|---|---|
| zona | `Zone` (Golfo, Bajío, CDMX, Edomex, Monarca, Centro-Pacífico, Sureste) | `cedis` |
| subcanal | `BU_Channel` (TDC CADENA = OXXO, HIPERMERCADO, CLUB DE MEMBRESIA…) | `pos_subchannel`, `nomisscom` |
| grupo | `Channel_Group` | `pos_consumer_type` |
| venta del mes | `gross_rev`, `unit_cases`, `discount_ac` del `month_cal` (mayormente ago-2025) | **no tiene** → POR VERIFICAR |
| nombre / coordenadas | `Cliente`, `pos_latitude`, `pos_longitude` (texto) | igual |

Identificadores (`pos_id`, `product_id`) siempre como texto.

## Trampas conocidas

- **Mes incompleto**: el extracto de ventas se corta a mitad de mes (Bepensa 202609 = 51% de un mes normal, extracto del
  10/09). Regla: último mes < 70% de la mediana de los 12 anteriores → fuera de comparaciones y de gráficas.
- **Periodo comparable**: últimos 12 meses completos vs los **mismos meses** del año anterior (solo meses con par);
  cada embotellador con su propio periodo.
- **Cadenas sin venta en NSR**: Costco aparece en clientes pero no compra hydration en las ventas NSR (compra directo):
  decir "sin venta en los datos", nunca $0.
- **Catálogos distintos por embotellador**: los `product_id` y descripciones de Femsa y Bepensa no coinciden; comparar por
  segmento/marca o mostrar el top propio de cada uno.
- **Geografía**: estado/municipio oficiales con INEGI (`src/tools/inegi.py`, CVEGEO + población); fuera de polígono →
  municipio más cercano con alerta. Si piden una ciudad (Mérida), no mostrar el estado (Yucatán).
- **Franquicia por nombre**: el nombre del cliente trae la cadena con ruido ("O X X O", "WAL - MART", "SAM´S"); usar
  `cadenas.clasificar` (regex → nombre limpio → aproximado con alerta) y exclusiones en `src/config/cadenas.py`
  (KK WALMART, SUPER CENTRO, FARMA, COSCO).
- **No son tiendas**: comedores, oficinas, CEDIS, vending (`TIPOS_PUNTO`): fuera de los conteos de tiendas.
- **`.env`**: `AZURE_STORAGE_CONNECTION_STRING` con espacios alrededor del `=`; nunca imprimirla.
- **Excel abierto** (Windows): no se puede sobrescribir; el código guarda una copia con la hora; luego borrar la copia.

## Herramientas listas (reusar antes de escribir código nuevo)

`src/tools/blob.py` (listar/bajar) · `dwh.py` (`bajar`, `ventas` con periodo comparable, `catalogo`, `potencial`) ·
`inegi.py` · `cadenas.py` (`clasificar`, `limpiar`, `cargar` = base completa de un embotellador) · `marca.py`.
Comandos: `uv run python -m src.main evaluar|cadenas …` (ver `--help`).
