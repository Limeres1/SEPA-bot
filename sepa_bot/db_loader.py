"""
db_loader.py — Carga los .jsonl que ya genera el bot en una base de
datos SQLite real, para poder conectar Power BI (u otra herramienta)
directamente a un archivo .db en vez de a archivos sueltos.

Esquema (deliberadamente chico — ver el diagrama que te mostré):

    COMERCIO (id_comercio PK, nombre, ...)
    SUCURSAL (id_sucursal PK, id_comercio FK, direccion, ...)
    PRODUCTO (id_producto PK, descripcion, marca, ...)
    HISTORIAL_PRECIOS (id PK autoincremental, fecha, id_comercio FK,
                        id_sucursal FK, id_producto FK,
                        precio_lista, precio_referencia)

COMERCIO, SUCURSAL y PRODUCTO son "tablas de dimensión": se vacían y
se vuelven a cargar enteras en cada corrida (son el catálogo vigente,
no interesa su historia). HISTORIAL_PRECIOS es la única tabla que
CRECE con el tiempo: se usa INSERT OR IGNORE sobre una clave única
(fecha, id_comercio, id_sucursal, id_producto) para que correr este
script muchas veces sobre el mismo historial_precios.jsonl nunca
duplique filas.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

import psycopg

from . import config

logger = logging.getLogger("sepa_bot.db_loader")

DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS comercio (
    id_comercio TEXT PRIMARY KEY,
    nombre TEXT,
    razon_social TEXT,
    cuit TEXT
);

CREATE TABLE IF NOT EXISTS sucursal (
    id_comercio TEXT,
    id_sucursal TEXT,
    nombre TEXT,
    calle TEXT,
    numero TEXT,
    localidad TEXT,
    provincia TEXT,
    codigo_postal TEXT,
    latitud REAL,
    longitud REAL,
    PRIMARY KEY (id_comercio, id_sucursal),
    FOREIGN KEY (id_comercio) REFERENCES comercio(id_comercio)
);

CREATE TABLE IF NOT EXISTS producto (
    id_producto TEXT PRIMARY KEY,
    descripcion TEXT,
    marca TEXT
);

CREATE TABLE IF NOT EXISTS historial_precios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    id_comercio TEXT,
    id_sucursal TEXT,
    id_producto TEXT,
    precio_lista REAL,
    precio_referencia REAL,
    UNIQUE (fecha, id_comercio, id_sucursal, id_producto)
);

CREATE INDEX IF NOT EXISTS idx_historial_producto ON historial_precios(id_producto);
CREATE INDEX IF NOT EXISTS idx_historial_fecha ON historial_precios(fecha);
"""

DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS comercio (
    id_comercio TEXT PRIMARY KEY,
    nombre TEXT,
    razon_social TEXT,
    cuit TEXT
);

CREATE TABLE IF NOT EXISTS sucursal (
    id_comercio TEXT,
    id_sucursal TEXT,
    nombre TEXT,
    calle TEXT,
    numero TEXT,
    localidad TEXT,
    provincia TEXT,
    codigo_postal TEXT,
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    PRIMARY KEY (id_comercio, id_sucursal)
);

CREATE TABLE IF NOT EXISTS producto (
    id_producto TEXT PRIMARY KEY,
    descripcion TEXT,
    marca TEXT
);

CREATE TABLE IF NOT EXISTS historial_precios (
    id SERIAL PRIMARY KEY,
    fecha TEXT NOT NULL,
    id_comercio TEXT,
    id_sucursal TEXT,
    id_producto TEXT,
    precio_lista DOUBLE PRECISION,
    precio_referencia DOUBLE PRECISION,
    UNIQUE (fecha, id_comercio, id_sucursal, id_producto)
);

