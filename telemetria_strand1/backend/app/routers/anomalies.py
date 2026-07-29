"""Endpoints de deteccion de anomalias y de gestion de sus umbrales."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AnomalyRule, Frame
from ..schemas import AnomalyReportOut, AnomalyRuleOut, AnomalyRuleUpdate
from ..services.anomalies import evaluar

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("", response_model=AnomalyReportOut)
def informe(db: Session = Depends(get_db)):
    frames = db.scalars(select(Frame)).all()
    reglas = db.scalars(select(AnomalyRule).order_by(AnomalyRule.id)).all()
    hallazgos = evaluar(frames, reglas)

    conteo = Counter(h["severity"] for h in hallazgos)
    afectados = {fid for h in hallazgos for fid in h["frame_ids"]}
    resumen = {
        "critical": conteo.get("critical", 0),
        "warning": conteo.get("warning", 0),
        "normal": max(len(frames) - len(afectados), 0),
        "unknown": sum(1 for f in frames if f.status == "unclassified"),
    }
    return AnomalyReportOut(resumen=resumen, hallazgos=hallazgos, reglas=reglas)


@router.get("/rules", response_model=list[AnomalyRuleOut])
def reglas(db: Session = Depends(get_db)):
    return db.scalars(select(AnomalyRule).order_by(AnomalyRule.id)).all()


@router.patch("/rules/{key}", response_model=AnomalyRuleOut)
def actualizar_regla(key: str, cambios: AnomalyRuleUpdate, db: Session = Depends(get_db)):
    """Ajusta un umbral. Los limites no estan fijados en el codigo a proposito."""
    regla = db.scalar(select(AnomalyRule).where(AnomalyRule.key == key))
    if regla is None:
        raise HTTPException(status_code=404, detail="Regla no encontrada")

    if cambios.enabled is not None:
        regla.enabled = cambios.enabled
    if cambios.severity is not None:
        if cambios.severity not in ("normal", "warning", "critical"):
            raise HTTPException(status_code=400, detail="Severidad no valida")
        regla.severity = cambios.severity
    if cambios.params is not None:
        regla.params = {**(regla.params or {}), **cambios.params}

    db.commit()
    db.refresh(regla)
    return regla
