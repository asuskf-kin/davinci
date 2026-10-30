"""UN solo Excel (todos los embotelladores juntos) que replica el pitch y la estructura del Excel de referencia
OXXO_Walmart_Costco_Nacional: banner negro (filas 1–5), pestañas, cabeceras de 36 pt, cebra EFEFEE, bordes D4D5D6,
bloque de KPIs, 'Resumen por cadena', Top 10 estados/municipios con barras apiladas y 'Resumen para el tomador de
decisiones'. Hojas en el mismo orden: Resumen · Detalle PdV · Por zona · Por estado · Por municipio; lo nuevo (columna
Embotellador, venta del análisis, estatus, potencial, Tendencia mensual y Productos) va DESPUÉS de lo del original.
Todo con fórmulas vivas sobre 'Detalle PdV'; las columnas se ubican por nombre, nunca por letra fija.
"""
import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from src.config import cadenas as cfg
from src.tools import inegi, marca

NEGRO, NEGRO2, AMARILLO, ZEBRA, LINEA, GRIS, GRIS2 = "141417", "222326", "E5FF01", "EFEFEE", "D4D5D6", "999EA6", "D4D5D6"
DINERO, DINERO2 = '\\$#,##0;"($"#,##0\\);\\-', "\\$#,##0.00"
PCT, NUM, DEC = "0.0%;\\(0.0%\\);\\-", "#,##0;\\(#,##0\\);\\-", "#,##0.0;\\(#,##0.0\\);\\-"
FILA0 = 8
PAISES = {"mx": "MÉXICO", "gt": "GUATEMALA", "co": "COLOMBIA", "pe": "PERÚ", "ar": "ARGENTINA", "br": "BRASIL"}
CORTOS = {"México": "Edomex", "Ciudad de México": "CDMX", "Veracruz de Ignacio de la Llave": "Veracruz",
          "Michoacán de Ocampo": "Michoacán", "Coahuila de Zaragoza": "Coahuila"}
LIN = Side(style="thin", color=LINEA)
CAJA = Border(left=LIN, right=LIN, top=LIN, bottom=LIN)


def _f(nombre="Albert Sans", size=10, bold=False, color=None):
    return Font(name=nombre, size=size, bold=bold, color=color)


def _fill(c):
    return PatternFill("solid", fgColor=c)


def banner(ws, col, ultima_col, etiqueta, titulo, sub):
    """Filas 1–5 en negro con etiqueta, título amarillo y subtítulo (como el original)."""
    ws.sheet_view.showGridLines = False
    for r in range(1, 6):
        for c in range(1, ultima_col + 1):
            ws.cell(r, c).fill = _fill(NEGRO)
    ws.cell(2, col, etiqueta).font = _f(size=9, bold=True, color=GRIS)
    ws.cell(3, col, titulo).font = _f("Space Grotesk", 18, True, AMARILLO)
    ws.cell(4, col, sub).font = _f(size=9, color=GRIS2)
    ws.row_dimensions[3].height = 25.5
    img = Image(io.BytesIO(marca.logo_png("formal", "oscuro", 120)))
    img.height, img.width = 30, int(30 * img.width / img.height)
    ws.add_image(img, f"{L(max(ultima_col - 2, col + 3))}2")


def cabecera(ws, fila, col, textos, amarillas=()):
    for j, t in enumerate(textos, col):
        c = ws.cell(fila, j, t)
        am = t in amarillas
        c.font = _f("Space Grotesk", 10, True, NEGRO if am else "FFFFFF")
        c.fill = _fill(AMARILLO if am else NEGRO)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = CAJA
    ws.row_dimensions[fila].height = 36


def celda(ws, f, c, v, fmt=None, *, fuente=None, centro=False, zebra=None):
    x = ws.cell(f, c, None if (not isinstance(v, str) and pd.isna(v)) else v)
    x.font = fuente or _f()
    x.border = CAJA
    if fmt:
        x.number_format = fmt
    if centro:
        x.alignment = Alignment(horizontal="center")
    if zebra if zebra is not None else (f % 2 == 1 and f > FILA0):
        x.fill = _fill(ZEBRA)
    return x


def titulo_seccion(ws, fila, col, texto):
    c = ws.cell(fila, col, texto)
    c.font = _f("Space Grotesk", 13, True)
    c.border = Border(bottom=Side(style="medium", color=AMARILLO))


def _columnas_detalle(d, hay_ingreso, hay_potencial, analisis):
    """[(cabecera, serie o plantilla de fórmula, formato)] — primero las del original (A..U), luego las nuevas."""
    A = analisis.capitalize()
    cols = [("pos_id", d["pos_id"], None), ("Cliente", d["cliente"], None), ("Cadena", d["cadena"], None),
            ("Formato", d["formato"], None), ("Tipo de punto", d["tipo_punto"], None), ("Zona", d["zona"], None),
            ("Estado", d["estado"], None), ("Municipio", d["municipio"], None), ("Clave INEGI (CVEGEO)", d["cvegeo"], None),
            ("Latitud", d["lat"], "0.000000"), ("Longitud", d["lon"], "0.000000"),
            ("Ver en mapa", '=HYPERLINK("https://www.google.com/maps?q="&{Latitud}{r}&","&{Longitud}{r},"Abrir mapa")', None),
            ("Channel_Group", d["grupo"], None), ("BU_Channel", d["subcanal"], None)]
    if hay_ingreso:
        cols += [("Ingreso bruto ($)", d["ingreso"], DINERO), ("Cajas unitarias", d["cajas"], DEC),
                 ("Precio por caja ($)", '=IF(N({Cajas unitarias}{r})=0,"",{Ingreso bruto ($)}{r}/{Cajas unitarias}{r})', DINERO2),
                 ("Descuento ($)", d["descuento"], DINERO),
                 ("% descuento", '=IF(N({Ingreso bruto ($)}{r})=0,"",{Descuento ($)}{r}/{Ingreso bruto ($)}{r})', PCT),
                 ("Venta > 0", '=IF({Ingreso bruto ($)}{r}="","",IF({Ingreso bruto ($)}{r}>0,"Sí","No"))', None)]
    cols.append(("Asignación geográfica", d["asignacion"], None))
    # --- nuevo (después de lo del original) ---
    rv, ra, cj = f"Revenue {A} 12m ($)", f"Revenue {A} 12m anterior ($)", f"Cajas {A} 12m"
    cols += [("Embotellador", d["embotellador"], None)] + ([("Territorio", d["territorio"], None)] if "territorio" in d else [])
    cols += [("Franquicia", d["franquicia"], None), ("Nombre limpio", d["nombre_limpio"], None),
             ("Método franquicia", d["metodo_franquicia"], None), ("Población municipio", d["poblacion"], NUM),
             (rv, d["revenue_12m"], DINERO), (ra, d["revenue_12m_anterior"], DINERO),
             (f"Crecimiento {A}", f'=IF({{{ra}}}{{r}}=0,"",{{{rv}}}{{r}}/{{{ra}}}{{r}}-1)', PCT), (cj, d["cajas_12m"], DEC),
             (f"Precio por caja {A} ($)", f'=IF({{{cj}}}{{r}}=0,"",{{{rv}}}{{r}}/{{{cj}}}{{r}})', DINERO2),
             (f"Compra {A}", f'=IF({{{rv}}}{{r}}>0,"Sí","No")', None), (f"Estatus {A}", d["estatus"], None),
             ("Primer mes de compra", d["primer_mes"], None), ("Último mes de compra", d["ultimo_mes"], None),
             ("Meses con compra", d["meses_con_compra"], NUM)]
    if hay_potencial:
        cols += [("Prioridad (modelo)", d["prioridad"], None), ("Potencial (cajas/mes)", d["potencial_cajas_mes"], DEC)]
    cols.append(("Alertas", d["alertas"].replace("", None), None))
    return cols


