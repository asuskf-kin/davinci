"""Excel para el tomador de decisiones (marca Kin, mismo pitch que el Excel de cadenas): resumen y hallazgos arriba,
detalle y listas de acción en hojas aparte. Estilo (banner, cabeceras, cebra, logo) desde cadenas_excel."""
import pandas as pd
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from src.tools import marca
from src.tools.cadenas_excel import _f, _fill, AMARILLO, banner, cabecera, celda, titulo_seccion

ETIQUETA = "CANAL MODERNO · CUSTOMER POTENTIAL · KIN ANALYTICS"
CUERPO = _f()


def _formato(col):
    c = col.lower()
    if c.startswith("%") or "crecimiento" in c and "cajas" not in c:
        return "0.0%;\\(0.0%\\);\\-"
    if "revenue" in c:
        return '\\$#,##0;"($"#,##0\\);\\-'
    if any(k in c for k in ("cajas", "potencial", "promedio", "meses con")):
        return "#,##0.0;\\(#,##0.0\\);\\-"
    return "#,##0;\\(#,##0\\);\\-"


def _tabla(ws, df, fila=7, col=1):
    """Escribe df con cabecera Kin (36 pt), cebra EFEFEE, bordes D4D5D6 y formatos por nombre de columna."""
    cabecera(ws, fila, col, [str(c) for c in df.columns])
    for i, fila_df in enumerate(df.itertuples(index=False), fila + 1):
        for j, v in enumerate(fila_df, col):
            celda(ws, i, j, v, _formato(df.columns[j - col]) if isinstance(v, (int, float)) else None, zebra=(i - fila) % 2 == 0)
    for j, nombre in enumerate(df.columns, col):
        largo = max([len(str(nombre)) * 0.8] + [len(str(v)) for v in df.iloc[:200, j - col]])
        ws.column_dimensions[get_column_letter(j)].width = min(max(10, largo + 2), 48)
    return fila + len(df)


def _hoja(wb, nombre, df, nota):
    ws = wb.create_sheet(nombre)
    ws.sheet_properties.tabColor = "222326"
    banner(ws, 2, max(len(df.columns), 8), ETIQUETA, nombre, nota)
    _tabla(ws, df, 7)
    ws.freeze_panes = "A8"
    ws.auto_filter.ref = f"A7:{get_column_letter(len(df.columns))}{7 + len(df)}"
    return ws


