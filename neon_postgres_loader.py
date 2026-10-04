import os
from pathlib import Path

import psycopg

from sepa_bot import config


CREATE_TABLES_SQL = """
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

CREATE INDEX IF NOT EXISTS idx_historial_fecha ON historial_precios(fecha);
CREATE INDEX IF NOT EXISTS idx_historial_producto ON historial_precios(id_producto);
"""


def _leer_jsonl(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                yield __import__("json").loads(linea)


def crear_esquema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLES_SQL)
    conn.commit()


def _valor(obj, clave, default=None):
    if obj is None:
        return default
    return obj.get(clave, default)


def cargar_dimension(conn, archivo: str, tabla: str, mapeo: dict[str, str], id_cols: tuple[str, ...]):
    path = config.JSON_DIR / archivo
    rows = list(_leer_jsonl(path))
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {tabla}")
        insert_sql = (
            f"INSERT INTO {tabla} ({', '.join(mapeo.keys())}) VALUES "
            f"({', '.join('%s' for _ in mapeo)})"
        )
        insertados = 0
        vistos = set()
        for fila in rows:
            clave = tuple(_valor(fila, col) for col in id_cols)
            if not all(clave) or clave in vistos:
                continue
            vistos.add(clave)
            valores = [_valor(fila, campo) for campo in mapeo.values()]
            cur.execute(insert_sql, valores)
            insertados += 1
    conn.commit()
    return insertados


def cargar_historial(conn, archivo: str):
    path = config.JSON_DIR / archivo
    rows = list(_leer_jsonl(path))
    if not rows:
        return 0, 0

    sql = """
        INSERT INTO historial_precios
        (fecha, id_comercio, id_sucursal, id_producto, precio_lista, precio_referencia)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (fecha, id_comercio, id_sucursal, id_producto)
        DO NOTHING
    """

    insertadas = 0
    with conn.cursor() as cur:
        for fila in rows:
            try:
                precio_lista = float(fila.get('productos_precio_lista')) if fila.get('productos_precio_lista') not in (None, '') else None
                precio_ref = float(fila.get('productos_precio_referencia')) if fila.get('productos_precio_referencia') not in (None, '') else None
            except (TypeError, ValueError):
                precio_lista = None
                precio_ref = None

            cur.execute(sql, (
                fila.get('fecha'),
                fila.get('id_comercio'),
                fila.get('id_sucursal'),
                fila.get('id_producto'),
                precio_lista,
                precio_ref,
            ))
            if cur.rowcount:
                insertadas += 1
    conn.commit()
    return len(rows), insertadas


def cargar_todo_neon() -> dict:
    if not config.DATABASE_URL:
        raise RuntimeError("Falta DATABASE_URL. Configural la variable de entorno antes de cargar a Neon.")

    conn = psycopg.connect(config.DATABASE_URL)
    try:
        crear_esquema(conn)

        n_comercio = cargar_dimension(
            conn,
            "comercio.jsonl",
            "comercio",
            {
                "id_comercio": "id_comercio",
                "nombre": "comercio_bandera_nombre",
                "razon_social": "comercio_razon_social",
                "cuit": "comercio_cuit",
            },
            ("id_comercio",),
        )

        n_sucursal = cargar_dimension(
            conn,
            "sucursales.jsonl",
            "sucursal",
            {
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
            ("id_comercio", "id_sucursal"),
        )

        n_producto = cargar_dimension(
            conn,
            "productos.jsonl",
            "producto",
            {
                "id_producto": "id_producto",
                "descripcion": "productos_descripcion",
                "marca": "productos_marca",
            },
            ("id_producto",),
        )

        leidas, nuevas = cargar_historial(conn, config.HISTORIAL_ARCHIVO)

        return {
            "db_mode": "postgres",
            "comercios_cargados": n_comercio,
            "sucursales_cargadas": n_sucursal,
            "productos_cargados": n_producto,
            "historial_leidas": leidas,
            "historial_nuevas": nuevas,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    print(cargar_todo_neon())
