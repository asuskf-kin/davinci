"""Estado y municipio oficiales de INEGI (Marco Geoestadístico) por lat/long, con clave CVEGEO y población.

Fuente: servicio del Catálogo Único de Claves de INEGI (sin key): /v2/mgee/ (estados) y /v2/geo/mgem/{cve_ent}
(polígonos municipales). Se guarda en caché en data/referencia/inegi/ y no se vuelve a bajar.
Un punto fuera de todo polígono (costa, frontera) se asigna al municipio más cercano y se dice a cuántos metros.
"""
import json
from functools import cache

import numpy as np
import pandas as pd
import requests
import shapely
from shapely.geometry import shape

from src.config import settings

URL = "https://gaia.inegi.org.mx/wscatgeo/v2"
CACHE = settings.DATA / "referencia" / "inegi"


def _json(ruta, archivo):
    local = CACHE / archivo
    if not local.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        r = requests.get(f"{URL}/{ruta}", timeout=180)
        r.raise_for_status()
        local.write_bytes(r.content)
    return json.loads(local.read_text(encoding="utf-8"))


@cache
def municipios():
    """GeoDataFrame-lite: DataFrame con cvegeo, estado, municipio, poblacion y geometría (shapely)."""
    estados = {e["cve_ent"]: e["nomgeo"] for e in _json("mgee/", "mgee.json")["datos"]}
    filas = []
    for cve, nombre in estados.items():
        for f in _json(f"geo/mgem/{cve}", f"mgem_{cve}.geojson")["features"]:
            p = f["properties"]
            filas.append({"cvegeo": p["cvegeo"], "estado": nombre, "municipio": p["nomgeo"],
                          "poblacion": int(p.get("pob_total") or 0), "geom": shape(f["geometry"])})
    return pd.DataFrame(filas)


def asignar(lat, lon):
    """Para cada punto: cvegeo, estado, municipio, poblacion (del municipio) y asignacion ('Dentro del polígono' o 'Más cercano (N m)')."""
    m = municipios()
    arbol = shapely.STRtree(m["geom"].tolist())
    pts = shapely.points(np.asarray(lon, float), np.asarray(lat, float))
    idx = np.full(len(pts), -1)
    p, g = arbol.query(pts, predicate="within")
    idx[p] = g
    asign = np.where(idx >= 0, "Dentro del polígono", "")
    fuera = np.where(idx < 0)[0]
    if len(fuera):
        cerca = arbol.nearest(pts[fuera])
        idx[fuera] = cerca
        metros = shapely.distance(pts[fuera], m["geom"].values[cerca]) * 111_320  # grados → m (aprox.)
        asign = asign.astype(object)
        asign[fuera] = [f"Más cercano ({d:,.0f} m)" for d in metros]
    r = m.iloc[idx][["cvegeo", "estado", "municipio", "poblacion"]].reset_index(drop=True)
    r["asignacion"] = asign
    return r


def poblacion_estados():
    m = municipios()
    return m.groupby("estado")["poblacion"].sum()
