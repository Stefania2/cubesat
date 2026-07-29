"""Exportacion de datos en JSON y CSV.

Cada exportacion indica en su nombre la capa a la que pertenece (raw, processed,
decoded) para que un archivo descargado no pueda confundirse con otro.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import DecodedField, Frame, Observation

router = APIRouter(prefix="/api/export", tags=["export"])

CONJUNTOS = ("observations", "frames-raw", "frames-processed", "telemetry-decoded")


def _nombre(conjunto: str, extension: str) -> str:
    sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"strand1_{conjunto}_{sello}.{extension}"


def _filas(db: Session, conjunto: str) -> tuple[list[str], list[dict]]:
    if conjunto == "observations":
        columnas = [
            "observation_id", "norad_id", "station_id", "station_name", "observer",
            "status", "frequency_hz", "mode", "start", "end", "max_elevation_deg", "source",
        ]
        filas = [
            {c: getattr(o, c) for c in columnas}
            for o in db.scalars(select(Observation).order_by(Observation.observation_id))
        ]
    elif conjunto == "frames-raw":
        # Capa RAW: exactamente lo que entrego SatNOGS, sin metricas derivadas.
        columnas = ["id", "timestamp", "norad_id", "observer", "observation_id", "raw_hex"]
        filas = [
            {c: getattr(f, c) for c in columnas}
            for f in db.scalars(select(Frame).order_by(Frame.timestamp))
        ]
    elif conjunto == "frames-processed":
        columnas = [
            "id", "timestamp", "observer", "byte_count", "entropy_bits_per_byte",
            "printable_ratio", "distinct_bytes", "status", "frame_type", "protocol",
        ]
        filas = [
            {c: getattr(f, c) for c in columnas}
            for f in db.scalars(select(Frame).order_by(Frame.timestamp))
        ]
    else:  # telemetry-decoded
        columnas = ["timestamp", "protocol_name", "field_name", "value_numeric", "value_text", "unit"]
        filas = [
            {c: getattr(d, c) for c in columnas}
            for d in db.scalars(select(DecodedField).order_by(DecodedField.timestamp))
        ]
    return columnas, filas


def _serializar(valor):
    return valor.isoformat() if isinstance(valor, datetime) else valor


@router.get("/{conjunto}.{formato}")
def exportar(
    conjunto: str,
    formato: str,
    db: Session = Depends(get_db),
):
    if conjunto not in CONJUNTOS:
        raise HTTPException(
            status_code=404,
            detail=f"Conjunto desconocido. Disponibles: {', '.join(CONJUNTOS)}",
        )
    if formato not in ("json", "csv"):
        raise HTTPException(status_code=404, detail="Formato debe ser json o csv")

    columnas, filas = _filas(db, conjunto)

    if formato == "json":
        cuerpo = {
            "satellite": settings.satellite_name,
            "norad_id": settings.norad_id,
            "dataset": conjunto,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "count": len(filas),
            "nota": (
                "telemetry-decoded solo contiene datos si hay una definicion de "
                "protocolo validada; en caso contrario va vacio a proposito."
            ),
            "data": [{k: _serializar(v) for k, v in fila.items()} for fila in filas],
        }
        contenido = json.dumps(cuerpo, indent=2, ensure_ascii=False)
        return StreamingResponse(
            io.StringIO(contenido),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{_nombre(conjunto, "json")}"'},
        )

    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=columnas)
    escritor.writeheader()
    for fila in filas:
        escritor.writerow({k: _serializar(v) for k, v in fila.items()})
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{_nombre(conjunto, "csv")}"'},
    )
