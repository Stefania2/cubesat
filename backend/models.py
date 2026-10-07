"""Modelos de datos del dashboard STRAND-1.

Modelos Pydantic para las respuestas REST y los mensajes WebSocket.
Los campos que no se pueden medir con los datos actuales se representan como
`None` y el frontend los muestra como «N/A — metrica no disponible». Los
valores numericos solo cristalizan cuando hay fuente real (GNU Radio o la
simulacion del proyecto). Nunca se inventan.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IntegridadBit(BaseModel):
    valido: bool
    bits_entrada: int
    bits_recuperados: int
    diferencia: int
    sha256_entrada: str
    sha256_recuperado: str
    frames_esperados: int
    mensaje: str


class MetricsOut(BaseModel):
    snr_db: float | None = None
    ber: float | None = None
    rssi_dbm: float | None = None
    fer: float | None = None
    potencia_relativa_dbfs: float | None = None
    ruido_estimado: float | None = None
    frecuencia_hz: float | None = None
    tasa_bits_bps: float | None = None
    ancho_banda_hz: float | None = None
    frames_recibidos: int | None = None
    frames_validos: int | None = None
    frames_error: int | None = None
    nota_rssi: str | None = None
    nota_fer: str | None = None
    nota_frecuencia: str | None = None
    nota_ancho_banda: str | None = None


class TelemetriaParam(BaseModel):
    key: str
    label: str
    value: Any
    unit: str | None = None
    status: str
    disponible: bool = True


class FrameTelemetria(BaseModel):
    timestamp: str | None = None
    observer: str | None = None
    tamano_bytes: int | None = None
    hex: str | None = None
    decodificado: bool = False
    campos: dict[str, Any] = {}


class TelemetriaOut(BaseModel):
    total_frames: int
    ultimo_timestamp: str | None = None
    parametros: list[TelemetriaParam] = []
    frames: list[FrameTelemetria] = []
    nota: str | None = None


class SpectrumOut(BaseModel):
    disponible: bool
    fuente: str | None = None
    frecuencia_central_hz: float | None = None
    ancho_banda_hz: float | None = None
    datos: list[dict[str, float]] = []
    nota: str | None = None


class ConstellationOut(BaseModel):
    disponible: bool
    fuente: str | None = None
    puntos: list[dict[str, float]] = []
    nota: str | None = None


class ConfigOut(BaseModel):
    modulacion: str = "BPSK"
    frecuencia_hz: float | None = None
    tasa_bits_bps: float | None = None
    muestras_por_simbolo: int | None = None
    rolloff: float | None = None
    bits_esperados: int | None = None
    archivo_bits: str | None = None
    snr_min_db: float | None = None
    snr_max_db: float | None = None
    snr_default_db: float | None = None


class StatusOut(BaseModel):
    link_status: str
    sim_status: str
    timestamp: str
    frames_received: int | None = None
    frames_valid: int | None = None
    frames_error: int | None = None
    mensaje: str | None = None


class LogEntry(BaseModel):
    timestamp: str
    nivel: str
    mensaje: str


class WsMessage(BaseModel):
    type: str
    timestamp: str
    payload: dict[str, Any] = {}