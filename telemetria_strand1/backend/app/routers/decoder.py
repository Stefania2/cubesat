"""Endpoint del decodificador manual de HEX."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Frame, ProtocolDefinition
from ..schemas import DecodeRequest
from ..services.decoder import analizar_hex

router = APIRouter(prefix="/api/decoder", tags=["decoder"])


def _validados(db: Session) -> list[ProtocolDefinition]:
    return list(db.scalars(
        select(ProtocolDefinition).where(
            ProtocolDefinition.validated.is_(True),
            ProtocolDefinition.norad_id == settings.norad_id,
        )
    ))


@router.post("")
def decodificar(payload: DecodeRequest, db: Session = Depends(get_db)):
    """Analiza una cadena hexadecimal introducida a mano."""
    try:
        return analizar_hex(payload.hex, _validados(db))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/frame/{frame_id}")
def decodificar_frame(frame_id: int, db: Session = Depends(get_db)):
    """Reejecuta el analisis sobre un frame ya almacenado."""
    frame = db.get(Frame, frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame no encontrado")
    salida = analizar_hex(frame.raw_hex, _validados(db))
    salida["frame_id"] = frame.id
    salida["timestamp"] = frame.timestamp.isoformat()
    salida["observer"] = frame.observer
    return salida
