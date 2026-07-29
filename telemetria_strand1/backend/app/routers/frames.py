"""Endpoints de frames: listado, detalle, series temporales y KPIs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Frame, Observation, ProtocolDefinition
from ..schemas import FrameListOut, FrameOut, KpiOut, SerieOut, SeriePunto

router = APIRouter(prefix="/api/frames", tags=["frames"])

RANGOS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


def _inicio_rango(db: Session, rango: str) -> datetime | None:
    delta = RANGOS.get(rango, RANGOS["all"])
    if delta is None:
        return None
    # El conjunto de datos es historico: anclar la ventana al ultimo frame
    # disponible en vez de a "ahora" evita devolver siempre cero resultados.
    ultimo = db.scalar(select(func.max(Frame.timestamp)))
    if ultimo is None:
        return None
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=timezone.utc)
    return ultimo - delta


@router.get("", response_model=FrameListOut)
def listar_frames(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    observer: str | None = None,
    observation_id: int | None = None,
    rango: str = Query("all", pattern="^(24h|7d|30d|all)$"),
    search: str | None = None,
):
    consulta = select(Frame)
    conteo = select(func.count(Frame.id))

    filtros = []
    if status:
        filtros.append(Frame.status == status)
    if observer:
        filtros.append(Frame.observer == observer)
    if observation_id:
        filtros.append(Frame.observation_id == observation_id)
    if search:
        filtros.append(Frame.raw_hex.contains(search.upper().replace(" ", "")))
    inicio = _inicio_rango(db, rango)
    if inicio is not None:
        filtros.append(Frame.timestamp >= inicio)

    for f in filtros:
        consulta = consulta.where(f)
        conteo = conteo.where(f)

    total = db.scalar(conteo) or 0
    items = db.scalars(
        consulta.order_by(Frame.timestamp.desc()).limit(limit).offset(offset)
    ).all()
    return FrameListOut(total=total, items=items, limit=limit, offset=offset)


@router.get("/kpis", response_model=KpiOut)
def kpis(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Frame.id))) or 0
    decodificados = db.scalar(
        select(func.count(Frame.id)).where(
            Frame.status.in_(["decoded", "partially_decoded"])
        )
    ) or 0
    observaciones = db.scalar(select(func.count(Observation.observation_id))) or 0
    estaciones = db.scalar(
        select(func.count(func.distinct(Frame.observer))).where(Frame.observer.is_not(None))
    ) or 0
    ultimo = db.scalar(select(func.max(Frame.timestamp)))
    primero = db.scalar(select(func.min(Frame.timestamp)))

    return KpiOut(
        frames_procesados=total,
        frames_decodificados=decodificados,
        porcentaje_decodificado=round(100.0 * decodificados / total, 1) if total else 0.0,
        observaciones=observaciones,
        estaciones=estaciones,
        ultimo_frame=ultimo,
        primer_frame=primero,
        # Todo lo que muestra la aplicacion procede de observaciones reales de
        # SatNOGS. No hay datos de ejemplo en ninguna metrica.
        es_demo=False,
        fuente="SatNOGS DB · observaciones reales",
    )


def _rango_de_buckets(primero: str, ultimo: str, granularidad: str) -> list[str]:
    """Genera todas las claves de intervalo entre dos extremos, sin saltarse ninguna."""
    claves: list[str] = []

    if granularidad == "mes":
        anio, mes = (int(x) for x in primero.split("-"))
        anio_fin, mes_fin = (int(x) for x in ultimo.split("-"))
        while (anio, mes) <= (anio_fin, mes_fin):
            claves.append(f"{anio:04d}-{mes:02d}")
            mes += 1
            if mes > 12:
                anio, mes = anio + 1, 1
        return claves

    formato = "%Y-%m-%dT%H:00" if granularidad == "hora" else "%Y-%m-%d"
    paso = timedelta(hours=1) if granularidad == "hora" else timedelta(days=1)
    actual = datetime.strptime(primero, formato)
    fin = datetime.strptime(ultimo, formato)
    while actual <= fin:
        claves.append(actual.strftime(formato))
        actual += paso
    return claves


@router.get("/series", response_model=SerieOut)
def series(
    db: Session = Depends(get_db),
    rango: str = Query("all", pattern="^(24h|7d|30d|all)$"),
):
    """Serie temporal de frames recibidos, procesados y decodificados."""
    inicio = _inicio_rango(db, rango)
    consulta = select(Frame.timestamp, Frame.status, Frame.byte_count)
    if inicio is not None:
        consulta = consulta.where(Frame.timestamp >= inicio)
    filas = db.execute(consulta.order_by(Frame.timestamp)).all()

    if not filas:
        return SerieOut(rango=rango, granularidad="ninguna", puntos=[], total_en_rango=0)

    granularidad = {"24h": "hora", "7d": "dia", "30d": "dia"}.get(rango, "mes")

    def clave(ts: datetime) -> str:
        if granularidad == "hora":
            return ts.strftime("%Y-%m-%dT%H:00")
        if granularidad == "dia":
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m")

    recibidos: Counter = Counter()
    procesados: Counter = Counter()
    decodificados: Counter = Counter()

    for ts, status, byte_count in filas:
        k = clave(ts)
        recibidos[k] += 1
        # "Procesado" = el frame tiene bytes analizables y metricas calculadas.
        if byte_count and byte_count > 0:
            procesados[k] += 1
        if status in ("decoded", "partially_decoded"):
            decodificados[k] += 1

    # Rellenar los intervalos sin datos con cero. Un eje categorico se salta los
    # huecos y los comprime en un solo paso: con este conjunto habria pintado
    # 2023-11 pegado a 2025-04 como si fueran meses consecutivos, ocultando 16
    # meses sin recepciones.
    claves = _rango_de_buckets(min(recibidos), max(recibidos), granularidad)

    puntos = [
        SeriePunto(
            bucket=k,
            recibidos=recibidos.get(k, 0),
            procesados=procesados.get(k, 0),
            decodificados=decodificados.get(k, 0),
        )
        for k in claves
    ]
    return SerieOut(
        rango=rango,
        granularidad=granularidad,
        puntos=puntos,
        total_en_rango=sum(recibidos.values()),
    )


@router.get("/estaciones")
def estaciones(db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100)):
    """Ranking de estaciones terrenas por numero de frames aportados."""
    filas = db.execute(
        select(Frame.observer, func.count(Frame.id).label("n"), func.max(Frame.timestamp))
        .where(Frame.observer.is_not(None))
        .group_by(Frame.observer)
        .order_by(func.count(Frame.id).desc())
        .limit(limit)
    ).all()
    return [
        {"observer": obs, "frames": n, "ultimo": ultimo.isoformat() if ultimo else None}
        for obs, n, ultimo in filas
    ]


@router.get("/distribucion")
def distribucion(db: Session = Depends(get_db)):
    """Distribucion de longitudes y de estados de clasificacion."""
    longitudes = db.execute(
        select(Frame.byte_count, func.count(Frame.id))
        .group_by(Frame.byte_count)
        .order_by(Frame.byte_count)
    ).all()
    estados = db.execute(
        select(Frame.status, func.count(Frame.id)).group_by(Frame.status)
    ).all()
    tipos = db.execute(
        select(Frame.frame_type, func.count(Frame.id)).group_by(Frame.frame_type)
    ).all()
    return {
        "longitudes": [{"bytes": b, "frames": n} for b, n in longitudes],
        "estados": [{"estado": e, "frames": n} for e, n in estados],
        "tipos": [{"tipo": t, "frames": n} for t, n in tipos],
    }


@router.get("/{frame_id}", response_model=FrameOut)
def detalle_frame(frame_id: int, db: Session = Depends(get_db)):
    frame = db.get(Frame, frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame no encontrado")
    return frame
