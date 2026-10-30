# davinci
AI-powered analytics agent that transforms raw DWH data into strategic business intelligence.

Agente de analítica de Kin Analytics sobre el **datawarehouse de Customer Potential** (Azure Blob `prospecting-data`).
El cerebro es **Claude Code** (sin API propia): lee `.claude/CLAUDE.md` y las skills, hace las preguntas y corre las
herramientas de `src/`. Todo es **solo lectura**: no se sube nada a Azure.

## Preparar

```bash
uv sync
```

Crear `.env` en la raíz con la cadena de conexión de Azure (no se versiona):

```
AZURE_STORAGE_CONNECTION_STRING = <cadena>
```

## Cómo piensa el agente

No es un script de un solo proceso: ante cualquier pregunta sabe **dónde está el dato** (skill `dwh-navegacion`),
**qué bajar** (lo mínimo, de bronze para arriba), **cómo analizarlo** (periodo comparable, comparación justa, sin
inventar) y **cómo presentarlo** con el pitch de Kin abriendo con un **hook** (skill `pitch-hook-kin`). Recetas listas:
`cadenas-retail` y `evaluacion-cp`. Todo está en `.claude/CLAUDE.md`.

## Usar con Claude Code

Abrir el repo en Claude Code y pedir, por ejemplo:

- "Evalúa Customer Potential hydration de Femsa y Bepensa" → skill `evaluacion-cp`
- "Analiza las cadenas OXXO, Walmart y Costco" → skill `cadenas-retail`
- "Compara Mérida de Bepensa con CDMX de Femsa en OXXO, Walmart y las demás cadenas" → `cadenas-retail` con territorios

## Comandos (los corre el agente; también a mano)

| Comando | Qué entrega |
|---|---|
| `uv run python -m src.main evaluar --pais mx --analisis hydration --embotelladores femsa,bepensa` | `outputs/{fecha}_cp_hydration_mx/`: Excel (resumen, segmentos, listas para recuperar y crecer) y mapa de hexágonos |
| `uv run python -m src.main cadenas --cadenas oxxo,walmart,costco` | `outputs/{fecha}_cadenas_hydration_mx/`: UN Excel con fórmulas (formato del Excel OXXO_Walmart_Costco_Nacional) y tablero HTML |
| `uv run python -m src.main cadenas --cadenas oxxo,walmart --otras --territorios "Mérida=bepensa:Yucatán/Mérida;CDMX=femsa:Ciudad de México"` | `outputs/{fecha}_cadenas_hydration_merida_cdmx/`: Excel con Comparativo y tablero Juntos/Separados con mapa |

Pruebas: `uv run python -m unittest discover -s tests -t .`

## Datos que usa (de bronze para arriba)

| Capa | Ruta | Para |
|---|---|---|
| bronze | `bronze/ko/{pais}/{emb}/clients/{fecha}/…_validos.parquet` | clientes validados del canal |
| bronze | `bronze/ko/{pais}/{emb}/product_catalog/{analisis}/{fecha}/…xlsx` | productos validados (solo "Sí") |
| bronze | `bronze/ko/{pais}/{emb}/sales/{analisis}/{fecha}/…parquet` | ventas PDV × producto × mes |
| silver | `silver/ko/{pais}/{emb}/clients/{analisis}_modern/{fecha}/…_catalog.csv` | clientes que compran (evaluar) |
| gold | `gold/ko/{pais}/{emb}/customer_potencial/{analisis}/{fecha}/Results for Bottler/` | potencial del modelo |

Siempre la corrida (fecha) más reciente de cada ruta. Nunca `drop_zone/` crudo. Estado y municipio: INEGI.

## Ver los HTML

Servidor `entregables` de `.claude/launch.json` (puerto 8772, sirve `outputs/`), o abrir el archivo en el navegador
(el mapa base necesita internet).

Especificación completa: [SPEC.md](SPEC.md).
