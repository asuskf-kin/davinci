"""Rutas y constantes del agente (fuente: SPEC §8.1, paths del datawarehouse en minúsculas)."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # consolas cp1252 se caen con "→" / "✓"
sys.stderr.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "data"            # espejo local del blob (fuera de git)
STATE = RAIZ / "state"          # bitácora de corridas
CONTENEDOR = "prospecting-data"
# Por defecto el agente solo usa datos validados del datawarehouse: bronze y capas superiores (nunca drop_zone crudo)
CAPAS = ("bronze", "silver", "gold")

# Embotelladores que se evalúan por defecto (análisis hydration, canal moderno; ambos con silver en el datawarehouse).
EMBOTELLADORES = ("femsa", "bepensa")


def silver_clientes(pais, emb, analisis, canal_en="modern"):
    return f"silver/ko/{pais}/{emb}/clients/{analisis}_{canal_en}/"


def bronze_ventas(pais, emb, analisis):
    return f"bronze/ko/{pais}/{emb}/sales/{analisis}/"


def gold_cp(pais, emb, analisis):
    return f"gold/ko/{pais}/{emb}/customer_potencial/{analisis}/"


def salida(pais, analisis, fecha):
    """Entregables en la raíz del repo: outputs/{AAAAMMDD}_cp_{analisis}_{pais}/ (nunca se suben al blob)."""
    return RAIZ / "outputs" / f"{fecha}_cp_{analisis}_{pais}"
