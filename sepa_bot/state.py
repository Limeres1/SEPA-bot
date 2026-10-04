"""Registro de la última ejecución y su resultado para diagnóstico."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import config


def guardar_estado(resultado: dict[str, Any]) -> None:
    estado = {
        "ultima_corrida_utc": datetime.now(timezone.utc).isoformat(),
        "resultado": resultado,
    }
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def leer_estado() -> dict[str, Any] | None:
    if not config.STATE_FILE.exists():
        return None
    with open(config.STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
