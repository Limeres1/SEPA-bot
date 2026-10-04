"""
seleccion_historial.py — Decide, UNA SOLA VEZ, qué sucursales seguir
para armar el historial de precios, y guarda esa elección en disco.

Por qué persistir y no recalcular cada día: si eligiéramos sucursales
al azar en cada corrida, nunca se armaría una serie de tiempo
consistente (hoy seguirías la sucursal A, mañana la B, y el gráfico de
evolución de precio no tendría sentido). Se elige una vez, se guarda
en 'data/state/sucursales_seguidas.json', y de ahí en adelante todas
las corridas usan siempre la misma selección.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from . import config

logger = logging.getLogger("sepa_bot.seleccion")


def _leer_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def obtener_sucursales_seguidas() -> set[tuple[str, str]]:
    """
    Devuelve un set de tuplas (id_comercio, id_sucursal) a seguir.

    Si ya existe una selección guardada, la reutiliza tal cual. Si no
    existe todavía, arma una nueva: agrupa las sucursales disponibles
    por comercio, y elige 1 sucursal al azar de cada una de hasta
    HISTORIAL_MAX_COMERCIOS cadenas distintas.
    """
    archivo = config.HISTORIAL_SUCURSALES_ARCHIVO

    if archivo.exists():
        with open(archivo, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {(d["id_comercio"], d["id_sucursal"]) for d in data}

    sucursales = _leer_jsonl(config.JSON_DIR / "sucursales.jsonl")
    if not sucursales:
        logger.warning(
            "No hay sucursales.jsonl todavía; no se puede armar la selección de seguimiento en esta corrida."
        )
        return set()

    por_comercio: dict[str, list[dict]] = {}
    for s in sucursales:
        por_comercio.setdefault(s.get("id_comercio"), []).append(s)

    comercios_disponibles = list(por_comercio.keys())
    random.shuffle(comercios_disponibles)
    elegidos = comercios_disponibles[: config.HISTORIAL_MAX_COMERCIOS]

    seleccion = []
    for id_comercio in elegidos:
        candidata = random.choice(por_comercio[id_comercio])
        seleccion.append({
            "id_comercio": id_comercio,
            "id_sucursal": candidata.get("id_sucursal"),
            "nombre": candidata.get("sucursales_nombre"),
            "localidad": candidata.get("sucursales_localidad"),
        })

    archivo.parent.mkdir(parents=True, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(seleccion, f, ensure_ascii=False, indent=2)

    logger.info(
        "Selección de sucursales a seguir armada por primera vez: "
        "%d sucursales de %d cadenas distintas -> guardada en %s",
        len(seleccion), len(elegidos), archivo,
    )
    return {(d["id_comercio"], d["id_sucursal"]) for d in seleccion}
