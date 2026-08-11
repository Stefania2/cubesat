# STRAND-1 Telemetry

Plataforma de recopilación, visualización, procesamiento y análisis de telemetría del
satélite **STRaND-1** (NORAD 39090), a partir de observaciones de la red **SatNOGS**.

## Principio rector

La aplicación **nunca interpreta ni inventa el significado de una trama HEX si el
protocolo no ha sido validado**. Esto no es una limitación accidental: es la regla que
organiza el modelo de datos, la API y la interfaz.

Los datos viven en cuatro capas que no se mezclan en ningún punto:

| Capa | Dónde vive | Qué contiene |
| --- | --- | --- |
| **RAW DATA** | `frames.raw_hex` | El hexadecimal tal como lo entregó SatNOGS. No se altera nunca. |
| **PROCESSED DATA** | `frames.byte_count`, `entropy_bits_per_byte`, … | Métricas objetivas sobre los bytes. Ciertas sin conocer el protocolo. |
| **DECODED TELEMETRY** | `decoded_fields` | Valores físicos. Solo existen si una fila de `protocol_definitions` con `validated = true` dice cómo extraerlos. |
| **UNKNOWN DATA** | `frames.status = 'unclassified'` | El estado por defecto. Un frame sin estructura reconocida se queda aquí. |

### Cuándo la telemetría se decodifica

STRaND-1 **sí dispone de una especificación primaria publicada por AMSAT-UK**. El
arranque registra su definición como validada y el servicio `strand_amsat.py` decodifica
la estructura `C0 80`, el nodo I2C, el canal, el tamaño del dato y las ecuaciones de
calibración publicadas. No se utiliza el valor físico entregado por
`satnogs-decoders` para estos campos: su implementación lee `DATA_SIZE` como si fuese
la medida y puede producir valores constantes incorrectos.

La interfaz muestra un valor como **`Decoded`** únicamente si la trama encaja en esa
estructura validada y la conversión está definida. Mantiene **`Not decoded`** o
**`Not available`** cuando la trama no es una baliza reconocida, el canal no fue emitido
por el satélite o la especificación no define una conversión física. Por ejemplo, la
ausencia de un canal de temperatura transmitido no se sustituye por una estimación.

El mecanismo es general: para otro satélite se debe insertar una definición en
`protocol_definitions` con `validated = true`, referencia bibliográfica y `field_spec`.

## Arquitectura

```
frontend/   React 19 + TypeScript + Tailwind v4 + Recharts   (Vite)
backend/    FastAPI + SQLAlchemy + PostgreSQL                 (Pandas para análisis)
```

El frontend habla siempre con rutas `/api` relativas; Vite las redirige al backend,
de modo que no hay CORS que configurar por entorno.

## Puesta en marcha

### 1. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload
```

Arranca en `http://127.0.0.1:8000`; la documentación OpenAPI está en `/docs`.

En el primer arranque crea las tablas, inserta las reglas de anomalías por defecto,
registra el protocolo validado de STRaND-1 y siembra el conjunto base de 100 frames
desde `../frames_STRAND1.csv`. El conjunto base permite arrancar rápido; el análisis
histórico ampliado se incorpora mediante las herramientas de ingesta.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Abre `http://localhost:5173`.

### Base de datos

La aplicación corre sobre **PostgreSQL**. Crea el rol y la base una sola vez
(requiere privilegios de administrador):

```bash
sudo -u postgres psql -c "CREATE ROLE strand LOGIN PASSWORD 'strand' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE strand1 OWNER strand;"
```

Configura `backend/.env` (hay una plantilla en `.env.example`):

```
DATABASE_URL=postgresql+psycopg://strand:strand@localhost:5432/strand1
REQUIRE_POSTGRES=true       # falla el arranque si PostgreSQL no responde
SATNOGS_API_TOKEN=...       # opcional, mejora los límites de peticiones
```

Con `REQUIRE_POSTGRES=true` la aplicación **aborta el arranque** indicando el motivo si
no puede conectar. Es lo que quieres en un entorno donde PostgreSQL es el destino: sin
esa opción caería a un archivo SQLite local y podrías estar trabajando sobre él sin
darte cuenta.

La conexión fuerza `timezone=utc`, de modo que la API siempre emite marcas de tiempo en
UTC con independencia de la zona del servidor.

## Datos y trazabilidad

| Conjunto | Uso | Contenido |
| --- | --- | --- |
| Base local | Siembra inicial de la aplicación | 100 frames de `frames_STRAND1.csv` |
| Histórico ampliado | Análisis y gemelo digital | 36.641 frames de 3.049 observaciones, entre noviembre de 2016 y julio de 2026 |

