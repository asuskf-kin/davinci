"""Retail por cadena (OXXO, Walmart, Costco… configurables) con TODO el datawarehouse de un análisis: clientes validados,
catálogo validado, ventas PDV × producto × mes y potencial del modelo → Excel con fórmulas por embotellador (formato del
Excel de referencia OXXO_Walmart_Costco_Nacional) + tablero HTML para validar y comparar.

Fuente válida = datawarehouse (solo lectura; no se cuadra contra archivos externos):
  bronze/ko/{pais}/{emb}/clients/…_validos.parquet            todos los clientes validados del canal (compren o no)
  bronze/ko/{pais}/{emb}/product_catalog/{analisis}/…xlsx     productos VALIDADOS (solo "Sí"; nunca products_nsr crudos)
  bronze/ko/{pais}/{emb}/sales/{analisis}/…parquet            ventas del análisis (24 meses; último mes incompleto fuera)
  gold/ko/{pais}/{emb}/customer_potencial/{analisis}/…        potencial del modelo (si existe)
Estado/municipio/población: INEGI por polígono (src/tools/inegi.py). Reglas de cadena/formato/tipo: src/config/cadenas.py.

Uso: cadenas --pais mx --analisis hydration --embotelladores femsa,bepensa [--cadenas oxxo,walmart,costco]
     cadenas --territorios "Mérida=bepensa:Yucatán/Mérida;CDMX=femsa:Ciudad de México"   (comparar territorios:
       Nombre=embotellador:Estado INEGI[/Municipio INEGI]; juntos y separados en el Excel y en el tablero comparativo)
  --cadenas = las del Excel; el tablero clasifica todas las de src/config/cadenas.py (el resto = "Independientes").
Salida (solo local): outputs/{AAAAMMDD}_cadenas_{analisis}_{pais}/cadenas_{analisis}_{pais}.xlsx (UN solo Excel con
  todos los embotelladores) + tablero_cadenas.html
"""
import argparse
import difflib
import json
import unicodedata
from datetime import date, datetime

import numpy as np
import pandas as pd

from src.config import cadenas as cfg
from src.config import settings
from src.tools import dwh, inegi

OTROS = "Independientes"
OTRAS = "Otras cadenas"


def limpiar(nombres):
    """Nombre limpio para inferir la franquicia: MAYÚSCULAS sin acentos ni signos, letras sueltas unidas ("O X X O" → OXXO)."""
    n = nombres.fillna("").map(lambda s: unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()).str.upper()
    n = n.str.replace(r"[^A-Z0-9]+", " ", regex=True).str.strip()
    return n.str.replace(r"\b(?:[A-Z] ){2,}[A-Z]\b", lambda m: m.group(0).replace(" ", ""), regex=True)


def _aproximada(limpio, alias):
    """Primera cadena cuyo alias se parece (≥ SIMILITUD) a una palabra o a dos palabras juntas del nombre."""
    pal = limpio.split()
    cands = [p for p in pal if len(p) >= 4] + [a + b for a, b in zip(pal, pal[1:]) if len(a + b) >= 5]
    for k, als in alias.items():
        if any(difflib.SequenceMatcher(None, c, a).ratio() >= cfg.SIMILITUD for c in cands for a in als):
            return k
    return None


