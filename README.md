# davinci
AI-powered analytics agent that transforms raw DWH data into strategic business intelligence.

Agente de analítica de Kin Analytics sobre el **datawarehouse de Customer Potential** (Azure Blob `prospecting-data`).
El cerebro es **Claude Code** (sin API propia): lee `.claude/CLAUDE.md` y las skills, hace las preguntas y corre las
herramientas de `src/`. Todo es **solo lectura**: no se sube nada a Azure.

## Preparar

Requisitos:
- [uv](https://docs.astral.sh/uv/) y Python ≥ 3.14 (uv lo instala si falta). `python` debe estar en el PATH: el hook de
  seguridad (`.claude/settings.json` → `src/runtime/sandbox.py`) se corre con él; si no, Claude Code bloquea los comandos.
- [Claude Code](https://claude.com/claude-code) (el cerebro del agente).
- Acceso de lectura al blob de Azure (`prospecting-data`).
- LibreOffice (`soffice`) para recalcular y revisar los Excel en el QA (opcional para correr los comandos).
- Internet: INEGI (estado/municipio) y mapa base de los HTML.

```bash
uv sync
```

```bash
cp .env.example .env
```

Completar en `.env` la cadena de conexión (`AZURE_STORAGE_CONNECTION_STRING`); el `.env` no se versiona. Probar:

```bash
uv run python -m unittest discover -s tests -t .
```

`data/` (copia local del blob e INEGI), `state/` (bitácora de corridas) y `outputs/` (entregables) se crean solos y no
se versionan.

## Estructura

```
.claude/CLAUDE.md      el "prompt" del agente: cómo trabaja, reglas firmes, mapa de skills
.claude/skills/        conocimiento: dwh-navegacion, pitch-hook-kin, cadenas-retail, evaluacion-cp, marca Kin, UX…
.claude/settings.json  hook que pide OK antes de cualquier escritura en el blob
.claude/launch.json    servidor "entregables" (puerto 8772) para ver los HTML de outputs/
src/main.py            entrada única: evaluar | cadenas
src/config/            settings (capas, rutas) · cadenas (reglas de cadena, alias, columnas por embotellador)
src/runtime/           executor (bitácora) · sandbox (hook)
src/tools/             blob · dwh · inegi · marca · evaluacion/excel/mapa · cadenas/cadenas_excel/tablero/comparativo
tests/                 pruebas del arnés
SPEC.md                especificación (requisitos RF-xx y reglas)
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

Prompts listos para reproducir un entregable sin refinamiento (solo se cambian los parámetros): [`prompts/`](prompts/).
Comparar ciudades por cadena (y agregar otra ciudad): [`prompts/comparar-ciudades-cadenas.md`](prompts/comparar-ciudades-cadenas.md).

## Comandos (los corre el agente; también a mano)

| Comando | Qué entrega |
|---|---|
| `uv run python -m src.main evaluar --pais mx --analisis hydration --embotelladores femsa,bepensa` | `outputs/{fecha}_cp_hydration_mx/`: Excel (resumen, segmentos, listas para recuperar y crecer) y mapa de hexágonos |
| `uv run python -m src.main cadenas --cadenas oxxo,walmart,costco` | `outputs/{fecha}_cadenas_hydration_mx/`: UN Excel con fórmulas (formato del Excel OXXO_Walmart_Costco_Nacional) y tablero HTML |
| `uv run python -m src.main cadenas --cadenas oxxo,walmart --otras --territorios "Mérida=bepensa:Yucatán/Mérida;CDMX=femsa:Ciudad de México"` | `outputs/{fecha}_cadenas_hydration_merida_cdmx/`: Excel con Comparativo y banda "Nunca compraron" en el Resumen; tablero (Ver: Territorio de operación / Por ciudad) con mapa dividido, tendencias, productos, franquicias y Nunca compraron; filtros con "Todas" y "✕ Limpiar" |

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
