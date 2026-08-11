#!/usr/bin/env python3
"""Genera la geometría de STRaND-1 con SGP4 y el TLE indicado.

Ejemplo:
    python simular_paso_sgp4.py --inicio 2026-08-09T10:55:44Z --duracion-s 21600

El archivo JSON de salida conserva el TLE y los parámetros de la estación para
que el Doppler y la geometría puedan reproducirse después.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from orbita_sgp4 import Observer, load_tle, points_as_dicts, propagate_window, tle_epoch

DEFAULT_TLE = Path("tle/strand1_2026-08-09.tle")
DEFAULT_OUTPUT = Path("resultados_simulacion/paso_sgp4_strand1.json")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("la fecha debe incluir UTC, por ejemplo 2026-08-09T10:55:44Z")
    return parsed.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tle", type=Path, default=DEFAULT_TLE, help="archivo TLE de dos o tres líneas")
    parser.add_argument("--inicio", type=parse_utc, help="inicio UTC; por defecto, la época del TLE")
    parser.add_argument("--duracion-s", type=int, default=21_600, help="duración de la ventana (s)")
    parser.add_argument("--paso-s", type=int, default=10, help="resolución temporal (s)")
    parser.add_argument("--lat", type=float, default=4.7110, help="latitud de estación (grados)")
    parser.add_argument("--lon", type=float, default=-74.0721, help="longitud de estación (grados)")
    parser.add_argument("--alt-m", type=float, default=2600.0, help="altitud de estación (m)")
    parser.add_argument("--frecuencia-hz", type=float, default=437.568e6, help="frecuencia de downlink")
    parser.add_argument("--salida", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    tle = load_tle(args.tle)
    observer = Observer(args.lat, args.lon, args.alt_m)
    start = args.inicio or tle_epoch(tle)
    points = propagate_window(tle, observer, start, args.duracion_s, args.paso_s, args.frecuencia_hz)
    visible = [point for point in points if point.elevation_deg >= 5.0]
    args.salida.parent.mkdir(exist_ok=True)
    args.salida.write_text(json.dumps({
        "tle": asdict(tle),
        "tle_epoch_utc": tle_epoch(tle).isoformat().replace("+00:00", "Z"),
        "observer": asdict(observer),
        "downlink_hz": args.frecuencia_hz,
        "start_utc": start.isoformat().replace("+00:00", "Z"),
        "step_s": args.paso_s,
        "points": points_as_dicts(points),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"TLE: {tle.name} · época {tle_epoch(tle).isoformat()}")
    print(f"Muestras: {len(points)} · visibles sobre 5°: {len(visible)}")
    if visible:
        print(f"Elevación máxima: {max(point.elevation_deg for point in visible):.2f}°")
        print(f"Doppler: {min(point.doppler_hz for point in visible):.1f} a {max(point.doppler_hz for point in visible):.1f} Hz")
    print(f"Salida: {args.salida}")


if __name__ == "__main__":
    main()
