"""STRAND-1 Telemetry API.

Recopilacion, procesamiento y analisis de telemetria del satelite STRaND-1
(NORAD 39090) a partir de observaciones de la red SatNOGS.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import DB_BACKEND, SessionLocal, get_db, init_db
from .ingest import (
    crear_reglas_por_defecto,
    decodificar_frames_almacenados,
    ingerir_csv,
    ingerir_csv_extraccion,
    ingerir_demoddata,
    ingerir_satnogs,
    registrar_protocolo_strand,
)
from .models import Frame, Observation, ProtocolDefinition
from .routers import anomalies, decoder, export, frames, gemelo, observations, telemetry
from .schemas import IngestResultOut, StatusOut
from .services.satnogs import SatnogsError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        crear_reglas_por_defecto(db)
        # La baliza de STRaND-1 tiene especificacion publicada y decodificador
        # oficial, asi que se registra como protocolo validado en el arranque.
        registrar_protocolo_strand(db)
        total = db.scalar(select(func.count(Frame.id))) or 0
        if total == 0 and settings.seed_csv_path.exists():
            logger.info("Base vacia: sembrando desde %s", settings.seed_csv_path)
            try:
                ingerir_csv(db)
            except Exception as exc:
                logger.warning("No se pudo sembrar el CSV: %s", exc)
    yield


app = FastAPI(
    title="STRAND-1 Telemetry API",
    description=__doc__,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(frames.router)
app.include_router(observations.router)
app.include_router(telemetry.router)
app.include_router(decoder.router)
app.include_router(anomalies.router)
app.include_router(export.router)
app.include_router(gemelo.router)

sistema = APIRouter(prefix="/api", tags=["sistema"])


@sistema.get("/status", response_model=StatusOut)
def estado(db: Session = Depends(get_db)):
    return StatusOut(
        satellite=settings.satellite_name,
        norad_id=settings.norad_id,
        database=DB_BACKEND,
        frames=db.scalar(select(func.count(Frame.id))) or 0,
        observaciones=db.scalar(select(func.count(Observation.observation_id))) or 0,
        protocolos_validados=db.scalar(
            select(func.count(ProtocolDefinition.id)).where(
                ProtocolDefinition.validated.is_(True)
            )
        ) or 0,
        satnogs_token_configurado=bool(settings.satnogs_api_token),
    )


@sistema.post("/ingest/csv", response_model=IngestResultOut)
def ingesta_csv(db: Session = Depends(get_db)):
    """Carga el CSV local de telemetria real."""
    try:
        resultado = ingerir_csv(db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return IngestResultOut(
        **resultado,
        mensaje=f"{resultado['insertados']} frames nuevos, {resultado['duplicados']} ya existentes.",
    )


@sistema.post("/ingest/demoddata", response_model=IngestResultOut)
def ingesta_demoddata(db: Session = Depends(get_db), directorio: str | None = None):
    """Carga archivos de demoddata (`data_<obs>_<fecha>_g<n>`) de SatNOGS Network."""
    ruta = Path(directorio) if directorio else settings.demoddata_dir
    try:
        resultado = ingerir_demoddata(db, ruta)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    ignorados = resultado.pop("ignorados", [])
    mensaje = f"{resultado['insertados']} frames nuevos, {resultado['duplicados']} ya existentes."
    if ignorados:
        mensaje += f" Ignorados: {', '.join(ignorados)}."
    return IngestResultOut(**resultado, mensaje=mensaje)


@sistema.post("/telemetry/decodificar")
def decodificar_almacenados(db: Session = Depends(get_db), solo_pendientes: bool = True):
    """Pasa el decodificador oficial de STRaND-1 por los frames guardados."""
    registrar_protocolo_strand(db)
    return decodificar_frames_almacenados(db, solo_pendientes=solo_pendientes)


@sistema.post("/ingest/extraccion", response_model=IngestResultOut)
def ingesta_extraccion(db: Session = Depends(get_db), archivo: str | None = None):
    """Carga el CSV de extraccion masiva de SatNOGS Network."""
    ruta = Path(archivo) if archivo else settings.extraccion_csv_path
    try:
        resultado = ingerir_csv_extraccion(db, ruta)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    sin_telemetria = resultado.pop("sin_telemetria", 0)
    sin_marca = resultado.pop("sin_marca_de_tiempo", 0)
    mensaje = f"{resultado['insertados']} frames nuevos, {resultado['duplicados']} ya existentes."
    if sin_telemetria:
        mensaje += f" {sin_telemetria} observaciones sin telemetria (no son frames)."
    if sin_marca:
        mensaje += f" {sin_marca} filas descartadas por no traer marca de tiempo."
    return IngestResultOut(**resultado, mensaje=mensaje)


@sistema.post("/ingest/satnogs", response_model=IngestResultOut)
def ingesta_satnogs(db: Session = Depends(get_db), limite: int = Query(100, ge=1, le=1000)):
    """Descarga frames nuevos desde SatNOGS DB."""
    try:
        resultado = ingerir_satnogs(db, limite=limite)
    except SatnogsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"No se pudo contactar con SatNOGS DB: {exc}"
        ) from exc
    return IngestResultOut(
        **resultado,
        mensaje=f"{resultado['insertados']} frames nuevos, {resultado['duplicados']} ya existentes.",
    )


app.include_router(sistema)


@app.get("/", include_in_schema=False)
def raiz():
    return {
        "servicio": "STRAND-1 Telemetry API",
        "satelite": settings.satellite_name,
        "norad_id": settings.norad_id,
        "docs": "/docs",
    }