ANCHOS_DETALLE = {"pos_id": 12, "Cliente": 34, "Cadena": 10, "Formato": 20, "Tipo de punto": 26, "Zona": 17, "Estado": 24,
                  "Municipio": 26, "Clave INEGI (CVEGEO)": 12, "Latitud": 11, "Longitud": 11, "Ver en mapa": 12,
                  "Channel_Group": 13, "BU_Channel": 22, "Ingreso bruto ($)": 15, "Cajas unitarias": 12,
                  "Precio por caja ($)": 11, "Descuento ($)": 13, "% descuento": 11, "Venta > 0": 9,
                  "Asignación geográfica": 20, "Embotellador": 13, "Nombre limpio": 30, "Método franquicia": 20, "Alertas": 40}


def _y(nombres):
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _detalle(wb, d, hay_ingreso, hay_potencial, analisis, etiqueta, embs):
    ws = wb.create_sheet("Detalle PdV")
    ws.sheet_properties.tabColor = NEGRO2
    cols = _columnas_detalle(d, hay_ingreso, hay_potencial, analisis)
    banner(ws, 2, len(cols), etiqueta, f"Detalle de PdV — {_y(list(dict.fromkeys(d['cadena'])))} (nacional)",
           f"Un renglón por punto de venta ({_y(embs)}) · lat/long del archivo · estado y municipio INEGI asignados por polígono")
    letra = {h: L(j) for j, (h, _, _) in enumerate(cols, 1)}
    cabecera(ws, FILA0 - 1, 1, [h for h, _, _ in cols], amarillas=("Estado", "Municipio"))
    azul = _f(color="0563C1")
    for j, (h, v, fmt) in enumerate(cols, 1):
        if isinstance(v, str):
            p = v.replace("{r}", "\0")
            for k, l in letra.items():
                p = p.replace("{" + k + "}", l)
            valores = [p.replace("\0", str(FILA0 + i)) for i in range(len(d))]
        else:
            valores = v.tolist()
        for i, x in enumerate(valores):
            celda(ws, FILA0 + i, j, x, fmt, fuente=azul if h == "Ver en mapa" else None)
        ws.column_dimensions[L(j)].width = ANCHOS_DETALLE.get(h, 15)
    fin = FILA0 + len(d) - 1
    ws.freeze_panes = f"C{FILA0}"
    ws.auto_filter.ref = f"A{FILA0 - 1}:{L(len(cols))}{fin}"
    return letra, fin


def _r(letra, h, fin):
    return f"'Detalle PdV'!${letra[h]}${FILA0}:${letra[h]}${fin}"