def clasificar(nombres, claves):
    """(cadena, formato, tipo_punto, nombre_limpio, metodo) por nombre; cadena None si no es de las claves dadas.

    Orden: 1) regex sobre el nombre original · 2) alias sobre el nombre limpio y compacto · 3) aproximada (verificar).
    La regex de exclusión ("no") se aplica siempre, también sobre el nombre limpio."""
    n = nombres.fillna("").str.upper().str.strip()
    limpio = limpiar(nombres)
    cadena = pd.Series(None, index=n.index, dtype=object)
    formato = pd.Series(None, index=n.index, dtype=object)
    metodo = pd.Series(None, index=n.index, dtype=object)
    excl = {k: (n.str.contains(cfg.CADENAS[k]["no"], regex=True) | limpio.str.contains(cfg.CADENAS[k]["no"], regex=True))
            if cfg.CADENAS[k]["no"] else pd.Series(False, index=n.index) for k in claves}
    for k in claves:
        m = cadena.isna() & n.str.contains(cfg.CADENAS[k]["si"], regex=True) & ~excl[k]
        cadena[m], metodo[m] = k, "nombre"
    # alias = una palabra o 2–3 palabras seguidas que EMPIEZAN con el alias ("OXXO12605", "SAM S CLUB"; no "BOX XOLALPA")
    juntas = limpio.map(lambda s: (lambda w: w + [a + b for a, b in zip(w, w[1:])] + [a + b + c for a, b, c in zip(w, w[1:], w[2:])])(s.split()))
    for k in claves:
        m = cadena.isna() & ~excl[k] & juntas.map(lambda ws, als=cfg.ALIAS.get(k, []): any(x.startswith(a) for x in ws for a in als))
        cadena[m], metodo[m] = k, "nombre limpio"
    resto = cadena.isna() & limpio.ne("")
    alias = {k: cfg.ALIAS[k] for k in claves if k in cfg.ALIAS}
    aprox = limpio[resto].map(lambda s: _aproximada(s, alias))
    aprox = aprox[aprox.notna()]
    aprox = aprox[[not excl[k][i] for i, k in aprox.items()]]
    cadena[aprox.index], metodo[aprox.index] = aprox, "aproximado (verificar)"
    for k in claves:
        m = cadena.eq(k)
        cadena[m] = cfg.CADENAS[k]["nombre"]
        for f, patron in cfg.CADENAS[k]["formatos"]:
            mf = m & formato.isna() & (limpio.str.contains(patron, regex=True) if patron else True)
            formato[mf] = f
    tipo = pd.Series("Tienda", index=n.index, dtype=object)
    asignado = pd.Series(False, index=n.index)
    for t, patron in cfg.TIPOS_PUNTO:
        m = ~asignado & n.str.contains(patron, regex=True)
        tipo[m], asignado = t, asignado | m
    return cadena, formato, tipo, limpio, metodo


def _alertas(d, tiene_ingreso):
    """Calidad del dato: no se borra nada, solo se marca (validar, no limpiar)."""
    a = [[] for _ in range(len(d))]

    def marcar(mask, texto):
        for i in np.where(np.asarray(mask))[0]:
            a[i].append(texto)

    marcar(d["tipo_punto"].ne("Tienda"), "no es tienda")
    marcar(d["asignacion"].str.startswith("Más cercano"), "fuera de polígono INEGI (asignado al más cercano)")
    marcar(d["metodo_franquicia"].eq("aproximado (verificar)"), "franquicia inferida por parecido (verificar)")
    marcar(d["cliente"].duplicated(keep=False) & d["cadena"].ne(OTROS), "nombre repetido")
    if tiene_ingreso:
        marcar(d["ingreso"].fillna(0) <= 0, "sin venta en el mes")
        base = d["ingreso"].where((d["ingreso"] > 0) & d["tipo_punto"].eq("Tienda"))
        log = np.log(base)
        med = log.groupby(d["formato"]).transform("median")
        mad = (log - med).abs().groupby(d["formato"]).transform("median") * 1.4826
        z = (log - med) / mad.replace(0, np.nan)
        marcar(z > 3.5, "venta del mes atípica alta vs su formato")
        marcar(z < -3.5, "venta del mes atípica baja vs su formato")
    return ["; ".join(x) for x in a]


