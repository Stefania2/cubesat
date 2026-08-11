# Volcado de la base de datos

Contiene la telemetria de STRaND-1 ya ingerida y decodificada. Es lo que
alimenta la plataforma web y el gemelo digital, y es el conjunto que respalda
las cifras del capitulo 3 y de la seccion 11 del informe tecnico.

## Que hay dentro

| Tabla | Filas | Que es |
|---|---:|---|
| `frames` | 36 641 | Una fila por trama recibida: hexadecimal crudo, estacion, calidad y el analisis en JSON |
| `decoded_fields` | 198 349 | Formato largo, una fila por (trama, campo) con su valor y unidad |
| `observations` | 3 049 | Una fila por pase observado: estacion, elevacion maxima, estado |
| `protocol_definitions` | 1 | La especificacion de la baliza de AMSAT-UK |
| `anomaly_rules` | 6 | Reglas de deteccion configuradas |

Rango temporal: **2016-11-30 a 2026-07-13**. Las balizas decodificables se
cortan en enero de 2023, cuando el satelite dejo de emitir telemetria
interpretable.

Origen de los datos: red SatNOGS, combinando el archivo historico de SatNOGS DB
(2016-2022) con las observaciones de SatNOGS Network (2022-2026). Son datos
publicos; los nombres de estacion y de observador son los que la propia red
publica.

## Restaurar

```bash
./restaurar.sh
```

Crea la base `strand1` y la rellena. Aborta si ya existe, en lugar de mezclar
dos conjuntos en silencio. Para reemplazarla:

```bash
dropdb -h localhost -U strand strand1 && ./restaurar.sh
```

Se puede reubicar con las variables de entorno de PostgreSQL:

```bash
PGDATABASE=otra PGUSER=otro PGHOST=otro ./restaurar.sh
```

## En un proveedor gestionado (Supabase, Neon, Render)

Ahi la base viene dada y el usuario no puede crear otras, asi que hay que pedir
el segundo modo. En Supabase --- que es donde esta la base de produccion --- la
base se llama `postgres` y el usuario del *session pooler* lleva pegada la
referencia del proyecto:

```bash
PGHOST=aws-0-<region>.pooler.supabase.com PGPORT=5432 \
PGUSER=postgres.<ref> PGPASSWORD='<clave>' PGDATABASE=postgres \
PGSSLMODE=require ./restaurar.sh --base-existente
```

Tres detalles que se pagan caros si se pasan por alto:

**Supabase publica tres extremos, no dos.** La conexion directa
(`db.<ref>.supabase.co:5432`), el *session pooler*
(`aws-0-<region>.pooler.supabase.com:5432`) y el *transaction pooler* (mismo
host, puerto 6543). El reparto no es "directo contra pooler": los dos primeros
sirven para restaurar, el tercero no.

**El de transacciones no vale para restaurar.** No admite todas las sentencias de
un volcado y la restauracion falla a medias, dejando unas tablas si y otras no.

**El de transacciones tambien rompe la aplicacion, por otro motivo.** psycopg3
usa sentencias preparadas, que el modo transaccion de Supavisor no soporta. Si en
produccion se conecta por el 6543 hay que anadir `?prepare_threshold=0` a la
cadena.

**Y la conexion directa no vale desde un servidor sin IPv6.** Los proyectos
gratuitos perdieron su IPv4 dedicada, de modo que `db.<ref>.supabase.co` solo
resuelve a IPv6. Desde Render, que sale por IPv4, falla con `Network is
unreachable` --- aunque la misma cadena funcione desde una maquina local con
IPv6, que es lo que hace confuso el diagnostico.

Por eso el backend en produccion usa el **session pooler**: es el unico de los
tres que es IPv4 y admite sentencias preparadas a la vez.

**El volcado no trae CREATE DATABASE ni \connect**, comprobado, de modo que se
restaura limpiamente dentro de la base que el proveedor haya creado --- en
Supabase se llama `postgres` --- y las tablas caen en el esquema `public`.

El script se niega a restaurar si esas tablas ya existen: mezclar dos conjuntos
en silencio es peor que un error, porque nada falla y los recuentos mienten.

Despues, apunta `DATABASE_URL` en `../backend/.env` a la base restaurada. La
plantilla esta en `../backend/.env.example`.

## Por que se versiona

Sin la base, el analisis del capitulo 3 no se puede reproducir sin volver a
descargar de SatNOGS, y recorrer el archivo trama a trama son dias por el limite
de tasa de la API. Los CSV del directorio padre son exportaciones **parciales**
--- suman 34 963 tramas unicas frente a las 36 641 de aqui ---, asi que no
sirven para citar cifras.

El volcado se genero con `--no-owner --no-privileges`, de modo que no arrastra
roles ni contrasenas: 38,6 MB de SQL que comprimen a 2,6 MB.

Para regenerarlo tras cambiar los datos:

```bash
pg_dump -h localhost -U strand -d strand1 --no-owner --no-privileges \
  | gzip -9 > strand1.sql.gz
```
