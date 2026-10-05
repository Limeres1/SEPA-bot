# Guía técnica del SEPA Bot

**Propósito:** explicar qué contiene cada archivo y cómo colaboran los módulos para obtener y guardar precios del dataset minorista SEPA.  
**Alcance:** describe la estructura y el comportamiento que implementa actualmente el código. No agrega una interfaz web ni realiza gráficos.

## 1. Resumen del sistema

SEPA Bot es un proceso de ingesta escrito en Python. Consulta la API CKAN pública del portal de Datos Abiertos de Desarrollo Productivo, obtiene el recurso denominado `Lunes`, verifica su fecha de modificación, descarga el ZIP, extrae sus CSV, los convierte a JSON Lines y guarda el historial semanal en SQLite o PostgreSQL.

El daemon local está configurado para los lunes a las **14:00 de Buenos Aires**; si estuvo apagado o el recurso todavía no se actualizó, puede recuperar la captura el martes. Para una ejecución local puntual, `scripts/run_weekly_local.bat` fuerza SQLite en `data/sepa.db`; puede programarse los martes a las 14:30 con el Programador de tareas de Windows. En GitHub Actions, el workflow programado se ejecuta los lunes a esa hora y guarda las capturas en PostgreSQL remoto para que no se pierdan al finalizar el runner. La fecha registrada sigue siendo la del lunes. Si el portal todavía no actualizó el recurso en la fecha permitida, el bot registra `sin_actualizacion` como pendiente de reintento.

El bot recopila datos. El cálculo del valor mensual de la canasta y los gráficos quedan para la aplicación que consuma la base de datos.

## 2. Flujo completo de una captura semanal

```mermaid
flowchart TD
    A[Arranque: --server, --daemon o --once] --> B[main.py calcula la semana y el momento]
    B --> C{¿La semana ya figura en la base configurada?}
    C -- Sí --> D[No duplica la captura]
    C -- No --> E[ckan_client consulta metadata CKAN]
    E --> F[Selecciona recurso Lunes]
    F --> G{¿last_modified es válido para la semana?}
    G -- No --> H[Registra sin_actualizacion en la base configurada]
    G -- Sí --> I[downloader descarga el ZIP]
    I --> J[Extrae ZIP internos y encuentra CSV]
    J --> K[csv_to_json convierte CSV a JSONL]
    K --> L[weekly_history selecciona sucursales]
    L --> M[product_catalog identifica productos y opciones]
    M --> N[Normaliza precios cuando puede identificar presentación]
    N -->     O[Inserta observaciones en SQLite o PostgreSQL]
    O --> P[Guarda estado y logs]
```

### Secuencia explicada

1. `main.py` recibe el modo de ejecución. En modo servidor consulta la hora local usando la zona configurada y solo considera una captura el lunes desde la hora programada o una recuperación el martes.
2. `weekly_history.semana_procesada()` revisa si la fecha de ese lunes ya tiene una captura registrada. La fecha semanal es la clave para impedir duplicados.
3. `CKANClient` consulta `package_show` y devuelve metadata de los recursos publicados.
4. `pick_resource_for_date()` selecciona el recurso cuyo nombre corresponde al lunes. A diferencia del selector antiguo, no reemplaza silenciosamente el lunes por el recurso más reciente de otro día.
5. `resource_updated_on()` convierte `last_modified` a la zona `America/Argentina/Buenos_Aires` y comprueba que la modificación corresponda al lunes; en la recuperación admite también el martes.
6. Si el recurso no es reciente, se agrega un registro de control `sin_actualizacion` y se termina esa semana sin descargar un archivo antiguo.
7. `download_resource()` descarga el archivo en streaming y extrae CSV. Puede recorrer ZIP anidados hasta cinco niveles.
8. `convertir_multiples()` genera archivos JSONL en `data/json/`. Los CSV con igual nombre se combinan para que los datos de una cadena no sobrescriban los de otra.
9. `obtener_sucursales_seguidas()` mantiene una sucursal por cadena, conserva la selección entre corridas y prefiere sucursales de CABA, luego de GBA.
10. `encontrar_items()` relaciona registros con las reglas de `product_catalog.py`. `weekly_history.py` guarda precios, ubicación, identificación del producto, opción, presentación y estado.
11. Se conserva el lunes como `fecha_semana` y también `fecha_consulta` en UTC para auditoría.
12. Si la conversión termina correctamente, se limpian los archivos de descarga y extracción, según `LIMPIAR_RAW_DESPUES`.

