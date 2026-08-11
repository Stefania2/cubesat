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

set -uo pipefail

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VENV=$(cd "$RAIZ/../.." && pwd)/strand_api
PUERTO_API=8000
PUERTO_WEB=5173

fallo() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

ocupado() { ss -ltn 2>/dev/null | grep -q ":$1 "; }

# --- comprobaciones antes de arrancar nada --------------------------------

[ -x "$VENV/bin/python" ] || fallo "falta el entorno virtual del backend en $VENV
       python3 -m venv $VENV
       $VENV/bin/pip install -r $RAIZ/backend/requirements.txt"

[ -d "$RAIZ/frontend/node_modules" ] || fallo "faltan las dependencias del frontend
       cd $RAIZ/frontend && npm install"

ocupado "$PUERTO_API" && fallo "el puerto $PUERTO_API ya esta ocupado"
ocupado "$PUERTO_WEB" && fallo "el puerto $PUERTO_WEB ya esta ocupado"

# La base no es opcional: con REQUIRE_POSTGRES=true el backend no degrada a
# SQLite, se cae en el arranque. Decirlo aqui es mas claro que una traza de
# SQLAlchemy con la contrasena dentro.
if command -v pg_isready >/dev/null && ! pg_isready -q -h localhost -p 5432; then
  fallo "PostgreSQL no responde en localhost:5432; arrancalo antes"
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
    --host 127.0.0.1 --port "$PUERTO_API" ) &
pid_api=$!

# --host hace que Vite escuche tambien en IPv6. Sin el, el navegador --- que
# resuelve localhost a ::1 antes que a 127.0.0.1 --- responde "no se puede
# acceder al sitio" aunque el servidor este perfectamente vivo.
( cd "$RAIZ/frontend" && exec npm run dev -- --host ) &
pid_web=$!

printf '\n  Backend   http://127.0.0.1:%s/docs\n' "$PUERTO_API"
printf '  Panel     http://localhost:%s\n' "$PUERTO_WEB"
printf '\n  Ctrl+C para parar los dos.\n\n'

# Si uno de los dos se cae, se para tambien el otro, en vez de dejar medio
# sistema en pie aparentando que todo funciona.
wait -n
