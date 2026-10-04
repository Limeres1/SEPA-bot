"""
downloader.py — Descarga el recurso elegido y lo deja listo como CSV.

Maneja dos casos:
  - El recurso ya es un .csv directo -> se descarga tal cual.
  - El recurso es un .zip (lo más probable dado el volumen diario del
    SEPA) -> se descarga y se extrae, devolviendo la ruta al/los .csv
    encontrados adentro.
"""

from __future__ import annotations

import logging
import time
import zipfile
from pathlib import Path
from typing import Any

import requests

from . import config

logger = logging.getLogger("sepa_bot.downloader")


class DownloadError(RuntimeError):
    pass


def download_file(url: str, dest: Path) -> Path:
    """Descarga con reintentos y en streaming (no carga todo en memoria)."""
    last_exc: Exception | None = None

    for intento in range(1, config.MAX_RETRIES + 1):
        try:
            logger.info("Descargando (intento %d/%d): %s", intento, config.MAX_RETRIES, url)
            with requests.get(url, stream=True, timeout=config.HTTP_TIMEOUT_SECONDS) as resp:
                resp.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=config.DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
            logger.info("Descarga OK -> %s (%.2f MB)", dest, dest.stat().st_size / 1024 / 1024)
            return dest
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Falló el intento %d: %s", intento, exc)
            if intento < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF_SECONDS * intento)  # backoff simple

    raise DownloadError(f"No se pudo descargar {url} tras {config.MAX_RETRIES} intentos") from last_exc


def _extraer_zip(path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        zf.extractall(dest_dir)


def extract_csvs_if_needed(path: Path, extract_dir: Path, max_profundidad: int = 5) -> list[Path]:
    """
    Si 'path' es un .zip, lo extrae y devuelve las rutas a los .csv que
    contenga. Si ya es un .csv, lo devuelve tal cual en una lista.

    El SEPA entrega el archivo del día como un .zip que, adentro, trae
    OTROS .zip (uno por comercio: 'sepa_1_comercio-sepa-12_...zip',
    etc.), y recién dentro de esos están los .csv. Por eso esta función
    extrae en capas: después de cada extracción, vuelve a buscar si
    aparecieron nuevos .zip y los extrae también, hasta un máximo de
    'max_profundidad' niveles (para no quedar en un loop infinito si
    algún día cambia el formato).

    Algunos comercios suben un .zip de 0 bytes (no reportaron precios
    ese día) o corrupto; esos se omiten con un warning en vez de
    frenar todo el proceso.
    """
    if path.suffix.lower() == ".csv":
        return [path]

    if path.suffix.lower() != ".zip":
        raise DownloadError(f"Formato de archivo no soportado: {path.suffix} ({path})")

    logger.info("Extrayendo %s en %s", path, extract_dir)
    _extraer_zip(path, extract_dir)

    zips_procesados: set[str] = set()
    for profundidad in range(max_profundidad):
        zips_encontrados = sorted(extract_dir.rglob("*.zip"))
        zips_nuevos = [z for z in zips_encontrados if str(z) not in zips_procesados]
        if not zips_nuevos:
            break

        logger.info(
            "Nivel %d: encontrados %d zip(s) anidados, extrayendo...",
            profundidad + 1, len(zips_nuevos),
        )
        for z in zips_nuevos:
            zips_procesados.add(str(z))
            if z.stat().st_size == 0:
                logger.warning("Zip vacío (0 bytes), se omite: %s", z.name)
                continue
            try:
                _extraer_zip(z, z.parent / (z.stem + "_extraido"))
            except zipfile.BadZipFile:
                logger.warning("Zip corrupto o inválido, se omite: %s", z.name)

    csvs = sorted(extract_dir.rglob("*.csv"))
    if not csvs:
        raise DownloadError(
            f"No se encontró ningún .csv tras extraer recursivamente {path} "
            f"(revisados {len(zips_procesados)} zip(s) anidados)"
        )
    return csvs


def download_resource(resource: dict[str, Any], dest_dir: Path) -> tuple[list[Path], list[Path]]:
    """
    Descarga un recurso de CKAN (dict con 'url', 'format', 'name') y
    devuelve una tupla (csvs, artefactos_temporales):

    - csvs: la lista de rutas .csv listas para procesar.
    - artefactos_temporales: la lista de rutas (el .zip descargado y,
      si corresponde, la carpeta donde se extrajo) que se pueden
      borrar una vez que ya se terminó de convertir todo a JSON. A
      escala nacional esto puede pesar varios GB por día, así que
      limpiarlo es necesario para poder dejar el bot corriendo
      desatendido durante mucho tiempo (ver config.LIMPIAR_RAW_DESPUES).
    """
    url = resource.get("url")
    if not url:
        raise DownloadError(f"El recurso no tiene URL de descarga: {resource}")

    nombre = resource.get("name", "recurso")
    formato = (resource.get("format") or "").lower()
    es_zip = "zip" in formato or url.lower().endswith(".zip")
    sufijo = ".zip" if es_zip else ".csv"

    fecha = time.strftime("%Y-%m-%d")
    dest_file = dest_dir / f"{fecha}_{nombre}{sufijo}"

    downloaded = download_file(url, dest_file)
    extract_dir = dest_dir / f"{fecha}_{nombre}_extraido"
    csvs = extract_csvs_if_needed(downloaded, extract_dir)

    artefactos_temporales = [downloaded]
    if es_zip:
        artefactos_temporales.append(extract_dir)

    return csvs, artefactos_temporales