## 3. Archivos del repositorio

### Archivos de la raíz

| Archivo | Función |
|---|---|
| `README.md` | Introducción y comandos de operación. Es una guía rápida, no el detalle de todos los módulos. |
| `GUIA_TECNICA_DEL_PROYECTO.md` | Este documento: arquitectura, responsabilidades, flujo, datos y límites conocidos. |
| `DOCUMENTACION_REQUISITOS.md` | Requisitos funcionales/no funcionales y descripción inicial del alcance. Puede contener decisiones anteriores al flujo semanal actual; ante diferencias, contrastar con el código y `requerimientos.md`. |
| `requerimientos.md` | Requerimientos del usuario para la canasta y sus productos. Describe categorías, alternativas y cantidades orientativas. |
| `PENDIENTES_POR_DEFINIR.md` | Decisiones detalladas que se fueron acordando. Sirve como fuente complementaria; algunas respuestas pueden haber quedado reflejadas en código y otras no. |
| `pyproject.toml` | Metadatos del paquete, versión mínima de Python, dependencias e instalación del comando `sepa-bot`. |
| `requirements.txt` | Lista de dependencias para instalar con `pip`. |
| `.env.example` | Plantilla de variables de entorno. Se puede copiar como `.env` y personalizar. No contiene secretos reales. |
| `.gitignore` | Evita versionar el entorno virtual, secretos, bytecode y artefactos/datos generados, incluida la base local. |
| `neon_postgres_loader.py` | Cargador heredado para JSONL a Neon/PostgreSQL; no participa en la captura semanal actual. |
| `sepa_bot/migrate_sqlite_to_postgres.py` | Migra las tablas de historial semanal existentes desde SQLite a PostgreSQL/Neon. |
| `.github/workflows/run_weekly.yml` | Ejecuta pruebas y captura semanal los lunes en GitHub Actions, sin depender de una PC encendida. |

### Paquete `sepa_bot/`

| Archivo | Responsabilidad |
|---|---|
| `__init__.py` | Inicializa el paquete Python. Está vacío; no ejecuta lógica. |
| `__main__.py` | Permite ejecutar `python -m sepa_bot`; delega a `main.main()`. |
| `main.py` | Punto de entrada CLI. Interpreta `--once`, `--daemon`, `--server`, `--inspect`, `--load-db`; programa la operación semanal y define la recuperación del martes. |
| `config.py` | Lee variables de entorno y centraliza URLs, carpetas, zona horaria, horario, formato, opciones CSV y limpieza. El valor predeterminado es SQLite y lunes 14:00 de Buenos Aires. |
| `ckan_client.py` | Cliente HTTP para CKAN. Consulta metadata, lista recursos, elige el recurso del lunes y compara `last_modified` con la fecha objetivo. También conserva un selector antiguo de “recurso de hoy” para el modo genérico. |
| `downloader.py` | Descarga archivos en streaming, reintenta errores de red y extrae ZIP directos o anidados para encontrar CSV. |
| `csv_to_json.py` | Inspecciona CSV y los convierte a JSON o JSONL. Detecta encoding y separador. En el flujo semanal se usa JSONL y se combinan archivos con el mismo nombre. También contiene una función heredada para historial JSONL diario, que ya no usa el pipeline semanal. |
| `product_catalog.py` | Define categorías, opciones de producto, alias de búsqueda, unidad de comparación y referencias mensuales, incluidos 30 huevos por opción. Normaliza texto para ignorar mayúsculas y tildes. |
| `weekly_history.py` | Lógica principal del historial actual: lee JSONL, selecciona/persiste sucursales, compara localidad, interpreta números y presentaciones, estima precios normalizados y escribe en SQLite o PostgreSQL según `DB_MODE`. |
| `pipeline.py` | Coordina CKAN, comprobación de actualidad, descarga, extracción, conversión, captura, limpieza y estado de ejecución. |
| `db_loader.py` | Utilidad anterior que importa los JSONL a tablas `comercio`, `sucursal`, `producto` e `historial_precios` en SQLite o PostgreSQL. No es el camino usado para el nuevo historial semanal. |
| `seleccion_historial.py` | Seleccionador anterior de sucursales a partir de `sucursales.jsonl`. La captura semanal usa la lógica nueva en `weekly_history.py`; este módulo queda como código heredado. |
| `state.py` | Guarda y lee `data/state/last_run.json`, con fecha UTC y resumen de la última ejecución del pipeline. No decide el calendario semanal. |
| `logging_setup.py` | Configura logs en consola y `data/logs/sepa_bot.log`; rota diariamente y retiene catorce archivos anteriores. |

