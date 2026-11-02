---
name: pitch-hook-kin
description: "Cómo presentar cualquier entregable del agente (tablero HTML, Excel, mapa, resumen) a un tomador de decisiones con el pitch de Kin — abrir con un hook (el dato que más importa, con número), comparar cara a cara de forma justa, poco texto y mucho visual — más las reglas de UX/UI aprendidas con el usuario (pares, nada que se lea como 0, controles donde tienen efecto, colores distinguibles, tooltips dentro de la ventana, leyendas que coinciden) y el QA antes de entregar. Usar al construir o corregir cualquier tablero, Excel, mapa o reporte, o cuando pidan 'más visual', 'para gerencia', 'pitch', 'hook' o 'que se entienda'."
---

# Presentar con pitch y hook (usuario, 2026-10-30)

Marca: skill `brand-guidelines-kin` (vía `src/tools/marca.py`). UX: skill `impeccable` (modo *Operate* para tableros).
Ejecutivo en texto: skill `executive-brief-hook`.

## El pitch, en orden

1. **Hook**: lo primero que se ve es el dato que cambia la decisión, con número y comparación
   ("CDMX tiene 3.9× más PdV, pero cada tienda compradora de Mérida vende $35K vs $21K"). Frases-dato cortas, no párrafos.
2. **Cara a cara**: los mismos indicadores lado a lado para lo que se compara (ciudades, embotelladores, cadenas).
3. **Dónde y quién**: mapa, top de franquicias/tiendas, qué vende cada uno.
4. **Cómo va**: tendencia y crecimiento contra el mismo periodo del año anterior.
5. **Detalle**: tablas filtrables y hoja de detalle en el Excel (con fórmulas vivas).
6. **Qué falta**: lo POR VERIFICAR dicho con claridad (sin gold, sin venta del mes, mes incompleto).

## Reglas de comparación (no negociables)

- **Justa**: solo indicadores que existen en todos los lados; si a uno le falta (potencial, venta del mes), se quita
  de la comparación, no se pone 0 ni "solo X".
- **En pares**: la misma cosa (cadena, franquicia, segmento) con una barra por lado, siempre en el mismo orden y color.
  Nunca listas mezcladas tipo "OXXO · Mérida, OXXO · CDMX".
- **Lo que no coincide va aparte**: si los catálogos no son iguales, top propio de cada lado.
- **Unidades claras**: diferencias en las mismas unidades (en tasas, puntos); evitar índices tipo "0.21x".
- **Estimaciones = referencia, no predicción**: una oportunidad calculada (p. ej. tiendas que nunca compraron × promedio
  de las que sí compran de su franquicia en su ciudad) se rotula "Referencia" y se explica cómo se calculó; si no hay
  con qué compararla, se dice ("sin compradores para comparar"), nunca se inventa.
- **Lo agregado manda**: franquicias sumadas (todos los OXXO), no tienda por tienda, salvo que se pida.
- **Reparto al 100%** cuando la pregunta es "qué vende": % del revenue de esa cadena por producto, no % de tiendas
  (se repite y no dice nada). Umbral: el top solo con ≥ 1%; el resto ≥ 1% en "Resto de {análisis} (N productos)" y
  los < 1% avisados aparte; los tooltips listan cada uno con su % y $.

## Reglas de UX/UI aprendidas

- **Nada que se lea como 0** (0%, 0.0%, $0, "—" repetido): no se dibuja; si no hay dato, un aviso que diga por qué
  ("Costco no tiene venta de hydration en los datos", "Circle K no tiene tiendas en Mérida").
- **Las gráficas no caen a 0 por falta de dato**: mes sin dato corta la línea; mes incompleto no se grafica (aviso).
- **Controles donde tienen efecto**: un selector solo vive en la sección que cambia (p. ej. "Ver: Territorio de operación | Por ciudad" dentro de
  Resumen y Franquicias), con su propio estado. Filtros técnicos activos pero ocultos.
