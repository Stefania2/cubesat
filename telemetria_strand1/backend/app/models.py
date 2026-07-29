"""Modelos de datos.

La separacion entre capas es deliberada y es la regla central del proyecto:

  RAW DATA        -> Frame.raw_hex, tal como lo entrega SatNOGS. Nunca se altera.
  PROCESSED DATA  -> Frame.byte_count, entropy, ... metricas calculadas sobre los
                     bytes, ciertas sin necesidad de conocer el protocolo.
  DECODED         -> DecodedField, solo se puebla si un ProtocolDefinition validado
                     dice como interpretar los bytes.
  UNKNOWN         -> el estado por defecto. Un frame sin protocolo identificado se
                     queda en `unclassified` y no recibe interpretacion alguna.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class FrameStatus(str, enum.Enum):
    """Estado de decodificacion de un frame."""

    DECODED = "decoded"
    PARTIALLY_DECODED = "partially_decoded"
    UNCLASSIFIED = "unclassified"
    ERROR = "error"


class Observation(Base):
    """Observacion de SatNOGS Network.

    Los campos son opcionales porque el endpoint de telemetria de SatNOGS DB no
    devuelve metadatos de observacion: solo llegan si se consulta ademas la API
    de Network o si el frame trae `observation_id`.
    """

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    norad_id: Mapped[int] = mapped_column(Integer, index=True)
    satellite_name: Mapped[str | None] = mapped_column(String(120))

    station_id: Mapped[int | None] = mapped_column(Integer, index=True)
    station_name: Mapped[str | None] = mapped_column(String(160))
    station_owner: Mapped[str | None] = mapped_column(String(160))
    observer: Mapped[str | None] = mapped_column(String(160))

    status: Mapped[str | None] = mapped_column(String(40))
    frequency_hz: Mapped[float | None] = mapped_column(Float)
    mode: Mapped[str | None] = mapped_column(String(60))
    transmitter: Mapped[str | None] = mapped_column(String(160))

    start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_elevation_deg: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str] = mapped_column(String(40), default="satnogs")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    frames: Mapped[list["Frame"]] = relationship(back_populates="observation")


class Frame(Base):
    """Frame de telemetria crudo mas las metricas derivadas de sus bytes."""

    __tablename__ = "frames"
    __table_args__ = (
        UniqueConstraint("raw_hex", "timestamp", "observer", name="uq_frame_identity"),
        Index("ix_frames_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ── RAW ────────────────────────────────────────────────────────────────
    raw_hex: Mapped[str] = mapped_column(Text, nullable=False)
    norad_id: Mapped[int] = mapped_column(Integer, index=True)
    sat_id: Mapped[str | None] = mapped_column(String(80))
    observer: Mapped[str | None] = mapped_column(String(160), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    app_source: Mapped[str | None] = mapped_column(String(40))
    transmitter: Mapped[str | None] = mapped_column(String(160))
    version: Mapped[str | None] = mapped_column(String(20))
    station_id: Mapped[int | None] = mapped_column(Integer)

    observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("observations.observation_id"), nullable=True, index=True
    )
    observation: Mapped[Observation | None] = relationship(back_populates="frames")

    # ── PROCESSED ──────────────────────────────────────────────────────────
    # Metricas objetivas sobre los bytes; no dependen de conocer el protocolo.
    byte_count: Mapped[int] = mapped_column(Integer, default=0)
    entropy_bits_per_byte: Mapped[float | None] = mapped_column(Float)
    printable_ratio: Mapped[float | None] = mapped_column(Float)
    distinct_bytes: Mapped[int | None] = mapped_column(Integer)

    # ── CLASIFICACION ──────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(30), default=FrameStatus.UNCLASSIFIED.value, index=True
    )
    frame_type: Mapped[str] = mapped_column(String(60), default="unclassified")
    protocol: Mapped[str | None] = mapped_column(String(60))
    # Evidencia estructural encontrada (banderas AX.25, FCS valido...). Es
    # descriptiva: registra que se busco y que se encontro, no una interpretacion.
    analysis: Mapped[dict | None] = mapped_column(JSON)

    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    decoded_fields: Mapped[list["DecodedField"]] = relationship(
        back_populates="frame", cascade="all, delete-orphan"
    )


class ProtocolDefinition(Base):
    """Definicion validada de un protocolo de telemetria.

    Mientras esta tabla este vacia ningun frame puede pasar a `decoded`: es el
    mecanismo que impide que la aplicacion invente el significado de los bytes.
    Para STRaND-1 no existe una especificacion publica validada, de modo que la
    instalacion por defecto no trae ninguna definicion.
    """

    __tablename__ = "protocol_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    norad_id: Mapped[int] = mapped_column(Integer, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(Text)
    validated: Mapped[bool] = mapped_column(default=False)
    # Lista de campos: nombre, offset, longitud, tipo, escala, unidad.
    field_spec: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DecodedField(Base):
    """Valor extraido de un frame mediante una definicion de protocolo validada."""

    __tablename__ = "decoded_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    frame_id: Mapped[int] = mapped_column(ForeignKey("frames.id", ondelete="CASCADE"), index=True)
    frame: Mapped[Frame] = relationship(back_populates="decoded_fields")

    protocol_name: Mapped[str] = mapped_column(String(80))
    field_name: Mapped[str] = mapped_column(String(80), index=True)
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(30))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AnomalyRule(Base):
    """Umbral configurable para la deteccion de anomalias.

    No se fijan limites fisicos arbitrarios: cada regla se crea explicitamente y
    puede editarse o desactivarse desde la interfaz.
    """

    __tablename__ = "anomaly_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    label: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    # Parametros del umbral, distintos segun la regla.
    params: Mapped[dict | None] = mapped_column(JSON)
