"""Evaluación de Customer Potential para el tomador de decisiones: clientes, ventas y potencial por embotellador.

Fuentes (solo paths del datawarehouse, SPEC §8.1; la corrida más reciente de cada uno, solo lectura):
  silver/ko/{pais}/{emb}/clients/{analisis}_modern/{fecha}/…_validos_catalog.csv   clientes que compran + métricas
  bronze/ko/{pais}/{emb}/sales/{analisis}/{fecha}/….parquet                         ventas PDV × producto × mes
  bronze/ko/{pais}/{emb}/product_mapping/{analisis}/{fecha}/….csv                   descripción de los productos
  gold/ko/{pais}/{emb}/customer_potencial/{analisis}/{fecha}/Results for Bottler/   potencial del modelo (si existe)
Sin gold, el potencial queda POR VERIFICAR (no se estima: regla 9, no alucinar).
Salida (solo local, nunca al blob): outputs/{AAAAMMDD}_cp_{analisis}_{pais}/  cp_{analisis}_{pais}.xlsx + cp_{analisis}_{pais}_mapa.html
"""
import argparse
import json
from datetime import date

import pandas as pd

from src.config import settings
from src.tools import dwh

PRIORIDADES = ["Very High", "High", "Moderate", "Low"]
SEGMENTO_QUE_ES = {
    "Frecuente": "compra en 75% o más de los meses desde su primera compra y compró en los últimos 3 meses",
    "Ocasional": "compró en los últimos 3 meses pero en menos del 75% de los meses",
    "Nuevo": "su primera compra fue en los últimos 6 meses y compró en los últimos 3 meses",
    "En riesgo": "no compra hace 3 meses o más (venta que se puede perder)",
}


_num, _mes = dwh.num, dwh.mes