def cargar(pais, emb, analisis):
    """Base completa de un embotellador: clientes (todos, con cadena u 'Independientes'), ventas, catálogo y potencial."""
    f, ruta_local, ruta = dwh.bajar(f"bronze/ko/{pais}/{emb}/clients/", "_validos.parquet")
    if ruta_local is None:
        raise SystemExit(f"{emb}: no hay clientes validados en bronze/ko/{pais}/{emb}/clients/. Paro aquí.")
    c = pd.read_parquet(ruta_local)
    col = cfg.COLUMNAS.get(emb, {})
    cadena, formato, tipo, limpio, metodo = clasificar(c["Cliente"], list(cfg.CADENAS))
    es = cadena.notna()
    d = pd.DataFrame({
        "embotellador": emb.capitalize(), "pos_id": c["pos_id"].astype(str), "cliente": c["Cliente"],
        "nombre_limpio": limpio, "metodo_franquicia": metodo.fillna("—"),
        "cadena": cadena.fillna(OTROS), "formato": formato.fillna(OTROS),
        "tipo_punto": tipo.where(es, "Tienda"),
        "zona": c[col["zona"]] if "zona" in col else "(sin zona)",
        "lat": dwh.num(c["pos_latitude"]), "lon": dwh.num(c["pos_longitude"]),
        "grupo": c[col["grupo"]] if "grupo" in col else None,
        "subcanal": c[col["subcanal"]] if "subcanal" in col else None,
    }).reset_index(drop=True)
    for k in ("ingreso", "cajas", "descuento"):
        d[k] = dwh.num(c[col[k]]).to_numpy() if k in col else np.nan
    d = pd.concat([d, inegi.asignar(d["lat"], d["lon"])], axis=1)

    ve = dwh.ventas(pais, emb, analisis)
    v, per = ve["v"], ve["periodo"]
    d = d.join(ve["por_cliente"], on="pos_id")
    d[["revenue_12m", "cajas_12m", "revenue_12m_anterior"]] = d[["revenue_12m", "cajas_12m", "revenue_12m_anterior"]].fillna(0)
    vv = v[v["month_445"] <= per["ultimo_completo"]]
    vida = vv[vv["revenue"] > 0].groupby("pos_id")["month_445"].agg(primer_mes="min", ultimo_mes="max", meses_con_compra="nunique")
    d = d.join(vida, on="pos_id")
    d["meses_con_compra"] = d["meses_con_compra"].fillna(0)
    d["compra_analisis"] = np.where(d["revenue_12m"] > 0, "Sí", "No")
    fin = dwh.mes(per["ultimo_completo"])
    d["meses_sin_compra"] = fin - dwh.mes(d["ultimo_mes"])
    d["estatus"] = np.select(
        [d["primer_mes"].isna(), fin - dwh.mes(d["primer_mes"]) < 6, d["meses_sin_compra"] >= 3],
        ["Nunca compró", "Nuevo (6 meses)", "Perdido (3+ meses sin compra)"], "Activo")

    gold, fu_gold = dwh.potencial(pais, emb, analisis)
    if gold is not None:
        d = d.join(gold[["prioridad", "potencial_cajas_mes"]], on="pos_id")
    else:
        d["prioridad"], d["potencial_cajas_mes"] = None, np.nan
    cat, fu_cat = dwh.catalogo(pais, emb, analisis)
    tiene_ingreso = "ingreso" in col
    d["alertas"] = _alertas(d, tiene_ingreso)
    vv = vv.join(d.set_index("pos_id")[["cadena", "estado"]], on="pos_id")
    sin_cliente = vv["cadena"].isna().sum()
    vv["cadena"] = vv["cadena"].fillna(OTROS)
    vv["estado"] = vv["estado"].fillna("(cliente fuera de bronze)")
    info = {"fuentes": [dwh.fuente(emb, "clientes validados (bronze)", f, ruta, "no hay clientes"), fu_cat, ve["fuente"], fu_gold],
            "periodo": per, "ult12": ve["ult12"], "tiene_ingreso": tiene_ingreso, "tiene_potencial": gold is not None,
            "mes_venta_clientes": c[col["mes"]].value_counts().to_dict() if "mes" in col else None,
            "filas_venta_sin_cliente": int(sin_cliente), "clientes_bronze": len(d),
            "productos_vendidos_fuera_del_catalogo": int((~vv["product_id"].isin(cat.index)).sum()) if cat is not None else None}
    return d, vv, cat, info