CREATE INDEX IF NOT EXISTS idx_historial_producto ON historial_precios(id_producto);
CREATE INDEX IF NOT EXISTS idx_historial_fecha ON historial_precios(fecha);
"""


def _leer_jsonl(path: Path):
    if not path.exists():
        logger.warning("No existe %s, se omite.", path)
        return
    with open(path, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                yield json.loads(linea)


def crear_esquema(conn) -> None:
    is_postgres = conn.__class__.__module__.startswith("psycopg")
    ddl = DDL_POSTGRES if is_postgres else DDL_SQLITE
    if is_postgres:
        with conn.cursor() as cur:
            cur.execute(ddl)
    else:
        conn.executescript(ddl)
    conn.commit()


def _is_postgres(conn) -> bool:
    return conn.__class__.__module__.startswith("psycopg")


def _placeholders(conn, n: int) -> str:
    return ", ".join("%s" for _ in range(n)) if _is_postgres(conn) else ", ".join("?" for _ in range(n))


def _cargar_dimension(
    conn,
    jsonl_path: Path,
    tabla: str,
    mapeo: dict[str, str],
    id_col_jsonl: str | tuple[str, ...],
) -> int:
    """
    Vacía la tabla y la vuelve a cargar entera desde el .jsonl.
    Es una operación 'destructiva' a propósito: estas tablas reflejan
    el catálogo VIGENTE, no queremos arrastrar comercios/sucursales
    dados de baja.
    """
    filas = list(_leer_jsonl(jsonl_path))
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {tabla}")

    columnas_sql = list(mapeo.keys())
    campos_jsonl = list(mapeo.values())
    sql = f"INSERT INTO {tabla} ({', '.join(columnas_sql)}) VALUES ({_placeholders(conn, len(columnas_sql))})"

    id_cols = id_col_jsonl if isinstance(id_col_jsonl, tuple) else (id_col_jsonl,)

    insertadas = 0
    vistos: set[tuple] = set()
    for fila in filas:
        clave = tuple(fila.get(c) for c in id_cols)
        if not all(clave) or clave in vistos:
            continue
        vistos.add(clave)
        valores = [fila.get(campo) for campo in campos_jsonl]
        cur.execute(sql, valores)
        insertadas += 1

    conn.commit()
    logger.info("Tabla '%s': %d filas cargadas desde %s", tabla, insertadas, jsonl_path.name)
    return insertadas


def _cargar_historial(conn, jsonl_path: Path) -> tuple[int, int]:
    """
    A diferencia de las dimensiones, NO se borra nada: se insertan
    todas las filas del .jsonl, y el UNIQUE de la tabla + ON CONFLICT
    / INSERT OR IGNORE se encargan de no duplicar si ya estaban cargadas.
    """
    cur = conn.cursor()
    sql = """
        INSERT INTO historial_precios
            (fecha, id_comercio, id_sucursal, id_producto, precio_lista, precio_referencia)
        VALUES ({placeholders})
    """.format(placeholders=_placeholders(conn, 6))

    if _is_postgres(conn):
        sql += " ON CONFLICT (fecha, id_comercio, id_sucursal, id_producto) DO NOTHING"

    leidas = 0
    nuevas = 0
    for fila in _leer_jsonl(jsonl_path):
        leidas += 1

        def _num(v):
            try:
                return float(v) if v not in (None, "") else None
            except ValueError:
                return None

        valores = (
            fila.get("fecha"),
            fila.get("id_comercio"),
            fila.get("id_sucursal"),
            fila.get("id_producto"),
            _num(fila.get("productos_precio_lista")),
            _num(fila.get("productos_precio_referencia")),
        )
        cur.execute(sql, valores)
        if _is_postgres(conn):
            nuevas += 1 if cur.rowcount else 0
        else:
            nuevas += 1 if cur.rowcount else 0

    conn.commit()
    logger.info(
        "Historial: %d filas leídas del .jsonl, %d eran nuevas (el resto ya estaban cargadas)",
        leidas, nuevas,
    )
    return leidas, nuevas


def _cargar_postgres(conn) -> dict:
    logger.info("Cargando base PostgreSQL/Neon")
    crear_esquema(conn)

    n_comercio = _cargar_dimension(
        conn, config.JSON_DIR / "comercio.jsonl",
        "comercio",
        mapeo={
            "id_comercio": "id_comercio",
            "nombre": "comercio_bandera_nombre",
            "razon_social": "comercio_razon_social",
            "cuit": "comercio_cuit",
        },
        id_col_jsonl="id_comercio",
    )
    n_sucursal = _cargar_dimension(
        conn, config.JSON_DIR / "sucursales.jsonl",
        "sucursal",
        mapeo={
            "id_comercio": "id_comercio",
            "id_sucursal": "id_sucursal",
            "nombre": "sucursales_nombre",
            "calle": "sucursales_calle",
            "numero": "sucursales_numero",
            "localidad": "sucursales_localidad",
            "provincia": "sucursales_provincia",
            "codigo_postal": "sucursales_codigo_postal",
            "latitud": "sucursales_latitud",
            "longitud": "sucursales_longitud",
        },
        id_col_jsonl=("id_comercio", "id_sucursal"),
    )
    n_producto = _cargar_dimension(
        conn, config.JSON_DIR / "productos.jsonl",
        "producto",
        mapeo={
            "id_producto": "id_producto",
            "descripcion": "productos_descripcion",
            "marca": "productos_marca",
        },
        id_col_jsonl="id_producto",
    )

    leidas, nuevas = _cargar_historial(conn, config.JSON_DIR / config.HISTORIAL_ARCHIVO)

    return {
        "db_mode": "postgres",
        "comercios_cargados": n_comercio,
        "sucursales_cargadas": n_sucursal,
        "productos_cargados": n_producto,
        "historial_leidas": leidas,
        "historial_nuevas": nuevas,
    }


def cargar_todo(db_path: Path | None = None) -> dict:
    if config.DB_MODE == "postgres":
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL no está configurada. Revisá .env o exportá la variable.")
        conn = psycopg.connect(config.DATABASE_URL)
        try:
            return _cargar_postgres(conn)
        finally:
            conn.close()

    db_path = db_path or config.DB_PATH
    logger.info("Cargando base de datos SQLite en %s", db_path)

    conn = sqlite3.connect(db_path)
    try:
        crear_esquema(conn)

        n_comercio = _cargar_dimension(
            conn, config.JSON_DIR / "comercio.jsonl",
            "comercio",
            mapeo={
                "id_comercio": "id_comercio",
                "nombre": "comercio_bandera_nombre",
                "razon_social": "comercio_razon_social",
                "cuit": "comercio_cuit",
            },
            id_col_jsonl="id_comercio",
        )
        n_sucursal = _cargar_dimension(
            conn, config.JSON_DIR / "sucursales.jsonl",
            "sucursal",
            mapeo={
                "id_comercio": "id_comercio",
                "id_sucursal": "id_sucursal",
                "nombre": "sucursales_nombre",
                "calle": "sucursales_calle",
                "numero": "sucursales_numero",
                "localidad": "sucursales_localidad",
                "provincia": "sucursales_provincia",
                "codigo_postal": "sucursales_codigo_postal",
                "latitud": "sucursales_latitud",
                "longitud": "sucursales_longitud",
            },
            id_col_jsonl=("id_comercio", "id_sucursal"),
        )
        n_producto = _cargar_dimension(
            conn, config.JSON_DIR / "productos.jsonl",
            "producto",
            mapeo={
                "id_producto": "id_producto",
                "descripcion": "productos_descripcion",
                "marca": "productos_marca",
            },
            id_col_jsonl="id_producto",
        )

        leidas, nuevas = _cargar_historial(conn, config.JSON_DIR / config.HISTORIAL_ARCHIVO)

    finally:
        conn.close()

    return {
        "db_path": str(db_path),
        "comercios_cargados": n_comercio,
        "sucursales_cargadas": n_sucursal,
        "productos_cargados": n_producto,
        "historial_leidas": leidas,
        "historial_nuevas": nuevas,
    }