def _agregado(wb, nombre, letra, fin, claves, valores, cadenas, hay_ingreso, hay_potencial, analisis, etiqueta, titulo, sub,
              llave_detalle, extra=(), congelar="B8", anchos=None):
    """Una fila por clave (ordenadas por # PdV): columnas del original (conteos, total, %, ingreso, prom.) y luego las
    del análisis; fila TOTAL; escala de color en los conteos por cadena (como el original)."""
    ws = wb.create_sheet(nombre)
    ws.sheet_properties.tabColor = NEGRO2
    A = analisis.capitalize()
    met, corta = ("Ingreso bruto ($)", "Ingreso") if hay_ingreso else (f"Revenue {A} 12m ($)", f"Revenue {A}")
    nk, nc = len(claves), len(cadenas)
    cab = [h for h, _ in claves] + cadenas + ["Total PdV", "% del total", "% acumulado"] \
        + [f"{corta} {c} ($)" for c in cadenas] + [f"{corta} total ($)", f"% {corta.lower()}"] \
        + [f"{corta} prom. {c} por PdV ($)" for c in cadenas]
    cab += ([f"Revenue {A} 12m ($)"] if hay_ingreso else []) + [f"Revenue {A} 12m anterior ($)", f"Crecimiento {A}",
                                                                 f"PdV que compran {A}", f"% que compran {A}"] \
        + (["Potencial (cajas/mes)"] if hay_potencial else []) + [h for h, _, _ in extra]
    banner(ws, 2, len(cab) + 1, etiqueta, titulo, sub)
    cabecera(ws, FILA0 - 1, 1, cab, amarillas=("Total PdV",))
    tot = FILA0 + len(valores)
    cT, c0 = nk + nc + 1, nk + nc + 4
    cI = c0 + nc
    col = {h: j for j, h in enumerate(cab, 1)}
    rv, ra, pc = col.get(f"Revenue {A} 12m ($)", cI), col[f"Revenue {A} 12m anterior ($)"], col[f"PdV que compran {A}"]
    # con ingreso del mes, el denominador del promedio por PdV son los PdV que traen ingreso
    den = (lambda r, j, crit, c: f'COUNTIFS({crit},{_r(letra, "Cadena", fin)},"{c}",{_r(letra, met, fin)},"<>")') if hay_ingreso \
        else (lambda r, j, crit, c: f"{L(nk + 1 + j)}{r}")
    clave_f = _f("Space Grotesk", 10, True, NEGRO)
    for i, fila in enumerate(valores.to_dict("records")):
        r = FILA0 + i
        for j, (_, k) in enumerate(claves, 1):
            celda(ws, r, j, fila[k], fuente=clave_f if j == 1 else None)
        crit = f"{_r(letra, llave_detalle, fin)},$A{r}"
        for j, c in enumerate(cadenas):
            celda(ws, r, nk + 1 + j, f'=COUNTIFS({crit},{_r(letra, "Cadena", fin)},"{c}")', NUM)
        celda(ws, r, cT, f"=SUM({L(nk + 1)}{r}:{L(nk + nc)}{r})", NUM)
        celda(ws, r, cT + 1, f"={L(cT)}{r}/${L(cT)}${tot}", PCT)
        celda(ws, r, cT + 2, f"=SUM(${L(cT + 1)}${FILA0}:{L(cT + 1)}{r})", PCT)
        for j, c in enumerate(cadenas):
            celda(ws, r, c0 + j, f'=SUMIFS({_r(letra, met, fin)},{crit},{_r(letra, "Cadena", fin)},"{c}")', DINERO)
        celda(ws, r, cI, f"=SUM({L(c0)}{r}:{L(c0 + nc - 1)}{r})", DINERO)
        celda(ws, r, cI + 1, f"=IF(${L(cI)}${tot}=0,0,{L(cI)}{r}/${L(cI)}${tot})", PCT)
        for j, c in enumerate(cadenas):
            celda(ws, r, cI + 2 + j, f"=IFERROR({L(c0 + j)}{r}/{den(r, j, crit, c)},0)", DINERO)
        if hay_ingreso:
            celda(ws, r, rv, f"=SUMIFS({_r(letra, f'Revenue {A} 12m ($)', fin)},{crit})", DINERO)
        celda(ws, r, ra, f"=SUMIFS({_r(letra, f'Revenue {A} 12m anterior ($)', fin)},{crit})", DINERO)
        celda(ws, r, ra + 1, f'=IF({L(ra)}{r}=0,"",{L(rv)}{r}/{L(ra)}{r}-1)', PCT)
        celda(ws, r, pc, f'=COUNTIFS({crit},{_r(letra, f"Compra {A}", fin)},"Sí")', NUM)
        celda(ws, r, pc + 1, f"=IF({L(cT)}{r}=0,0,{L(pc)}{r}/{L(cT)}{r})", PCT)
        if hay_potencial:
            celda(ws, r, col["Potencial (cajas/mes)"], f"=SUMIFS({_r(letra, 'Potencial (cajas/mes)', fin)},{crit})", DEC)
        for h, k, fmt in extra:
            celda(ws, r, col[h], k(r, col) if callable(k) else fila[k], fmt)
    # TOTAL (fila amarilla)
    celda(ws, tot, 1, "TOTAL", zebra=False)
    for j in range(2, nk + 1):
        celda(ws, tot, j, None, zebra=False)
    for j in list(range(nk + 1, cT + 2)) + list(range(c0, cI + 2)) + [col[h] for h in cab if h.startswith(("Revenue", "PdV que", "Potencial", "Población"))]:
        celda(ws, tot, j, f"=SUM({L(j)}{FILA0}:{L(j)}{tot - 1})", ws.cell(FILA0, j).number_format, zebra=False)
    for j, c in enumerate(cadenas):
        dd = f'COUNTIFS({_r(letra, "Cadena", fin)},"{c}",{_r(letra, met, fin)},"<>")' if hay_ingreso else f"{L(nk + 1 + j)}{tot}"
        celda(ws, tot, cI + 2 + j, f"=IFERROR({L(c0 + j)}{tot}/{dd},0)", DINERO, zebra=False)
    celda(ws, tot, ra + 1, f'=IF({L(ra)}{tot}=0,"",{L(rv)}{tot}/{L(ra)}{tot}-1)', PCT, zebra=False)
    celda(ws, tot, pc + 1, f"=IF({L(cT)}{tot}=0,0,{L(pc)}{tot}/{L(cT)}{tot})", PCT, zebra=False)
    for h, k, fmt in extra:
        if callable(k):
            celda(ws, tot, col[h], k(tot, col), fmt, zebra=False)
    for j in range(1, len(cab) + 1):
        ws.cell(tot, j).font = _f("Space Grotesk", 10, True, NEGRO)
        ws.cell(tot, j).fill = _fill(AMARILLO)
    for j in range(nk + 1, nk + nc + 1):
        ws.conditional_formatting.add(f"{L(j)}{FILA0}:{L(j)}{tot - 1}",
                                      ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max", end_color=GRIS))
    for j in range(1, len(cab) + 1):
        ws.column_dimensions[L(j)].width = (anchos or {}).get(j, 15 if j > nk + nc else 10)
    ws.freeze_panes = congelar
    ws.auto_filter.ref = f"A{FILA0 - 1}:{L(len(cab))}{tot - 1}"
    return tot, nk + 1


def _resumen(wb, d, letra, fin, cadenas, hay_ingreso, hay_potencial, periodos, h, analisis, embs, etiqueta,
             fuente, est_tot, mun_tot, est_c0, mun_c0):
    ws = wb["Resumen"]
    ws.sheet_properties.tabColor = AMARILLO
    A, nc = analisis.capitalize(), len(cadenas)
    g0 = nc + 4                       # columna de los Top 10 (G con 3 cadenas, como el original)
    ultima = g0 + nc + 1
    banner(ws, 5 if nc == 3 else 2, ultima + 1, etiqueta, f"{' · '.join(cadenas)}: cuántos son y dónde están",
           f"Fuente: {fuente} · estado/municipio INEGI por lat/long · ventas {A} " + " · ".join(f"{e} {p}" for e, p in periodos.items()))
    cad, tipo, emb = _r(letra, "Cadena", fin), _r(letra, "Tipo de punto", fin), _r(letra, "Embotellador", fin)
    for c, w in {"A": 2, "B": 40, L(g0 - 1): 4, L(g0): 28, L(ultima + 1): 2}.items():
        ws.column_dimensions[c].width = w
    for j in range(3, 3 + nc):
        ws.column_dimensions[L(j)].width = 30
    for j in range(g0 + 1, ultima + 1):
        ws.column_dimensions[L(j)].width = 12

    # Bloque de KPIs (filas 7–11)
    # Bloque de KPIs: TIENDAS (sin comedores, oficinas ni CEDIS), igual que el tablero; número y leyenda coinciden
    lugares = "ciudades" if "territorio" in d else "estados"
    hoja_l = "Por territorio" if "territorio" in d else "Por estado"
    titulo_seccion(ws, 7, 2, "Número de tiendas")
    ws.cell(9, 2, f"TOTAL {nc} CADENAS").font = _f(size=9, bold=True, color=GRIS)
    x = ws.cell(10, 2, f'=COUNTIFS({tipo},"Tienda")')
    x.font, x.number_format, x.alignment = _f("Space Grotesk", 26, True), NUM, Alignment(horizontal="center")
    ws.cell(11, 2, f"=COUNTA('Por municipio'!C{FILA0}:C{mun_tot - 1})&\" municipios · \"&COUNTA('{hoja_l}'!A{FILA0}:A{est_tot - 1})&\" {lugares}\"").font = _f(size=9, color=GRIS)
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for j, c in enumerate(cadenas, 3):
        fondo = _fill(NEGRO if j == 3 else NEGRO2)
        n_est = d.loc[d["cadena"].eq(c) & d["tipo_punto"].eq("Tienda"), "territorio" if "territorio" in d else "estado"].nunique()
        for r, v, fnt, fmt in ((9, c.upper(), _f(size=9, bold=True, color=GRIS), None),
                               (10, f'=COUNTIFS({cad},"{c}",{tipo},"Tienda")', _f("Space Grotesk", 26, True, AMARILLO if j == 3 else "FFFFFF"), NUM),
                               (11, f"tiendas · {n_est} {lugares}", _f(size=9, color=GRIS2), None)):
            x = ws.cell(r, j, v)
            x.font, x.fill, x.alignment = fnt, fondo, centro
            if fmt:
                x.number_format = fmt
    ws.row_dimensions[10].height = 39.75

    # Resumen por cadena (filas 15+)
    titulo_seccion(ws, 14, 2, "Resumen por cadena")
    cabecera(ws, 15, 2, ["Indicador"] + cadenas, amarillas=(cadenas[0],))
    filas = []                                           # (texto, plantilla o callable(j, c), formato, negrita, grande)
    add = lambda *x: filas.append(x)
    add("# PdV", '=COUNTIFS({cad},"{c}")', NUM, True, True)
    grupo = _r(letra, "Territorio", fin) if "territorio" in d else emb
    for e in embs:
        add(f"   {e}", '=COUNTIFS({cad},"{c}",' + grupo + f',"{e}")', NUM, False, False)
    add("   de los cuales: tiendas", '=COUNTIFS({cad},"{c}",{tipo},"Tienda")', NUM, False, False)
    add("   comedores / corporativo / CEDIS / otros", '=COUNTIFS({cad},"{c}",{tipo},"<>Tienda")', NUM, False, False)
    zr = _r(letra, "Zona", fin)
    zonas = d.groupby(["embotellador", "zona"]).size()
    for (e, z), n in zonas[zonas >= 0.01 * len(d)].sort_values(ascending=False).items():
        add(f"   Zona {z} ({e})", '=COUNTIFS({cad},"{c}",' + zr + f',"{z}",' + emb + f',"{e}")', NUM, False, False)
    terr = "territorio" in d
    if not terr:
        add("# estados con presencia", lambda j, c: f"=COUNTIF('Por estado'!{L(est_c0 + j)}{FILA0}:{L(est_c0 + j)}{est_tot - 1},\">0\")", NUM, True, False)
    add("# municipios con presencia", lambda j, c: f"=COUNTIF('Por municipio'!{L(mun_c0 + j)}{FILA0}:{L(mun_c0 + j)}{mun_tot - 1},\">0\")", NUM, True, False)
    er, mr = _r(letra, "Estado", fin), _r(letra, "Clave INEGI (CVEGEO)", fin)

    def top(nivel, k):
        def f(j, c):
            e = d[d["cadena"] == c]
            g = (e.groupby(["cvegeo", "municipio", "estado"]) if nivel == "m" else e.groupby("estado")).size().sort_values(ascending=False)
            if k >= len(g):
                return "—"
            ll = g.index[k]
            if nivel == "m":
                return f'="{ll[1]}, {CORTOS.get(ll[2], ll[2])} ("&COUNTIFS({cad},"{c}",{mr},"{ll[0]}")&")"'
            return f'="{CORTOS.get(ll, ll)} ("&COUNTIFS({cad},"{c}",{er},"{ll}")&")"'
        return f
    for k in range(0 if terr else 3):
        add(f"Estado #{k + 1}", top("e", k), None, True, False)
    for k in range(3):
        add(f"Municipio #{k + 1}", top("m", k), None, True, False)

    def top3(j, c):
        e = d[d["cadena"] == c].groupby("estado").size().sort_values(ascending=False).index[:3]
        return "=(" + "+".join(f'COUNTIFS({cad},"{c}",{er},"{x}")' for x in e) + f')/COUNTIFS({cad},"{c}")'
    if not terr:
        add("% de PdV en los 3 estados top", top3, PCT, True, False)
    if hay_ingreso:
        ing, cj, ds, vt = (_r(letra, x, fin) for x in ("Ingreso bruto ($)", "Cajas unitarias", "Descuento ($)", "Venta > 0"))
        solo = "" if d["ingreso"].notna().all() else f" (solo {_y(sorted(d.loc[d['ingreso'].notna(), 'embotellador'].unique()))})"
        add(f"Ingreso bruto ($){solo}", f'=SUMIFS({ing},{{cad}},"{{c}}")', DINERO, True, False)
        add("Ingreso promedio por PdV ($)", f'=IFERROR({{r:Ingreso bruto ($){solo}}}/COUNTIFS({{cad}},"{{c}}",{ing},"<>"),0)', DINERO, True, True)
        add("Cajas unitarias", f'=SUMIFS({cj},{{cad}},"{{c}}")', NUM, True, False)
        add("Cajas por PdV", f'=IFERROR({{r:Cajas unitarias}}/COUNTIFS({{cad}},"{{c}}",{ing},"<>"),0)', DEC, True, False)
        add("Precio por caja ($)", f"=IF({{r:Cajas unitarias}}=0,0,{{r:Ingreso bruto ($){solo}}}/{{r:Cajas unitarias}})", DINERO2, True, False)
        add("% descuento sobre ingreso", f'=IF({{r:Ingreso bruto ($){solo}}}=0,0,SUMIFS({ds},{{cad}},"{{c}}")/{{r:Ingreso bruto ($){solo}}})', PCT, True, False)
        add("PdV sin venta en el mes", f'=COUNTIFS({{cad}},"{{c}}",{vt},"No")', NUM, True, False)
    # --- nuevo: el análisis (después de lo del original) ---
    rv, ra, cja, com, es = (_r(letra, x, fin) for x in (f"Revenue {A} 12m ($)", f"Revenue {A} 12m anterior ($)",
                                                         f"Cajas {A} 12m", f"Compra {A}", f"Estatus {A}"))
    add(f"PdV que compran {A}", f'=COUNTIFS({{cad}},"{{c}}",{com},"Sí")', NUM, True, False)
    add(f"% de PdV que compran {A}", f"=IF({{r:# PdV}}=0,0,{{r:PdV que compran {A}}}/{{r:# PdV}})", PCT, True, False)
    add(f"Revenue {A} 12m ($)", f'=SUMIFS({rv},{{cad}},"{{c}}")', DINERO, True, False)
    add(f"Revenue {A} 12m anterior ($)", f'=SUMIFS({ra},{{cad}},"{{c}}")', DINERO, True, False)
    add(f"Crecimiento {A} vs año anterior", f"=IF({{r:Revenue {A} 12m anterior ($)}}=0,0,{{r:Revenue {A} 12m ($)}}/{{r:Revenue {A} 12m anterior ($)}}-1)", PCT, True, False)
    add(f"Revenue {A} por PdV comprador ($)", f"=IF({{r:PdV que compran {A}}}=0,0,{{r:Revenue {A} 12m ($)}}/{{r:PdV que compran {A}}})", DINERO, True, True)
    add(f"Cajas {A} 12m", f'=SUMIFS({cja},{{cad}},"{{c}}")', NUM, True, False)
    add(f"Precio por caja {A} ($)", f"=IF({{r:Cajas {A} 12m}}=0,0,{{r:Revenue {A} 12m ($)}}/{{r:Cajas {A} 12m}})", DINERO2, True, False)
    add(f"PdV nuevos en {A} (6 meses)", f'=COUNTIFS({{cad}},"{{c}}",{es},"Nuevo*")', NUM, True, False)
    add("PdV que dejaron de comprar (3+ meses)", f'=COUNTIFS({{cad}},"{{c}}",{es},"Perdido*")', NUM, True, False)
    if hay_potencial:
        pot, pri = _r(letra, "Potencial (cajas/mes)", fin), _r(letra, "Prioridad (modelo)", fin)
        solo = "" if d["potencial_cajas_mes"].notna().any() and len(embs) == d.loc[d["potencial_cajas_mes"].notna(), "embotellador"].nunique() \
            else f" (solo {_y(sorted(d.loc[d['potencial_cajas_mes'].notna(), 'embotellador'].unique()))})"
        add(f"Potencial del modelo (cajas/mes){solo}", f'=SUMIFS({pot},{{cad}},"{{c}}")', NUM, True, False)
        add(f"PdV prioridad Very High + High{solo}", f'=COUNTIFS({{cad}},"{{c}}",{pri},"Very High")+COUNTIFS({{cad}},"{{c}}",{pri},"High")', NUM, True, False)
    # una fila que no aplica a todas las cadenas (p. ej. "Municipio #3" con "—") es ruido: fuera
    filas[:] = [x for x in filas if not callable(x[1]) or all(x[1](j, c) != "—" for j, c in enumerate(cadenas))]
    fila_de = {t: 16 + i for i, (t, *_) in enumerate(filas)}
    desde_analisis = [t for t, *_ in filas].index(f"PdV que compran {A}")
    sin_venta = {c for c in cadenas if not (d.loc[d["cadena"].eq(c), "revenue_12m"] > 0).any()}
    for i, (t, p, fmt, negrita, grande) in enumerate(filas):
        r = 16 + i
        zebra = i % 2 == 1
        celda(ws, r, 2, t, fuente=_f(bold=negrita), zebra=zebra)
        for j, c in enumerate(cadenas):
            if c in sin_venta and desde_analisis <= i and not t.startswith(("Potencial", "PdV prioridad")):
                celda(ws, r, 3 + j, f"Sin venta de {A} en los datos", fuente=_f(size=9, color=GRIS), centro=True, zebra=zebra)
                continue
            v = p(j, c) if callable(p) else p.replace("{cad}", cad).replace("{tipo}", tipo).replace("{c}", c)
            if not callable(p):
                for nom, fr in fila_de.items():
                    v = v.replace("{r:" + nom + "}", f"{L(3 + j)}{fr}")
            celda(ws, r, 3 + j, v, fmt, fuente=_f("Space Grotesk", 11, True) if grande else None, centro=True, zebra=zebra)
    ult = 16 + len(filas) - 1

    # Top 10 estados (14–25) y municipios (28–39), referencias a las hojas de agregados (como el original)
    primera = (14, "Por territorio", "Por territorio", est_c0, "Territorio") if terr else (14, "Top 10 estados", "Por estado", est_c0, "Estado")
    n1 = min(10, est_tot - FILA0)
    for fila_t, texto, hoja, c0, nombre in (primera, (28, "Top 10 municipios", "Por municipio", mun_c0, "Municipio")):
        titulo_seccion(ws, fila_t, g0, texto)
        cabecera(ws, fila_t + 1, g0, [nombre] + cadenas + ["Total"], amarillas=("Total",))
        for i in range(n1 if fila_t == 14 else 10):
            r, rr = fila_t + 2 + i, FILA0 + i
            z = i % 2 == 1
            v = f"='{hoja}'!A{rr}" if hoja != "Por municipio" else f"='{hoja}'!C{rr}&\", \"&'{hoja}'!B{rr}"
            celda(ws, r, g0, v, fuente=_f("Space Grotesk", 10, True), zebra=z)
            for j in range(nc + 1):
                celda(ws, r, g0 + 1 + j, f"='{hoja}'!{L(c0 + j)}{rr}", NUM, zebra=z)

    # Barras apiladas de los Top 10, debajo de la tabla más larga
    fila_g = max(ult, 39) + 3
    for k, (r0, n, titulo) in enumerate(((16, n1, f"PdV por {'territorio' if terr else 'estado (top 10)'}"), (30, 10, "PdV por municipio (top 10)"))):
        titulo_seccion(ws, fila_g - 1, 2 if k == 0 else g0, titulo)
        ch = _barras_kin("bar", stacked=True)
        for j in range(nc):
            ch.add_data(Reference(ws, min_col=g0 + 1 + j, min_row=r0 - 1, max_row=r0 + n - 1), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=g0, min_row=r0, max_row=r0 + n - 1))
        ch.x_axis.scaling.orientation = "maxMin"
        colorear(ch)
        ws.add_chart(ch, f"{L(2 if k == 0 else g0)}{fila_g}")

    # Resumen para el tomador de decisiones (etiqueta en B, texto en C:… combinado)
    r = fila_g + 21
    titulo_seccion(ws, r, 2, "Resumen para el tomador de decisiones")
    for i, (k, v) in enumerate(h.items()):
        rr = r + 1 + i
        x = celda(ws, rr, 2, k, fuente=_f("Space Grotesk", 10, True, NEGRO), zebra=False)
        x.fill = _fill(AMARILLO if i == 0 else ZEBRA)
        x.alignment = Alignment(vertical="top", wrap_text=True)
        y = celda(ws, rr, 3, v, zebra=False)
        y.alignment = Alignment(vertical="top", wrap_text=True)
        for j in range(4, ultima + 1):
            ws.cell(rr, j).border = CAJA
        ws.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=ultima)
        ws.row_dimensions[rr].height = max(48, 14 * (1 + len(v) // 140))
    ws.cell(r + len(h) + 2, 2, "kinanalytics.com").font = _f(size=9, color=GRIS)
    return filas, cad, tipo, desde_analisis


def _comparativo(wb, filas, cad, tipo, cadenas, terrs, ter, etiqueta, analisis, d, primera_fila_analisis):
    """Horizontal y sin gráficas: filas = indicadores; por cadena, columnas = cada territorio + Diferencia (1.º − 2.º).
    Cada cadena con su banda de color (la de las gráficas), territorios con su color (como el tablero) y la diferencia
    resaltada: amarillo = el 1.º territorio es mayor, gris = el 2.º es mayor. Cadena sin venta del análisis: un bloque con nota."""
    ws = wb.create_sheet("Comparativo")
    ws.sheet_properties.tabColor = AMARILLO
    ws.sheet_view.showGridLines = False
    A = analisis.capitalize()
    dos = len(terrs) == 2
    sub = terrs + ([f"Diferencia ({terrs[0]} − {terrs[1]})"] if dos else [])
    k = len(sub)
    usadas = [(t, p, fmt, neg, gr) for t, p, fmt, neg, gr in filas
              if not callable(p) and t.strip() not in terrs and not t.strip().startswith("Zona ")]
    desde = [t for t, *_ in usadas].index(primera_fila_analisis)
    compra = d["revenue_12m"] > 0
    vende = lambda c, t: bool((compra & d["cadena"].eq(c) & (d["territorio"].eq(t) if t else True)).any())
    ultima = 1 + k * len(cadenas)
    banner(ws, 2, ultima, etiqueta, f"{' vs '.join(terrs)}: cadena por cadena",
           (f"Diferencia = {terrs[0]} − {terrs[1]} en las mismas unidades (en porcentajes, puntos) · "
            f"amarillo = {terrs[0]} es mayor · gris = {terrs[1]} es mayor") if dos else "Cada cadena con sus territorios lado a lado")
    # bandas de cadena (paleta de las gráficas) y encabezados de territorio (colores del tablero)
    bandas = [(c.lstrip("#"), "141417" if c.upper() != "#141417" else "FFFFFF") for c in marca.SERIES_CLARO + [marca.GRIS4]]
    color_t = {terrs[0]: (AMARILLO, NEGRO)} | ({terrs[1]: (NEGRO, "FFFFFF")} if dos else {})
    cabecera(ws, 6, 1, ["Indicador"])
    ws.merge_cells(start_row=6, start_column=1, end_row=7, end_column=1)
    for q, c in enumerate(cadenas):
        c0 = 2 + q * k
        fondo, letra = bandas[q % len(bandas)]
        ws.merge_cells(start_row=6, start_column=c0, end_row=6, end_column=c0 + k - 1)
        x = ws.cell(6, c0, c)
        x.font, x.fill, x.alignment = _f("Space Grotesk", 12, True, letra), _fill(fondo), Alignment(horizontal="center", vertical="center")
        for j2 in range(k):
            ws.cell(6, c0 + j2).fill = _fill(fondo)
        for j2, h in enumerate(sub):
            x = ws.cell(7, c0 + j2, h)
            f_, l_ = color_t.get(h, (GRIS, NEGRO))
            x.font, x.fill = _f("Space Grotesk", 10, True, l_), _fill(f_)
            x.alignment, x.border = Alignment(horizontal="center", vertical="center", wrap_text=True), CAJA
            ws.column_dimensions[L(c0 + j2)].width = 15
        # borde grueso a la izquierda de cada cadena para separar bloques
    ws.row_dimensions[6].height, ws.row_dimensions[7].height = 24, 48
    ws.column_dimensions["A"].width = 42
    fila_de = {t: FILA0 + i for i, (t, *_) in enumerate(usadas)}
    for i, (t, p, fmt, neg, gr) in enumerate(usadas):
        r, z = FILA0 + i, i % 2 == 1
        celda(ws, r, 1, t, fuente=_f(bold=neg), zebra=z)
        for q, c in enumerate(cadenas):
            c0 = 2 + q * k
            if i >= desde and not vende(c, None):
                continue                                   # bloque "sin venta" (se combina abajo)
            for j2, v in enumerate(terrs):
                cj = c0 + j2
                if i >= desde and not vende(c, v):
                    celda(ws, r, cj, "Sin venta", fuente=_f(size=9, color=GRIS), centro=True, zebra=z)
                    continue
                f = p.replace("{cad}", cad).replace("{tipo}", tipo).replace("{c}", c).replace(f'{cad},"{c}"', f'{cad},"{c}",{ter},"{v}"')
                for nom, fr in fila_de.items():
                    f = f.replace("{r:" + nom + "}", f"{L(cj)}{fr}")
                celda(ws, r, cj, f, fmt, fuente=_f("Space Grotesk", 11, True) if gr else None, centro=True, zebra=z)
            if dos:
                a, b, dc = L(c0), L(c0 + 1), c0 + 2
                if fmt == PCT:
                    celda(ws, r, dc, f'=IF(AND(ISNUMBER({a}{r}),ISNUMBER({b}{r})),({a}{r}-{b}{r})*100,"—")',
                          '+0.0" pts";-0.0" pts";0.0" pts"', centro=True, zebra=z)
                else:
                    celda(ws, r, dc, f'=IF(AND(ISNUMBER({a}{r}),ISNUMBER({b}{r})),{a}{r}-{b}{r},"—")',
                          (fmt or NUM).replace(";\\-", ";0"), centro=True, zebra=z)
                ws.cell(r, dc).font = _f(bold=True)
    fin = FILA0 + len(usadas) - 1
    # cadenas sin venta del análisis: un solo bloque con la nota
    for q, c in enumerate(cadenas):
        if vende(c, None):
            continue
        c0, r0 = 2 + q * k, FILA0 + desde
        ws.merge_cells(start_row=r0, start_column=c0, end_row=fin, end_column=c0 + k - 1)
        x = ws.cell(r0, c0, f"{c} no tiene venta de {A} en los datos (ventas NSR)")
        x.font, x.fill = _f(size=10, bold=True, color=NEGRO), _fill(ZEBRA)
        x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    # diferencia resaltada: amarillo = 1.º mayor, gris = 2.º mayor
    if dos:
        for q in range(len(cadenas)):
            col = L(2 + q * k + 2)
            rango = f"{col}{FILA0}:{col}{fin}"
            ws.conditional_formatting.add(rango, FormulaRule(formula=[f"AND(ISNUMBER({col}{FILA0}),{col}{FILA0}>0)"], fill=_fill(AMARILLO)))
            ws.conditional_formatting.add(rango, FormulaRule(formula=[f"AND(ISNUMBER({col}{FILA0}),{col}{FILA0}<0)"], fill=_fill(GRIS2)))
    # separador vertical entre cadenas
    for q in range(len(cadenas)):
        c0 = 2 + q * k
        for r in range(6, fin + 1):
            x = ws.cell(r, c0)
            x.border = Border(left=Side(style="medium", color=NEGRO), right=x.border.right, top=x.border.top, bottom=x.border.bottom)
    ws.freeze_panes = "B8"


def _barras_kin(tipo, stacked=False):
    """Barras con ejes visibles (openpyxl los oculta por defecto), leyenda abajo y sin título encima del área."""
    ch = BarChart()
    ch.type, ch.width, ch.height, ch.gapWidth = tipo, 16, 9, 60
    if stacked:
        ch.grouping, ch.overlap = "stacked", 100
        ch.x_axis.scaling.orientation = "maxMin"
    ch.legend.position = "b"
    ch.x_axis.delete = ch.y_axis.delete = False
    ch.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill=GRIS2.lstrip("#") if GRIS2.startswith("#") else GRIS2, w=6350))
    ch.y_axis.numFmt = "#,##0"
    return ch


