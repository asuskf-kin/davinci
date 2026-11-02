# Prompt · Comparar ciudades por cadena (retail, canal moderno)

Copia el bloque **PROMPT** en Claude Code, con este repo abierto. Solo cambia la sección **Parámetros**. Con los
parámetros de ejemplo sale exactamente el entregable de referencia, Mérida (Bepensa) vs CDMX (Femsa), sin más
refinamiento: todas las correcciones de UX que pidió el usuario ya están en el código (`src/tools/comparativo.py`,
`src/tools/cadenas_excel.py`) y en las skills.

---

## PROMPT

```text
Compara ciudades por cadena en el canal moderno con el comando `cadenas` de davinci. Es un entregable que ya existe en
el código: NO escribas ni modifiques código, NO rediseñes nada. Solo corre, valida y reporta.

### Parámetros
- análisis: hydration
- país: mx
- cadenas foco: oxxo,costco,walmart   (+ "Otras cadenas" con --otras; sin Independientes)
- ciudades (nombre=embotellador:Estado INEGI/Municipio INEGI; sin municipio = todo el estado):
    Mérida=bepensa:Yucatán/Mérida
    CDMX=femsa:Ciudad de México

### Skills (carga solo estas, en este orden)
1. `cadenas-retail`: la receta y el comando.
2. `dwh-navegacion`: SOLO si una ciudad es nueva (para validar el nombre INEGI y que el embotellador tenga
   clientes ahí). Si las ciudades ya corrieron antes, no la cargues.
3. `pitch-hook-kin`: solo la sección "QA antes de entregar".
NO cargues `brand-guidelines-kin`, `impeccable`, `dataviz` ni `ui-ux-pro-max`: la marca y la UX ya están en el código.
Cárgalas solo si te piden cambiar el diseño.

### Pasos
1. Ciudad nueva (si no, salta al paso 2): confirma el nombre exacto de estado y municipio INEGI y que el embotellador
   tenga clientes ahí:
   uv run python -c "from src.tools.cadenas import cargar; d,*_=cargar('mx','<embotellador>','hydration'); print(d[d.estado.str.contains('<estado>',case=False)].groupby(['estado','municipio']).size().sort_values().tail(15))"
   Si no hay clientes, dilo y para. No escojas otra ciudad por tu cuenta.
2. Corre UNA sola vez:
   uv run python -m src.main cadenas --cadenas oxxo,costco,walmart --otras --territorios "Mérida=bepensa:Yucatán/Mérida;CDMX=femsa:Ciudad de México"
   Orden de columnas y colores: por embotellador (en el orden en que aparece cada uno) y luego por ciudad; 1.ª
   amarillo, 2.ª blanco (negro en Excel), 3.ª gris.
3. QA, sin abrir los archivos completos en contexto:
   a. Excel: recalcula con LibreOffice (`soffice --headless --convert-to xlsx --outdir <scratchpad> <xlsx>`; en Windows
      `soffice` no suele estar en el PATH: usa "C:\Program Files\LibreOffice\program\soffice.com") y busca
      #VALUE!, #REF!, #DIV/0! y #NAME? en todas las hojas. Deben ser 0.
   b. Que cuadre: el total de PdV del Resumen (fila 10, columna B) = la suma de PdV por ciudad (banda "PdV que nunca
      compraron", fila 11). Una cadena sin compras debe tener nunca compraron = # PdV (100%).
   c. Tablero: abre `tablero_<ciudades>.html` con el servidor `entregables` (preview_start). Con un script asíncrono que
      guarde el progreso en `window.__q`, haz clic en todos los botones y encabezados de las 6 pestañas. Deben quedar
      0 errores en consola y los mapas vivos.
   d. Privacidad: el HTML no lleva coordenadas exactas (el propio código aborta si aparecen).
4. Reporta en pocas líneas: el hook (las 3–4 frases-dato del Resumen), la ruta de los entregables, qué verificaste y
   qué no, y lo POR VERIFICAR (cadenas sin compras, mes incompleto excluido).

### Reglas firmes (ya están en el código; no las cambies)
- Solo lectura del blob, de bronze para arriba. Nunca subir nada a Azure. El DWH es la verdad.
- Se cuentan TODOS los PdV (tiendas, comedores, cajas, oficinas) para que todo cuadre con "# PdV".
- Periodo comparable: últimos 12 meses completos vs los mismos meses del año anterior ("vs PY"). El mes incompleto
  queda fuera.
- Nada que se lea como 0. Lo que falta es "Sin venta de … en los datos" o POR VERIFICAR.
- Sin commits.
```

