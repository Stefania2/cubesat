"""Vocabulario de estados y forma comun de un resultado de validacion.

Cinco estados, y ninguno se asigna por omision a favor:

    VALIDATED      la comprobacion se ejecuto y el resultado cae en la tolerancia
    FAILED         se ejecuto y no cae en la tolerancia
    WARNING        se ejecuto; el resultado es utilizable con una salvedad documentada
    NOT_VERIFIED   no se ha ejecutado, o no hay referencia contra la que comparar
    NOT_AVAILABLE  el dato necesario no existe en las fuentes

Un `Resultado` sin `ejecutado_utc` no puede estar en VALIDATED: lo impide
`__post_init__`. Es la regla de oro del encargo convertida en codigo.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

VALIDATED = "VALIDATED"
FAILED = "FAILED"
WARNING = "WARNING"
NOT_VERIFIED = "NOT_VERIFIED"
NOT_AVAILABLE = "NOT_AVAILABLE"
ESTADOS = (VALIDATED, FAILED, WARNING, NOT_VERIFIED, NOT_AVAILABLE)

# Naturaleza de un valor. El informe distingue estas cuatro.
MEDIDO = "medido"          # recibido del satelite (baliza real)
CALCULADO = "calculado"    # resultado determinista de un modelo (SGP4, recta de calibracion)
DERIVADO = "derivado"      # estadistico sobre valores medidos (mediana, z)
ESTIMADO = "estimado"      # depende de supuestos no verificados (error de un TLE envejecido)


def ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def limpiar(valor: Any) -> Any:
    """JSON no admite NaN ni infinito: se sustituyen por None (dato ausente)."""
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if isinstance(valor, dict):
        return {str(k): limpiar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [limpiar(v) for v in valor]
    if hasattr(valor, "item") and not isinstance(valor, (str, bytes)):
        try:
            return limpiar(valor.item())
        except (ValueError, AttributeError):
            pass
    return valor


@dataclass
class Resultado:
    """Una comprobacion: que se esperaba, que salio, con que tolerancia."""

    id: str
    modulo: str
    nombre: str
    estado: str
    esperado: Any = None
    obtenido: Any = None
    tolerancia: Any = None
    detalle: str = ""
    referencia: str | None = None
    ejecutado_utc: str | None = None
    datos: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS:
            raise ValueError(f"estado desconocido: {self.estado}")
        if self.estado in (VALIDATED, FAILED, WARNING) and not self.ejecutado_utc:
            # Aprobar, suspender o advertir exige haber ejecutado algo.
            raise ValueError(f"{self.id}: un resultado {self.estado} necesita ejecutado_utc")

    def dict(self) -> dict:
        return limpiar(asdict(self))


def ejecutado(id: str, modulo: str, nombre: str, ok: bool, *, aviso: bool = False,
              **campos) -> Resultado:
    """Atajo para una comprobacion que se acaba de ejecutar."""
    estado = (WARNING if aviso else VALIDATED) if ok else FAILED
    return Resultado(id=id, modulo=modulo, nombre=nombre, estado=estado,
                     ejecutado_utc=ahora_utc(), **campos)


def no_verificado(id: str, modulo: str, nombre: str, detalle: str, **campos) -> Resultado:
    return Resultado(id=id, modulo=modulo, nombre=nombre, estado=NOT_VERIFIED,
                     detalle=detalle, **campos)


def no_disponible(id: str, modulo: str, nombre: str, detalle: str, **campos) -> Resultado:
    return Resultado(id=id, modulo=modulo, nombre=nombre, estado=NOT_AVAILABLE,
                     detalle=detalle, **campos)


def recuento(resultados: list[Resultado | dict]) -> dict[str, int]:
    cuenta = {e: 0 for e in ESTADOS}
    for r in resultados:
        cuenta[r["estado"] if isinstance(r, dict) else r.estado] += 1
    cuenta["total"] = len(resultados)
    return cuenta