### Directorios auxiliares

| Ruta / archivo | Función |
|---|---|
| `scripts/run_server.bat` | En Windows, entra a la carpeta del proyecto e inicia `python -m sepa_bot.main --server`. El proceso debe quedar activo. |
| `scripts/run_weekly_local.bat` | En Windows, ejecuta una captura con el entorno virtual local y fuerza SQLite en `data/sepa.db`; puede usarse manualmente o desde el Programador de tareas. |
| `scripts/run_daily.sh` | En Linux, activa el entorno virtual si existe y ejecuta una única vez con `--once`. Para que sea semanal se debe programar este script con cron o usar el daemon. |
| `systemd/sepa-bot.service` | Ejemplo de servicio Linux que ejecuta el modo servidor y lo reinicia si termina. Requiere ajustar rutas y tener `.env` en la ubicación configurada. |
| `tests/sample_precios_sepa.csv` | CSV pequeño de ejemplo para inspección/conversión. Contiene identificadores y precios, pero no descripción de producto ni datos de presentación; por eso no prueba el reconocimiento de la canasta. |
| `tests/test_product_catalog.py` | Comprueba normalización de tildes y algunas reglas de reconocimiento por marca/producto. |
| `tests/test_weekly_history.py` | Comprueba lectura de precios, normalización, persistencia, sucursal estable, huevos de referencia y captura semanal. |
| `tests/test_weekly_schedule.py` | Comprueba hora de ejecución, recuperación del martes y conversión de fechas según Buenos Aires. |
| `data/raw/` | ZIP/CSV descargados y extraídos temporalmente. Se limpia tras una conversión correcta si la limpieza está activada. |
| `data/json/` | JSONL intermedios: por ejemplo `productos.jsonl`, `sucursales.jsonl` y `comercio.jsonl`. |
| `data/state/` | Estado operativo, incluida la selección persistente de sucursales. |
| `data/logs/` | Logs rotativos del proceso. |
| `data/sepa.db` | Base SQLite predeterminada para desarrollo local. Está ignorada por Git; en GitHub Actions el historial persistente se guarda en PostgreSQL remoto. |

## 4. Qué contiene la base semanal

La captura actual crea dos tablas nuevas en SQLite o PostgreSQL, independientes de las tablas del cargador JSONL antiguo:

### `historial_canasta_semanal`

Una fila por producto reconocido, cadena, sucursal y semana. Incluye:

- `fecha_semana`: lunes de referencia, incluso si se ejecuta el martes.
- `fecha_consulta`: instante real de consulta, guardado en UTC.
- `id_bandera`, `cadena`, `id_comercio`, `id_sucursal`, `sucursal`, `localidad`: identificación del comercio y sucursal observados.
- `categoria`, `catalogo_key`, `opcion`, `producto_catalogo`: correspondencia con la canasta y su alternativa.
- `id_producto`, `ean`, `descripcion`, `marca`: campos disponibles para identificar el artículo en SEPA.
- `presentacion`, `cantidad_envase`, `unidad_envase`: datos de tamaño si se pueden extraer del CSV o descripción.
- `precio_lista` y `precio_referencia`: valores originales de SEPA.
- `precio_lista_normalizado` y `precio_referencia_normalizado`: precio por kg, litro o unidad cuando el parser identifica presentación y unidad compatibles.
- `cantidad_referencia_mensual`: referencia para la aplicación; por ahora 30 en las dos opciones de huevos.
- `estado`: `disponible`, `sin_precio` o `sin_dato` según el caso.