- **Todo cuadra con un solo total**: se cuentan todos los PdV en todas partes (no "solo tiendas" en unas cifras y
  todos en otras); si una cadena tiene 9 PdV, dice 9 en KPIs, tablas, Nunca compraron y Excel (usuario, 2026-11-02).
- **Etiquetas claras**: nombres de negocio ("Independientes", "Otras cadenas", "Resto de hydration"), sin jerga,
  sin duplicados; lo que no se entiende se explica en el tooltip del botón.
- **Crecimiento con color** (usuario, 2026-11-02): en KPIs, tarjetas y hook, verde si sube, rojo si baja, blanco si es
  0.0% (única excepción a la paleta Kin; tablas y barras siguen amarillo/gris).
- **Comparar ciudades en vertical**: una fila por ciudad (punto de color + nombre + valor), nunca "A · B" en una línea;
  igual el subtítulo del periodo.
- **Periodo corto**: "Oct 2025 – Ago 2026 vs PY" (PY = mismos meses del año anterior), no "202510–202608 vs 202410–202508".
- **Todo filtro de cadenas o franquicias** (encabezado, Mapa, Tendencias, Productos, búsqueda de Franquicias) lleva
  **"Todas"** al final (se marca cuando están todas) y **"✕ Limpiar"**, que solo aparece si hay algo elegido y vuelve al
  estado inicial.
- **Selector de vista**: "Ver: Territorio de operación | Por ciudad" (no "Juntos/Separados").
- **Nunca compraron también en el Resumen** (tablero: tarjeta del hook + KPI con enlace a su pestaña; Excel: filas en
  Resumen/Comparativo y hallazgo), no solo en su pestaña u hoja.
- **Número y leyenda coinciden** (si el número es tiendas, la leyenda habla de tiendas).
- **Colores distinguibles**: oscuro = amarillo → blanco → gris 3 → gris 2; claro (Excel) = amarillo → negro → gris 3 →
  gris 2 con borde oscuro. Nunca negro y gris 4 juntos. Ciudad/lado 1 amarillo, lado 2 blanco (HTML) o negro (Excel).
- **Tooltips** dentro de la ventana (se miden; arriba/izquierda si no caben).
- **Un clic no rompe nada**: cada control redibuja todo lo que depende de él (no solo la mitad de la sección).
- **Mapas**: dividido por lado (uno por ciudad), selector de cadena, tarjetas de resumen, top 5 clicable que vuela al
  punto; puntos en el centro de su celda H3 nivel 10 (~70 m), nunca coordenadas exactas; parar animaciones antes de
  redibujar y encuadrar solo si el mapa se ve (si no, Leaflet truena con `_leaflet_pos`). Una sección con mapas arma su
  estructura UNA vez y después solo actualiza contenido (ordenar una tabla no puede recrear los contenedores del mapa:
  se pierde el mapa; y cerrar mapas con `map.remove()` deja redibujados pendientes → `clearRect` de undefined).
- **Excel con el pitch del usuario**: banner negro filas 1–5 con logo, pestaña amarilla en el resumen, cabeceras 36 pt,
  cebra, bordes finos, fórmulas vivas; sin filas vacías ni columnas que no aplican; comparativos horizontales con banda
  de color por grupo y diferencias resaltadas (amarillo = lado 1 mayor, gris = lado 2 mayor).
- **Responsive**: columnas `minmax(0,1fr)`, nada se sale a la derecha; en JS no nombrar funciones globales `top`.

## QA antes de entregar (siempre)

1. Excel: recalcular con LibreOffice headless y buscar `#VALUE!`, `#REF!`, `#DIV/0!`, `#NAME?`; revisar una hoja
   renderizada a PNG si cambió el diseño.
2. Tablero: clic automático en **todos** los botones de **todas** las pestañas y vistas (registrar errores y lo que
   desaparece), cambio rápido de pestaña durante animaciones, tooltips en las 4 esquinas, sin desbordes horizontales.
3. Privacidad: ninguna coordenada exacta de PdV en el HTML (el código aborta si aparece).
4. Decir qué se verificó y qué no (p. ej. "gráficas del Excel no vistas renderizadas").