def hallazgos(d, info, analisis, nombres):
    """Frases para el tomador de decisiones, solo con cifras del dato (lo que falta, POR VERIFICAR)."""
    d = d[d["cadena"].isin(nombres)]
    emb = d["embotellador"].iat[0]
    t = d                                                # todos los PdV (tiendas, comedores, cajas…): cuadra con '# PdV'
    por = t.groupby("cadena")
    n = d.groupby("cadena").size().sort_values(ascending=False)
    h = {"COBERTURA": f"{n.index[0]} domina en número: {n.iat[0]:,} PdV ({n.iat[0] / n.sum():.0%} de los {n.sum():,} PdV de las "
                      f"{len(n)} cadenas en {emb}). " + " · ".join(
                          f"{k}: {v:,} PdV en {d.loc[d.cadena == k, 'estado'].nunique()} estados y "
                          f"{d.loc[d.cadena == k, 'cvegeo'].nunique()} municipios" for k, v in n.items()) + "."}
    e = d.groupby("estado").size().sort_values(ascending=False)
    h["DÓNDE ESTÁN"] = (f"Los 3 estados con más PdV ({', '.join(e.index[:3])}) concentran {e.iloc[:3].sum() / e.sum():.0%}. "
                        + " · ".join(f"{k}: #1 {d[d.cadena == k].groupby('estado').size().idxmax()}" for k in n.index) + ".")
    if info["tiene_ingreso"]:
        prom = por["ingreso"].mean().sort_values(ascending=False)
        h["VALOR POR PUNTO"] = ("Venta promedio por tienda en el mes (todas las categorías): "
                                + ", ".join(f"{k} ${v:,.0f}" for k, v in prom.items())
                                + (f". Una tienda {prom.index[0]} vende como {prom.iat[0] / prom.iat[-1]:,.0f} tiendas {prom.index[-1]}."
                                   if len(prom) > 1 and prom.iat[-1] else "."))
    else:
        h["VALOR POR PUNTO"] = (f"POR VERIFICAR — la base de clientes de {emb} no trae venta del mes; se usa la venta de "
                                f"{analisis} de los últimos 12 meses.")
    pen = por["compra_analisis"].apply(lambda s: (s == "Sí").mean())
    rev = por["revenue_12m"].sum()
    crec = rev / por["revenue_12m_anterior"].sum() - 1
    p = info["periodo"]
    h[analisis.upper()] = (f"PdV que compran {analisis}: " + ", ".join(f"{k} {v:.0%}" for k, v in pen.items())
                           + f". Venta {analisis} {p['desde']}–{p['hasta']}: "
                           + ", ".join(f"{k} ${rev[k]:,.0f}" + (f" ({crec[k]:+.1%} vs año anterior)" if np.isfinite(crec[k]) else
                                                                 " (sin venta el año anterior)") for k in rev.index) + ".")
    if info["tiene_potencial"]:
        h[analisis.upper()] += " Potencial del modelo: " + ", ".join(
            f"{k} {v:,.0f} cajas/mes" for k, v in por["potencial_cajas_mes"].sum().items()) + "."
    sin = t[t["compra_analisis"] == "No"].groupby("cadena").size()
    perdidos = t[t["estatus"].str.startswith("Perdido")].groupby("cadena").size()
    big = n.index[0]
    mun = d.pivot_table(index=["cvegeo", "municipio", "estado"], columns="cadena", values="pos_id", aggfunc="count", fill_value=0)
    otras = [k for k in n.index if k != big]
    blanco = mun[(mun[otras] == 0).all(axis=1)].sort_values(big, ascending=False).head(3) if otras else mun.iloc[:0]
    h["OPORTUNIDAD"] = (", ".join(f"{k}: {v:,} PdV que no compran {analisis}" for k, v in sin.items())
                        + (" y " + ", ".join(f"{k} {v:,} que dejaron de comprar" for k, v in perdidos.items()) if len(perdidos) else "")
                        + " — listas para activar (Detalle PdV, filtros Compra y Estatus)."
                        + (f" Municipios con más {big} y sin {', '.join(otras)}: "
                           + ", ".join(f"{i[1]}, {i[2]} ({r[big]:,})" for i, r in blanco.iterrows()) + "." if len(blanco) else ""))
    g = ["territorio", "cadena"] if "territorio" in t else ["cadena"]
    nun = t.assign(nun=t["estatus"].str.startswith("Nunca")).groupby(g)["nun"].agg(["sum", "size"])
    h["NUNCA COMPRARON"] = (" · ".join(f"{' '.join(k) if isinstance(k, tuple) else k}: {int(r['sum']):,} de {int(r['size']):,} PdV "
                                        f"({r['sum'] / r['size']:.0%})" for k, r in nun.iterrows() if r["sum"])
                            + f" nunca compraron {analisis} — dónde están y de qué franquicia, en la hoja 'Nunca compraron'.")
    al = pd.Series([x for s in d["alertas"] if s for x in s.split("; ")]).value_counts()
    h["CALIDAD DEL DATO"] = ("Sin alertas." if al.empty else " · ".join(f"{v:,} PdV con '{k}'" for k, v in al.items())
                             + ". Se marcan, no se borran.")
    if p["incompleto"]:
        h["CALIDAD DEL DATO"] += f" El mes {p['incompleto']} viene incompleto ({p['pct_incompleto']:.0%} de un mes normal) y queda fuera."
    h["SIGUIENTE PASO"] = ("Usar 'Por zona', 'Por estado' y 'Por municipio' para priorizar cobertura; filtrar 'Detalle PdV' por "
                           "Cadena, Compra, Estatus y Alertas para armar rutas; explorar tendencias y productos en el tablero HTML.")
    return h