Hay una restricción única que evita repetir la misma clave dentro de una semana: fecha, bandera, comercio, sucursal, regla de catálogo y producto.

### `capturas_semanales`

Una fila de control por fecha semanal. Registra hora de consulta, estado (`sin_actualizacion`, `completada` o `completada_sin_coincidencias`) y un resumen. La presencia de la fecha impide que el daemon vuelva a procesar la semana.

> La creación del esquema actual usa `CREATE TABLE IF NOT EXISTS`. El script de migración copia las dos tablas semanales existentes; no reemplaza un sistema de migraciones para futuros cambios de esquema.

## 5. Cómo se decide qué productos se guardan

`product_catalog.py` contiene un catálogo manual de reglas. El matcher arma un texto con campos de descripción y marca, elimina diferencias de mayúsculas/tildes y busca alias definidos. Si encuentra un artículo, asigna categoría, opción y unidad objetivo.

Esto no es un modelo de lenguaje ni una conciliación oficial de productos. Una regla demasiado amplia puede asociar un producto equivocado; una regla demasiado estricta puede dejar productos como `sin_dato`. El esquema del CSV real debe revisarse y el catálogo debe ajustarse con datos reales antes de confiar en que todas las filas esperadas serán reconocidas.

Para el precio normalizado, el parser busca contenido/unidad en campos posibles o en textos como `1 kg`, `500 ml` o `maple`. Cuando no logra determinar la cantidad, guarda el precio publicado pero deja vacío el normalizado. Los productos a granel requieren que la fuente identifique esa condición o la unidad para evitar asumir el contenido.

La aplicación web es responsable de decidir cómo ponderar cantidades mensuales, cómo escoger el menor precio entre opciones comparables y cómo construir gráficos. El bot guarda los precios disponibles; no calcula el total de la canasta.

## 6. Modos de ejecución

```powershell
py -3 -m sepa_bot.main --once
py -3 -m sepa_bot.main --server
py -3 -m sepa_bot.main --inspect ruta\archivo.csv
py -3 -m sepa_bot.main --load-db
```

- `--once`: procesa la semana actual ahora. El lunes asociado se calcula según la zona horaria configurada. No mantiene el proceso abierto.
- `--daemon` o `--server`: mantiene el proceso activo, revisa el reloj cada 30 segundos y realiza la captura el lunes desde `RUN_AT`. El martes intenta recuperar si no hay una entrada semanal en la base configurada.
- `--hora HH:MM`: modifica la hora mientras se ejecuta `--server`/`--daemon`; la zona se configura mediante `RUN_TIMEZONE`.
- `--inspect ARCHIVO.csv`: muestra encoding, delimitador, columnas y primeras filas, sin llamar a CKAN.
- `--load-db`: ejecuta el cargador antiguo de JSONL (`db_loader.py`) hacia su esquema de dimensiones/historial. No ejecuta la captura semanal, que escribe sus propias tablas semanales en la base configurada.

Para operación automática local, `--server` debe quedar ejecutándose en una computadora siempre encendida o como servicio de un servidor. La alternativa en la nube es el workflow de GitHub Actions descrito abajo.

En Windows también se puede programar `scripts/run_weekly_local.bat` para que
se ejecute una vez por semana. Ese lanzador fija `DB_MODE=sqlite`,
`DB_PATH=data\sepa.db` (en la raíz del proyecto) y la zona horaria de Buenos
Aires, independientemente de las variables PostgreSQL usadas por GitHub
Actions. Para permitir la recuperación de una actualización tardía del lunes,
se recomienda programarlo el martes a las 14:30; la PC debe estar encendida o
permitir que el Programador de tareas la active.

## 7. Configuración

Las variables se leen del entorno; `python-dotenv` también carga `.env` si existe. Un entorno del sistema tiene prioridad sobre `.env` porque se carga sin sobrescribir variables existentes.