def escribir(ruta, r, hallazgos, cli, mens, prod, est, mun, sub, seg, pri, fuentes, segmentos, periodo):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    ws.sheet_properties.tabColor = AMARILLO
    t = r.T.reset_index().rename(columns={"index": "Indicador"})
    banner(ws, 2, len(t.columns) + 2, ETIQUETA, f"Customer Potential · {periodo['analisis']}: clientes, ventas y potencial",
           f"Periodo comparado (mismos meses vs año anterior): {periodo['ult12']} · revenue en MXN · fuente: datawarehouse (silver, bronze y gold)")
    titulo_seccion(ws, 6, 1, "Resumen por embotellador")
    fin = _tabla(ws, t, 7)
    for i in range(8, fin + 1):  # formato por fila (la tabla está traspuesta)
        for j in range(2, len(t.columns) + 1):
            ws.cell(i, j).number_format = _formato(ws.cell(i, 1).value)
            if ws.cell(i, j).value is None:
                ws.cell(i, j).value = "POR VERIFICAR"
    ws.column_dimensions["A"].width = 44
    fila = fin + 2
    titulo_seccion(ws, fila, 1, "Qué dicen los datos y qué hacer")
    for x in hallazgos:
        fila += 1
        c = ws.cell(fila, 1, "• " + x)
        c.font, c.alignment = CUERPO, Alignment(wrap_text=False)
    fila += 2
    titulo_seccion(ws, fila, 1, "Segmentos de clientes")
    for k, v in segmentos.items():
        fila += 1
        x = celda(ws, fila, 1, k, fuente=_f("Space Grotesk", 10, True), zebra=False)
        x.fill = _fill("EFEFEE")
        celda(ws, fila, 2, v, zebra=False)
    ws.cell(fila + 2, 1, "kinanalytics.com").font = _f(size=9, color="999EA6")

    ws_t = _hoja(wb, "Tendencia mensual", mens.assign(pct_filas_outlier=mens["filas_outlier"] / mens["filas"])
                 .rename(columns={"month_445": "mes", "pct_filas_outlier": "% filas outlier"}),
                 "Ventas del catálogo por mes (incluye outliers marcados; no se borra nada).")
    piv = mens.pivot_table(index="month_445", columns="embotellador", values="revenue", aggfunc="sum").reset_index()
    c0 = len(mens.columns) + 3
    _tabla(ws_t, piv.rename(columns={"month_445": "mes"}), 7, c0)
    ch = LineChart()
    ch.title, ch.y_axis.title, ch.height, ch.width = "Revenue mensual por embotellador", "Revenue", 9, 22
    ch.add_data(Reference(ws_t, min_col=c0 + 1, max_col=c0 + len(piv.columns) - 1, min_row=7, max_row=7 + len(piv)),
                titles_from_data=True)
    ch.set_categories(Reference(ws_t, min_col=c0, min_row=8, max_row=7 + len(piv)))
    for s_, color in zip(ch.series, marca.SERIES_CLARO):
        s_.graphicalProperties.line.solidFill = color.lstrip("#")
    ws_t.add_chart(ch, f"{get_column_letter(c0)}{len(piv) + 10}")

    _hoja(wb, "Por estado", est, "Estado por coordenada del cliente. Potencial solo donde hay resultado del modelo (gold).")
    _hoja(wb, "Por municipio", mun, "Municipio por coordenada del cliente.")
    _hoja(wb, "Por subcanal", sub, "Femsa: BU_Channel · Bepensa: pos_subchannel.")
    _hoja(wb, "Segmentos", seg, " · ".join(f"{k}: {v}" for k, v in segmentos.items()))
    if len(pri):
        _hoja(wb, "Prioridad del modelo", pri, "Nivel de prioridad del modelo Customer Potential (solo embotelladores con gold).")

    cols = ["embotellador", "pos_id", "cliente", "estado", "municipio", "subcanal", "tamano", "segmento",
            "revenue_12m", "revenue_12m_anterior", "cajas_12m", "meses_con_compra", "meses_sin_compra", "ultimo_mes",
            "producto_top", "prioridad", "cajas_mes_modelo", "potencial_cajas_mes"]
    riesgo = cli[cli["segmento"] == "En riesgo"].assign(revenue_perdible=lambda d: d["revenue_12m"] + d["revenue_12m_anterior"])
    _hoja(wb, "Acción · recuperar", riesgo.sort_values("revenue_perdible", ascending=False)[cols + ["revenue_perdible"]],
          "Clientes que no compran hace 3+ meses, de mayor a menor venta en los últimos 24 meses: visitarlos primero.")
    crecer = cli[cli["potencial_cajas_mes"].notna() & (cli["potencial_cajas_mes"] > 0)]
    if len(crecer):
        _hoja(wb, "Acción · crecer", crecer.sort_values("potencial_cajas_mes", ascending=False)[cols],
              "Clientes con potencial de crecimiento según el modelo, de mayor a menor (cajas/mes).")
    _hoja(wb, "Productos", prod.sort_values(["embotellador", "revenue_12m"], ascending=[True, False]),
          "Productos del catálogo del análisis, últimos 12 meses.")
    _hoja(wb, "Clientes", cli[cols + ["revenue_24m", "cajas_24m", "primer_mes", "productos", "marca_top"]],
          "Un cliente por fila (sin coordenadas). Universo: silver de clientes que compran con venta total positiva.")
    _hoja(wb, "Fuentes", pd.DataFrame(fuentes), "Datos del datawarehouse usados (corrida más reciente de cada ruta).")
    wb.save(ruta)
    return ruta