def slug(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().replace(" ", "")


def territorios(spec):
    """'Mérida=bepensa:Yucatán/Mérida;CDMX=femsa:Ciudad de México' → {nombre: {emb, estado, municipio}} (nombres INEGI)."""
    out = {}
    for parte in filter(None, (x.strip() for x in spec.split(";"))):
        nombre, resto = parte.split("=", 1)
        emb, lugar = resto.split(":", 1)
        estado, _, municipio = lugar.partition("/")
        out[nombre.strip()] = {"emb": emb.strip().lower(), "estado": estado.strip(), "municipio": municipio.strip() or None}
    return out


def main(argv):
    p = argparse.ArgumentParser(prog="cadenas", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pais", default="mx")
    p.add_argument("--analisis", default="hydration")
    p.add_argument("--embotelladores", default=",".join(settings.EMBOTELLADORES))
    p.add_argument("--cadenas", default=",".join(cfg.POR_DEFECTO), help="claves de src/config/cadenas.py: " + ", ".join(cfg.CADENAS))
    p.add_argument("--otras", action="store_true",
                   help='agrupa las cadenas fuera de --cadenas en "Otras cadenas" (la franquicia queda en su columna)')
    p.add_argument("--independientes", action="store_true", help='suma "Independientes" (canal moderno que no es cadena)')
    p.add_argument("--territorios", default=None, help='"Mérida=bepensa:Yucatán/Mérida;CDMX=femsa:Ciudad de México"')
    a = p.parse_args(argv)
    pais, analisis = a.pais.lower(), a.analisis.lower()
    claves = [k.strip() for k in a.cadenas.split(",") if k.strip()]
    if malas := [k for k in claves if k not in cfg.CADENAS]:
        raise SystemExit(f"cadenas desconocidas {malas}; disponibles: {list(cfg.CADENAS)}")
    terr = territorios(a.territorios) if a.territorios else {}
    nombres = [cfg.CADENAS[k]["nombre"] for k in claves] + ([OTRAS] if a.otras else []) + ([OTROS] if a.independientes else [])
    embs = list(dict.fromkeys(t["emb"] for t in terr.values())) if terr else [e.strip().lower() for e in a.embotelladores.split(",") if e.strip()]
    sufijo = "_".join(slug(t) for t in terr) if terr else pais
    fecha = date.today().strftime("%Y%m%d")
    out = settings.RAIZ / "outputs" / f"{fecha}_cadenas_{analisis}_{sufijo}"
    out.mkdir(parents=True, exist_ok=True)
    from src.tools import cadenas_excel, comparativo, tablero

    clientes, ventas, catalogos, meta, hs = [], [], [], {}, {}
    for i, emb in enumerate(embs, 1):
        print(f"{i}. {emb}: clientes, cadenas, INEGI, catálogo, ventas {analisis} y potencial …")
        d, vv, cat, info = cargar(pais, emb, analisis)
        d["franquicia"] = d["cadena"]
        if a.otras:  # todo lo que no es foco ni independiente → "Otras cadenas"
            foco = set(nombres) - {OTRAS, OTROS}
            d.loc[~d["cadena"].isin(foco | {OTROS}), "cadena"] = OTRAS
            vv["cadena"] = vv["pos_id"].map(d.set_index("pos_id")["cadena"]).fillna(OTROS)
        assert d["pos_id"].is_unique, f"{emb}: pos_id repetidos"
        assert d["cvegeo"].notna().all(), f"{emb}: PdV sin municipio INEGI"
        de_bronze = vv["month_445"].isin(info["ult12"]) & vv["pos_id"].isin(d["pos_id"])
        assert abs(vv.loc[de_bronze, "revenue"].sum() - d["revenue_12m"].sum()) < 1, f"{emb}: revenue 12m no cuadra con las ventas"
        E = emb.capitalize()
        print(f"   {len(d):,} clientes · {(d.cadena != OTROS).sum():,} de cadenas "
              f"({(d.metodo_franquicia == 'nombre limpio').sum()} por nombre limpio, {(d.metodo_franquicia.str.startswith('aprox')).sum()} aproximados)")
        if cat is not None:
            catalogos.append(cat.assign(embotellador=E))
        grupos = {n: t for n, t in terr.items() if t["emb"] == emb} or {E: None}
        for nombre, t in grupos.items():
            dt = d if t is None else d[d["estado"].eq(t["estado"]) & (d["municipio"].eq(t["municipio"]) if t["municipio"] else True)]
            if dt.empty:
                raise SystemExit(f"{nombre}: ningún cliente de {emb} en {t['estado']}/{t['municipio'] or '(todo el estado)'}. Paro aquí.")
            dt = dt.assign(territorio=nombre) if t else dt
            hs[nombre] = hallazgos(dt, info, analisis, nombres)
            clientes.append(dt), ventas.append(vv[vv["pos_id"].isin(dt["pos_id"])].assign(embotellador=E, **({"territorio": nombre} if t else {})))
            meta[nombre] = {**info, "hallazgos": hs[nombre], "embotellador": E, "territorio": t}
            if t:
                print(f"   {nombre}: {len(dt):,} clientes ({(dt.cadena != OTROS).sum():,} de cadenas)")
    base, vt = pd.concat(clientes, ignore_index=True), pd.concat(ventas)
    if terr:  # comparación de territorios: solo los grupos elegidos (sin independientes salvo --independientes)
        base, vt = base[base["cadena"].isin(nombres)], vt[vt["cadena"].isin(nombres)]
    cats = pd.concat(catalogos) if catalogos else None
    try:
        x = cadenas_excel.escribir(out / f"cadenas_{analisis}_{sufijo}.xlsx", base, vt, cats, meta, hs, analisis, nombres, pais)
    except PermissionError:  # el Excel anterior está abierto: no se pisa, se guarda una copia con la hora
        x = cadenas_excel.escribir(out / f"cadenas_{analisis}_{sufijo}_{datetime.now():%H%M}.xlsx", base, vt, cats, meta, hs,
                                   analisis, nombres, pais)
        print("AVISO: el Excel anterior está abierto; se guardó una copia nueva con la hora")
    print(f"Excel: {x}")
    foco = nombres
    if terr:
        html = comparativo.escribir(out / f"tablero_{sufijo}.html", base, vt, cats, meta, analisis, foco)
    else:
        html = tablero.escribir(out / "tablero_cadenas.html", base, vt, cats, meta, analisis, pais, foco)
    (out / "cadenas_metadata.json").write_text(json.dumps(
        {"pais": pais, "analisis": analisis, "cadenas_excel": claves, "fecha": fecha, "territorios": terr, "grupos": meta,
         "reglas": cfg.CADENAS, "tipos_punto": cfg.TIPOS_PUNTO}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Tablero: {html}\nCarpeta: {out}")
