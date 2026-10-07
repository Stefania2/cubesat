"""Gestor de conexiones WebSocket del dashboard.

Mantiene las conexiones activas y difunde mensajes con la estructura
`WsMessage`. Es el unico punto de salida en tiempo real del backend.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class WebSocketManager:
    def __init__(self) -> None:
        self._activas: set[WebSocket] = set()

    async def conectar(self, ws: WebSocket) -> None:
        await ws.accept()
        self._activas.add(ws)
        logger.info("WebSocket conectado (%s activas)", len(self._activas))

    async def desconectar(self, ws: WebSocket) -> None:
        self._activas.discard(ws)
        logger.info("WebSocket desconectado (%s activas)", len(self._activas))

    async def enviar_mensaje(self, ws: WebSocket, tipo: str, payload: dict[str, Any]) -> None:
        try:
            mensaje = json.dumps({"type": tipo, "timestamp": ahora_iso(), "payload": payload})
            await ws.send_text(mensaje)
        except Exception as exc:
            logger.error("enviar_mensaje[%s]: %s: %s", tipo, type(exc).__name__, exc)
            self._activas.discard(ws)

    async def difundir(self, tipo: str, payload: dict[str, Any]) -> None:
        if not self._activas:
            return
        mensaje = json.dumps({"type": tipo, "timestamp": ahora_iso(), "payload": payload})
        caidas = []
        for ws in list(self._activas):
            try:
                await ws.send_text(mensaje)
            except Exception:
                caidas.append(ws)
        for ws in caidas:
            self._activas.discard(ws)

    @property
    def conexiones_activas(self) -> int:
        return len(self._activas)


manager = WebSocketManager()