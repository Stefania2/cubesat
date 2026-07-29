"""Esquemas Pydantic de la API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FrameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_hex: str
    norad_id: int
    observer: str | None
    timestamp: datetime
    observation_id: int | None
    station_id: int | None
    app_source: str | None
    byte_count: int
    entropy_bits_per_byte: float | None
    printable_ratio: float | None
    distinct_bytes: int | None
    status: str
    frame_type: str
    protocol: str | None
    analysis: dict | None


class FrameListOut(BaseModel):
    total: int
    items: list[FrameOut]
    limit: int
    offset: int


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_id: int
    norad_id: int
    satellite_name: str | None
    station_id: int | None
    station_name: str | None
    station_owner: str | None
    observer: str | None
    status: str | None
    frequency_hz: float | None
    mode: str | None
    transmitter: str | None
    start: datetime | None
    end: datetime | None
    max_elevation_deg: float | None
    frame_count: int = 0


class ObservationListOut(BaseModel):
    total: int
    items: list[ObservationOut]
    partial_metadata: bool = Field(
        default=False,
        description=(
            "True cuando las observaciones proceden de los identificadores que "
            "traen los frames y no de la API de Network, de modo que faltan "
            "estacion, elevacion maxima y ventana temporal."
        ),
    )


class KpiOut(BaseModel):
    frames_procesados: int
    frames_decodificados: int
    porcentaje_decodificado: float
    observaciones: int
    estaciones: int
    ultimo_frame: datetime | None
    primer_frame: datetime | None
    es_demo: bool = False
    fuente: str


class SeriePunto(BaseModel):
    bucket: str
    recibidos: int
    procesados: int
    decodificados: int


class SerieOut(BaseModel):
    rango: str
    granularidad: str
    puntos: list[SeriePunto]
    total_en_rango: int


class ParametroTelemetria(BaseModel):
    """Un parametro de telemetria y su estado real de decodificacion."""

    key: str
    label: str
    unit: str | None = None
    value: float | str | None = None
    status: str = "not_decoded"
    reason: str | None = None
    history: list[dict] = Field(default_factory=list)


class TelemetriaOut(BaseModel):
    parametros: list[ParametroTelemetria]
    protocolo_validado: bool
    nota: str
    # Resumen de lo que hay decodificado. Va en la respuesta para que todas las
    # pantallas cuenten lo mismo en lugar de deducirlo cada una por su cuenta.
    balizas: int = 0
    campos_totales: int = 0
    campos_constantes: int = 0


class DecodeRequest(BaseModel):
    hex: str = Field(..., description="Cadena hexadecimal, admite espacios.")


class AnomalyRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    label: str
    description: str | None
    enabled: bool
    severity: str
    params: dict | None


class AnomalyRuleUpdate(BaseModel):
    enabled: bool | None = None
    severity: str | None = None
    params: dict | None = None


class AnomalyOut(BaseModel):
    rule: str
    label: str
    severity: str
    message: str
    frame_ids: list[int]
    timestamp: str


class AnomalyReportOut(BaseModel):
    resumen: dict[str, int]
    hallazgos: list[AnomalyOut]
    reglas: list[AnomalyRuleOut]


class IngestResultOut(BaseModel):
    insertados: int
    duplicados: int
    total: int
    fuente: str
    mensaje: str


class StatusOut(BaseModel):
    satellite: str
    norad_id: int
    database: str
    frames: int
    observaciones: int
    protocolos_validados: int
    satnogs_token_configurado: bool
