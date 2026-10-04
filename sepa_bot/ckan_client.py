"""
ckan_client.py — Habla con la API CKAN del portal de datos abiertos.

CKAN es el software que usan la gran mayoría de los portales de datos
abiertos de gobierno (datos.gob.ar, datos.produccion.gob.ar, data.gov,
etc.). Todos exponen el mismo endpoint estándar:

    GET /api/3/action/package_show?id=<dataset_id>

que devuelve un JSON con la metadata del dataset, incluyendo la lista
de "resources" (los archivos descargables), cada uno con su URL directa,
formato y fecha de última modificación.

Esto es, ni más ni menos, lo que hace el botón "Descargar" que ves en
la página del dataset: llama a esta misma API por detrás.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

from . import config

logger = logging.getLogger("sepa_bot.ckan")

DIAS_ES = [
    "lunes", "martes", "miercoles", "jueves",
    "viernes", "sabado", "domingo",
]


def _normalizar(texto: str) -> str:
    """Saca tildes y pasa a minúsculas para poder comparar 'Miércoles' == 'miercoles'."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().lower()


class CKANError(RuntimeError):
    """Cualquier problema al hablar con la API de CKAN."""


class CKANClient:
    def __init__(self, base_url: str = config.CKAN_BASE_URL, dataset_id: str = config.DATASET_ID):
        self.base_url = base_url.rstrip("/")
        self.dataset_id = dataset_id
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "sepa-bot-demo/1.0 (+proyecto academico Analista de Sistemas)"
        })
        if config.CKAN_API_KEY:
            self.session.headers["Authorization"] = config.CKAN_API_KEY

    def get_package(self) -> dict[str, Any]:
        """Trae la metadata completa del dataset (incluye la lista de recursos)."""
        url = f"{self.base_url}/api/3/action/package_show"
        try:
            resp = self.session.get(
                url, params={"id": self.dataset_id}, timeout=config.HTTP_TIMEOUT_SECONDS
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CKANError(f"No se pudo consultar {url} (id={self.dataset_id}): {exc}") from exc

        payload = resp.json()
        if not payload.get("success"):
            raise CKANError(f"CKAN respondió success=false para id={self.dataset_id}: {payload}")

        return payload["result"]

    def list_resources(self) -> list[dict[str, Any]]:
        package = self.get_package()
        resources = package.get("resources", [])
        if not resources:
            raise CKANError(f"El dataset '{self.dataset_id}' no tiene recursos publicados.")
        return resources

    def pick_todays_resource(self, resources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """
        Los recursos de este dataset se llaman literalmente 'Lunes', 'Martes',
        etc. y se pisan/actualizan cada día. Elegimos el que coincide con
        el día de hoy; si no lo encontramos (por si cambian el naming),
        caemos al recurso con la fecha de modificación más reciente.
        """
        if resources is None:
            resources = self.list_resources()

        hoy = DIAS_ES[datetime.now().weekday()]

        for r in resources:
            nombre = _normalizar(r.get("name", ""))
            if nombre == hoy:
                logger.info("Recurso de hoy encontrado por nombre: '%s'", r.get("name"))
                return r

        logger.warning(
            "No encontré un recurso llamado '%s'; uso el de fecha de modificación más reciente.",
            hoy,
        )
        return max(
            resources,
            key=lambda r: r.get("last_modified") or r.get("metadata_modified") or "",
        )

    def pick_resource_for_date(
        self, target_date: date, resources: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Return the resource named for target_date's weekday without a stale fallback."""
        if resources is None:
            resources = self.list_resources()

        target_name = DIAS_ES[target_date.weekday()]
        for resource in resources:
            if _normalizar(str(resource.get("name", ""))) == target_name:
                return resource

        raise CKANError(f"No existe recurso CKAN para el día '{target_name}'.")


def resource_updated_on(
    resource: dict[str, Any], target_date: date, allow_next_day: bool = False
) -> bool:
    """Check that the resource itself was updated on the target local date."""
    value = resource.get("last_modified")
    if not value:
        return False
    try:
        modified = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if modified.tzinfo is None:
        modified = modified.replace(tzinfo=timezone.utc)
    modified_date = modified.astimezone(ZoneInfo(config.RUN_TIMEZONE)).date()
    allowed_dates = {target_date}
    if allow_next_day:
        from datetime import timedelta

        allowed_dates.add(target_date + timedelta(days=1))
    return modified_date in allowed_dates
