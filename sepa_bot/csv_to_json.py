"""
csv_to_json.py — Convierte un CSV (el que sea, no asumimos columnas
fijas) en JSON o JSON Lines.

Decisiones de diseño, explicadas porque importan para un dataset como
el del SEPA (~12 millones de registros/día):

1. Se recomienda JSON Lines (.jsonl: un objeto JSON por línea) en vez
   de un único array JSON gigante. Con millones de filas, un solo
   archivo .json de varios GB es incómodo de leer/procesar sin cargarlo
   entero en memoria; .jsonl se puede leer línea por línea.

2. No asumimos nombres de columna. El bot lee el header real del CSV
   descargado y genera un diccionario por fila con esas claves tal
   cual. Esto es intencional: todavía no tenemos confirmado el header
   exacto que usa el SEPA (varía si se agrega/saca una columna, o si
   se está probando con un CSV de ejemplo). Cuando se conozca el
   esquema definitivo, alcanza con agregar un diccionario de renombre
   de columnas acá (ver RENOMBRE_COLUMNAS más abajo) sin tocar el
   resto del pipeline.

3. Detección automática de delimitador y encoding con fallback, salvo
   que se fuerce explícitamente en config.py.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from . import config

logger = logging.getLogger("sepa_bot.converter")

# Si en el futuro se conoce el esquema exacto del SEPA y se quiere
# normalizar nombres de columna (ej. pasar de "id_producto" tal cual
# viene, a "id_producto" en snake_case consistente con el DER de la
# tesis), se define acá: {"columna_original": "columna_normalizada"}.
RENOMBRE_COLUMNAS: dict[str, str] = {
    # "ean_producto": "ean",
    # "PRECIO_LISTA": "precio_lista",
}

ENCODINGS_A_PROBAR = ["utf-8-sig", "utf-8", "latin-1"]
DELIMITADORES_A_PROBAR = [",", ";", "|", "\t"]


def _detectar_encoding_y_delimitador(csv_path: Path) -> tuple[str, str]:
    if config.CSV_ENCODING and config.CSV_DELIMITER:
        return config.CSV_ENCODING, config.CSV_DELIMITER

    encoding_elegido = config.CSV_ENCODING
    delimitador_elegido = config.CSV_DELIMITER

    muestra = b""
    with open(csv_path, "rb") as f:
        muestra = f.read(65536)

    if not encoding_elegido:
        for enc in ENCODINGS_A_PROBAR:
            try:
                muestra.decode(enc)
                encoding_elegido = enc
                break
            except UnicodeDecodeError:
                continue
        else:
            encoding_elegido = "latin-1"  # latin-1 nunca falla al decodificar

    if not delimitador_elegido:
        texto_muestra = muestra.decode(encoding_elegido, errors="ignore")
        try:
            dialecto = csv.Sniffer().sniff(texto_muestra, delimiters="".join(DELIMITADORES_A_PROBAR))
            delimitador_elegido = dialecto.delimiter
        except csv.Error:
            # Si el Sniffer no puede decidir, contamos ocurrencias como fallback simple.
            conteos = {d: texto_muestra.count(d) for d in DELIMITADORES_A_PROBAR}
            delimitador_elegido = max(conteos, key=conteos.get)

    logger.info("Detectado encoding=%s delimitador=%r para %s", encoding_elegido, delimitador_elegido, csv_path)
    return encoding_elegido, delimitador_elegido


def inspeccionar_csv(csv_path: Path, filas_ejemplo: int = 3) -> dict:
    """
    Devuelve un resumen rápido del CSV (columnas + primeras filas) sin
    convertir todo el archivo. Útil para el modo --inspect del CLI,
    para confirmar el esquema real apenas se tenga acceso al dataset.
    """
    encoding, delimitador = _detectar_encoding_y_delimitador(csv_path)
    with open(csv_path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter=delimitador)
        columnas = reader.fieldnames or []
        ejemplos = []
        for i, fila in enumerate(reader):
            if i >= filas_ejemplo:
                break
            ejemplos.append(fila)

    return {
        "archivo": str(csv_path),
        "encoding": encoding,
        "delimitador": delimitador,
        "columnas": columnas,
        "ejemplos": ejemplos,
    }


def convertir_multiples(
    csv_paths: list[Path],
    out_path: Path,
    formato: str = config.OUTPUT_FORMAT,
    max_filas: int | None = config.MAX_ROWS,
) -> dict:
    """
    Igual que convertir(), pero combina VARIOS CSV (por ejemplo, el
    'productos.csv' de cada uno de los ~18 comercios del día) en un
    único archivo de salida, agregando filas en vez de pisarlas.

    Esto es necesario porque el SEPA entrega un CSV por comercio con
    el MISMO nombre de archivo (todos se llaman 'productos.csv',
    'sucursales.csv', etc. dentro de su propia carpeta). Si se
    convirtiera cada uno a un .jsonl con nombre basado solo en el
    nombre del archivo, el segundo comercio pisaría el archivo del
    primero. Acá se combinan todos en uno solo; como cada fila del
    SEPA ya trae su propio 'id_comercio', no se pierde la trazabilidad
    de qué registro vino de qué comercio.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    columnas: list[str] = []

    def _filas_de(csv_path: Path):
        encoding, delimitador = _detectar_encoding_y_delimitador(csv_path)
        with open(csv_path, "r", encoding=encoding, newline="") as f_in:
            reader = csv.DictReader(f_in, delimiter=delimitador)
            if not columnas:
                columnas.extend(reader.fieldnames or [])
            yield from reader

    if formato == "jsonl":
        with open(out_path, "w", encoding="utf-8") as f_out:
            for csv_path in csv_paths:
                for fila in _filas_de(csv_path):
                    if max_filas is not None and total >= max_filas:
                        break
                    fila_final = {RENOMBRE_COLUMNAS.get(k, k): v for k, v in fila.items()}
                    f_out.write(json.dumps(fila_final, ensure_ascii=False) + "\n")
                    total += 1
                if max_filas is not None and total >= max_filas:
                    break

    elif formato == "json":
        registros = []
        for csv_path in csv_paths:
            for fila in _filas_de(csv_path):
                if max_filas is not None and total >= max_filas:
                    break
                registros.append({RENOMBRE_COLUMNAS.get(k, k): v for k, v in fila.items()})
                total += 1
            if max_filas is not None and total >= max_filas:
                break
        with open(out_path, "w", encoding="utf-8") as f_out:
            json.dump(registros, f_out, ensure_ascii=False, indent=2)

    else:
        raise ValueError(f"Formato de salida no soportado: {formato!r} (usar 'jsonl' o 'json')")

    resumen = {
        "csvs_origen": [str(p) for p in csv_paths],
        "cantidad_comercios_combinados": len(csv_paths),
        "json_destino": str(out_path),
        "formato": formato,
        "columnas": columnas,
        "filas_convertidas": total,
    }
    logger.info(
        "Combinadas %d filas desde %d archivo(s) '%s' -> %s",
        total, len(csv_paths), csv_paths[0].name if csv_paths else "?", out_path.name,
    )
    return resumen


