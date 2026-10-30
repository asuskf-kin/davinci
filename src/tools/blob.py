"""Azure Blob en SOLO LECTURA: listar la última corrida de una ruta y bajarla al espejo local data/.

La cadena viene de .env (AZURE_STORAGE_CONNECTION_STRING, con o sin espacios alrededor del "=") y nunca se imprime.
"""
import os
from functools import cache

from dotenv import dotenv_values

from src.config import settings


@cache
def contenedor(nombre=settings.CONTENEDOR):
    from azure.storage.blob import BlobServiceClient

    env = {k.strip(): (v or "").strip().strip('"') for k, v in dotenv_values(settings.RAIZ / ".env").items()}
    cadena = env.get("AZURE_STORAGE_CONNECTION_STRING") or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not cadena:
        raise RuntimeError("falta AZURE_STORAGE_CONNECTION_STRING en .env o en el entorno")
    return BlobServiceClient.from_connection_string(cadena).get_container_client(nombre)


def ultima_corrida(prefijo):
    """Archivos (nombre → tamaño) de la carpeta de fecha más reciente bajo `prefijo` ({prefijo}{AAAAMMDD}/…)."""
    if prefijo.split("/")[0] not in settings.CAPAS:
        raise SystemExit(f"{prefijo}: solo se leen las capas {settings.CAPAS} (bronze para arriba). Paro aquí.")
    archivos = {b.name: b.size for b in contenedor().list_blobs(name_starts_with=prefijo) if b.size}
    if not archivos:
        return None, {}
    fecha = max(n[len(prefijo):].split("/")[0] for n in archivos)
    return fecha, {n: s for n, s in archivos.items() if n.startswith(f"{prefijo}{fecha}/")}


def descargar(nombre, tamano):
    """Baja el blob a data/<nombre>; si ya está con el mismo tamaño, no lo vuelve a bajar."""
    local = settings.DATA / nombre
    if local.exists() and local.stat().st_size == tamano:
        return local
    local.parent.mkdir(parents=True, exist_ok=True)
    with open(local, "wb") as f:
        contenedor().download_blob(nombre, max_concurrency=8).readinto(f)
    return local
