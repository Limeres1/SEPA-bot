"""
main.py — Punto de entrada del bot.

Modos de uso:

    python -m sepa_bot.main --once
        Procesa la semana actual usando el lunes como fecha de referencia.

    python -m sepa_bot.main --daemon
    python -m sepa_bot.main --server
        Se queda en primer plano, captura los lunes a config.RUN_AT y
        recupera el lunes pendiente el martes si el proceso estuvo apagado.

    python -m sepa_bot.main --inspect archivo.csv
        No descarga nada: solo abre un CSV local (por ejemplo uno bajado
        a mano de la página) y muestra sus columnas y primeras filas.
        Útil para confirmar el esquema real del SEPA la primera vez.

Nota sobre producción: para un despliegue real, correr este bot con
--daemon/--server dentro de un proceso supervisado (systemd, Docker + restart
policy, etc.) es más robusto que dejarlo como un simple `python main.py &`.
También se puede invocar --once desde cron o el Programador de tareas
de Windows si se prefiere que el sistema operativo inicie la captura.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, datetime, time as time_of_day, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config
from .logging_setup import configurar_logging
from .pipeline import ejecutar_pipeline
from .csv_to_json import inspeccionar_csv
from .db_loader import cargar_todo
from .weekly_history import semana_procesada

logger = logging.getLogger("sepa_bot.main")


def _correr_una_vez() -> None:
    ahora = datetime.now(ZoneInfo(config.RUN_TIMEZONE))
    fecha_lunes = ahora.date() - timedelta(days=ahora.weekday())
    resultado = ejecutar_pipeline(
        fecha_semana=fecha_lunes,
        permitir_actualizacion_martes=ahora.weekday() == 1,
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    if not resultado.get("ok"):
        raise SystemExit(1)


def _captura_pendiente(
    ahora: datetime, hora_programada: time_of_day
) -> tuple[date, bool] | None:
    if ahora.weekday() == 0 and ahora.timetz().replace(tzinfo=None) >= hora_programada:
        return ahora.date(), False
    if ahora.weekday() == 1:
        return ahora.date() - timedelta(days=1), True
    return None


def _ejecutar_pendiente(
    hora: str, intentadas: set[tuple[date, int]] | None = None
) -> None:
    ahora = datetime.now(ZoneInfo(config.RUN_TIMEZONE))
    pendiente = _captura_pendiente(ahora, time_of_day.fromisoformat(hora))
    if pendiente is None:
        return

    fecha_semana, permitir_martes = pendiente
    clave_intento = (fecha_semana, ahora.weekday())
    if intentadas is not None and clave_intento in intentadas:
        return
    if semana_procesada(config.DB_PATH, fecha_semana):
        logger.info("La captura de la semana %s ya está registrada.", fecha_semana)
        if intentadas is not None:
            intentadas.add(clave_intento)
        return

    logger.info("Ejecutando captura semanal para el lunes %s.", fecha_semana)
    if intentadas is not None:
        intentadas.add(clave_intento)
    resultado = ejecutar_pipeline(
        fecha_semana=fecha_semana,
        permitir_actualizacion_martes=permitir_martes,
    )
    if not resultado.get("ok"):
        logger.error("Falló la captura semanal: %s", resultado.get("error"))


def _correr_como_daemon(hora: str) -> None:
    logger.info(
        "Daemon semanal iniciado. Captura los lunes a las %s (%s); recupera el martes si falta.",
        hora,
        config.RUN_TIMEZONE,
    )
    intentadas: set[tuple[date, int]] = set()

    while True:
        _ejecutar_pendiente(hora, intentadas)
        time.sleep(30)


def _inspeccionar(path_csv: str) -> None:
    resumen = inspeccionar_csv(Path(path_csv))
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


def _cargar_base_de_datos() -> None:
    resumen = cargar_todo()
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot de ingesta de datos abiertos del SEPA.")
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--once", action="store_true", help="Corre el pipeline una sola vez.")
    modo.add_argument("--daemon", action="store_true", help="Captura semanalmente y recupera el martes si faltó el lunes.")
    modo.add_argument("--server", action="store_true", help="Alias de --daemon para ejecutar como servicio/servidor.")
    modo.add_argument("--inspect", metavar="ARCHIVO.csv", help="Inspecciona un CSV local sin descargar nada.")
    modo.add_argument("--load-db", action="store_true", help="Carga los .jsonl ya generados a la base configurada (SQLite o PostgreSQL/Neon).")
    parser.add_argument("--hora", default=config.RUN_AT, help=f"Hora local semanal del bot (default {config.RUN_AT}; zona {config.RUN_TIMEZONE}).")

    args = parser.parse_args()
    configurar_logging()

    if args.inspect:
        _inspeccionar(args.inspect)
    elif args.once:
        _correr_una_vez()
    elif args.daemon or args.server:
        _correr_como_daemon(args.hora)
    elif args.load_db:
        _cargar_base_de_datos()


if __name__ == "__main__":
    main()
