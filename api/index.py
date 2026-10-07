"""Punto de entrada del backend para Vercel (funcion Python serverless).

Vercel busca una aplicacion ASGI llamada `app` en `api/index.py`. La aplicacion
real vive en `telemetria_strand1/backend/app`; aqui solo se pone ese directorio
en `sys.path` y se reexporta. `vercel.json` reescribe todo `/api/*` hacia esta
funcion, de modo que el frontend la alcanza con rutas relativas, sin CORS.

En local no se usa: `arrancar.sh` sigue lanzando uvicorn sobre `app.main:app`.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "telemetria_strand1" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402,F401