def colorear(ch, lineas=False):
    """Series con la paleta clara de la marca; barras con borde oscuro fino para que el gris claro se distinga del fondo."""
    for s, color in zip(ch.series, [x.lstrip("#") for x in marca.SERIES_CLARO + [marca.GRIS4]]):
        if lineas:
            s.graphicalProperties.line.solidFill = color
            s.graphicalProperties.line.width = 22000
        else:
            s.graphicalProperties.solidFill = color
            s.graphicalProperties.line.solidFill = NEGRO
            s.graphicalProperties.line.width = 3175


def _producto_cadena(wb, d, vv, cat, cadenas, ult12, analisis, etiqueta):
    """Qué vende cada franquicia y dónde: por franquicia y territorio/embotellador, cada producto como % del revenue (y de
    las cajas) de la franquicia — el bloque suma 100% en su fila TOTAL — con las tiendas que lo compraron en 12m."""
    from src.tools.comparativo import con_producto

    ws = wb.create_sheet("Producto × cadena")
    ws.sheet_properties.tabColor = NEGRO2
    g = "territorio" if "territorio" in d else "embotellador"
    tiendas = d[d["tipo_punto"].eq("Tienda") & d["cadena"].isin(cadenas)]
    v = pd.concat([vv[(vv["embotellador"] == e) & vv["month_445"].isin(m)] for e, m in ult12.items()])
    v = con_producto(v[(v["revenue"] > 0) & v["pos_id"].isin(tiendas["pos_id"])], cat)
    v = v.join(tiendas.set_index("pos_id")[["franquicia", "cadena"]], on="pos_id", rsuffix="_d")
    t = v.groupby([g, "cadena_d", "franquicia", "producto"]).agg(n=("pos_id", "nunique"), rev=("revenue", "sum"),
                                                                cj=("unit_cases", "sum")).reset_index()
    den = tiendas.groupby([g, "franquicia"]).size().rename("den")
    t = t.join(den, on=[g, "franquicia"])
    t = t.sort_values(["cadena_d", "franquicia", g, "rev"], ascending=[True, True, True, False])
    cols = ["Grupo", "Franquicia", g.capitalize(), "Producto", "Revenue 12m ($)", "% del revenue de la franquicia",
            "Cajas 12m", "% de las cajas de la franquicia", "Tiendas que lo compraron", "Tiendas de la franquicia"]
    banner(ws, 2, len(cols), etiqueta, "¿Qué vende cada cadena y dónde? · el 100% de lo que compra cada franquicia",
           f"Por franquicia y {g}: cómo se reparte el revenue (y las cajas) de {analisis} de la franquicia entre sus productos; "
           f"cada bloque suma 100% en su fila TOTAL · últimos 12 meses · solo tiendas · catálogo validado")
    cabecera(ws, FILA0 - 1, 1, cols, amarillas=("% del revenue de la franquicia",))
    C = {c: L(j) for j, c in enumerate(cols, 1)}
    r = FILA0
    for (cadena, franq, lugar), b in t.groupby(["cadena_d", "franquicia", g], sort=False):
        # lo que pesa menos de 0.1% del revenue de la franquicia se lee como 0%: va junto en una fila (el bloque sigue sumando 100%)
        chico = b["rev"] < 0.01 * b["rev"].sum()
        if chico.sum() > 1 or (chico.any() and len(b) > 1):
            resto = b[chico]
            b = pd.concat([b[~chico], pd.DataFrame([{**b.iloc[0].to_dict(), "producto": f"Resto de {analisis} ({len(resto)} productos con menos de 1% c/u)",
                                                    "rev": resto["rev"].sum(), "cj": resto["cj"].sum(), "n": None}])], ignore_index=True)
        r0 = r
        for x in b.itertuples(index=False):
            z = (r - r0) % 2 == 1
            fila = [cadena, franq, lugar, x.producto, x.rev, None, x.cj, None, x.n, x.den]
            for j, (c, val) in enumerate(zip(cols, fila), 1):
                celda(ws, r, j, val, DINERO if "($)" in c else DEC if c == "Cajas 12m" else NUM if "Tiendas" in c else None,
                      fuente=_f("Space Grotesk", 10, True) if j == 2 else None, zebra=z)
            rt = r0 + len(b)  # fila TOTAL del bloque
            celda(ws, r, 6, f"=IF({C['Revenue 12m ($)']}${rt}=0,0,{C['Revenue 12m ($)']}{r}/{C['Revenue 12m ($)']}${rt})", PCT, zebra=z)
            celda(ws, r, 8, f"=IF({C['Cajas 12m']}${rt}=0,0,{C['Cajas 12m']}{r}/{C['Cajas 12m']}${rt})", PCT, zebra=z)
            r += 1
        for j, val in enumerate([cadena, franq, lugar, f"TOTAL {franq} · {lugar}", f"=SUM(E{r0}:E{r - 1})", f"=SUM(F{r0}:F{r - 1})",
                                 f"=SUM(G{r0}:G{r - 1})", f"=SUM(H{r0}:H{r - 1})", None, int(b["den"].iat[0])], 1):
            x = celda(ws, r, j, val, [None, None, None, None, DINERO, PCT, DEC, PCT, None, NUM][j - 1], zebra=False)
            x.font, x.fill = _f("Space Grotesk", 10, True, NEGRO), _fill(GRIS2)
        r += 2
    fin = r - 2
    for j, c in enumerate(cols, 1):
        ws.column_dimensions[L(j)].width = 34 if c == "Producto" else 16
    ws.conditional_formatting.add(f"F{FILA0}:F{fin}", DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1, color="E5FF01"))
    ws.freeze_panes = f"E{FILA0}"
    ws.auto_filter.ref = f"A{FILA0 - 1}:{L(len(cols))}{fin}"
    if g == "territorio":
        _top_ciudad(wb, v, etiqueta)


