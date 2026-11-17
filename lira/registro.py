"""Registro de auditoria de LIRA: solo en local.

Decision de la usuaria (2026-11-17): el registro persistente vive solo en la
instalacion local. Cada interaccion se añade como una linea JSON a
`lira/_registro/AAAA-MM-DD.jsonl` (ignorado por git). En Vercel el disco es de
solo lectura y no se escribe nada: `activo()` es falso y la API lo dice.

Se registra: instante, sesion (anonima), texto recibido, modo (determinista /
IA), herramientas llamadas, acciones propuestas, aceptadas, rechazadas,
confirmadas o canceladas, verificacion de cifras y consumo de tokens. Nunca
la contraseña, la clave de la API ni la IP.
"""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

DIR = Path(os.environ.get("LIRA_REGISTRO_DIR", Path(__file__).resolve().parent / "_registro"))
_recientes: deque = deque(maxlen=200)


def activo() -> bool:
    return not os.environ.get("VERCEL")


def anotar(evento: dict) -> None:
    if not activo():
        return
    fila = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), **evento}
    _recientes.append(fila)
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        with open(DIR / f"{fila['utc'][:10]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass  # disco de solo lectura: queda en memoria


def recientes(n: int = 50) -> list[dict]:
    return list(_recientes)[-n:]