def generar_historial_precios(
    csv_paths: list[Path],
    out_path: Path,
    fecha: str,
    campos: list[str] | None = None,
    filtro_sucursales: set[tuple[str, str]] | None = None,
    filtro_descripcion_keywords: list[str] | None = None,
    campo_descripcion: str = "productos_descripcion",
) -> dict:
    """
    Igual que antes (agrega filas al historial sin pisar los días
    anteriores), pero ahora acepta dos filtros opcionales pensados
    para poder correr el bot durante mucho tiempo sin llenar el disco:

    - filtro_sucursales: set de (id_comercio, id_sucursal) a conservar.
      Si es None, no filtra por sucursal (guarda todas — ¡ojo con el
      volumen a escala nacional!).
    - filtro_descripcion_keywords: lista de palabras; se conserva la
      fila si 'productos_descripcion' CONTIENE alguna de ellas (sin
      distinguir mayúsculas/minúsculas). Si es None o vacía, no filtra
      por producto.
    """
    campos = campos if campos is not None else config.HISTORIAL_CAMPOS
    out_path.parent.mkdir(parents=True, exist_ok=True)

    keywords_upper = [k.upper() for k in (filtro_descripcion_keywords or [])]

    total_leidas = 0
    total_guardadas = 0
    with open(out_path, "a", encoding="utf-8") as f_out:
        for csv_path in csv_paths:
            encoding, delimitador = _detectar_encoding_y_delimitador(csv_path)
            with open(csv_path, "r", encoding=encoding, newline="") as f_in:
                reader = csv.DictReader(f_in, delimiter=delimitador)
                for fila in reader:
                    total_leidas += 1

                    if filtro_sucursales is not None:
                        clave = (fila.get("id_comercio"), fila.get("id_sucursal"))
                        if clave not in filtro_sucursales:
                            continue

                    if keywords_upper:
                        descripcion = (fila.get(campo_descripcion) or "").upper()
                        if not any(k in descripcion for k in keywords_upper):
                            continue

                    fila_liviana = {"fecha": fecha}
                    for campo in campos:
                        fila_liviana[campo] = fila.get(campo, "")
                    f_out.write(json.dumps(fila_liviana, ensure_ascii=False) + "\n")
                    total_guardadas += 1

    logger.info(
        "Historial de precios (%s): %d filas leídas, %d pasaron el filtro y se guardaron -> %s",
        fecha, total_leidas, total_guardadas, out_path,
    )
    return {
        "historial_destino": str(out_path),
        "fecha": fecha,
        "filas_leidas": total_leidas,
        "filas_guardadas": total_guardadas,
        "campos_guardados": ["fecha"] + campos,
    }


def convertir(
    csv_path: Path,
    out_path: Path,
    formato: str = config.OUTPUT_FORMAT,
    max_filas: int | None = config.MAX_ROWS,
) -> dict:
    """Convierte un único CSV. Atajo sobre convertir_multiples() para el caso de un solo archivo."""
    resumen = convertir_multiples([csv_path], out_path, formato, max_filas)
    resumen["csv_origen"] = resumen.pop("csvs_origen")[0]
    resumen.pop("cantidad_comercios_combinados", None)
    return resumen