def _top_ciudad(wb, u, etiqueta):
    """Top de productos de cada ciudad (los catálogos no coinciden: cada ciudad con su propio ranking)."""
    from src.tools.comparativo import top_ciudad

    t = top_ciudad(u)
    ws = wb.create_sheet("Top por ciudad")
    ws.sheet_properties.tabColor = NEGRO2
    cols = ["Ciudad", "#", "Producto", "Segmento", "Marca", "Revenue 12m ($)", "% del revenue de la ciudad", "Tiendas que lo compraron",
            "Franquicias que más lo venden"]
    banner(ws, 2, len(cols), etiqueta, "Top de productos en cada ciudad",
           "Cada ciudad con su propio ranking (los catálogos de cada embotellador no coinciden) · últimos 12 meses · solo tiendas")
    cabecera(ws, FILA0 - 1, 1, cols, amarillas=("Revenue 12m ($)",))
    for i, x in enumerate(t.itertuples(index=False)):
        for j, (val, fmt) in enumerate(zip([x.territorio, x.rank, x.producto, x.segmento, x.marca, x.rev, x.pct_rev, x.tiendas, x.franquicias],
                                           [None, NUM, None, None, None, DINERO, PCT, NUM, None]), 1):
            celda(ws, FILA0 + i, j, val, fmt, fuente=_f("Space Grotesk", 10, True) if j in (1, 2) else None)
    for j, w in enumerate([12, 6, 36, 18, 22, 16, 14, 14, 40], 1):
        ws.column_dimensions[L(j)].width = w
    ws.freeze_panes = f"D{FILA0}"
    ws.auto_filter.ref = f"A{FILA0 - 1}:{L(len(cols))}{FILA0 + len(t) - 1}"


