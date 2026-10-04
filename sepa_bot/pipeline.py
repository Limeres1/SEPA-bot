"""
pipeline.py — Orquesta la corrida de descarga y captura semanal:

    1. Preguntarle a CKAN qué recursos tiene el dataset del SEPA.
    2. En modo semanal, elegir el recurso del lunes y verificar su fecha.
    3. Descargarlo (y extraerlo si viene en .zip).
    4. Convertir el/los CSV resultantes a JSON Lines.
    5. Guardar precios reconocidos y sucursales en SQLite.
    6. Guardar un registro de la corrida (para diagnóstico).

El daemon la llama los lunes a la hora configurada o el martes para
recuperar una ejecución ausente. El CLI --once procesa la semana actual.
"""

from __future__ import annotations

import logging
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

from . import config, state
from .ckan_client import CKANClient, CKANError, resource_updated_on
from .downloader import DownloadError, download_resource
from .csv_to_json import convertir_multiples
from .weekly_history import (
    capturar_precios_semanales,
    registrar_sin_actualizacion,
    semana_procesada,
)

logger = logging.getLogger("sepa_bot.pipeline")


def _limpiar_temporales(rutas: list[Path]) -> None:
    for ruta in rutas:
        try:
            if ruta.is_dir():
                shutil.rmtree(ruta, ignore_errors=True)
            elif ruta.exists():
                ruta.unlink()
        except OSError as exc:
            logger.warning("No se pudo limpiar %s: %s", ruta, exc)
    logger.info("Limpieza de temporales completada (%d elemento(s) revisados).", len(rutas))


def ejecutar_pipeline(
    fecha_semana: date | None = None,
    permitir_actualizacion_martes: bool = False,
) -> dict:
    logger.info("=== Inicio de corrida del bot SEPA ===")
    resultado: dict = {"ok": False}

    try:
        if fecha_semana and semana_procesada(config.DB_PATH, fecha_semana):
            resultado = {
                "ok": True,
                "historial": {"fecha_semana": fecha_semana.isoformat(), "estado": "ya_procesada"},
            }
            state.guardar_estado(resultado)
            return resultado

        cliente = CKANClient()
        recursos = cliente.list_resources()
        recurso = (
            cliente.pick_resource_for_date(fecha_semana, recursos)
            if fecha_semana
            else cliente.pick_todays_resource(recursos)
        )
        logger.info(
            "Recurso elegido: '%s' (formato=%s, última modificación=%s)",
            recurso.get("name"), recurso.get("format"), recurso.get("last_modified"),
        )

        if fecha_semana and not resource_updated_on(
            recurso, fecha_semana, allow_next_day=permitir_actualizacion_martes
        ):
            fecha_modificacion = recurso.get("last_modified") or "desconocida"
            historial = registrar_sin_actualizacion(
                config.DB_PATH,
                fecha_semana,
                f"El recurso del lunes no fue actualizado en la fecha esperada; last_modified={fecha_modificacion}",
            )
            resultado = {"ok": True, "recurso": recurso.get("name"), "historial": historial}
            state.guardar_estado(resultado)
            return resultado

        csv_paths, artefactos_temporales = download_resource(recurso, config.RAW_DIR)
        logger.info("Se encontraron %d archivo(s) CSV tras la extracción.", len(csv_paths))

        # El SEPA entrega un CSV por comercio, todos con el mismo nombre
        # de archivo ('productos.csv', 'sucursales.csv', 'comercio.csv').
        # Los agrupamos por nombre para combinarlos en un solo .jsonl por
        # tipo, en vez de que cada comercio pise el archivo del anterior.
        grupos: dict[str, list[Path]] = defaultdict(list)
        for csv_path in csv_paths:
            grupos[csv_path.name].append(csv_path)

        conversiones = []
        for nombre_archivo, paths in grupos.items():
            nombre_salida = Path(nombre_archivo).stem + (
                ".jsonl" if config.OUTPUT_FORMAT == "jsonl" else ".json"
            )
            out_path = config.JSON_DIR / nombre_salida
            resumen = convertir_multiples(paths, out_path)
            conversiones.append(resumen)

        historial = None
        if fecha_semana and config.HISTORIAL_ENABLED:
            if config.HISTORIAL_CSV_OBJETIVO not in grupos:
                raise DownloadError("El recurso no contiene productos.csv para la captura semanal.")
            if config.OUTPUT_FORMAT != "jsonl":
                raise RuntimeError("La captura semanal requiere OUTPUT_FORMAT=jsonl.")
            historial = capturar_precios_semanales(
                db_path=config.DB_PATH,
                week_date=fecha_semana,
                productos_jsonl=config.JSON_DIR / "productos.jsonl",
                sucursales_jsonl=config.JSON_DIR / "sucursales.jsonl",
                comercios_jsonl=config.JSON_DIR / "comercio.jsonl",
                archivo_seleccion=config.HISTORIAL_SUCURSALES_ARCHIVO,
            )

        if config.LIMPIAR_RAW_DESPUES:
            _limpiar_temporales(artefactos_temporales)

        resultado = {
            "ok": True,
            "recurso": {
                "nombre": recurso.get("name"),
                "formato": recurso.get("format"),
                "url": recurso.get("url"),
                "last_modified": recurso.get("last_modified"),
            },
            "conversiones": conversiones,
            "historial": historial,
        }

    except CKANError as exc:
        logger.error("Error consultando el portal de datos abiertos: %s", exc)
        resultado = {"ok": False, "error": f"CKANError: {exc}"}
    except DownloadError as exc:
        logger.error("Error descargando/extrayendo el recurso: %s", exc)
        resultado = {"ok": False, "error": f"DownloadError: {exc}"}
    except Exception as exc:  # salvaguarda: nunca queremos que el bot muera en silencio
        logger.exception("Error inesperado en el pipeline")
        resultado = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    state.guardar_estado(resultado)
    logger.info("=== Fin de corrida del bot SEPA (ok=%s) ===", resultado.get("ok"))
    return resultado