---

## Cómo agregar otra ciudad

Agrega una entrada a **ciudades** (y al `--territorios` del paso 2), separada por `;`:

| Ciudad | Entrada | Nota |
|---|---|---|
| Cancún | `Cancún=bepensa:Quintana Roo/Benito Juárez` | Cancún está en el municipio Benito Juárez (INEGI) |
| Toda Yucatán | `Yucatán=bepensa:Yucatán` | sin municipio = todo el estado |
| Puebla | `Puebla=femsa:Puebla/Puebla` | validar en el paso 1 |

- El nombre de la izquierda es libre: es lo que se ve en el tablero y el Excel, y forma el nombre de la carpeta.
- Estado y municipio deben escribirse **exactamente como en INEGI** (con acentos). Si no hay clientes del embotellador
  ahí, el comando para con un mensaje claro.
- Embotelladores con datos: `femsa`, `bepensa` (`settings.EMBOTELLADORES`). Cada ciudad usa el suyo, y se pueden
  comparar dos ciudades del mismo embotellador.
- Con **3 o más ciudades** todo se arma igual (probado con Mérida · CDMX · Cancún: 155 clics sin errores, Excel sin errores) (pares con una barra por ciudad, un mapa por ciudad), pero:
  - la columna "Diferencia" del Comparativo del Excel solo existe con 2 ciudades;
  - la frase "N× más PdV" del hook compara las dos primeras.

  Para un cara a cara puro, usa 2 ciudades.
- Otras cadenas foco: claves de `src/config/cadenas.py` (`oxxo, walmart, costco, bodega_aurrera, sams, soriana,
  chedraui, seven, circle_k, dunosusa, super_aki`).

## Por qué este prompt ahorra recursos

- **Cero código nuevo:** reutiliza `cadenas` (una corrida) en vez de que el agente reconstruya el análisis.
- **Pocas skills:** carga 1 a 3 (las de marca y UX no hacen falta, ya están en el código).
- **Descarga mínima:** `blob.descargar` no vuelve a bajar lo que ya está en `data/` con el mismo tamaño.
- **QA por script:** no se leen los archivos completos en el contexto.

## Resultado esperado con los parámetros de ejemplo (corrida de referencia 2026-11-02)

`outputs/{AAAAMMDD}_cadenas_hydration_merida_cdmx/` con `cadenas_hydration_merida_cdmx.xlsx` (11 hojas: Resumen ·
Por territorio · Comparativo · Detalle PdV · Por zona · Por municipio · Tendencia mensual · Productos · Nunca compraron
· Producto × cadena · Top por ciudad), `tablero_merida_cdmx.html` (Resumen · Mapa · Tendencias · Productos ·
Franquicias · Nunca compraron) y `cadenas_metadata.json`.

| Indicador | Mérida (Bepensa) | CDMX (Femsa) |
|---|---|---|
| PdV (OXXO · Costco · Walmart · Otras cadenas) | 575 | 2,236 |
| Compran hydration | 92.7% | 92.8% |
| Revenue 12m por tienda compradora | $35.2K | $21.2K |
| Revenue vs año anterior | −13.7% | −22.0% |
| Nunca compraron hydration | 39 (6.8%) | 152 (6.8%) |

- Total: 2,811 PdV, de los cuales 191 nunca compraron.
- Costco: 9 PdV, 0 compras de hydration (POR VERIFICAR otro canal).
- Mérida: sep-2026 incompleto, queda fuera.