def _tendencia(wb, vv, cadenas, analisis, etiqueta, incompletos):
    ws = wb.create_sheet("Tendencia mensual")
    ws.sheet_properties.tabColor = NEGRO2
    A = analisis.capitalize()
    v = vv[vv["cadena"].isin(cadenas)].assign(grupo=lambda x: x["cadena"])
    grupos = list(cadenas)
    embs = list(dict.fromkeys(v["embotellador"]))
    bloques = []
    for titulo, k, f, fmt in (("Revenue ($)", "revenue", "sum", DINERO), ("Cajas", "unit_cases", "sum", DEC),
                              ("PdV compradores", "pos_id", "nunique", NUM)):
        p = v.pivot_table(index="month_445", columns="grupo", values=k, aggfunc=f).reindex(columns=grupos).fillna(0)
        pe = v.pivot_table(index="month_445", columns="embotellador", values=k, aggfunc=f).reindex(columns=embs).fillna(0)
        bloques.append((titulo, pd.concat([p, pe], axis=1), fmt))
    cols_b = grupos + embs
    banner(ws, 2, 3 * (len(cols_b) + 3), etiqueta, f"Tendencia mensual de {A} por cadena y embotellador",
           "Ventas del catálogo validado de las cadenas del análisis · las columnas por "
           "embotellador suman todas las cadenas" + (f" · mes incompleto (fuera de las comparaciones): {incompletos}" if incompletos else ""))
    c0 = 1
    for titulo, p, fmt in bloques:
        titulo_seccion(ws, 6, c0, titulo)
        cabecera(ws, FILA0 - 1, c0, ["Mes"] + cols_b + ["Total"], amarillas=("Total",))
        for i, (mes, fila) in enumerate(p.iterrows()):
            r = FILA0 + i
            celda(ws, r, c0, mes, fuente=_f("Space Grotesk", 10, True))
            for j, g in enumerate(cols_b, 1):
                celda(ws, r, c0 + j, float(fila[g]), fmt)
            celda(ws, r, c0 + len(cols_b) + 1, f"=SUM({L(c0 + len(grupos) + 1)}{r}:{L(c0 + len(cols_b))}{r})", fmt)
        for j in range(len(cols_b) + 2):
            ws.column_dimensions[L(c0 + j)].width = 13
        if titulo.startswith("Revenue"):
            ch = LineChart()
            ch.title, ch.height, ch.width = f"Revenue {A} mensual por cadena", 8, 22
            ch.legend.position = "b"
            ch.add_data(Reference(ws, min_col=c0 + 1, max_col=c0 + len(grupos), min_row=FILA0 - 1, max_row=FILA0 - 1 + len(p)), titles_from_data=True)
            ch.set_categories(Reference(ws, min_col=c0, min_row=FILA0, max_row=FILA0 - 1 + len(p)))
            colorear(ch, lineas=True)
            ws.add_chart(ch, f"A{FILA0 + len(p) + 2}")
        c0 += len(cols_b) + 3
    ws.freeze_panes = f"B{FILA0}"