El satélite de referencia es STRaND-1 (NORAD 39090), en UHF a 437.568 MHz. El modelo
de simulación evalúa BPSK a 9600 bps y FSK como alternativa; el modo concreto de una
observación se conserva en sus metadatos SatNOGS y no debe inferirse de una tabla fija.

El informe técnico final es la fuente de resultados integrados. Las cifras se trazan a
los archivos de entrada, scripts y salidas versionadas del repositorio; las tablas del
informe se regeneran con `../generar_tablas_informe.py`.

Los frames se descargan de `db.satnogs.org/api/telemetry`. Los metadatos de observación
(estación, ventana temporal, elevación máxima) no los devuelve ese endpoint: se
completan desde `network.satnogs.org/api/observations` con el botón **Sincronizar con
SatNOGS** de la pantalla Observations. Mientras no se sincronicen, los campos que faltan
se muestran como «Not available» en lugar de rellenarse.

La sincronización pide **cada observación por su identificador**, no el listado general.
Es deliberado: el listado devuelve las más recientes del satélite, que no tienen por qué
coincidir con los frames almacenados — con este conjunto no coinciden en absoluto, ya
que los frames apuntan a la serie 11–13 M y el listado arranca en la 14 M.

Las 32 observaciones de este conjunto figuran en SatNOGS con `status: bad`, pese a haber
producido frames que llegaron a la base de datos. La aplicación muestra ese estado tal
cual: es información sobre la calidad de la recepción, no un error que convenga ocultar.

La ingesta es idempotente: la clave `(raw_hex, timestamp, observer)` evita insertar dos
veces el mismo frame, así que se puede repetir sin ensuciar el conjunto.

## Detección de anomalías

Las reglas operan sobre hechos verificables —duplicados, frames constantes, longitud,
entropía, huecos temporales y, cuando el protocolo está validado, la dispersión de las
magnitudes decodificadas—. No hay límites físicos arbitrarios grabados en el código:
los umbrales viven en la tabla `anomaly_rules` y se editan desde la pantalla
**Advanced**. Una magnitud constante se señala como posible canal enrielado; no se
presenta automáticamente como una medida estable.

## API

| Endpoint | Devuelve |
| --- | --- |
| `GET /api/status` | Estado del sistema y backend de base de datos |
| `GET /api/frames` | Listado paginado con filtros (estado, estación, búsqueda HEX) |
| `GET /api/frames/kpis` | Métricas del dashboard |
| `GET /api/frames/series?rango=24h\|7d\|30d\|all` | Serie temporal |
| `GET /api/frames/distribucion` | Longitudes, estados y tipos |
| `GET /api/observations` | Observaciones y sus metadatos |
| `POST /api/observations/sync` | Completa metadatos desde SatNOGS Network |
| `GET /api/telemetry` | Parámetros y su estado real de decodificación |
| `POST /api/decoder` | Analiza una trama HEX introducida a mano |
| `GET /api/anomalies` | Informe de anomalías y reglas activas |
| `PATCH /api/anomalies/rules/{key}` | Ajusta un umbral |
| `GET /api/export/{conjunto}.{csv\|json}` | Exportación por capa |
| `POST /api/ingest/satnogs` | Descarga frames nuevos |

Conjuntos exportables: `observations`, `frames-raw`, `frames-processed`,
`telemetry-decoded`. Cada archivo lleva su capa en el nombre para que no puedan
confundirse entre sí.

## Diseño

Interfaz clara, minimalista y científica: fondo gris muy claro, tarjetas blancas, azul
marino dominante y verde para estados correctos. **Sin modo oscuro** — la aplicación se
compromete deliberadamente con un único aspecto claro.

La paleta del sistema (`src/index.css`, bloque `@theme`) sigue la especificación al pie
de la letra. Las **series de gráfica** son la única excepción y usan
`#1B5C8F / #5BA9D6 / #178A52`: los dos azules de marca (`#123B63` y `#1E5A8A`) quedan a
ΔE 10.9, por debajo del piso de 15, y no se distinguen en un trazo fino ni con visión
cromática normal. Los tres pasos elegidos superan las seis comprobaciones (banda de
luminosidad, suelo de croma, separación CVD, piso de visión normal y contraste sobre
blanco).

Cuando dos series coinciden exactamente —«Recibidos» y «Procesados» lo hacen mientras
todos los frames tengan bytes analizables— la segunda se dibuja con trazo discontinuo,
de modo que el solapamiento se ve en lugar de ocultar la línea de abajo.