def cargar(pais, emb, analisis):
    """Clientes unificados de un embotellador (una fila por cliente) + ventas mensuales + fuentes."""
    f_s, silver, ruta_s = dwh.bajar(settings.silver_clientes(pais, emb, analisis), "_catalog.csv")
    if silver is None:
        raise SystemExit(f"{emb}: no hay silver de clientes en {settings.silver_clientes(pais, emb, analisis)}. Paro aquí.")
    ve = dwh.ventas(pais, emb, analisis)
    v, ult12, per = ve["v"], ve["ult12"], ve["periodo"]
    f_m, mapeo, ruta_m = dwh.bajar(f"bronze/ko/{pais}/{emb}/product_mapping/{analisis}/", ".csv")
    gold, fu_gold = dwh.potencial(pais, emb, analisis)

    c = pd.read_csv(silver, dtype=str)
    a = f"{analisis}_"
    cli = pd.DataFrame({
        "embotellador": emb.capitalize(),
        "pos_id": c["pos_id"],
        "cliente": c["Cliente"],
        "estado": c["estado"],
        "municipio": c.get("municipio_coordenada", c["municipio"]),
        "subcanal": c.get("BU_Channel", c.get("pos_subchannel")),
        "lat": _num(c["pos_latitude"]),
        "lon": _num(c["pos_longitude"]),
        "revenue_24m": _num(c[a + "revenue"]),
        "cajas_24m": _num(c[a + "unit_cases"]),
        "meses_con_compra": _num(c[a + "meses_con_compra"]),
        "primer_mes": c[a + "primer_mes"],
        "ultimo_mes": c[a + "ultimo_mes"],
        "productos": _num(c[a + "productos"]),
        "producto_top": c[a + "producto_top"],
        "marca_top": c[a + "marca_top"],
        "tamano": c.get("pos_size_classification"),
    })

    cli = cli.join(ve["por_cliente"], on="pos_id")
    cli[["revenue_12m", "cajas_12m", "revenue_12m_anterior"]] = cli[["revenue_12m", "cajas_12m", "revenue_12m_anterior"]].fillna(0)

    fin = _mes(per["ultimo_completo"])
    span = fin - _mes(cli["primer_mes"]) + 1
    sin_compra = fin - _mes(cli["ultimo_mes"])
    cli["meses_sin_compra"] = sin_compra
    cli["segmento"] = "Ocasional"
    cli.loc[cli["meses_con_compra"] / span >= 0.75, "segmento"] = "Frecuente"
    cli.loc[span <= 6, "segmento"] = "Nuevo"
    cli.loc[sin_compra >= 3, "segmento"] = "En riesgo"  # gana sobre todo: es lo accionable

    cli["prioridad"], cli["potencial_cajas_mes"], cli["cajas_mes_modelo"] = None, float("nan"), float("nan")
    if gold is not None:
        g = gold
        cli = cli.drop(columns=["prioridad", "potencial_cajas_mes", "cajas_mes_modelo"]).join(g, on="pos_id")
        cli["tamano"] = cli["tamano"].fillna(cli.pop("tamano_modelo"))

    desc = {}
    if mapeo is not None:
        m = pd.read_csv(mapeo, sep=";", dtype=str, encoding="cp1252")
        desc = dict(zip(m["product_id"], m["Descripción"]))
    mens = v.groupby("month_445").agg(revenue=("revenue", "sum"), cajas=("unit_cases", "sum"),
                                      clientes=("pos_id", "nunique"), filas_outlier=("es_outlier", "sum"),
                                      filas=("es_outlier", "size")).reset_index()
    mens.insert(0, "embotellador", emb.capitalize())
    prod = v[v["month_445"].isin(ult12)].groupby("product_id").agg(
        revenue_12m=("revenue", "sum"), cajas_12m=("unit_cases", "sum"), clientes=("pos_id", "nunique")).reset_index()
    prod.insert(1, "descripcion", prod["product_id"].map(desc).fillna("(sin descripción en el mapeo)"))
    prod.insert(0, "embotellador", emb.capitalize())

    fuentes = [
        dwh.fuente(emb, "clientes (silver)", f_s, ruta_s, "no hay silver"),
        ve["fuente"],
        dwh.fuente(emb, "mapeo de productos (bronze)", f_m, ruta_m, "no hay mapeo"),
        fu_gold,
    ]
    return cli, mens, prod, fuentes, per


def _crec(actual, anterior):
    return (actual / anterior - 1).where(anterior > 0)