| Ajuste | Valor predeterminado | Efecto |
|---|---|---|
| `DB_MODE` | `sqlite` | Motor de la captura semanal y del cargador: `sqlite` o `postgres`. |
| `DB_PATH` | `data/sepa.db` | Archivo SQLite cuando `DB_MODE=sqlite`; se ignora en PostgreSQL. |
| `RUN_AT` | `14:00` | Hora local del lunes para el daemon. |
| `RUN_TIMEZONE` | `America/Argentina/Buenos_Aires` | Zona para calendario y validación de actualización. |
| `DATABASE_URL` | Vacía | URL de conexión PostgreSQL; requerida con `DB_MODE=postgres`. |
| `CKAN_API_KEY` | Vacía | Credencial opcional para una API CKAN que requiera autenticación. El dataset público usado aquí no la requiere. |
| `OUTPUT_FORMAT` | `jsonl` | Formato intermedio. La captura semanal requiere JSONL. |
| `CSV_DELIMITER`, `CSV_ENCODING` | Automáticos | Permiten fijar separador/encoding si se conoce el formato. |
| `LIMPIAR_RAW_DESPUES` | Activado | Elimina artefactos después de convertir correctamente. |
| `MAX_ROWS` | Sin límite | Límite opcional para las conversiones CSV; no es un límite de producto del historial. |

## 8. Dependencias y herramientas de empaquetado

- Python 3.11 o superior.
- `requests`: HTTP a CKAN y descarga.
- `python-dotenv`: carga opcional del archivo `.env`.
- `psycopg[binary]`: PostgreSQL para captura y cargador. SQLite forma parte de Python.
- `pyproject.toml` permite instalar el proyecto como paquete y expone el comando `sepa-bot`.
- `requirements.txt` ofrece instalación directa de dependencias con pip.

El scheduler semanal usa un bucle del propio proceso y `zoneinfo`; no necesita una biblioteca externa de cron. Por eso el proceso servidor debe permanecer activo.

## 9. Límites conocidos y comprobaciones antes de producción

1. La muestra CSV incluida no contiene `descripcion`, `marca` descriptiva ni presentación de envase; solo permite comprobar campos básicos y no validar las coincidencias de la canasta.
2. No se ha validado una captura integral reciente con el ZIP real del portal; la descarga es grande. Antes de producción conviene ejecutar `--inspect` sobre los CSV reales y comprobar nombres de columnas y estructura de ZIP.
3. Los nombres de columnas del SEPA pueden diferir de los alias que espera `weekly_history.py`. Si no coinciden, puede que precio, cadena, ubicación o presentación queden vacíos o que no se reconozcan productos.
4. La detección de productos por alias necesita revisión para evitar coincidencias ambiguas. Las categorías con productos heterogéneos requieren reglas específicas.
5. El criterio geográfico reconoce texto relacionado con CABA y Buenos Aires. Debe verificarse con los valores reales de localidad/provincia que publique el portal.
6. A las 14:00 se exige que `last_modified` corresponda al lunes. Si el portal publica más tarde, el bot registra `sin_actualizacion` y espera al lunes siguiente, salvo que se recupere el martes y el timestamp sea del lunes o martes.
7. Una captura queda marcada en `capturas_semanales` incluso si es `sin_actualizacion` o si termina sin coincidencias; esto impide reintentar esa misma semana automáticamente.
8. `seleccion_historial.py`, `db_loader.py` y `neon_postgres_loader.py` son caminos heredados y no deben confundirse con la escritura semanal a `historial_canasta_semanal`.
9. No hay UI, endpoint para la aplicación web, alertas ni sistema de backups. Se incluye una utilidad para migrar las tablas semanales existentes de SQLite a PostgreSQL, pero no un sistema general de migraciones de esquema.

## 10. Recorrido recomendado para entender o depurar

1. Revisar `config.py` y `.env` para saber hora, zona y motor de base efectivos.
2. Ejecutar `--inspect` sobre un CSV real para validar el esquema.
3. Revisar `product_catalog.py` contra descripciones reales, empezando por productos de marcas bien identificables.
4. Ejecutar las pruebas locales: `py -3 -m unittest discover -s tests -p 'test_*.py'`.
5. Ejecutar `--once` y revisar el JSON resumen, `data/state/last_run.json`, logs y tablas de la base configurada.
6. Dejar `--server` en un equipo siempre encendido o configurar la ejecución en GitHub Actions según la sección siguiente.

Para el detalle de requisitos del sistema, consultar `DOCUMENTACION_REQUISITOS.md`; para la lista de productos y opciones, consultar `requerimientos.md`.

