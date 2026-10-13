"""Endpoints de monitoreo del enlace RF simulado (pagina «Enlace RF»).

Todo lo que informa viene de `enlace_monitor`: subproceso GNU Radio, verificacion
de los 18.776 bits, metricas del tap IQ real y telemetria AMSAT re-decodificada.
No depende de la base de datos. Los endpoints viven bajo `/api/enlace/*` para no
chocar con los de la plataforma, y el websocket en `/ws/enlace`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..services import enlace_monitor as enl
from ..services.enlace_monitor import (
    BITS_RX_SIM,
    SNR_DEFAULT_DB,
    SNR_MAX_DB,
    SNR_MIN_DB,
    config_enlace,
    constelacion_enlace,
    enlace,
    espectro_enlace,
    estado_enlace,
    integridad_enlace,
    telemetria_enlace,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enlace", tags=["enlace"])
ws_router = APIRouter()
_conexiones: set[WebSocket] = set()


def _mensaje(tipo: str, payload: dict[str, Any]) -> str:
    return json.dumps({"type": tipo, "timestamp": enl.ahora_iso(), "payload": payload})


def _estado_snapshots() -> list[tuple[str, dict[str, Any]]]:
    paquetes: list[tuple[str, dict[str, Any]]] = [
        ("status_update", estado_enlace()),
        ("metrics_update", enlace.metricas_enlace()),
        ("integrity_update", integridad_enlace()),
        ("telemetry_update", telemetria_enlace()),
    ]
    espec = espectro_enlace()
    if espec.get("disponible"):
        paquetes.append(("spectrum_ready", espec))
    constelacion = constelacion_enlace()
    if constelacion.get("disponible"):
        paquetes.append(("constellation_ready", constelacion))
    if enlace.log:
        paquetes.append(("log_batch", list(enlace.log)))
    return paquetes


async def difundir(tipo: str, payload: dict[str, Any]) -> None:
    if not _conexiones:
        return
    texto = _mensaje(tipo, payload)
    caidas: list[WebSocket] = []
    for ws in list(_conexiones):
        try:
            await ws.send_text(texto)
        except Exception:
            caidas.append(ws)
    for ws in caidas:
        _conexiones.discard(ws)


async def difundir_todo() -> None:
    for tipo, payload in _estado_snapshots():
        await difundir(tipo, payload)


class SimularEnlace(BaseModel):
    action: str = Field(..., description="start | stop | reset")
    snr_db: float = Field(default=SNR_DEFAULT_DB, ge=SNR_MIN_DB, le=SNR_MAX_DB)


async def finalizar_simulacion(rc: int) -> None:
    if rc == 0 and enlace.snr_actual is not None:
        try:
            enlace.calcular_metricas(enlace.snr_actual)
        except Exception as exc:
            logger.exception("No se pudieron calcular las metricas")
            enlace.log.append(
                {
                    "timestamp": enl.ahora_iso(),
                    "nivel": "ERROR",
                    "mensaje": f"Metricas: {exc}",
                }
            )
    await difundir_todo()


# ── REST ────────────────────────────────────────────────────────────────────
@router.get("/status")
def status():
    return estado_enlace()


@router.get("/config")
def config():
    return config_enlace()


@router.get("/metrics")
def metrics():
    return enlace.metricas_enlace()


@router.get("/telemetry")
def telemetry():
    return telemetria_enlace()


@router.get("/frames")
def frames():
    return telemetria_enlace()


@router.get("/spectrum")
def spectrum():
    return espectro_enlace()


@router.get("/constellation")
def constellation():
    return constelacion_enlace()


@router.get("/integrity")
def integrity():
    return integridad_enlace()


@router.get("/history")
def history():
    return enlace.historial()


@router.get("/log")
def log_ruta():
    return list(enlace.log)


@router.post("/simulate")
async def simulate(req: SimularEnlace):
    if req.action == "start" and enl.motor_simulacion() == enl.MOTOR_NUMPY:
        # Sin GNU Radio: la replica en NumPy corre dentro de la peticion y el
        # resultado completo viaja en la respuesta.
        try:
            paquete = await asyncio.to_thread(enlace.simular_numpy, req.snr_db)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await difundir_todo()
        return {"estado": enlace.estado, "snr_db": enlace.snr_actual,
                "motor": enl.MOTOR_NUMPY, "paquete": paquete}
    if req.action == "start":
        try:
            enlace.iniciar(req.snr_db)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await difundir("status_update", estado_enlace())
        asyncio.create_task(enlace.supervisar(finalizar_simulacion))
        return {"estado": enlace.estado, "snr_db": enlace.snr_actual}
    if req.action == "stop":
        enlace.detener()
        return {"estado": enlace.estado}
    if req.action == "reset":
        enlace.reset()
        return {"estado": enlace.estado}
    raise HTTPException(status_code=422, detail="action debe ser start | stop | reset")


# ── WebSocket ────────────────────────────────────────────────────────────────
@ws_router.websocket("/ws/enlace")
async def ws_enlace(websocket: WebSocket):
    await websocket.accept()
    _conexiones.add(websocket)
    logger.info("WebSocket /ws/enlace conectado (%s activas)", len(_conexiones))
    try:
        for tipo, payload in _estado_snapshots():
            await websocket.send_text(_mensaje(tipo, payload))
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text(_mensaje("pong", {}))
    except WebSocketDisconnect:
        pass
    finally:
        _conexiones.discard(websocket)
        logger.info("WebSocket /ws/enlace desconectado (%s activas)", len(_conexiones))