def _productos(wb, vv, cat, cadenas, ventanas, analisis, etiqueta):
    """ventanas: {embotellador: (meses_12m, meses_año_anterior)} — cada embotellador con su periodo comparable."""
    ws = wb.create_sheet("Productos")
    ws.sheet_properties.tabColor = NEGRO2
    A = analisis.capitalize()
    v = vv[vv["cadena"].isin(cadenas)].assign(grupo=lambda x: x["cadena"])
    u = pd.concat([v[(v["embotellador"] == e) & v["month_445"].isin(m)] for e, (m, _) in ventanas.items()])
    a = pd.concat([v[(v["embotellador"] == e) & v["month_445"].isin(m)] for e, (_, m) in ventanas.items()])
    k = ["embotellador", "product_id"]
    p = u.groupby(k)[["revenue"]].sum().rename(columns={"revenue": "Revenue 12m total ($)"})
    for g in cadenas:
        p[f"Revenue 12m {g} ($)"] = u[u["grupo"] == g].groupby(k)["revenue"].sum()
    p["Revenue 12m anterior ($)"] = a.groupby(k)["revenue"].sum()
    p["Cajas 12m"] = u.groupby(k)["unit_cases"].sum()
    p["PdV compradores 12m"] = u.groupby(k)["pos_id"].nunique()
    p = p.fillna(0).reset_index()
    if cat is not None:
        atr = cat.reset_index()[["embotellador", "product_id", "Descripción", "Segmento", "brand", "flavor", "container",
                                 "presentacion", "serving_type"]].rename(columns={
            "brand": "Marca", "flavor": "Sabor", "container": "Envase", "presentacion": "Presentación", "serving_type": "Servicio"})
        p = atr.merge(p, on=k, how="right")
    orden = ["embotellador", "product_id"] + [c for c in p.columns if c not in k and not c.startswith(("Revenue", "Cajas", "PdV"))] \
        + [f"Revenue 12m {g} ($)" for g in cadenas] + ["Revenue 12m total ($)", "Revenue 12m anterior ($)", "Cajas 12m", "PdV compradores 12m"]
    p = p[orden].rename(columns={"embotellador": "Embotellador"}).sort_values("Revenue 12m total ($)", ascending=False).reset_index(drop=True)
    cols = list(p.columns) + ["Crecimiento", "Precio por caja ($)", "% del revenue"]
    banner(ws, 2, len(cols), etiqueta, f"Productos de {A} por cadena (catálogo validado)",
           "Últimos 12 meses completos vs los mismos meses del año anterior (cada embotellador con su periodo) · solo productos aprobados (Sí)")
    cabecera(ws, FILA0 - 1, 1, cols, amarillas=("Revenue 12m total ($)",))
    letra = {c: L(j) for j, c in enumerate(cols, 1)}
    fin = FILA0 + len(p) - 1
    t, an, cj = (letra[x] for x in ("Revenue 12m total ($)", "Revenue 12m anterior ($)", "Cajas 12m"))
    for i, fila in enumerate(p.itertuples(index=False)):
        r = FILA0 + i
        for j, (c, x) in enumerate(zip(p.columns, fila), 1):
            celda(ws, r, j, x, DINERO if "($)" in c else DEC if c == "Cajas 12m" else NUM if "PdV" in c else None,
                  fuente=_f("Space Grotesk", 10, True) if c == "Embotellador" else None)
        celda(ws, r, len(p.columns) + 1, f'=IF({an}{r}=0,"",{t}{r}/{an}{r}-1)', PCT)
        celda(ws, r, len(p.columns) + 2, f"=IF({cj}{r}=0,0,{t}{r}/{cj}{r})", DINERO2)
        celda(ws, r, len(p.columns) + 3, f"={t}{r}/SUM(${t}${FILA0}:${t}${fin})", PCT)
    for j, c in enumerate(cols, 1):
        ws.column_dimensions[L(j)].width = 34 if c == "Descripción" else 20 if c in ("Marca", "Sabor") else 14
    ws.freeze_panes = f"D{FILA0}"
    ws.auto_filter.ref = f"A{FILA0 - 1}:{L(len(cols))}{fin}"


