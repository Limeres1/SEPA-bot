# Bot de ingesta SEPA (demo)

Bot en Python que automatiza lo que hoy harías a mano en el navegador:

1. Consulta la **API pública del portal** (no scrapea HTML) para obtener
  el recurso de lunes de la semana que se va a registrar.
2. Lo **descarga** (y lo extrae si viene comprimido en `.zip`).
3. Convierte el CSV resultante a **JSON Lines** (`.jsonl`), un archivo
   de texto con un objeto JSON por línea — el formato recomendado
   cuando el CSV puede tener millones de filas, como es el caso del SEPA.
4. Puede quedar corriendo para capturar precios **cada lunes a las 14:00
  (hora de Buenos Aires)**. Si el proceso estuvo apagado el lunes,
  intenta recuperar la captura el martes.

El historial semanal se guarda en **SQLite** (`data/sepa.db`) por defecto,
o en **PostgreSQL** si se configura `DB_MODE=postgres` y `DATABASE_URL`.
Para ejecutarlo semanalmente en la nube, consulta la
[guía de GitHub Actions y Neon](GUIA_TECNICA_DEL_PROYECTO.md#11-ejecucion-en-github-actions-con-neon).
También se conservan los JSONL generados durante cada corrida. El bot recopila
precios; el cálculo de la canasta y los gráficos quedan fuera de este
proyecto para que los consuma la aplicación web existente.

## De dónde saca los datos

Portal: **Datos Abiertos de Desarrollo Productivo**
Dataset: **Precios Claros - Base SEPA** (minorista)
Página para mirarlo en el navegador: https://datos.produccion.gob.ar/dataset/sepa-precios

Ese portal corre sobre **CKAN**, el software estándar de los portales
de datos abiertos de gobierno (el mismo que usa datos.gob.ar). CKAN
siempre expone la misma API REST:

```
GET https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios
```

Esa consulta devuelve toda la metadata del dataset, incluyendo la
lista de recursos descargables (`Lunes`, `Martes`, `Miércoles`, etc.,
que se van actualizando y pisando cada día) con su URL directa de
descarga. Es, literalmente, lo que hace por detrás el botón
"Descargar" de la página — el bot llama a la misma API, sin necesidad
de scrapear HTML ni simular clicks.

## Instalación

```bash
cd sepa_bot_demo
python3 -m venv venv
source venv/bin/activate          # en Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## SQLite y servidor

1. Copiar `.env.example` a `.env` si se desea cambiar la configuración.
2. La configuración predeterminada usa SQLite en `data/sepa.db` y la zona
  horaria `America/Argentina/Buenos_Aires`:

```env
DB_MODE=sqlite
DB_PATH=data/sepa.db
RUN_AT=14:00
RUN_TIMEZONE=America/Argentina/Buenos_Aires
```

3. Ejecutar una captura manual de la semana actual:

```bash
python -m sepa_bot.main --once
```

4. Dejarlo corriendo como servicio:

```bash
python -m sepa_bot.main --server
```

El daemon consulta el recurso del lunes a las 14:00. Si el portal no actualizó
ese recurso, registra el estado “sin actualización” en la base configurada y espera a la
semana siguiente. Si el proceso estuvo apagado el lunes, prueba el martes y
mantiene el lunes como fecha de referencia. En Linux se puede usar
`systemd/sepa-bot.service`; en Windows, `scripts\run_server.bat`.

## Uso

### 1. Captura manual de la semana

```bash
python3 -m sepa_bot.main --once
```

Esto procesa el recurso del lunes de la semana actual, guarda en la base configurada
los productos reconocidos de una sucursal por cadena y muestra un resumen
JSON. Puede usarse el martes para recuperar una corrida ausente.

### 2. Dejarlo corriendo semanalmente

```bash
python3 -m sepa_bot.main --daemon
```

Por defecto captura todos los lunes a las **14:00, hora de Buenos Aires**.
El horario se puede cambiar con `RUN_AT` o con `--hora HH:MM`. Si el proceso
se inicia el martes y la captura del lunes no figura en la base, realiza un
intento de recuperación. No corre el pipeline completo todos los días.

Para dejarlo funcionando de forma desatendida en un servidor real, lo
recomendable es correr `--daemon` bajo un supervisor de procesos
(systemd, Docker con `restart: always`, `pm2`, etc.) en vez de dejarlo
como un proceso suelto. También se puede invocar `--once` desde cron
(Linux) o el Programador de tareas (Windows) en el día y horario deseados.

### 3. Inspeccionar un CSV sin descargar nada

Útil la primera vez que se tenga acceso real al dataset, para confirmar
el esquema exacto de columnas antes de decidir si hace falta
renombrarlas:

```bash
python3 -m sepa_bot.main --inspect ruta/a/un_archivo_bajado_a_mano.csv
```

Muestra el encoding y delimitador detectados, las columnas y las
primeras filas.

## Estructura del proyecto

```
sepa_bot_demo/
├── requirements.txt
├── README.md
├── sepa_bot/
│   ├── config.py          # toda la configuración ajustable
│   ├── ckan_client.py      # habla con la API de CKAN, elige el recurso del día
│   ├── downloader.py       # descarga con reintentos + extracción de zip
│   ├── csv_to_json.py      # conversión CSV -> JSON/JSONL, auto-detección de encoding/delimitador
│   ├── pipeline.py         # orquesta todo el flujo
│   ├── product_catalog.py  # categorías y reglas de coincidencia de productos
│   ├── weekly_history.py   # captura semanal, sucursales y SQLite/PostgreSQL
│   ├── state.py            # guarda un registro de la última corrida (para diagnóstico)
│   ├── logging_setup.py    # logging a archivo rotativo + consola
│   └── main.py             # CLI (--once / --daemon / --inspect)
├── tests/
│   └── sample_precios_sepa.csv   # CSV de ejemplo para probar la conversión sin depender de internet
└── data/                   # se crea sola al correr el bot
    ├── raw/                # CSV/ZIP descargados tal cual
    ├── json/               # .jsonl ya convertidos
    ├── state/              # last_run.json
    └── logs/               # sepa_bot.log (rotación diaria, 14 días de historial)
```

## Decisiones de diseño (y por qué)

- **JSON Lines en vez de un único JSON gigante**: con datasets de
  varios millones de filas por día, un solo array JSON de varios GB es
  incómodo de leer sin cargarlo entero en memoria. JSON Lines se puede
  procesar línea por línea.
- **No se asumen nombres de columna fijos**: el conversor lee el
  header real del CSV tal como venga. Cuando tengas acceso al dataset
  real y confirmes el esquema exacto, hay un diccionario
  `RENOMBRE_COLUMNAS` en `csv_to_json.py` pensado para normalizar
  nombres sin tocar el resto del código.
- **Auto-detección de encoding y delimitador**: los CSV de organismos
  públicos argentinos suelen venir en `;` o `|` y a veces en
  `latin-1` en vez de `utf-8`. El bot prueba varias combinaciones
  automáticamente; también se pueden fijar a mano en `config.py` si
  ya se conocen.
- **Captura semanal idempotente**: se registra como máximo una captura por
  lunes. El recurso debe haberse actualizado esa semana; si el proceso se
  recupera el martes, el lunes sigue siendo la fecha de referencia.
  El resumen de ejecución se conserva para diagnóstico.
- **Precios comparables**: se guardan la presentación y el precio publicado;
  cuando se conoce el contenido, se normaliza por kg, litro o unidad.
- **Sin interfaz ni gráficos en el bot**: esos cálculos pertenecen a la
  aplicación externa que consuma el historial en la base configurada.

## Nota

Si al correr `--once` el bot registra que no hubo actualización, consulta
`last_modified` del recurso `Lunes`; no usa un recurso de otro día como
reemplazo para la captura semanal. Si aparece un error de conexión o 404/403,
puede que:
- el `id` del dataset haya cambiado en el portal (se ajusta en
  `config.DATASET_ID`), o
- el naming de los recursos ya no sea "Lunes"/"Martes"/etc. (se ajusta
  la lógica en `ckan_client.pick_resource_for_date`).

En ambos casos, correr primero `--inspect` sobre un archivo bajado a
mano, y visitar `https://datos.produccion.gob.ar/dataset/sepa-precios`
en el navegador para confirmar el estado actual del dataset, es el
primer paso de diagnóstico.
