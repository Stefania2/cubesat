"""Propagación SGP4 y geometría estación-satélite a partir de un TLE.

El resto de los modelos usa una órbita circular para los barridos genéricos. Este
módulo añade una ruta reproducible con SGP4 para estudiar un paso concreto: lee el
TLE utilizado, conserva su época y calcula azimut, elevación, distancia, velocidad
radial y Doppler. La conversión TEME→terrestre usa GMST; es adecuada para análisis
de enlace y no pretende sustituir una biblioteca astrométrica de alta precisión.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sgp4.api import SGP4_ERRORS, Satrec, jday

from geometria_orbital import C_LIGHT

WGS84_A_KM = 6378.137
WGS84_F = 1.0 / 298.257223563
EARTH_ROTATION_RAD_S = 7.2921150e-5


@dataclass(frozen=True)
class Observer:
    lat_deg: float
    lon_deg: float
    alt_m: float = 0.0


@dataclass(frozen=True)
class Tle:
    name: str
    line1: str
    line2: str
    source: str = "local"


@dataclass(frozen=True)
class Sgp4Point:
    timestamp_utc: str
    azimuth_deg: float
    elevation_deg: float
    range_km: float
    range_rate_km_s: float
    doppler_hz: float


def load_tle(path: Path) -> Tle:
    """Carga un TLE de dos o tres líneas y conserva el nombre si existe."""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) == 2:
        name, line1, line2 = path.stem, lines[0], lines[1]
    elif len(lines) >= 3:
        name, line1, line2 = lines[-3], lines[-2], lines[-1]
    else:
        raise ValueError(f"TLE inválido en {path}: se requieren dos líneas orbitales")
    if not line1.startswith("1 ") or not line2.startswith("2 "):
        raise ValueError(f"TLE inválido en {path}: las líneas deben empezar por '1 ' y '2 '")
    return Tle(name=name, line1=line1, line2=line2, source=str(path))


def tle_epoch(tle: Tle) -> datetime:
    """Convierte el campo YYDDD.dddddddd de la línea 1 a UTC."""
    epoch = tle.line1[18:32]
    yy = int(epoch[:2])
    year = 1900 + yy if yy >= 57 else 2000 + yy
    day = float(epoch[2:])
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day - 1.0)


def _gmst_rad(jd_ut1: float) -> float:
    """Tiempo sidéreo medio de Greenwich, aproximación IAU 1982."""
    t = (jd_ut1 - 2451545.0) / 36525.0
    seconds = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t * t
        - 6.2e-6 * t * t * t
    )
    return math.radians((seconds / 240.0) % 360.0)


def _observer_ecef(observer: Observer) -> tuple[float, float, float]:
    lat = math.radians(observer.lat_deg)
    lon = math.radians(observer.lon_deg)
    e2 = WGS84_F * (2.0 - WGS84_F)
    n = WGS84_A_KM / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    alt_km = observer.alt_m / 1000.0
    return (
        (n + alt_km) * math.cos(lat) * math.cos(lon),
        (n + alt_km) * math.cos(lat) * math.sin(lon),
        (n * (1.0 - e2) + alt_km) * math.sin(lat),
    )


def _rotate_z(vector: tuple[float, float, float], angle: float) -> tuple[float, float, float]:
    c, s = math.cos(angle), math.sin(angle)
    x, y, z = vector
    return (c * x - s * y, s * x + c * y, z)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(x - y for x, y in zip(a, b))


def propagate_point(
    tle: Tle,
    observer: Observer,
    timestamp: datetime,
    downlink_hz: float,
) -> Sgp4Point:
    """Propaga un instante y devuelve geometría y Doppler para la estación."""
    if timestamp.tzinfo is None:
        raise ValueError("timestamp debe incluir zona horaria")
    utc = timestamp.astimezone(timezone.utc)
    sat = Satrec.twoline2rv(tle.line1, tle.line2)
    second = utc.second + utc.microsecond / 1e6
    jd, fr = jday(utc.year, utc.month, utc.day, utc.hour, utc.minute, second)
    error, position_eci, velocity_eci = sat.sgp4(jd, fr)
    if error:
        raise RuntimeError(SGP4_ERRORS.get(error, f"error SGP4 {error}"))

    gmst = _gmst_rad(jd + fr)
    ground_ecef = _observer_ecef(observer)
    ground_eci = _rotate_z(ground_ecef, gmst)
    ground_velocity_eci = (-EARTH_ROTATION_RAD_S * ground_eci[1], EARTH_ROTATION_RAD_S * ground_eci[0], 0.0)

    relative_eci = _sub(tuple(position_eci), ground_eci)
    relative_velocity = _sub(tuple(velocity_eci), ground_velocity_eci)
    distance = math.sqrt(_dot(relative_eci, relative_eci))
    range_rate = _dot(relative_eci, relative_velocity) / distance

    sat_ecef = _rotate_z(tuple(position_eci), -gmst)
    topocentric = _sub(sat_ecef, ground_ecef)
    lat = math.radians(observer.lat_deg)
    lon = math.radians(observer.lon_deg)
    east = -math.sin(lon) * topocentric[0] + math.cos(lon) * topocentric[1]
    north = (
        -math.sin(lat) * math.cos(lon) * topocentric[0]
        - math.sin(lat) * math.sin(lon) * topocentric[1]
        + math.cos(lat) * topocentric[2]
    )
    up = (
        math.cos(lat) * math.cos(lon) * topocentric[0]
        + math.cos(lat) * math.sin(lon) * topocentric[1]
        + math.sin(lat) * topocentric[2]
    )
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, up / distance))))
    azimuth = math.degrees(math.atan2(east, north)) % 360.0
    # Si el satélite se acerca, range_rate es negativo y el Doppler recibido es
    # positivo: la portadora observada sube.
    doppler = -range_rate * 1000.0 / C_LIGHT * downlink_hz

    return Sgp4Point(
        timestamp_utc=utc.isoformat().replace("+00:00", "Z"),
        azimuth_deg=round(azimuth, 3),
        elevation_deg=round(elevation, 3),
        range_km=round(distance, 3),
        range_rate_km_s=round(range_rate, 6),
        doppler_hz=round(doppler, 3),
    )


def propagate_window(
    tle: Tle,
    observer: Observer,
    start: datetime,
    duration_s: int,
    step_s: int,
    downlink_hz: float,
) -> list[Sgp4Point]:
    """Propaga una ventana temporal completa con paso fijo."""
    if duration_s <= 0 or step_s <= 0:
        raise ValueError("duration_s y step_s deben ser positivos")
    return [
        propagate_point(tle, observer, start + timedelta(seconds=offset), downlink_hz)
        for offset in range(0, duration_s + 1, step_s)
    ]


def points_as_dicts(points: list[Sgp4Point]) -> list[dict]:
    return [asdict(point) for point in points]
