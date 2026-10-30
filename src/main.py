"""Entrada única del agente davinci (el cerebro y el bucle son Claude Code; esto son sus herramientas).

Uso: uv run python -m src.main <comando> [flags]

  evaluar   evalúa Customer Potential de un análisis (p. ej. hydration) para varios embotelladores con los datos
            del datawarehouse (silver de clientes + ventas de bronze + gold si existe) → mapa.html + Excel.
            Solo lectura en el blob. Ej.: evaluar --pais mx --analisis hydration --embotelladores femsa,bepensa
  cadenas   retail por cadena (OXXO, Walmart, Costco… en src/config/cadenas.py) con clientes, catálogo validado, ventas y
            potencial → Excel con fórmulas por embotellador + tablero HTML. Ej.: cadenas --cadenas oxxo,walmart,costco
"""
import sys

from src.runtime import executor

COMANDOS = {"evaluar": "src.tools.evaluacion", "cadenas": "src.tools.cadenas"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMANDOS:
        print(__doc__)
        return 2
    modulo = __import__(COMANDOS[argv[0]], fromlist=["main"])
    executor.correr(argv[0], modulo.main, argv[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
