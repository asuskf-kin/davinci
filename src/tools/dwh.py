"""Lectura reutilizable del datawarehouse (solo lectura): última corrida de cada ruta del SPEC §8.1, ventas del análisis
por cliente con su periodo comparable y el potencial del modelo (gold). Lo usan `evaluar` y `cadenas`.
"""
import pandas as pd

from src.config import settings
from src.tools import blob


def bajar(prefijo, fin):
    """(fecha, ruta local del archivo principal, ruta en el blob) de la última corrida; (None, None, None) si no hay."""
    fecha, archivos = blob.ultima_corrida(prefijo)
    principal = [n for n in archivos if n.endswith(fin) and not n.endswith(("_metadata.json", "_qa.html"))]
    if not principal:
        return None, None, None
    blob.descargar(principal[0], archivos[principal[0]])  # solo lo que se usa
    return fecha, settings.DATA / principal[0], principal[0]


def num(s):
    return pd.to_numeric(s, errors="coerce")


def mes(aaaamm):
    """AAAAMM → número de mes absoluto (para restar meses)."""
    a = num(aaaamm)
    return (a // 100) * 12 + a % 100


def fuente(emb, dato, fecha, ruta, falta):
    return {"embotellador": emb.capitalize(), "dato": dato, "fecha": fecha,
            "ruta": f"{settings.CONTENEDOR}/{ruta}" if ruta else f"POR VERIFICAR: {falta}"}


def ventas(pais, emb, analisis):
    """Ventas del análisis (bronze) + periodo comparable + totales por cliente (revenue_12m, cajas_12m, revenue_12m_anterior).

    Último mes incompleto (corte del extracto): < 70% de la mediana de los 12 anteriores → fuera de las comparaciones.
    Comparación: últimos 12 meses completos contra los mismos meses del año anterior (solo los que tienen par).
    """
    f, ruta_local, ruta = bajar(settings.bronze_ventas(pais, emb, analisis), ".parquet")
    if ruta_local is None:
        raise SystemExit(f"{emb}: no hay ventas de {analisis} en {settings.bronze_ventas(pais, emb, analisis)}. Paro aquí.")
    v = pd.read_parquet(ruta_local, columns=["pos_id", "product_id", "month_445", "unit_cases", "revenue", "es_outlier"])
    v["revenue"], v["unit_cases"] = num(v["revenue"]), num(v["unit_cases"])
    por_mes = v.groupby("month_445")["revenue"].sum().sort_index()
    meses = por_mes.index.tolist()
    incompleto = meses[-1] if len(meses) > 12 and por_mes.iloc[-1] < 0.7 * por_mes.iloc[-13:-1].median() else None
    completos = meses[:-1] if incompleto else meses
    ult12 = [m for m in completos[-12:] if str(int(m) - 100) in meses]
    prev12 = [str(int(m) - 100) for m in ult12]
    por_cli = v.assign(
        revenue_12m=v["revenue"].where(v["month_445"].isin(ult12), 0),
        cajas_12m=v["unit_cases"].where(v["month_445"].isin(ult12), 0),
        revenue_12m_anterior=v["revenue"].where(v["month_445"].isin(prev12), 0),
    ).groupby("pos_id")[["revenue_12m", "cajas_12m", "revenue_12m_anterior"]].sum()
    periodo = {"desde": ult12[0], "hasta": ult12[-1], "meses": len(ult12), "anterior_desde": prev12[0],
               "anterior_hasta": prev12[-1], "incompleto": incompleto, "ultimo_completo": completos[-1],
               "pct_incompleto": round(por_mes.iloc[-1] / por_mes.iloc[-13:-1].median(), 3) if incompleto else None}
    return {"v": v, "por_cliente": por_cli, "periodo": periodo, "ult12": ult12,
            "fuente": fuente(emb, "ventas (bronze)", f, ruta, "no hay ventas")}


def catalogo(pais, emb, analisis):
    """Productos VALIDADOS del análisis: catálogo aprobado de bronze (solo "Sí"), con tamaño en ml leído de la descripción.
    Nunca los products_nsr crudos de drop_zone (usuario, 2026-10-30)."""
    f, ruta_local, ruta = bajar(f"bronze/ko/{pais}/{emb}/product_catalog/{analisis}/", ".xlsx")
    fu = fuente(emb, "catálogo validado (bronze)", f, ruta, "no hay catálogo aprobado")
    if ruta_local is None:
        return None, fu
    c = pd.read_excel(ruta_local, header=6, dtype=str)
    c = c[c[f"¿Es {analisis}?"] == "Sí"].drop(columns=[f"¿Es {analisis}?", "product_info"], errors="ignore")
    t = c["Descripción"].str.upper().str.extract(r"(\d+(?:[.,]\d+)?)\s?(ML|LT(?![A-Z])|L(?![A-Z]))")  # "625MLPET", "1L6PK"
    ml = pd.to_numeric(t[0].str.replace(",", "."), errors="coerce") * t[1].map({"ML": 1, "L": 1000, "LT": 1000})
    c["presentacion"] = ml.map(lambda x: "(sin tamaño)" if pd.isna(x) else f"{x / 1000:g} L" if x >= 1000 else f"{x:g} ml")
    return c.set_index("product_id"), fu


def potencial(pais, emb, analisis):
    """Potencial del modelo por pos_id (gold, Results for Bottler) o None si no hay gold."""
    f, ruta_local, ruta = bajar(settings.gold_cp(pais, emb, analisis), "_Conservative_Scenario.csv")
    fu = fuente(emb, "potencial del modelo (gold)", f, ruta, "no hay gold de Customer Potential")
    if ruta_local is None:
        return None, fu
    g = pd.read_csv(ruta_local, dtype=str)
    sfx = f"_CustomCat_{analisis}"
    return pd.DataFrame({
        "pos_id": g["pos_id"],
        "prioridad": g["Priority Level" + sfx],
        "potencial_cajas_mes": num(g["Monthly Growth Potential (Unit Cases)" + sfx]),
        "cajas_mes_modelo": num(g["Monthly Sales (Unit Cases)" + sfx]),
        "tamano_modelo": g.get("size_class_internal"),
    }).set_index("pos_id"), fu