def resumen(cli):
    g = cli.groupby("embotellador")
    r = pd.DataFrame({
        "Clientes que compran": g.size(),
        "Revenue últimos 12 meses": g["revenue_12m"].sum(),
        "Revenue 12 meses anteriores": g["revenue_12m_anterior"].sum(),
        "Cajas últimos 12 meses": g["cajas_12m"].sum(),
        "Revenue 12m por cliente": g["revenue_12m"].mean(),
        "Meses con compra (promedio)": g["meses_con_compra"].mean(),
        "Clientes en riesgo": g["segmento"].apply(lambda s: (s == "En riesgo").sum()),
        "Revenue 12m de clientes en riesgo": cli[cli["segmento"] == "En riesgo"].groupby("embotellador")["revenue_12m"].sum(),
        "Estados": g["estado"].nunique(),
        "Municipios": g["municipio"].nunique(),
        "Potencial (cajas/mes, modelo)": g["potencial_cajas_mes"].sum(min_count=1),
        "Cajas/mes actuales (modelo)": g["cajas_mes_modelo"].sum(min_count=1),
        "Clientes prioridad Very High + High": g["prioridad"].apply(lambda s: s.isin(PRIORIDADES[:2]).sum() if s.notna().any() else pd.NA),
    }).fillna({"Revenue 12m de clientes en riesgo": 0})
    r.insert(3, "Crecimiento revenue vs año anterior", _crec(r["Revenue últimos 12 meses"], r["Revenue 12 meses anteriores"]))
    r["% clientes en riesgo"] = r["Clientes en riesgo"] / r["Clientes que compran"]
    r["Crecimiento posible (% sobre lo actual)"] = r["Potencial (cajas/mes, modelo)"] / r["Cajas/mes actuales (modelo)"]
    top = cli.sort_values("revenue_12m", ascending=False).groupby("embotellador")
    r["% revenue del 20% de clientes que más compra"] = top.apply(
        lambda d: d["revenue_12m"].head(max(1, len(d) // 5)).sum() / d["revenue_12m"].sum() if d["revenue_12m"].sum() else pd.NA)
    return r


def por(cli, col):
    g = cli.groupby(["embotellador", col], dropna=False)
    t = pd.DataFrame({
        "clientes": g.size(),
        "revenue_12m": g["revenue_12m"].sum(),
        "revenue_12m_anterior": g["revenue_12m_anterior"].sum(),
        "cajas_12m": g["cajas_12m"].sum(),
        "revenue_12m_por_cliente": g["revenue_12m"].mean(),
        "clientes_en_riesgo": g["segmento"].apply(lambda s: (s == "En riesgo").sum()),
        "potencial_cajas_mes": g["potencial_cajas_mes"].sum(min_count=1),
        "cajas_mes_modelo": g["cajas_mes_modelo"].sum(min_count=1),
    })
    t.insert(3, "crecimiento_vs_anio_anterior", _crec(t["revenue_12m"], t["revenue_12m_anterior"]))
    t["%_en_riesgo"] = t["clientes_en_riesgo"] / t["clientes"]
    t["%_crecimiento_posible"] = t["potencial_cajas_mes"] / t["cajas_mes_modelo"]
    t["%_revenue_del_embotellador"] = t["revenue_12m"] / t.groupby(level=0)["revenue_12m"].transform("sum")
    return t.reset_index().sort_values(["embotellador", "revenue_12m"], ascending=[True, False])


def hallazgos(r, est, seg, cli, periodo):
    """Frases cortas para el tomador de decisiones (solo cifras del dato; lo que no hay queda POR VERIFICAR)."""
    h = []
    for emb, x in r.iterrows():
        pe = periodo["por_emb"][emb]
        h.append(f"{emb}: {x['Clientes que compran']:,.0f} clientes compraron {periodo['analisis']} y dejaron "
                 f"${x['Revenue últimos 12 meses']:,.0f} en {pe['meses']} meses ({pe['desde']}–{pe['hasta']}).")
        if pe["incompleto"]:
            h.append(f"{emb}: el mes {pe['incompleto']} viene incompleto ({pe['pct_incompleto']:.0%} de un mes normal; corte del "
                     f"extracto) y queda fuera de las comparaciones — POR VERIFICAR con el embotellador.")
        if pd.notna(x["Crecimiento revenue vs año anterior"]):
            sube = "creció" if x["Crecimiento revenue vs año anterior"] >= 0 else "cayó"
            h.append(f"{emb}: el revenue {sube} {abs(x['Crecimiento revenue vs año anterior']):.1%} frente a los mismos meses del año anterior ({pe['anterior_desde']}–{pe['anterior_hasta']}).")
        h.append(f"{emb}: {x['% revenue del 20% de clientes que más compra']:.0%} del revenue lo hace el 20% de los clientes "
                 f"que más compra: cuidarlos es lo primero.")
        h.append(f"{emb}: {x['Clientes en riesgo']:,.0f} clientes ({x['% clientes en riesgo']:.0%}) no compran hace 3 meses o más; "
                 f"en el periodo dejaron ${x['Revenue 12m de clientes en riesgo']:,.0f}. Visitarlos recupera venta.")
        if pd.notna(x["Potencial (cajas/mes, modelo)"]):
            h.append(f"{emb}: el modelo ve {x['Potencial (cajas/mes, modelo)']:,.0f} cajas/mes más "
                     f"(+{x['Crecimiento posible (% sobre lo actual)']:.1%} sobre lo actual); "
                     f"{x['Clientes prioridad Very High + High']:,.0f} clientes tienen prioridad Very High o High.")
            e = est[(est["embotellador"] == emb) & est["potencial_cajas_mes"].notna()].nlargest(3, "potencial_cajas_mes")
            h.append(f"{emb}: más potencial en " + ", ".join(f"{a} ({b:,.0f} cajas/mes)" for a, b in
                                                           zip(e["estado"], e["potencial_cajas_mes"])) + ".")
        else:
            h.append(f"{emb}: POR VERIFICAR — no hay resultado del modelo Customer Potential en gold; "
                     f"falta correr el modelo (Synapse) y la etapa gold para conocer su potencial.")
        e = est[est["embotellador"] == emb].nlargest(3, "revenue_12m")
        h.append(f"{emb}: los estados que más venden son " + ", ".join(
            f"{a} ({b:.0%})" for a, b in zip(e["estado"], e["%_revenue_del_embotellador"])) + ".")
    return h


def main(argv):
    p = argparse.ArgumentParser(prog="evaluar", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pais", default="mx")
    p.add_argument("--analisis", default="hydration")
    p.add_argument("--embotelladores", default=",".join(settings.EMBOTELLADORES))
    a = p.parse_args(argv)
    pais, analisis = a.pais.lower(), a.analisis.lower()
    embs = [e.strip().lower() for e in a.embotelladores.split(",") if e.strip()]

    clis, mens, prods, fuentes, periodos = [], [], [], [], {}
    for i, emb in enumerate(embs, 1):
        print(f"{i}/{len(embs)} cargando {emb} …")
        c, m, pr, f, per = cargar(pais, emb, analisis)
        clis.append(c), mens.append(m), prods.append(pr), fuentes.extend(f)
        periodos[emb.capitalize()] = per
    cli = pd.concat(clis, ignore_index=True)
    periodo = {"analisis": analisis, "por_emb": periodos,
               "ult12": " · ".join(f"{e} {p['desde']}–{p['hasta']} vs {p['anterior_desde']}–{p['anterior_hasta']}" for e, p in periodos.items())}

    r = resumen(cli)
    est, mun, sub, seg = por(cli, "estado"), por(cli, "municipio"), por(cli, "subcanal"), por(cli, "segmento")
    pri = por(cli[cli["prioridad"].notna()], "prioridad")
    h = hallazgos(r, est, seg, cli, periodo)

    # QA: lo que se muestra cuadra con la fuente
    for emb, x in r.iterrows():
        d = cli[cli["embotellador"] == emb]
        assert x["Clientes que compran"] == d["pos_id"].nunique() == len(d), f"{emb}: pos_id repetidos en silver"
        assert abs(est[est["embotellador"] == emb]["revenue_12m"].sum() - x["Revenue últimos 12 meses"]) < 1, emb
    print("QA ok: un cliente por fila; totales por estado = total del embotellador")

    fecha = date.today().strftime("%Y%m%d")
    out = settings.salida(pais, analisis, fecha)
    out.mkdir(parents=True, exist_ok=True)
    from src.tools import excel, mapa

    xlsx = excel.escribir(out / f"cp_{analisis}_{pais}.xlsx", r, h, cli, pd.concat(mens), pd.concat(prods),
                          est, mun, sub, seg, pri, fuentes, SEGMENTO_QUE_ES, periodo)
    html = mapa.escribir(out / f"cp_{analisis}_{pais}_mapa.html", cli, r, h, analisis, pais)
    (out / "evaluacion_metadata.json").write_text(json.dumps({
        "pais": pais, "analisis": analisis, "embotelladores": embs, "fecha": fecha, "fuentes": fuentes,
        "periodos": periodos,
        "hallazgos": h, "segmentos": SEGMENTO_QUE_ES,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n".join(["", "Hallazgos:", *("· " + x for x in h), "", f"Excel: {xlsx}", f"Mapa:  {html}"]))