## 11. Ejecución en GitHub Actions con Neon

La captura semanal actual usa SQLite de forma predeterminada para desarrollo local. Para correrla en GitHub Actions, conviene usar PostgreSQL administrado: el runner es temporal y su archivo SQLite se elimina al terminar. **Neon PostgreSQL** es compatible con el driver `psycopg` que ya utiliza el proyecto. Neon publica un [plan Free permanente sin tarjeta](https://neon.com/pricing); los límites y condiciones pueden cambiar, así que verifica el uso y las cuotas vigentes. Supabase también ofrece PostgreSQL, pero no hace falta cambiar de motor ni agregar un driver para usar Neon.

### Crear la base en Neon y migrar los datos

1. Crea un proyecto PostgreSQL en Neon y copia la URL de conexión recomendada por su panel, con SSL (`sslmode=require`). Guárdala como secreto; no la pegues en el código, en `.env.example` ni en un issue.
2. En PowerShell, desde la raíz del proyecto, configura la conexión temporalmente y ejecuta la migración de las tablas semanales existentes:

   ```powershell
   $env:DB_MODE = "postgres"
   $env:DATABASE_URL = 'postgresql://USUARIO:CONTRASEÑA@HOST/BASE?sslmode=require'
   python -m sepa_bot.migrate_sqlite_to_postgres --sqlite-path data\sepa.db
   ```

   El comando copia `historial_canasta_semanal` y `capturas_semanales` en lotes, evita duplicados si se vuelve a ejecutar y no imprime la URL. La base debe ser la SQLite que contiene el historial semanal. Si empiezas sin historial que conservar, puedes omitir la migración: la primera captura crea las tablas en PostgreSQL.
3. Al terminar, cierra la terminal o elimina la variable temporal (`Remove-Item Env:DATABASE_URL`, `Remove-Item Env:DB_MODE`). La migración no borra ni modifica la base SQLite original.

### Subir el proyecto a un repositorio privado

1. En GitHub, crea un repositorio nuevo y selecciona **Private**. Si el repositorio local ya tiene Git inicializado (como en este proyecto), no inicialices un segundo repositorio con otro `git init`.
2. Desde PowerShell en la carpeta del proyecto, revisa que `.env`, `data\sepa.db`, archivos JSONL y datos privados estén ignorados antes de añadir los fuentes:

   ```powershell
   git status --short
   git add .gitignore .env.example README.md GUIA_TECNICA_DEL_PROYECTO.md pyproject.toml requirements.txt sepa_bot tests scripts systemd .github
   git status --short
   git commit -m "Configurar captura semanal en GitHub Actions"
   git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
   git push -u origin main
   ```

   Si `origin` ya existe, revisa `git remote -v` y usa `git remote set-url origin ...` en lugar de agregarlo de nuevo. No subas `.env` ni la base local. No agregues `neon_postgres_loader.py` si no lo necesitas: es un camino heredado y no se requiere para la captura semanal.

### Cargar los Secrets

1. En GitHub, abre **Settings → Secrets and variables → Actions → New repository secret**.
2. Crea `DATABASE_URL` y pega la URL PostgreSQL de Neon completa, incluida la opción SSL que indica el proveedor.
3. `CKAN_API_KEY` es opcional para este dataset público; no crees ese secret salvo que reemplaces CKAN por una API autenticada.
4. El workflow configura `DB_MODE=postgres`, inyecta los Secrets solo durante el job y ejecuta `python -m sepa_bot.main --once`. Las pruebas corren antes de la captura. El contenido descargado y SQLite local del runner no son persistentes; el historial queda en Neon.
5. Comprueba **Actions → SEPA weekly capture** y ejecuta **Run workflow** una vez para probarlo. El evento programado solo se activa desde la rama predeterminada del repositorio, así que confirma que el workflow esté allí. GitHub Actions programa el cron en UTC: `0 17 * * 1` corresponde a los lunes a las **14:00 en Argentina (UTC−3)**. Los disparos programados pueden retrasarse y están sujetos a las cuotas de GitHub; no son garantía de ejecución exactamente al minuto. El caché del workflow conserva como ayuda la selección de sucursales entre runners, pero Neon es la persistencia del historial.