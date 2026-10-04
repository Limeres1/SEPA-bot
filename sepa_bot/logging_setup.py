"""logging_setup.py — Logging simple a consola + archivo rotativo por día."""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from . import config


def configurar_logging(nivel: int = logging.INFO) -> None:
    log_file = config.LOG_DIR / "sepa_bot.log"

    formato = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler_archivo = TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=14, encoding="utf-8"
    )
    handler_archivo.setFormatter(formato)

    handler_consola = logging.StreamHandler(sys.stdout)
    handler_consola.setFormatter(formato)

    raiz = logging.getLogger("sepa_bot")
    raiz.setLevel(nivel)
    raiz.handlers.clear()
    raiz.addHandler(handler_archivo)
    raiz.addHandler(handler_consola)
