"""Reglas de cadenas de retail (por nombre del cliente) y columnas de cada embotellador. Editar aquí, no en el código.

Aprendido del Excel de referencia OXXO_Walmart_Costco_Nacional (Femsa MX, 2026-10-30):
OXXO = "OXXO" u "O X X O" en el nombre; Walmart = Wal-Mart / Superama / Supercenter; Costco = Costco.
Las regex se aplican sobre el nombre en MAYÚSCULAS. Gana la primera cadena que cumple.
"""

# clave → nombre, regex que la identifica, regex que la excluye, formatos (primer patrón que cumple; si ninguno, el último)
CADENAS = {
    "oxxo": {"nombre": "OXXO", "si": r"\bO\s?X\s?X\s?O\b", "no": None,
             "formatos": [("OXXO Gas", r"\bGAS\b"), ("OXXO Tienda", None)]},
    "walmart": {"nombre": "Walmart", "si": r"WAL[\s\-\.]?MART|SUPERAMA|SUPER\s?CENTER", "no": r"^KK\b|BODEGA|AURRERA|SAM'?S|SUPER CENTRO|FARMA",
                "formatos": [("Walmart Express", r"EXPRESS|SUPERAMA"), ("Walmart Supercenter", None)]},
    "costco": {"nombre": "Costco", "si": r"COSTCO", "no": r"\bCOSCO\b",  # COSCO = Coscomatepec (no es Costco)
               "formatos": [("Costco", None)]},
    "bodega_aurrera": {"nombre": "Bodega Aurrerá", "si": r"AURRERA", "no": None,
                       "formatos": [("Mi Bodega / Express", r"MI BODEGA|EXPRESS"), ("Bodega Aurrerá", None)]},
    "sams": {"nombre": "Sam's Club", "si": r"\bSAM'?S\b", "no": None, "formatos": [("Sam's Club", None)]},
    "soriana": {"nombre": "Soriana", "si": r"SORIANA", "no": None, "formatos": [("Soriana", None)]},
    "chedraui": {"nombre": "Chedraui", "si": r"CHEDRAUI", "no": None, "formatos": [("Chedraui", None)]},
    "seven": {"nombre": "7-Eleven", "si": r"7[\s\-]?ELEVEN", "no": None, "formatos": [("7-Eleven", None)]},
    "circle_k": {"nombre": "Circle K", "si": r"CIRCLE\s?K|CIRCULO\s?K", "no": None, "formatos": [("Circle K", None)]},
    "dunosusa": {"nombre": "Dunosusa", "si": r"DUNOSUSA", "no": None, "formatos": [("Dunosusa", None)]},
    "super_aki": {"nombre": "Super Aki", "si": r"SUPER\s?AKI", "no": None, "formatos": [("Super Aki", None)]},
}
POR_DEFECTO = ("oxxo", "walmart", "costco")

# Limpieza para inferir la franquicia (cuando la regex no la encuentra): alias sobre el nombre limpio y compacto
# (sin acentos, signos ni espacios; "O X X O" → "OXXO") y, si no, coincidencia aproximada por palabra (≥ SIMILITUD)
ALIAS = {
    "oxxo": ["OXXO"], "walmart": ["WALMART", "SUPERAMA", "SUPERCENTER"], "costco": ["COSTCO"],
    "bodega_aurrera": ["AURRERA"], "sams": ["SAMSCLUB"], "soriana": ["SORIANA"], "chedraui": ["CHEDRAUI"],
    "seven": ["7ELEVEN", "SEVENELEVEN"], "circle_k": ["CIRCLEK", "CIRCULOK"], "dunosusa": ["DUNOSUSA"], "super_aki": ["SUPERAKI"],
}
SIMILITUD = 0.88  # SORIANO≈SORIANA (0.857) queda fuera

# Tipo de punto: el primero que cumple; si ninguno, "Tienda"
TIPOS_PUNTO = [
    ("Comedor de empleados", r"COMEDOR(?! WALMART EXPRESS)"),
    ("Corporativo / oficinas", r"CORPORATIVO|CORPORTIVO|OFICINAS|INCORP"),
    ("CEDIS / logística", r"\bCEDIS\b|CENTRO DE DISTRIBUCION"),
    ("Vending (máquinas)", r"VENDING"),
    ("Restaurante dentro de tienda", r"SUBWAY|RESTAURANTE|CAFETERIA|^KK\b|COMEDOR WALMART EXPRESS"),
    ("Punto adicional en tienda (accesos/cajas)", r"ACCESO|\bCAJAS?\b"),
]

# Columnas propias de cada embotellador en bronze/clients (las que no tiene, no se muestran)
COLUMNAS = {
    "femsa": {"zona": "Zone", "subcanal": "BU_Channel", "grupo": "Channel_Group", "ingreso": "gross_rev",
              "cajas": "unit_cases", "descuento": "discount_ac", "mes": "month_cal"},
    "bepensa": {"zona": "cedis", "subcanal": "pos_subchannel", "grupo": "pos_consumer_type"},
}
