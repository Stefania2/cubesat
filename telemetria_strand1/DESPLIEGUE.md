# Despliegue

Tres piezas en tres sitios distintos, porque cada una necesita algo diferente:

| Pieza | Donde | Por que ahi |
|---|---|---|
| Frontend (SPA de Vite) | Vercel | Son archivos estaticos con enrutado en cliente: encaje perfecto |
| Backend (FastAPI) | **Render** (o Railway, Fly.io) | Necesita un proceso vivo y mas de 250 MB de dependencias |
| PostgreSQL | **Supabase** (o Neon) | Los datos no caben en el codigo |

En negrita, lo que esta desplegado; entre parentesis, las alternativas
equivalentes. Los tres pasos van en ese orden --- base, backend, frontend ---
porque cada uno necesita la URL del anterior.

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

**En produccion esta en Supabase.** El volcado y su guion estan en el repositorio
privado `strand-1`, rama `main` (en `cubesat` no se versionan).

La base ocupa 85 MB, asi que cabria en los tres gestionados gratuitos:

| | Plan gratuito | Aviso |
|---|---|---|
| **Supabase** | 500 MB, sin caducidad | El proyecto se **pausa a los 7 dias** sin actividad; se reanuda a mano |
| **Neon** | 500 MB, sin caducidad | La rama se suspende al minuto de inactividad, pero despierta sola en segundos |
| **Render** | 1 GB | **Caduca a los 30 dias** y se borra |

El de Render queda descartado de entrada para algo que debe seguir en pie durante
la evaluacion. De los otros dos, Neon pide menos vigilancia --- se suspende sola
pero la primera consulta la despierta en un segundo, sin intervencion ---
mientras que Supabase obliga a entrar al panel a reanudar si pasa una semana
entera sin trafico. Ese es el precio de lo que decidio la eleccion: panel de
tablas y editor SQL en el navegador, util para inspeccionar el conjunto sin
montar nada en local.

**Consecuencia practica:** antes de una sustentacion o una demostracion, entrar al
panel de Supabase y comprobar que el proyecto no esta pausado. Con
`REQUIRE_POSTGRES=true` un proyecto pausado no significa una API lenta, significa
un backend que no arranca.

En un gestionado la base viene creada y no se pueden crear otras, asi que hay
que pedir el segundo modo. En Supabase la base se llama `postgres` y el usuario
del *session pooler* lleva pegada la referencia del proyecto:

```bash
cd telemetria_strand1/db
PGHOST=aws-0-<region>.pooler.supabase.com PGPORT=5432 \
PGUSER=postgres.<ref> PGPASSWORD='<clave>' PGDATABASE=postgres \
PGSSLMODE=require ./restaurar.sh --base-existente
```

**Copia la cadena del panel, no la construyas a mano.** Los nombres de servidor
son largos y cambiantes, y Supabase publica **tres** extremos distintos que no
son intercambiables:

| Extremo | Host | Puerto | Para que sirve |
|---|---|---|---|
| Directa | `db.<ref>.supabase.co` | 5432 | Solo desde redes con IPv6 |
| *Session pooler* | `aws-0-<region>.pooler.supabase.com` | 5432 | **El que usa el backend** |
| *Transaction pooler* | `aws-0-<region>.pooler.supabase.com` | 6543 | Exige `?prepare_threshold=0` |

**La conexion directa no vale desde Render.** Los proyectos gratuitos perdieron
su IPv4 dedicada, asi que `db.<ref>.supabase.co` solo resuelve a IPv6 y Render
sale por IPv4: el arranque falla con `Network is unreachable`. Funciona desde una
maquina local con IPv6, que es lo que hace tan confuso el fallo --- se prueba la
cadena, responde, y en el servidor no.

**El pooler de transacciones tampoco, sin retoques.** psycopg3 usa sentencias
preparadas y el modo transaccion de Supavisor no las soporta. Se puede usar
anadiendo `?prepare_threshold=0`, pero es una condicion mas que recordar. Para
**restaurar** no sirve en ningun caso: no admite todas las sentencias de un
volcado y la restauracion falla a medias, dejando unas tablas si y otras no.

