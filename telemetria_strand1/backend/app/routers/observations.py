"""Endpoints de observaciones de SatNOGS."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..ingest import sincronizar_observaciones
from ..models import Frame, Observation
from ..schemas import ObservationListOut, ObservationOut
from ..services.satnogs import SatnogsError

router = APIRouter(prefix="/api/observations", tags=["observations"])


@router.get("", response_model=ObservationListOut)
def listar(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    total = db.scalar(select(func.count(Observation.observation_id))) or 0
    filas = db.scalars(
        select(Observation).order_by(Observation.observation_id.desc()).limit(limit).offset(offset)
    ).all()

    conteos = dict(db.execute(
        select(Frame.observation_id, func.count(Frame.id))
        .where(Frame.observation_id.is_not(None))
        .group_by(Frame.observation_id)
    ).all())

    items = []
    for o in filas:
        salida = ObservationOut.model_validate(o)
        salida.frame_count = conteos.get(o.observation_id, 0)
        items.append(salida)

    # Si ninguna observacion viene de Network, faltan estacion, elevacion y
    # ventana temporal: la interfaz debe avisarlo en vez de dejar huecos mudos.
    parcial = all(o.source != "satnogs-network" for o in filas) if filas else False

    return ObservationListOut(total=total, items=items, partial_metadata=parcial)


@router.post("/sync")
def sincronizar(
    db: Session = Depends(get_db),
    limite: int = Query(100, ge=1, le=500),
    incluir_recientes: bool = Query(
        False,
        description=(
            "Ademas de completar las observaciones de nuestros frames, trae las "
            "mas recientes del satelite aunque no tengan frames asociados."
        ),
    ),
):
    """Completa los metadatos consultando SatNOGS Network."""
    try:
        r = sincronizar_observaciones(db, limite=limite, incluir_recientes=incluir_recientes)
    except SatnogsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # red caida, DNS, timeout
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo contactar con SatNOGS Network: {exc}",
        ) from exc

    return {
        **r,
        "mensaje": (
            f"{r['resueltas_por_id']} de {r['solicitadas']} observaciones resueltas en "
            f"SatNOGS Network · {r['nuevas']} nuevas, {r['actualizadas']} actualizadas."
        ),
    }


@router.get("/{observation_id}", response_model=ObservationOut)
def detalle(observation_id: int, db: Session = Depends(get_db)):
    obs = db.scalar(select(Observation).where(Observation.observation_id == observation_id))
    if obs is None:
        raise HTTPException(status_code=404, detail="Observacion no encontrada")
    salida = ObservationOut.model_validate(obs)
    salida.frame_count = db.scalar(
        select(func.count(Frame.id)).where(Frame.observation_id == observation_id)
    ) or 0
    return salida
