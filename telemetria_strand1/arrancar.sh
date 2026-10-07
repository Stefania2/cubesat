#!/usr/bin/env bash
#
# Arranca el backend (FastAPI) y el frontend (Vite) a la vez, y los detiene
# juntos con un solo Ctrl+C.
#
#     ./arrancar.sh          ->  panel en http://localhost:5173
#
# Todo se resuelve contra la ubicacion de este archivo y no contra el
# directorio de trabajo. Eso importa: la configuracion del backend lee el
# .env del directorio actual, asi que uvicorn tiene que ejecutarse dentro de
# backend/ o arranca sin cadena de conexion a la base.
#
# Antes de lanzar nada se corrigen solas las tres causas tipicas de que
# "localhost no abra":
#   1. Un proceso anterior (uvicorn/vite del propio proyecto) sigue ocupando
#      el puerto 8000 o el 5173 -> se detiene y se continua.
#   2. PostgreSQL no esta arriba -> se avisa con el comando para arrancarlo.
#   3. El backend se cae al bootear -> se espera a que responda y, si falla,
#      se imprime el final de su log en vez de quedarse mudo.
# Al final se abre el navegador solo en el panel.

set -uo pipefail

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VENV=$(cd "$RAIZ/../.." && pwd)/strand_api
PUERTO_API=8000
PUERTO_WEB=5173
LOG_API=/tmp/arrancar_strand1_api.log
LOG_WEB=/tmp/arrancar_strand1_web.log

fallo() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

pid_en_puerto() { ss -ltnp 2>/dev/null | awk -v p=":$1" '$4 ~ p { print $6 }' | grep -oP 'pid=\K[0-9]+' | head -1; }

limpiar_puertos() {
  for p in "$PUERTO_API" "$PUERTO_WEB"; do
    if ss -ltn 2>/dev/null | grep -q ":$p "; then
      pid=$(pid_en_puerto "$p")
      if [ -n "$pid" ] && ps -p "$pid" -o args= 2>/dev/null | grep -qE 'uvicorn|vite|node'; then
        printf 'Puerto %s: un proceso anterior del proyecto (pid %s) lo ocupaba; se detiene y se sigue.\n' "$p" "$pid"
        kill "$pid" 2>/dev/null
        sleep 1
        continue
      fi
      fallo "el puerto $p ya esta ocupado por otro proceso; liberalo antes de arrancar"
    fi
  done
}

# La cadena que va a usar el backend: la del entorno o, si no, la de su .env.
# Mismo orden de precedencia que pydantic-settings.
url_base() {
  if [ -n "${DATABASE_URL:-}" ]; then
    printf '%s' "$DATABASE_URL"
  elif [ -f "$RAIZ/backend/.env" ]; then
    grep -E '^DATABASE_URL=' "$RAIZ/backend/.env" | tail -1 | cut -d= -f2-
  fi
}

# Sin cadena definida el backend usa su valor por defecto, que es localhost.
base_es_local() {
  local url
  url=$(url_base)
  [ -z "$url" ] || printf '%s' "$url" | grep -qE '@(localhost|127\.0\.0\.1)[:/]'
}

postgres_ok() {
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -q -h localhost -p 5432 || pg_isready -q -h 127.0.0.1 -p 5432
  else
    (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null
  fi
}

salud_backend() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "http://127.0.0.1:$PUERTO_API/api/status" >/dev/null 2>&1
  else
    (exec 3<>/dev/tcp/127.0.0.1/$PUERTO_API) 2>/dev/null
  fi
}

# --- comprobaciones antes de arrancar nada --------------------------------

[ -x "$VENV/bin/python" ] || fallo "falta el entorno virtual del backend en $VENV
       python3 -m venv $VENV
       $VENV/bin/pip install -r $RAIZ/backend/requirements.txt"

[ -d "$RAIZ/frontend/node_modules" ] || fallo "faltan las dependencias del frontend
       cd $RAIZ/frontend && npm install"

limpiar_puertos

# La base no es opcional: con REQUIRE_POSTGRES=true el backend no degrada a
# SQLite, se cae en el arranque. Decirlo aqui es mas claro que una traza de
# SQLAlchemy con la contrasena dentro. Solo se comprueba el servidor local si
# la cadena apunta a el: con una base remota (Neon) no hace falta tenerlo arriba.
if ! base_es_local; then
  printf 'Base de datos remota: se omite la comprobacion del PostgreSQL local.\n'
elif ! postgres_ok; then
  fallo "PostgreSQL no responde en localhost:5432. Arrancalo primero:
       sudo systemctl start postgresql     (Debian/Ubuntu con systemd)
       sudo service postgresql start       (SysVinit)
       o, si lo tienes como servicio propio, levantalo y vuelve a ejecutar este script"
fi

# --- arranque -------------------------------------------------------------

# Hay que bajar el arbol entero, no solo los dos hijos directos: npm lanza
# vite a traves de un sh intermedio, y matar unicamente a npm deja el
# servidor de Vite vivo y el puerto 5173 ocupado. Se recorre de abajo arriba
# para que ningun nieto quede huerfano y siga escuchando.
matar_arbol() {
  local pid=$1 hijo
  for hijo in $(pgrep -P "$pid" 2>/dev/null); do
    matar_arbol "$hijo"
  done
  kill "$pid" 2>/dev/null
}

pid_api=""
pid_web=""

detener() {
  trap - EXIT INT TERM
  printf '\nDeteniendo el backend y el frontend...\n'
  [ -n "$pid_web" ] && matar_arbol "$pid_web"
  [ -n "$pid_api" ] && matar_arbol "$pid_api"
  wait 2>/dev/null
  printf 'Listo.\n'
}
trap detener EXIT INT TERM

# El exec dentro del subshell es lo que hace que $! sea el pid del proceso
# de verdad y no el de una cascara intermedia que muere sola.
( cd "$RAIZ/backend" && exec "$VENV/bin/python" -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$PUERTO_API" ) >"$LOG_API" 2>&1 &
pid_api=$!

# --host hace que Vite escuche tambien en IPv6. Sin el, el navegador --- que
# resuelve localhost a ::1 antes que a 127.0.0.1 --- responde "no se puede
# acceder al sitio" aunque el servidor este perfectamente vivo.
( cd "$RAIZ/frontend" && exec npm run dev -- --host ) >"$LOG_WEB" 2>&1 &
pid_web=$!

# Espera a que el backend responda antes de cantar victoria: si se cae al
# bootear (por ejemplo la base), aqui se imprime el motivo real en vez de que
# el script quede mudo y "no se abra localhost".
printf 'Arrancando... esperando a que el backend responda\n'
ok=""
for _ in $(seq 1 40); do
  if salud_backend; then ok=1; break; fi
  kill -0 "$pid_api" 2>/dev/null || break
  sleep 1
done

if [ -z "$ok" ]; then
  printf '\nERROR: el backend no respondio. Ultimas lineas de su log:\n'
  tail -n 30 "$LOG_API" 2>/dev/null
  detener
  exit 1
fi

printf '\n  Backend   http://127.0.0.1:%s/docs\n' "$PUERTO_API"
printf '  Panel     http://localhost:%s\n' "$PUERTO_WEB"
printf '\n  Ctrl+C para parar los dos.\n\n'

# Abre el navegador en el panel; si no hay navegador grafico, no pasa nada.
( xdg-open "http://localhost:$PUERTO_WEB" >/dev/null 2>&1 & ) || true

# Si uno de los dos se cae, se para tambien el otro, en vez de dejar medio
# sistema en pie aparentando que todo funciona.
wait -n