**El de sesion es el bueno**: es IPv4, admite sentencias preparadas y acepta el
parametro de arranque `-c timezone=utc` que envia `app/database.py`. Ojo al
usuario, que ahi no es `postgres` a secas sino `postgres.<ref>`:

```
postgresql+psycopg://postgres.<ref>:<clave>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

**Tiene que llevar el dialecto explicito**: sin `+psycopg`, SQLAlchemy asume
psycopg2, que no esta en `requirements.txt`. Y hay que conservar el
`?sslmode=require` que trae la cadena, o la conexion sera rechazada.

Al pegarla en el panel de Render, **cuidado con los espacios al final**: se cuelan
con facilidad al copiar y Render los guarda tal cual, produciendo un error de
resolucion de nombre que no se parece en nada a su causa.

Comprueba que llegaron las cinco tablas; el script imprime los recuentos. Deben
salir 36 641 tramas y 198 349 campos decodificados.

## 2. Backend

El `render.yaml` de la **raiz del repositorio** lo describe todo. Tiene que estar
en la raiz: Render no busca blueprints en subdirectorios, y `rootDir` ya situa el
servicio en `telemetria_strand1/backend`.

Si el panel ofrece **Blueprint**, esa es la via corta: apunta al repositorio y
solo pide las variables marcadas `sync: false`. Pero **la opcion no siempre esta
en el menu `New +`** --- segun la version del panel vive aparte, en la seccion
`Blueprints` de la barra lateral, o directamente no aparece. En ese caso se crea
un **Web Service** normal y se rellena a mano lo que el archivo ya trae:

| Campo | Valor |
|---|---|
| Repository / Branch | el repositorio, rama `main` |
| Root Directory | `telemetria_strand1/backend` |
| Language | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/` |
| Instance Type | Free |

**El Root Directory es el campo que se olvida y el que rompe el despliegue.** Sin
el, Render instala el `requirements.txt` de la raiz del repositorio --- el de los
guiones de simulacion, sin FastAPI ni uvicorn --- el build termina bien y el
arranque falla con `ModuleNotFoundError: No module named 'fastapi'`. Cuando esta
puesto, el panel lo muestra como prefijo del campo Start Command, que sirve de
confirmacion.

`gunicorn` no sirve, aunque sea lo que el panel sugiere de ejemplo: FastAPI es
ASGI y gunicorn habla WSGI.

Las variables de entorno, por la via que sea:

| Variable | Valor |
|---|---|
| `PYTHON_VERSION` | `3.12.7` (solo hace falta escribirla en la via manual) |
| `DATABASE_URL` | la cadena del paso 1 |
| `REQUIRE_POSTGRES` | `true` |
| `CORS_ORIGINS` | el dominio del frontend, sin barra final |
| `SATNOGS_DB_TOKEN` | solo si vas a descargar datos nuevos |
| `REDIS_URL` | opcional, muy recomendable en plan gratuito (ver abajo) |

**Sobre la region:** conviene elegir la de Render mas cercana a la del proyecto de
Supabase --- la region aparece en el propio nombre del *pooler*,
`aws-0-<region>.pooler.supabase.com`. No es critico, pero cada consulta cruza esa
distancia y el arranque del gemelo trae 71 631 lecturas de una vez.

**Sobre `CORS_ORIGINS` y el comodin:** no pongas `*`. La aplicacion monta el
middleware con `allow_credentials=True` y los navegadores rechazan el comodin en
esa combinacion; el sintoma es un error de CORS que aparenta ser del frontend.

**Sobre `REDIS_URL`:** el estado del gemelo son 71 631 lecturas traidas de la
base y un DataFrame de 21 833 x 77 que tarda 4 s en construirse. La primera
peticion de cada instancia paga unos diez segundos, y en plan gratuito el
servicio se duerme, de modo que eso se repite tras cada despertar.

Con un Key Value de Render --- crealo y pega su direccion interna,
`redis://red-...:6379` --- el estado se guarda comprimido en 1,4 MB y se
recupera en **0,07 s**: 242 veces mas rapido, medido.

La cache es opcional y no critica: sin la variable, sin la biblioteca o con el
servidor caido, se recalcula y la API responde igual. La clave incluye la
version de pandas, porque lo que se guarda es un pickle de un DataFrame y su
formato no es estable entre versiones.

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
