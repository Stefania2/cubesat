"""API del dashboard STRAND-1 (GNU Radio -> Python -> FastAPI/WebSocket).

Capa de MONITOREO y VISUALIZACION del enlace RF simulado. No modifica la
cadena de 18.776 bits: lee las salidas de `cadena_strand1_awgn.py` como
copias y las expone por REST y WebSocket.
"""

from __future__ import annotations

import logging
import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config
from . import integridad
from . import metrics_service
from .gnuradio_interface import runner
from .metrics_service import metrics
from .models import (
    ConfigOut,
    ConstellationOut,
    IntegridadBit,
    LogEntry,
    MetricsOut,
    SpectrumOut,
    StatusOut,
    TelemetriaOut,
)
from .telemetry_service import telemetria_out
from .websocket_manager import manager, ahora_iso

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="STRAND-1 Ground Station API",
    description="Dashboard de monitoreo del enlace RF simulado (GNU Radio).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimularRequest(BaseModel):
    action: str = Field(..., description="start | stop | reset")
    snr_db: float = Field(default=config.SNR_DEFAULT_DB, ge=config.SNR_MIN_DB, le=config.SNR_MAX_DB)


# ─────────────────────────────────────────────────────────────────────────────
# Publicacion en tiempo real
# ─────────────────────────────────────────────────────────────────────────────
async def finalizar_simulacion(rc: int) -> None:
    if rc == 0:
        try:
            metrics.actualizar(runner.snr_actual or config.SNR_DEFAULT_DB)
        except Exception as exc:
            logger.exception("No se pudieron calcular metricas")
            await manager.difundir("log", LogEntry(
                timestamp=ahora_iso(), nivel="ERROR", mensaje=f"Metricas: {exc}"
            ).model_dump())
            return
    await difundir_estado()


async def difundir_estado() -> None:
    await manager.difundir("status_update", estado_payload())
    await manager.difundir("metrics_update", metrics.metrics_out().model_dump())
    integridad_payload = integridad.validar_bits(config.BITS_RX_SIM if (config.BITS_RX_SIM.exists()) else config.BITS_RX)
    await manager.difundir("integrity_update", integridad_payload.model_dump())
    await manager.difundir("telemetry_update", telemetria_out().model_dump())
    if metrics.spectrum_out().disponible:
        await manager.difundir("spectrum_ready", metrics.spectrum_out().model_dump())
    if metrics.constellation_out().disponible:
        await manager.difundir("constellation_ready", metrics.constellation_out().model_dump())
    if runner.log:
        await manager.difundir("log_batch", [e.model_dump() for e in runner.log])


def estado_payload() -> dict:
    en_marcha = runner.estado == "RUNNING"
    ok = runner.resultado.get("rc") == 0 or metrics._estado.get("disponible")
    if en_marcha:
        link = "ACTIVE"
    elif ok:
        link = "ACTIVE"
    else:
        link = "OFFLINE"
    return {
        "link_status": link,
        "sim_status": runner.estado,
        "timestamp": ahora_iso(),
        "frames_received": metrics._estado.get("frames_recibidos") or 100,
        "frames_valid": metrics._estado.get("frames_validos"),
        "frames_error": metrics._estado.get("frames_error"),
        "mensaje": runner.resultado.get("stderr", "").strip()[-300:] or None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints REST
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/status", response_model=StatusOut)
async def api_status():
    return estado_payload()


@app.get("/api/telemetry", response_model=TelemetriaOut)
async def api_telemetry():
    return telemetria_out()


@app.get("/api/frames", response_model=TelemetriaOut)
async def api_frames():
    return telemetria_out()


@app.get("/api/metrics", response_model=MetricsOut)
async def api_metrics():
    return metrics.metrics_out()


@app.get("/api/spectrum", response_model=SpectrumOut)
async def api_spectrum():
    return metrics.spectrum_out()


@app.get("/api/constellation", response_model=ConstellationOut)
async def api_constellation():
    return metrics.constellation_out()


@app.get("/api/config", response_model=ConfigOut)
async def api_config():
    return ConfigOut(
        modulacion=config.MODULATION,
        frecuencia_hz=config.FREQ_HZ,
        tasa_bits_bps=config.SYMBOL_RATE,
        muestras_por_simbolo=config.SAMPLES_PER_SYMBOL,
        rolloff=config.ROLLOFF,
        bits_esperados=config.N_BITS,
        archivo_bits=str(config.BITS_TX),
        snr_min_db=config.SNR_MIN_DB,
        snr_max_db=config.SNR_MAX_DB,
        snr_default_db=config.SNR_DEFAULT_DB,
    )


@app.get("/api/integrity", response_model=IntegridadBit)
async def api_integridad():
    ruta = config.BITS_RX_SIM if config.BITS_RX_SIM.exists() else config.BITS_RX
    return integridad.validar_bits(ruta)


@app.get("/api/history", response_model=list)
async def api_historial():
    return metrics.historial()


@app.get("/api/log", response_model=list[LogEntry])
async def api_log():
    return runner.log


@app.post("/api/simulate")
async def api_simular(req: SimularRequest):
    if req.action == "start":
        try:
            runner.iniciar(req.snr_db)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        await manager.difundir("status_update", estado_payload())
        asyncio.create_task(runner.supervisar(finalizar_simulacion))
        return {"estado": "RUNNING", "snr_db": runner.snr_actual}
    if req.action == "stop":
        runner.detener()
        return {"estado": runner.estado}
    if req.action == "reset":
        runner.reset()
        metrics.reset()
        return {"estado": runner.estado}
    raise HTTPException(status_code=422, detail="action debe ser start | stop | reset")


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.conectar(websocket)
    try:
        await manager.enviar_mensaje(websocket, "status_update", estado_payload())
        await manager.enviar_mensaje(websocket, "metrics_update", metrics.metrics_out().model_dump())
        await manager.enviar_mensaje(websocket, "integrity_update",
                                     integridad.validar_bits(
                                         config.BITS_RX_SIM if config.BITS_RX_SIM.exists() else config.BITS_RX
                                     ).model_dump())
        await manager.enviar_mensaje(websocket, "telemetry_update", telemetria_out().model_dump())
        if metrics.spectrum_out().disponible:
            await manager.enviar_mensaje(websocket, "spectrum_ready", metrics.spectrum_out().model_dump())
        if metrics.constellation_out().disponible:
            await manager.enviar_mensaje(websocket, "constellation_ready", metrics.constellation_out().model_dump())
        while True:
            mensaje = await websocket.receive_text()
            if mensaje == "ping":
                await manager.enviar_mensaje(websocket, "pong", {})
    except WebSocketDisconnect:
        await manager.desconectar(websocket)
    except Exception:
        logger.exception("error en /ws")
        await manager.desconectar(websocket)


@app.get("/api/health")
async def health():
    return {"estado": "ok", "conexiones_ws": manager.conexiones_activas}