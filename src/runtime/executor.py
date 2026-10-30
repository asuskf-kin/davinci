"""Corre una herramienta y la anota en state/corridas.jsonl, salga bien o mal (comando, argv, código, error, segundos)."""
import json
import time
from datetime import datetime

from src.config import settings


def correr(comando, funcion, argv):
    inicio, codigo, error = time.time(), 0, None
    try:
        return funcion(argv)
    except BaseException as e:  # también SystemExit / KeyboardInterrupt: la bitácora lo anota y se relanza
        codigo, error = (e.code if isinstance(e, SystemExit) and isinstance(e.code, int) else 1), repr(e)
        raise
    finally:
        settings.STATE.mkdir(exist_ok=True)
        with open(settings.STATE / "corridas.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"cuando": datetime.now().isoformat(timespec="seconds"), "comando": comando,
                                "argv": argv, "codigo": codigo, "error": error,
                                "segundos": round(time.time() - inicio, 1)}, ensure_ascii=False) + "\n")