def escribir(ruta, base, vv, cat, infos, hs, analisis, nombres, pais):
    """base/vv/cat: todos los grupos juntos; infos/hs: {grupo (embotellador o territorio): info / hallazgos};
    nombres: cadenas a mostrar como columnas (p. ej. OXXO, Walmart, Otras cadenas, Independientes)."""
    cadenas = list(nombres)
    d = base[base["cadena"].isin(cadenas)].sort_values(["embotellador", "zona", "estado", "municipio", "cadena"]).reset_index(drop=True)
    cadenas = [c for c in cadenas if c in set(d["cadena"])]
    embs = list(infos)
    # comparación de territorios: solo indicadores que existen en todos (comparación justa); nacional: los que haya
    junta = all if "territorio" in d else any
    hay_ingreso = junta(i["tiene_ingreso"] for i in infos.values())
    hay_potencial = junta(i["tiene_potencial"] for i in infos.values())
    etiqueta = f"CANAL MODERNO · {' + '.join(e.upper() for e in embs)} {PAISES.get(pais, pais.upper())} · {analisis.upper()}"
    periodos = {e: f"{i['periodo']['desde']}–{i['periodo']['hasta']}" for e, i in infos.items()}
    fuente = " + ".join(i["fuentes"][0]["ruta"].split("/")[-1].rsplit(".", 1)[0] for i in infos.values())
    h = {k: " ".join(f"{e}: {hs[e][k]}" for e in embs if k in hs[e]) for k in dict.fromkeys(k for e in embs for k in hs[e])}
    wb = Workbook()
    wb.active.title = "Resumen"
    letra, fin = _detalle(wb, d, hay_ingreso, hay_potencial, analisis, etiqueta, embs)
    orden = lambda k: d.groupby(k).size().sort_values(ascending=False).index
    comun = (cadenas, hay_ingreso, hay_potencial, analisis, etiqueta)
    z = d.groupby("zona").agg(n=("pos_id", "size"), embotellador=("embotellador", lambda s: _y(sorted(s.unique())))).sort_values("n", ascending=False).reset_index()
    _agregado(wb, "Por zona", letra, fin, [("Zona", "zona")], z, *comun, "PdV por zona",
              f"Conteo e ingreso por cadena en cada zona comercial ({_y(embs)})", "Zona",
              extra=[("Embotellador", "embotellador", None)], anchos={1: 22})
    e = pd.DataFrame({"estado": orden("estado")})
    e["poblacion"] = e["estado"].map(inegi.poblacion_estados())
    dens = lambda r, col: f'=IF({L(col["Población (INEGI)"])}{r}=0,0,{L(col["Total PdV"])}{r}/{L(col["Población (INEGI)"])}{r}*100000)'
    extra = [("Población (INEGI)", "poblacion", NUM), ("PdV por 100 mil hab.", dens, DEC)]
    if "territorio" in d:
        t = d.groupby("territorio").agg(n=("pos_id", "size"), embotellador=("embotellador", "first")).reset_index()
        est_tot, est_c0 = _agregado(wb, "Por territorio", letra, fin, [("Territorio", "territorio")], t.sort_values("n", ascending=False),
                                    *comun, "PdV por territorio", "Los mismos indicadores para cada territorio (juntos = fila TOTAL)",
                                    "Territorio", extra=[("Embotellador", "embotellador", None)], anchos={1: 22})
    else:
        est_tot, est_c0 = _agregado(wb, "Por estado", letra, fin, [("Estado", "estado")], e, *comun, "PdV por estado",
                                    "Estado asignado con el Marco Geoestadístico INEGI · ordenado por número de PdV", "Estado",
                                    extra, anchos={1: 28})
    m = d.groupby(["cvegeo", "estado", "municipio"]).agg(n=("pos_id", "size"), zona=("zona", lambda s: s.mode().iat[0]),
                                                        poblacion=("poblacion", "first")).reset_index().sort_values("n", ascending=False)
    mun_tot, mun_c0 = _agregado(wb, "Por municipio", letra, fin, [("Clave INEGI", "cvegeo"), ("Estado", "estado"),
                                                                ("Municipio", "municipio"), ("Zona principal", "zona")],
                                m.drop(columns="n"), *comun, "PdV por municipio",
                                f"{len(m)} municipios con presencia · ordenado de mayor a menor número de PdV · fórmulas sobre Detalle PdV",
                                "Clave INEGI (CVEGEO)", extra, congelar="E8", anchos={1: 11, 2: 26, 3: 28, 4: 17})
    filas, cad, tipo, desde = _resumen(wb, d, letra, fin, cadenas, hay_ingreso, hay_potencial, periodos, h, analisis, embs, etiqueta,
                                fuente, est_tot, mun_tot, est_c0, mun_c0)
    if "territorio" in d:
        _comparativo(wb, filas, cad, tipo, cadenas, list(dict.fromkeys(d["territorio"])), _r(letra, "Territorio", fin),
                     etiqueta, analisis, d, filas[desde][0])
        wb.move_sheet("Comparativo", offset=-(len(wb.sheetnames) - 2))
        wb.move_sheet("Por territorio", offset=-(len(wb.sheetnames) - 3))
    # el mes del corte del extracto (incompleto) no entra en la tendencia: haría ver una caída que no existe
    # la hoja suma todos los grupos, así que se corta en el último mes completo de TODOS (si no, el total también "cae")
    corte = min(i["periodo"]["ultimo_completo"] for i in infos.values())
    _tendencia(wb, vv[vv["month_445"] <= corte], cadenas, analisis, etiqueta,
               ", ".join(f"{e} {i['periodo']['incompleto']}" for e, i in infos.items() if i["periodo"]["incompleto"]))
    _productos(wb, vv, cat, cadenas, {i.get("embotellador", e): (i["ult12"], [str(int(x) - 100) for x in i["ult12"]]) for e, i in infos.items()},
               analisis, etiqueta)
    _producto_cadena(wb, d, vv, cat, cadenas, {i.get("embotellador", e): i["ult12"] for e, i in infos.items()}, analisis, etiqueta)
    wb.save(ruta)
    return ruta
