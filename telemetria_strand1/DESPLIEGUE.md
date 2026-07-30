# Despliegue

Tres piezas en tres sitios distintos, porque cada una necesita algo diferente:

| Pieza | Donde | Por que ahi |
|---|---|---|
| Frontend (SPA de Vite) | Vercel | Son archivos estaticos con enrutado en cliente: encaje perfecto |
| Backend (FastAPI) | Render, Railway o Fly.io | Necesita un proceso vivo y mas de 250 MB de dependencias |
| PostgreSQL | Neon, Supabase o el gestionado del proveedor | Los datos no caben en el codigo |

## Por que el backend no va en Vercel

No es una preferencia, son tres topes concretos:

1. **Peso.** Las dependencias suman unos 190 MB instaladas --- pandas 74 MB y
   numpy 70 MB son la mayor parte --- contra un limite de 250 MB descomprimidos
   para funciones Python. Queda sin margen, y pandas no es opcional: el motor
   del gemelo digital se apoya entero en el.
2. **Estado.** `gemelo_digital.estado.reconstruir()` tarda 4,1 s en construir un
   DataFrame de 21 833 x 77 y lo guarda en una cache de modulo. Con un proceso
   persistente eso se paga una vez; en serverless, cada arranque en frio lo
   vuelve a pagar y arriesga agotar el tiempo limite de la funcion.
3. **Entrypoint.** Vercel sugiere
   `telemetria_strand1.backend.app.main:app`, que no es importable: haria falta
   `__init__.py` en `telemetria_strand1/` y en `backend/`, y no existen. El
   modulo real es `app.main:app` con `backend/` como raiz, que es lo que
   configura `render.yaml`.

## 1. Base de datos

El volcado y su guion estan en el repositorio privado `strand-1`, rama `main`
(en `cubesat` no se versionan). Elige proveedor:

| | Plan gratuito | Aviso |
|---|---|---|
| **Supabase** | 500 MB, sin caducidad | El proyecto se **pausa a los 7 dias** sin actividad; se reanuda a mano |
| **Neon** | 500 MB, sin caducidad | La rama se suspende al minuto de inactividad, pero despierta sola en segundos |
| **Render** | 1 GB | **Caduca a los 30 dias** y se borra |

La base ocupa 85 MB, asi que cabe en los tres. Para algo que debe seguir en pie
durante la evaluacion, Neon es el que menos vigilancia pide.

En un gestionado la base viene creada y no se pueden crear otras, asi que hay
que pedir el segundo modo:

```bash
cd telemetria_strand1/db
PGHOST=<host> PGPORT=5432 PGUSER=<usuario> PGPASSWORD=<clave> PGDATABASE=postgres \
  ./restaurar.sh --base-existente
```

**Con Supabase, usa el puerto 5432 y no el 6543.** El 6543 es el pooler de
transacciones: no admite todas las sentencias de un volcado y la restauracion
falla a medias, dejando unas tablas si y otras no. Ese mismo pooler rompe
despues la aplicacion, porque psycopg3 usa sentencias preparadas; si en
produccion se conecta por el 6543 hay que anadir `?prepare_threshold=0` a
`DATABASE_URL`.

Comprueba que llegaron las cinco tablas; el script imprime los recuentos. Deben
salir 36 641 tramas y 198 349 campos decodificados.

Guarda la cadena de conexion. **Tiene que llevar el dialecto explicito**: sin
`+psycopg`, SQLAlchemy asume psycopg2, que no esta en `requirements.txt`.

```
postgresql+psycopg://usuario:clave@host:5432/base
```

## 2. Backend

Con Render, el `render.yaml` de la **raiz del repositorio** lo describe todo;
basta crear un Blueprint apuntando al repositorio. Tiene que estar en la raiz:
Render no busca blueprints en subdirectorios, y `rootDir` ya situa el servicio
en `telemetria_strand1/backend`. Las variables marcadas `sync: false` se rellenan a
mano:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | la cadena del paso 1 |
| `REQUIRE_POSTGRES` | `true` |
| `CORS_ORIGINS` | el dominio del frontend, sin barra final |
| `SATNOGS_DB_TOKEN` | solo si vas a descargar datos nuevos |

En otro proveedor, la configuracion equivalente es:

- directorio raiz: `telemetria_strand1/backend`
- instalacion: `pip install -r requirements.txt`
- arranque: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

**Sobre `REQUIRE_POSTGRES`:** sin el, la aplicacion cae a SQLite en silencio si
PostgreSQL no responde. En produccion eso significa servir una base vacia sin
que nada falle de forma visible; es peor que un error de arranque.

**Sobre `CORS_ORIGINS`:** acepta un solo origen, varios separados por comas o una
lista JSON. Si el navegador rechaza las respuestas de la API con el frontend ya
desplegado, este es el primer sitio donde mirar.

**Sobre la version de Python:** el codigo usa uniones PEP 604 y genericos
nativos, asi que necesita **3.10 o posterior**. La 3.14 del equipo de desarrollo
no es un requisito.

## 3. Frontend

En Vercel, con el directorio raiz en `telemetria_strand1/frontend`. El
`vercel.json` de ahi fija la compilacion y, sobre todo, la reescritura que hace
falta para un SPA: cualquier ruta que no sea un archivo de `assets/` se sirve
como `index.html`. Sin eso, entrar directamente en `/gemelo` da un 404, porque
esa ruta solo existe para React Router, no en el sistema de archivos.

Define una variable de entorno:

| Variable | Valor |
|---|---|
| `VITE_API_URL` | la raiz del backend, sin barra final |

Si se deja vacia, las peticiones quedan relativas --- que es lo correcto en
desarrollo, donde las sirve el proxy de Vite --- y en produccion irian al propio
dominio de Vercel, donde no hay API.

Las variables `VITE_*` se incrustan **en tiempo de compilacion**, no se leen al
arrancar: si cambias el dominio del backend hay que volver a desplegar el
frontend.

## Orden y comprobacion

Base, backend, frontend: cada paso necesita la URL del anterior. Al terminar:

```bash
curl https://<backend>/api/gemelo/resumen
```

Debe responder 21 833 eventos y 588 pases. Si eso funciona y el frontend sigue
sin datos, el problema es `CORS_ORIGINS` o `VITE_API_URL`, no la API.
