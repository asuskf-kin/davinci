import json
import subprocess
import sys
import unittest

import pandas as pd

from src import main
from src.config import settings
from src.tools import blob, cadenas, evaluacion, mapa


class Sandbox(unittest.TestCase):
    def hook(self, comando):
        p = subprocess.run([sys.executable, "src/runtime/sandbox.py"], input=json.dumps({"tool_input": {"command": comando}}),
                           capture_output=True, text=True, cwd=settings.RAIZ)
        return p.stdout

    def test_pide_ok_al_tocar_el_blob(self):
        self.assertIn('"ask"', self.hook("uv run python -m src.main subir paso2"))
        self.assertIn('"ask"', self.hook("python -c 'c.upload_blob(x)'"))

    def test_deja_pasar_lo_local(self):
        self.assertEqual(self.hook("uv run python -m src.main cadenas"), "")


class Entrada(unittest.TestCase):
    def test_comando_desconocido(self):
        self.assertEqual(main.main(["xyz"]), 2)

    def test_salida_en_la_raiz_con_fecha(self):
        self.assertEqual(settings.salida("mx", "hydration", "20261030"),
                         settings.RAIZ / "outputs" / "20261030_cp_hydration_mx")

    def test_solo_bronze_para_arriba(self):
        with self.assertRaises(SystemExit):
            blob.ultima_corrida("drop_zone/ko/mx/femsa/products_nsr/")


def clientes():
    return pd.DataFrame({
        "embotellador": ["Femsa", "Femsa", "Bepensa"], "pos_id": ["1", "2", "3"], "estado": ["A", "B", "C"],
        "municipio": ["a", "b", "c"], "segmento": ["En riesgo", "Frecuente", "Nuevo"],
        "lat": [19.4326077, 19.5, 21.0], "lon": [-99.1332080, -99.2, -89.6],
        "revenue_12m": [100.0, 300.0, 50.0], "revenue_12m_anterior": [200.0, 100.0, 0.0], "cajas_12m": [1.0, 3.0, 0.5],
        "meses_con_compra": [5, 20, 2], "potencial_cajas_mes": [2.0, 0.0, float("nan")],
        "cajas_mes_modelo": [10.0, 5.0, float("nan")], "prioridad": ["High", "Low", None],
    })


class Evaluacion(unittest.TestCase):
    def test_por_estado_cuadra_y_sin_gold_queda_vacio(self):
        t = evaluacion.por(clientes(), "estado")
        self.assertEqual(t.groupby("embotellador")["revenue_12m"].sum().to_dict(), {"Bepensa": 50.0, "Femsa": 400.0})
        self.assertTrue(t.loc[t["embotellador"] == "Bepensa", "potencial_cajas_mes"].isna().all())
        self.assertEqual(t.loc[t["estado"] == "A", "crecimiento_vs_anio_anterior"].item(), -0.5)

    def test_mapa_sin_coordenadas_de_pdv(self):
        d = mapa._datos(clientes())
        texto = json.dumps(d)
        self.assertNotIn("19.4326077", texto)
        self.assertNotIn("-99.133208", texto)
        self.assertEqual(sum(n for n, r in zip(d["col"]["n"], d["col"]["res"]) if r == 6), 3)


class Cadenas(unittest.TestCase):
    def test_limpieza_infiere_la_franquicia(self):
        n = pd.Series(["O X X O ROMA SUR", "OXXO12605 31", "WAL - MART STA MARIA", "SAM´S CLUB IXTAPALUCA",
                       "GYM BOX XOLALPA", "KK WALMART PERISUR", "FRAGUA 917 CARRET. COSCO", "SUPER FARMA SHOP GO",
                       "WALTMART VICTORIA CENTRO", "COSTCO COAPA COMEDOR"])
        cad, fmt, tipo, limpio, metodo = cadenas.clasificar(n, ["oxxo", "walmart", "costco", "sams"])
        self.assertEqual(cad.fillna("-").tolist(), ["OXXO", "OXXO", "Walmart", "Sam's Club", "-", "-", "-", "-", "Walmart", "Costco"])
        self.assertEqual(metodo[8], "aproximado (verificar)")
        self.assertEqual(limpio[0], "OXXO ROMA SUR")
        self.assertEqual(tipo[9], "Comedor de empleados")

    def test_territorios(self):
        t = cadenas.territorios("Mérida=bepensa:Yucatán/Mérida; CDMX=femsa:Ciudad de México")
        self.assertEqual(t, {"Mérida": {"emb": "bepensa", "estado": "Yucatán", "municipio": "Mérida"},
                             "CDMX": {"emb": "femsa", "estado": "Ciudad de México", "municipio": None}})
        self.assertEqual(cadenas.slug("Mérida"), "merida")


if __name__ == "__main__":
    unittest.main()
