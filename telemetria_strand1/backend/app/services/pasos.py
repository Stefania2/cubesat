"""Reconstruccion del movimiento de STRaND-1 durante una observacion de SatNOGS.

Para cada observacion de SatNOGS Network se conoce la estacion (latitud,
longitud, altura), la ventana del pase y el TLE con que se programo. Con eso
SGP4 da, segundo a segundo, donde estaba el satelite y como lo veia la
estacion (azimut, elevacion, distancia). Es la misma propagacion que usa el
resto del proyecto (`orbita_sgp4.py` en la raiz del repositorio).

Procedencia: la posicion es ESTIMADA (modelo SGP4 sobre un TLE real, cuya
precision se degrada con la antigüedad del TLE); la estacion, la ventana y las
tramas recibidas son REALES. El JSON de geometria lo genera
`tools/descargar_geometria_observaciones.py`.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

# parents[0] services [1] app [2] backend [3] telemetria_strand1 [4] cubesat
RAIZ_REPO = Path(__file__).resolve().parents[4]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

RUTA_GEOMETRIA = Path(__file__).resolve().parents[1] / "data" / "geometria_observaciones.json"
FRECUENCIA_HZ = 437.568e6
PASO_S = 5
MARGEN_S = 60                # se dibuja un minuto antes y despues de la ventana
PERIODO_ORBITA_S = 6020      # ~100,3 min (14,35 vueltas al dia)


@lru_cache(maxsize=1)
def geometria() -> dict:
    if not RUTA_GEOMETRIA.exists():
        return {"estaciones": {}, "tles": [], "observaciones": {}, "fuente": None}
    return json.loads(RUTA_GEOMETRIA.read_text(encoding="utf-8"))


def tiene_geometria(observation_id: int) -> bool:
    return str(observation_id) in geometria()["observaciones"]


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def reconstruir(observation_id: int, inicio: datetime, fin: datetime) -> dict | None:
    """Trayectoria del pase, vista desde la estacion, y una orbita completa."""
    import orbita_sgp4 as o

    g = geometria()
    meta = g["observaciones"].get(str(observation_id))
    if meta is None:
        return None
    est = g["estaciones"][str(meta["estacion"])]
    l1, l2 = g["tles"][meta["tle"]]
    tle = o.Tle(name="STRAND-1", line1=l1, line2=l2, source="SatNOGS Network")
    obs = o.Observer(lat_deg=est["lat"], lon_deg=est["lng"], alt_m=est["alt_m"] or 0.0)
    inicio, fin = _utc(inicio), _utc(fin)

    puntos = []
    t = inicio - timedelta(seconds=MARGEN_S)
    while t <= fin + timedelta(seconds=MARGEN_S):
        p = o.propagate_point(tle, obs, t, FRECUENCIA_HZ)
        s = o.subsatellite_point(tle, t)
        puntos.append({"t": p.timestamp_utc, "lat": s["lat_deg"], "lon": s["lon_deg"],
                       "alt_km": s["alt_km"], "az": p.azimuth_deg, "el": p.elevation_deg,
                       "dist_km": p.range_km, "doppler_hz": p.doppler_hz,
                       "en_ventana": inicio <= t <= fin})
        t += timedelta(seconds=PASO_S)

    medio = inicio + (fin - inicio) / 2
    orbita = []
    for k in range(0, PERIODO_ORBITA_S + 1, 60):
        s = o.subsatellite_point(tle, medio - timedelta(seconds=PERIODO_ORBITA_S / 2) + timedelta(seconds=k))
        orbita.append({"lat": s["lat_deg"], "lon": s["lon_deg"], "alt_km": s["alt_km"]})

    epoca = o.tle_epoch(tle)
    return {
        "estacion": {"id": meta["estacion"], "nombre": est["nombre"], "lat": est["lat"],
                     "lng": est["lng"], "alt_m": est["alt_m"]},
        "tle": {"linea1": l1, "linea2": l2, "epoca": epoca.isoformat(),
                "antiguedad_dias": round((medio - epoca).total_seconds() / 86400, 2)},
        "azimut_salida": meta.get("azimut_salida"), "azimut_puesta": meta.get("azimut_puesta"),
        "paso_s": PASO_S, "puntos": puntos, "orbita": orbita,
        "elevacion_max_calculada": max(p["el"] for p in puntos),
        "procedencia": {
            "posicion": "ESTIMADO: SGP4 sobre el TLE con que SatNOGS programó este pase",
            "estacion_y_ventana": "REAL: SatNOGS Network",
            "tramas": "REAL: balizas recibidas por la estación en este pase",
        },
        "fuente_geometria": g.get("fuente"),
    }
