"""Marca Kin (skill brand-guidelines-kin) para todo lo visual: fuentes locales embebidas, logo oficial desde archivo
(nunca redibujado) y paleta. Excel: logo rasterizado a PNG con resvg. HTML: fuentes base64 + logo data-URI.
"""
import base64
from functools import cache

from src.config import settings

SKILL = settings.RAIZ / ".claude" / "skills" / "brand-guidelines-kin" / "assets"
LOGOS = {  # (tipo, fondo) → archivo oficial (§10 de la skill)
    ("formal", "oscuro"): "logos/formal/Kin_Logo_FV_19.svg", ("formal", "claro"): "logos/formal/Kin_Logo_FV_13.svg",
    ("informal", "oscuro"): "logos/informal/Kin_Logo_IV_19.svg", ("informal", "claro"): "logos/informal/Kin_Logo_IV_13.svg",
}
# Tokens (assets/tokens/colors_and_type.css)
AMARILLO, NEGRO, GRIS4, GRIS3, GRIS2, GRIS1, BLANCO = "#E5FF01", "#141417", "#222326", "#999EA6", "#D4D5D6", "#EFEFEE", "#FFFFFF"
SERIES_OSCURO = [AMARILLO, BLANCO, GRIS3, GRIS2]   # orden de series de la marca sobre fondo oscuro
SERIES_CLARO = [AMARILLO, NEGRO, GRIS3, GRIS2]     # sobre fondo claro (sin blanco); los claros llevan borde oscuro


def logo_png(tipo="formal", fondo="oscuro", alto=60):
    import resvg_py

    return resvg_py.svg_to_bytes(svg_path=str(SKILL / LOGOS[(tipo, fondo)]), height=alto)


def logo_data_uri(tipo="informal", fondo="oscuro"):
    return "data:image/svg+xml;base64," + base64.b64encode((SKILL / LOGOS[(tipo, fondo)]).read_bytes()).decode()


@cache
def fuentes_css():
    """@font-face de Space Grotesk y Albert Sans (variables, woff2 locales en base64): sin CDN."""
    css = []
    for fam, archivo, pesos in (("Space Grotesk", "space-grotesk.woff2", "300 700"), ("Albert Sans", "albert-sans.woff2", "100 900")):
        b64 = base64.b64encode((SKILL / "fonts" / archivo).read_bytes()).decode()
        css.append(f"@font-face{{font-family:'{fam}';src:url(data:font/woff2;base64,{b64}) format('woff2');"
                   f"font-weight:{pesos};font-style:normal;font-display:swap}}")
    return "\n".join(css)
