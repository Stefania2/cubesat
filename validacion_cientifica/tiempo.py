"""Referencia temporal unica: UTC.

Toda fecha que entra al modulo pasa por `instante_utc`, y toda fecha que sale
por `iso`. Asi la telemetria (marcas de SatNOGS en UTC), la propagacion SGP4
(escala UTC, tomada como UT1 — ver `orbital.py`) y el eje de reproduccion del
gemelo comparan el mismo instante, y una prueba automatica puede comprobarlo
mirando un solo campo.

Una fecha sin zona horaria se rechaza: suponer UTC en silencio es exactamente
el tipo de error que desplaza horas una reconstruccion sin que nadie lo note.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

ESCALA = "UTC"


class FechaInvalida(ValueError):
    pass


def instante_utc(valor: str | datetime | pd.Timestamp, *, exigir_zona: bool = True) -> pd.Timestamp:
    """Convierte a `pd.Timestamp` en UTC. Sin zona horaria, error."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise FechaInvalida("falta el instante")
    try:
        t = pd.Timestamp(valor)
    except (ValueError, TypeError) as exc:
        raise FechaInvalida(f"«{valor}» no es una fecha ISO 8601") from exc
    if pd.isna(t):
        raise FechaInvalida(f"«{valor}» no es una fecha")
    if t.tzinfo is None:
        if exigir_zona:
            raise FechaInvalida(f"«{valor}» no indica zona horaria; use UTC explícito (sufijo Z)")
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC")


def iso(t: pd.Timestamp | datetime | None) -> str | None:
    """ISO 8601 en UTC con microsegundos y sufijo Z: una sola forma de escribir fechas."""
    if t is None or (not isinstance(t, datetime) and pd.isna(t)):
        return None
    t = pd.Timestamp(t)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def a_datetime(t: pd.Timestamp) -> datetime:
    return pd.Timestamp(t).tz_convert("UTC").to_pydatetime().astimezone(timezone.utc)
