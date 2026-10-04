"""Copy the weekly-history tables from SQLite to PostgreSQL."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

import psycopg

from . import config
from .weekly_history import crear_esquema

TABLES = ("historial_canasta_semanal", "capturas_semanales")
BATCH_SIZE = 1000


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def migrar_sqlite_a_postgres(sqlite_path: Path) -> dict[str, int]:
    if config.DB_MODE != "postgres":
        raise RuntimeError("Para migrar, configura DB_MODE=postgres.")
    if not config.DATABASE_URL:
        raise RuntimeError("Falta DATABASE_URL para conectar a PostgreSQL.")
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"No existe la base SQLite: {sqlite_path}")

    trasladadas: dict[str, int] = {}
    with closing(sqlite3.connect(sqlite_path)) as source:
        with closing(psycopg.connect(config.DATABASE_URL)) as target:
            crear_esquema(target)
            for table in TABLES:
                info = source.execute(
                    f"PRAGMA table_info({_quote_identifier(table)})"
                ).fetchall()
                if not info:
                    raise RuntimeError(
                        f"La base SQLite no contiene la tabla requerida: {table}"
                    )

                columns = [row[1] for row in info if row[1] != "id"]
                quoted_columns = ", ".join(map(_quote_identifier, columns))
                select_sql = f"SELECT {quoted_columns} FROM {_quote_identifier(table)}"
                placeholders = ", ".join(["%s"] * len(columns))
                insert_sql = (
                    f"INSERT INTO {_quote_identifier(table)} ({quoted_columns}) "
                    f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                )

                source_cursor = source.execute(select_sql)
                copied = 0
                while rows := source_cursor.fetchmany(BATCH_SIZE):
                    copied += target.executemany(insert_sql, rows).rowcount
                trasladadas[table] = copied
            target.commit()

    return trasladadas


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migra el historial semanal SQLite a la base PostgreSQL de DATABASE_URL."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=config.DB_PATH,
        help=f"Archivo SQLite de origen (por defecto: {config.DB_PATH}).",
    )
    args = parser.parse_args()
    print(migrar_sqlite_a_postgres(args.sqlite_path))


if __name__ == "__main__":
    main()
