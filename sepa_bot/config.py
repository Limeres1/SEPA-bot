"""
config.py — Configuración central del bot SEPA.

Todo lo que puede necesitar ajustarse (dataset a consultar, carpetas de
salida, horario de corrida, etc.) vive acá para no tener que tocar el
resto del código.
"""

import os
from pathlib import Path


def _cargar_variables_de_entorno() -> None:
    """Carga .env cuando está disponible sin romper la ejecución local."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env", override=False)


_cargar_variables_de_entorno()

# --- Portal de datos abiertos (CKAN) -----------------------------------
# datos.produccion.gob.ar corre sobre CKAN, el mismo software que usa
# datos.gob.ar. La API REST de CKAN es siempre la misma, cambia el id
# del dataset ("package") y el host.
CKAN_BASE_URL = "https://datos.produccion.gob.ar"
CKAN_PACKAGE_SHOW_ENDPOINT = f"{CKAN_BASE_URL}/api/3/action/package_show"
CKAN_API_KEY = os.environ.get("CKAN_API_KEY", "").strip()

# Dataset recomendado: Precios Claros - Base SEPA (minorista).
# Si en algún momento cambia el "id" del dataset en el portal, alcanza
# con actualizar esta constante.
DATASET_ID = "sepa-precios"

# Nombre alternativo por si el id anterior deja de resolver (fallback).
DATASET_ID_FALLBACK_URL = f"{CKAN_BASE_URL}/dataset/sepa-precios"

# --- Carpetas de trabajo -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"       # acá caen los .csv/.zip descargados tal cual
JSON_DIR = DATA_DIR / "json"     # acá caen los .jsonl ya convertidos
STATE_DIR = DATA_DIR / "state"   # acá vive el registro de la última corrida
LOG_DIR = DATA_DIR / "logs"

for d in (RAW_DIR, JSON_DIR, STATE_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

STATE_FILE = STATE_DIR / "last_run.json"

# --- Base de datos --------------------------------------------------------
# El proyecto soporta dos modos:
#   - sqlite  : usa el archivo local data/sepa.db
#   - postgres: usa DATABASE_URL (por ejemplo, la conexión de Neon)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_MODE = os.environ.get("DB_MODE", "sqlite").strip().lower()
if DB_MODE not in {"sqlite", "postgres"}:
    raise ValueError("DB_MODE debe ser 'sqlite' o 'postgres'.")
DB_PATH = Path(os.environ.get("DB_PATH", str(DATA_DIR / "sepa.db")))

# --- Programación de la captura semanal ----------------------------------
# Hora local de la captura del lunes y zona horaria explícita para evitar
# depender de la configuración regional del servidor.
RUN_AT = os.environ.get("RUN_AT", "14:00")
RUN_TIMEZONE = os.environ.get("RUN_TIMEZONE", "America/Argentina/Buenos_Aires")

# --- Descarga --------------------------------------------------------------
HTTP_TIMEOUT_SECONDS = 60
DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

# --- Conversión CSV -> JSON ------------------------------------------------
# Si en el futuro se conoce el separador/encoding real del CSV del SEPA,
# fijarlo acá evita tener que auto-detectarlo en cada corrida.
# Dejar en None para que el bot lo detecte automáticamente.
CSV_DELIMITER = None      # ej: "|" o ";" si se conoce de antemano
CSV_ENCODING = None       # ej: "latin-1" si se conoce de antemano

# Formato de salida: "jsonl" (una línea JSON por registro, recomendado
# para datasets grandes) o "json" (un único array, más cómodo para
# demos chicas pero poco práctico con millones de filas).
OUTPUT_FORMAT = "jsonl"

# --- Historial semanal de precios ----------------------------------------
HISTORIAL_ENABLED = True
# Conservado para compatibilidad con la carga de un historial JSONL antiguo.
HISTORIAL_ARCHIVO = "historial_precios.jsonl"

# CSV de origen de precios dentro del recurso semanal.
HISTORIAL_CSV_OBJETIVO = "productos.csv"
# La sucursal elegida se conserva entre semanas, mientras siga existiendo.
HISTORIAL_SUCURSALES_ARCHIVO = STATE_DIR / "sucursales_seguidas.json"

# --- Limpieza de temporales -------------------------------------------------
# El .zip descargado y las carpetas extraídas (que pueden pesar varios GB
# por día a escala nacional) se borran automáticamente después de convertir
# todo a JSON. Sin esto, correr el bot desatendido durante un año llena el
# disco igual, aunque el historial ya esté bien filtrado.
LIMPIAR_RAW_DESPUES = True

# Límite opcional de filas a convertir (útil para demos y pruebas).
# Poner None para procesar el archivo completo.
MAX_ROWS = None
