#!/usr/bin/env bash
# =============================================================
# Dashboard STRAND-1 (Linux/macOS)
# Arranca el backend FastAPI + el frontend Vite.
#
# Uso:  bash arrancar_dashboard.sh
#       BACKEND_PORT=8150 FRONTEND_PORT=4175 bash arrancar_dashboard.sh
# =============================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8150}"
FRONTEND_PORT="${FRONTEND_PORT:-4175}"

# Intenta usar el venv del proyecto (../strand); si no existe, python del PATH.
PYTHON_BIN="${PYTHON:-${RAIZ}/../strand/bin/python}"
if [ ! -x "${PYTHON_BIN}" ]; then
  PYTHON_BIN="python"
fi

# Nota: el proxy del frontend (/api y /ws) apunta a 127.0.0.1:8150
# en dashboard/vite.config.js, así que el backend debe quedar en ese puerto.
BACKEND_PID=""
cleanup() {
  if [ -n "${BACKEND_PID}" ] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "==> Arrancando backend FastAPI en http://127.0.0.1:${BACKEND_PORT}"
(
  cd "${RAIZ}"
  "${PYTHON_BIN}" -m uvicorn backend.main:app --host 127.0.0.1 --port "${BACKEND_PORT}"
) &
BACKEND_PID=$!

# Espera a que el backend este listo
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "==> Arrancando frontend Vite en http://localhost:${FRONTEND_PORT}"
if [ ! -d "${RAIZ}/dashboard/node_modules" ]; then
  echo "(dashboard/node_modules no existe; ejecutando 'npm install'...)"
  (cd "${RAIZ}/dashboard" && npm install)
fi
(cd "${RAIZ}/dashboard" && npm run preview -- --port "${FRONTEND_PORT}" --strictPort)

echo "Dashboard listo: http://localhost:${FRONTEND_PORT}"
echo "Backend:          http://127.0.0.1:${BACKEND_PORT}/docs"