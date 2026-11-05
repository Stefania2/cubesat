"""Descarga la geometria de las observaciones de STRaND-1 en SatNOGS Network.

Cada observacion de Network guarda el TLE con que se programo el pase y la
posicion de la estacion (latitud, longitud, altura). La tabla `observations`
de la plataforma no los conserva, y sin ellos no se puede reconstruir el
movimiento del satelite durante un pase. Este script los descarga una vez y
los deja en un JSON versionado que lee la ruta `/api/observations/{id}/paso`:

    backend/app/data/geometria_observaciones.json

    {"generado_utc": ..., "fuente": ...,
     "estaciones": {"2859": {"nombre", "lat", "lng", "alt_m"}},
     "tles": [["1 39090U ...", "2 39090 ..."], ...],
     "observaciones": {"6836614": {"estacion": 2859, "tle": 0,
                                   "azimut_salida": 119.0, "azimut_puesta": 358.0}}}

Los TLE se guardan una sola vez y cada observacion apunta a su indice: muchas
observaciones del mismo dia comparten TLE.

Uso (desde telemetria_strand1/):
    ../../strand_api/bin/python tools/descargar_geometria_observaciones.py

La API de lectura es publica, pero sin token limita pronto (una espera de casi
una hora tras unas decenas de paginas). Si `backend/.env` define
SATNOGS_NETWORK_TOKEN se envia; nunca se imprime.

Recorre el listado con cursor (de lo mas reciente a lo mas antiguo), respeta
`Retry-After`, guarda el avance en cada pagina para poder retomarlo y se
detiene al pasar de `DESDE`, la fecha mas antigua de la tabla `observations`.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

NORAD = 39090
URL = "https://network.satnogs.org/api/observations/"
DESDE = "2022-12-01T00:00:00Z"
HASTA = "2026-08-01T00:00:00Z"
SALIDA = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "geometria_observaciones.json"
AVANCE = SALIDA.with_name(".geometria_avance.json")
ENV = Path(__file__).resolve().parents[1] / "backend" / ".env"
PAUSA_S = 1.0


def _token() -> str:
    if not ENV.exists():
        return ""
    for linea in ENV.read_text(encoding="utf-8").splitlines():
        if linea.startswith("SATNOGS_NETWORK_TOKEN="):
            return linea.split("=", 1)[1].strip()
    return ""


def _escribir(estaciones: dict, tles: list, observaciones: dict, completo: bool) -> None:
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": "SatNOGS Network, /api/observations/?norad_cat_id=39090 (campos tle1, tle2, "
                  "station_lat, station_lng, station_alt, rise_azimuth, set_azimuth)",
        "completo": completo,
        "estaciones": estaciones, "tles": tles, "observaciones": observaciones,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    estaciones: dict[str, dict] = {}
    tles: list[list[str]] = []
    observaciones: dict[str, dict] = {}
    url: str | None = None
    paginas = 0
    if AVANCE.exists():
        a = json.loads(AVANCE.read_text(encoding="utf-8"))
        estaciones, tles, observaciones, url, paginas = (
            a["estaciones"], a["tles"], a["observaciones"], a["siguiente"], a["paginas"])
        print(f"Retomo en la pagina {paginas} con {len(observaciones)} observaciones", file=sys.stderr)
    indice_tle = {tuple(t): i for i, t in enumerate(tles)}

    params = {"norad_cat_id": NORAD, "start": DESDE, "end": HASTA, "format": "json"}
    cabeceras = {"User-Agent": "strand1-proyecto-grado (UNAD)"}
    if _token():
        cabeceras["Authorization"] = f"Token {_token()}"
    primera = url is None
    url = url or URL
    with httpx.Client(timeout=60.0, headers=cabeceras) as c:
        while url:
            r = c.get(url, params=params if primera else None)
            if r.status_code == 429:
                espera = float(r.headers.get("Retry-After", 30))
                print(f"Limite de tasa: espero {espera:.0f} s", file=sys.stderr)
                time.sleep(espera)
                continue
            if r.status_code == 401 and "Authorization" in c.headers:
                # Un token no valido para Network hace fallar incluso lo publico.
                print("El token no vale para SatNOGS Network: sigo sin token", file=sys.stderr)
                del c.headers["Authorization"]
                continue
            r.raise_for_status()
            primera = False
            lote = r.json()
            for o in lote:
                if o.get("norad_cat_id") != NORAD or not o.get("tle1") or o.get("station_lat") is None:
                    continue
                est = str(o["ground_station"])
                estaciones.setdefault(est, {"nombre": o.get("station_name"), "lat": o["station_lat"],
                                            "lng": o["station_lng"], "alt_m": o.get("station_alt") or 0})
                clave = (o["tle1"].strip(), o["tle2"].strip())
                if clave not in indice_tle:
                    indice_tle[clave] = len(tles)
                    tles.append(list(clave))
                observaciones[str(o["id"])] = {
                    "estacion": int(est), "tle": indice_tle[clave],
                    "azimut_salida": o.get("rise_azimuth"), "azimut_puesta": o.get("set_azimuth")}
            paginas += 1
            url = r.links.get("next", {}).get("url")
            # El listado va de lo reciente a lo antiguo: pasado DESDE, no queda nada util.
            if lote and min(o["start"] for o in lote) < DESDE:
                url = None
            AVANCE.parent.mkdir(parents=True, exist_ok=True)
            AVANCE.write_text(json.dumps({"estaciones": estaciones, "tles": tles,
                                          "observaciones": observaciones, "siguiente": url,
                                          "paginas": paginas}), encoding="utf-8")
            # El resultado se escribe en cada pagina: si SatNOGS obliga a esperar,
            # lo descargado ya sirve, y la proxima ejecucion retoma desde AVANCE.
            _escribir(estaciones, tles, observaciones, completo=url is None)
            fecha = lote[-1]["start"] if lote else "?"
            print(f"pagina {paginas} (hasta {fecha}): {len(observaciones)} observaciones",
                  file=sys.stderr, flush=True)
            time.sleep(PAUSA_S)

    _escribir(estaciones, tles, observaciones, completo=True)
    AVANCE.unlink(missing_ok=True)
    print(f"{len(observaciones)} observaciones, {len(estaciones)} estaciones, {len(tles)} TLE -> {SALIDA}")


if __name__ == "__main__":
    main()
