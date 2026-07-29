"""Cliente de las APIs publicas de SatNOGS.

Se usan dos servicios distintos:
  - SatNOGS DB (`db.satnogs.org/api/telemetry`): frames de telemetria crudos.
  - SatNOGS Network (`network.satnogs.org/api/observations`): metadatos de las
    observaciones (estacion, elevacion maxima, ventana temporal).

El endpoint de telemetria no devuelve metadatos de observacion, de ahi que haga
falta la segunda llamada para poblar la seccion de observaciones.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class SatnogsError(RuntimeError):
    """Fallo al consultar la API de SatNOGS."""


class SatnogsThrottled(SatnogsError):
    """SatNOGS esta limitando las peticiones (HTTP 429)."""

    def __init__(self, espera_s: float | None = None):
        self.espera_s = espera_s
        detalle = f" Reintenta en {espera_s:.0f} s." if espera_s else " Reintenta en unos minutos."
        super().__init__("SatNOGS esta limitando las peticiones (429)." + detalle)


# Segundos entre peticiones consecutivas. SatNOGS lo mantienen voluntarios y
# completar cientos de observaciones supone una peticion por cada una.
PAUSA_ENTRE_PETICIONES = 0.5


def _headers(servicio: str) -> dict[str, str]:
    """Cabeceras para `db` o `network`, cada uno con su propio token.

    Nunca se envia el token de un servicio al otro. Mandar a SatNOGS DB un token
    que no es suyo es peor que no mandar ninguno: responde 401 a la peticion
    entera, incluidos los endpoints publicos que sin token si contestan.
    """
    token = settings.token_db if servicio == "db" else settings.token_network
    return {"Authorization": f"Token {token}"} if token else {}


def _parse_timestamp(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def _paginar(
    client: httpx.Client, url: str, params: dict, limite: int, servicio: str = "network"
) -> Iterator[dict]:
    """Recorre las paginas de la API hasta alcanzar `limite` elementos."""
    obtenidos = 0
    siguiente: str | None = url
    primera = True

    while siguiente and obtenidos < limite:
        respuesta = client.get(
            siguiente, params=params if primera else None, headers=_headers(servicio)
        )
        primera = False
        if respuesta.status_code == 401:
            raise SatnogsError(
                "SatNOGS devolvio 401. Configura SATNOGS_API_TOKEN en el archivo .env"
            )
        if respuesta.status_code != 200:
            raise SatnogsError(
                f"SatNOGS devolvio {respuesta.status_code}: {respuesta.text[:200]}"
            )

        datos = respuesta.json()
        elementos = datos if isinstance(datos, list) else datos.get("results", [])
        for elemento in elementos:
            if obtenidos >= limite:
                return
            yield elemento
            obtenidos += 1

        siguiente = None if isinstance(datos, list) else datos.get("next")


def fetch_telemetry(norad_id: int | None = None, limite: int = 100) -> list[dict[str, Any]]:
    """Descarga frames de telemetria crudos de SatNOGS DB."""
    norad_id = norad_id or settings.norad_id
    url = f"{settings.satnogs_db_url}/telemetry/"
    params = {"satellite": norad_id, "format": "json"}

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        crudos = list(_paginar(client, url, params, limite, servicio="db"))

    frames = []
    for item in crudos:
        raw = item.get("frame") or ""
        if not raw:
            continue
        frames.append({
            "raw_hex": raw.upper(),
            "norad_id": item.get("norad_cat_id") or norad_id,
            "sat_id": item.get("sat_id"),
            "observer": item.get("observer"),
            "timestamp": _parse_timestamp(item.get("timestamp")),
            "app_source": item.get("app_source"),
            "transmitter": item.get("transmitter"),
            "version": item.get("version"),
            "station_id": item.get("station_id"),
            "observation_id": item.get("observation_id"),
        })
    logger.info("SatNOGS DB: %d frames descargados para NORAD %s", len(frames), norad_id)
    return frames


def _limpiar_nombre_tle(tle0: str | None) -> str:
    """El campo tle0 puede venir con el marcador de linea 0 ('0 STRAND 1')."""
    nombre = (tle0 or "").strip()
    if nombre.startswith("0 "):
        nombre = nombre[2:].strip()
    return nombre or settings.satellite_name


def _mapear_observacion(item: dict, norad_id: int) -> dict[str, Any]:
    """Traduce una observacion de la API al modelo interno.

    `observation_frequency` es la frecuencia realmente sintonizada por la
    estacion; `transmitter_downlink_low` es la nominal del transmisor. Se
    prefiere la primera y se cae a la segunda.
    """
    return {
        "observation_id": item.get("id"),
        "norad_id": item.get("norad_cat_id") or norad_id,
        "satellite_name": _limpiar_nombre_tle(item.get("tle0")),
        "station_id": item.get("ground_station"),
        "station_name": item.get("station_name"),
        # SatNOGS no expone un propietario aparte: `observer` es el usuario
        # dueño de la estacion terrena.
        "station_owner": item.get("observer"),
        "observer": item.get("observer"),
        "status": item.get("status"),
        "frequency_hz": item.get("observation_frequency") or item.get("transmitter_downlink_low"),
        "mode": item.get("transmitter_mode"),
        "transmitter": item.get("transmitter_description"),
        "start": _parse_timestamp(item.get("start")),
        "end": _parse_timestamp(item.get("end")),
        "max_elevation_deg": item.get("max_altitude"),
        "source": "satnogs-network",
        "fetched_at": datetime.now(timezone.utc),
    }


def fetch_observation(client: httpx.Client, observation_id: int) -> dict[str, Any] | None:
    """Descarga una observacion concreta por su identificador."""
    url = f"{settings.satnogs_network_url}/observations/{observation_id}/"
    respuesta = client.get(url, params={"format": "json"}, headers=_headers("network"))

    if respuesta.status_code == 404:
        return None
    if respuesta.status_code == 429:
        espera = respuesta.headers.get("Retry-After")
        raise SatnogsThrottled(float(espera) if espera else None)
    if respuesta.status_code != 200:
        raise SatnogsError(f"SatNOGS devolvio {respuesta.status_code} para la observacion {observation_id}")

    return _mapear_observacion(respuesta.json(), settings.norad_id)


def fetch_observations_by_ids(ids: list[int]) -> list[dict[str, Any]]:
    """Descarga metadatos de un conjunto concreto de observaciones.

    Es la via correcta para completar las observaciones que referencian nuestros
    frames: el listado general devuelve las mas recientes, que no tienen por que
    solaparse con los frames almacenados (de hecho, con este conjunto no lo hacen).

    Es una peticion por observacion, asi que se espacian y un 429 no invalida el
    trabajo ya hecho: se devuelve lo obtenido hasta ese punto para que el llamante
    lo persista. Como las observaciones ya completadas dejan de estar pendientes,
    reejecutar la sincronizacion continua donde se corto.
    """
    encontradas: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for numero, obs_id in enumerate(ids):
            try:
                datos = fetch_observation(client, obs_id)
            except SatnogsThrottled as exc:
                logger.warning(
                    "SatNOGS Network: limite de tasa tras %d observaciones. %s",
                    len(encontradas), exc,
                )
                break
            if datos is not None:
                encontradas.append(datos)
            if numero + 1 < len(ids):
                time.sleep(PAUSA_ENTRE_PETICIONES)

    logger.info("SatNOGS Network: %d de %d observaciones resueltas por ID", len(encontradas), len(ids))
    return encontradas


def fetch_observations(
    norad_id: int | None = None,
    sat_id: str | None = None,
    limite: int = 100,
) -> list[dict[str, Any]]:
    """Descarga el listado de observaciones mas recientes del satelite."""
    norad_id = norad_id or settings.norad_id
    url = f"{settings.satnogs_network_url}/observations/"
    # El filtro por sat_id devuelve mas resultados que el de NORAD; se usa
    # cuando se conoce, y se cae al NORAD en caso contrario.
    params: dict[str, Any] = {"format": "json"}
    if sat_id:
        params["sat_id"] = sat_id
    else:
        params["satellite__norad_cat_id"] = norad_id

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        crudos = list(_paginar(client, url, params, limite))

    observaciones = [_mapear_observacion(item, norad_id) for item in crudos]
    logger.info("SatNOGS Network: %d observaciones recientes descargadas", len(observaciones))
    return observaciones
