#!/usr/bin/env python3
"""Extraccion masiva de telemetria hexadecimal de las observaciones de SatNOGS.

Recorre todas las observaciones de un satelite y, para cada una, obtiene las
tramas de telemetria asociadas, guardando el resultado en CSV o Excel con la
estructura:

    observation_id | frame_number | telemetry_hex

Por que la API y no la pagina HTML
----------------------------------
La peticion original era raspar los elementos `<span class="hex">` de
`network.satnogs.org/observations/{id}/`. Ese camino no sirve, por dos motivos
comprobados:

1. `https://network.satnogs.org/robots.txt` prohibe expresamente `/observations/`,
   que es justo la ruta a recorrer. Es un servicio mantenido por voluntarios y
   pide que los clientes automaticos no lo rastreen.

2. El HTML servido **no contiene ningun `class="hex"`**: el navegador los
   construye con JavaScript despues de descargar los archivos de demoddata. Un
   scraper HTTP no encontraria nada, y uno con navegador completo cargaria mucho
   mas el servicio para obtener exactamente lo mismo.

Este script usa la API publica, que es la via sancionada y entrega el mismo dato:
la observacion lista sus archivos de demoddata y cada archivo contiene los bytes
crudos de una trama. Su representacion hexadecimal es identica a la que la web
muestra en los `<span class="hex">`.

Uso
---
    python extraer_telemetria_satnogs.py --sat-id IFDT-2351-8184-5400-1710
    python extraer_telemetria_satnogs.py --norad 39090 --salida telemetria.xlsx
    python extraer_telemetria_satnogs.py --estados good --max 50

El proceso nunca se detiene por un fallo puntual: los errores de red, las
observaciones inaccesibles y las que no tienen telemetria se registran y se
sigue adelante.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import httpx

API_NETWORK = "https://network.satnogs.org/api"
SIN_TELEMETRIA = "SIN_TELEMETRIA"

logger = logging.getLogger("satnogs")


# ─── Resultado ──────────────────────────────────────────────────────────────

@dataclass
class Trama:
    observation_id: int
    frame_number: int
    telemetry_hex: str
    timestamp: str = ""
    byte_count: int = 0


@dataclass
class Estadisticas:
    observaciones_listadas: int = 0
    observaciones_con_telemetria: int = 0
    observaciones_sin_telemetria: int = 0
    observaciones_con_error: int = 0
    tramas: int = 0
    errores: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        return (
            f"{self.observaciones_listadas} observaciones recorridas · "
            f"{self.observaciones_con_telemetria} con telemetria · "
            f"{self.observaciones_sin_telemetria} sin telemetria · "
            f"{self.observaciones_con_error} con error · "
            f"{self.tramas} tramas extraidas"
        )


# ─── Cliente ────────────────────────────────────────────────────────────────

class ClienteSatnogs:
    """Cliente con reintentos, pausa entre peticiones y respeto al limite de tasa."""

    def __init__(self, token: str = "", pausa: float = 0.5, reintentos: int = 3):
        self.pausa = pausa
        self.reintentos = reintentos
        cabeceras = {
            # Identificarse es buena practica con un servicio comunitario.
            "User-Agent": "strand1-telemetry-extractor/1.0 (proyecto academico)",
        }
        if token:
            cabeceras["Authorization"] = f"Token {token}"
        self.cliente = httpx.Client(timeout=45.0, follow_redirects=True, headers=cabeceras)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cliente.close()

    def _get(self, url: str, params: dict | None = None) -> httpx.Response | None:
        """GET con reintentos. Devuelve None si se agotan sin exito."""
        for intento in range(1, self.reintentos + 1):
            try:
                respuesta = self.cliente.get(url, params=params)
            except httpx.RequestError as exc:
                espera = self.pausa * 2 ** intento
                logger.warning("  red: %s (intento %d/%d, espero %.1fs)",
                               type(exc).__name__, intento, self.reintentos, espera)
                time.sleep(espera)
                continue

            if respuesta.status_code == 429:
                # Limite de tasa: esperar lo que indique el servidor.
                espera = float(respuesta.headers.get("Retry-After", 30))
                logger.warning("  limite de tasa alcanzado, espero %.0fs", espera)
                time.sleep(espera)
                continue

            if respuesta.status_code in (404, 403):
                return respuesta  # el llamante decide

            if respuesta.status_code >= 500:
                espera = self.pausa * 2 ** intento
                logger.warning("  servidor %d (intento %d/%d, espero %.1fs)",
                               respuesta.status_code, intento, self.reintentos, espera)
                time.sleep(espera)
                continue

            return respuesta

        return None

    def listar_observaciones(
        self,
        sat_id: str | None,
        norad: int | None,
        estados: list[str] | None,
        maximo: int,
    ) -> Iterator[dict]:
        """Recorre la paginacion de observaciones del satelite."""
        params: dict = {"format": "json"}
        if sat_id:
            params["sat_id"] = sat_id
        elif norad:
            params["satellite__norad_cat_id"] = norad
        else:
            raise ValueError("Hace falta --sat-id o --norad")

        url: str | None = f"{API_NETWORK}/observations/"
        emitidas = 0
        primera = True

        while url and emitidas < maximo:
            respuesta = self._get(url, params if primera else None)
            primera = False

            if respuesta is None:
                logger.error("No se pudo listar observaciones tras varios intentos.")
                return
            if respuesta.status_code != 200:
                logger.error("Listado devolvio %d: %s",
                             respuesta.status_code, respuesta.text[:160])
                return

            datos = respuesta.json()
            elementos = datos if isinstance(datos, list) else datos.get("results", [])

            # Un error de parametro llega como lista de un solo objeto con
            # la clave `error` y codigo HTTP 200.
            if len(elementos) == 1 and isinstance(elementos[0], dict) and "error" in elementos[0]:
                logger.error("La API rechazo la consulta: %s", elementos[0]["error"])
                return

            for obs in elementos:
                if emitidas >= maximo:
                    return
                if estados and (obs.get("status") or "").lower() not in estados:
                    continue
                yield obs
                emitidas += 1

            # La API devuelve una lista simple y pagina por cursor en la cabecera
            # `Link`. El parametro `page` esta deprecado y responde con un error
            # en el cuerpo, no con un codigo HTTP de fallo.
            siguiente = respuesta.links.get("next", {}).get("url")
            if siguiente and elementos:
                url = siguiente
            elif isinstance(datos, dict) and datos.get("next"):
                url = datos["next"]
            else:
                url = None

            time.sleep(self.pausa)

    def descargar_payload(self, url: str) -> bytes | None:
        """Descarga un archivo de demoddata y devuelve sus bytes."""
        respuesta = self._get(url)
        if respuesta is None or respuesta.status_code != 200:
            return None
        return respuesta.content


# ─── Extraccion ─────────────────────────────────────────────────────────────

def _marca_de_tiempo(url: str) -> str:
    """Extrae la marca de tiempo del nombre del archivo de demoddata.

    Formato: data_<obs>_<YYYY-MM-DDTHH-MM-SS>_g<n>
    """
    nombre = url.rsplit("/", 1)[-1]
    partes = nombre.split("_")
    if len(partes) >= 3 and "T" in partes[2]:
        fecha, _, hora = partes[2].partition("T")
        return f"{fecha}T{hora.replace('-', ':')}Z"
    return ""


def extraer_de_observacion(
    cliente: ClienteSatnogs,
    obs: dict,
    stats: Estadisticas,
) -> list[Trama]:
    """Obtiene todas las tramas hexadecimales de una observacion."""
    obs_id = obs.get("id")
    demoddata = obs.get("demoddata") or []

    if not demoddata:
        stats.observaciones_sin_telemetria += 1
        return [Trama(observation_id=obs_id, frame_number=0, telemetry_hex=SIN_TELEMETRIA)]

    tramas: list[Trama] = []
    for numero, entrada in enumerate(demoddata, start=1):
        url = entrada.get("payload_demod") if isinstance(entrada, dict) else entrada
        if not url:
            continue

        datos = cliente.descargar_payload(url)
        if datos is None:
            stats.errores.append(f"obs {obs_id}: no se pudo descargar {url.rsplit('/', 1)[-1]}")
            continue
        if not datos:
            continue

        tramas.append(Trama(
            observation_id=obs_id,
            frame_number=numero,
            telemetry_hex=datos.hex().upper(),
            timestamp=_marca_de_tiempo(url),
            byte_count=len(datos),
        ))
        time.sleep(cliente.pausa)

    if not tramas:
        stats.observaciones_sin_telemetria += 1
        return [Trama(observation_id=obs_id, frame_number=0, telemetry_hex=SIN_TELEMETRIA)]

    stats.observaciones_con_telemetria += 1
    stats.tramas += len(tramas)
    return tramas


def extraer(
    cliente: ClienteSatnogs,
    sat_id: str | None,
    norad: int | None,
    estados: list[str] | None,
    maximo: int,
    ya_extraidas: set[int],
    escritor: "EscritorIncremental | None" = None,
) -> tuple[list[Trama], Estadisticas]:
    stats = Estadisticas()
    filas: list[Trama] = []

    for obs in cliente.listar_observaciones(sat_id, norad, estados, maximo):
        obs_id = obs.get("id")
        stats.observaciones_listadas += 1

        if obs_id in ya_extraidas:
            logger.info("[%4d] obs %-10s ya extraida, se omite",
                        stats.observaciones_listadas, obs_id)
            continue

        try:
            tramas = extraer_de_observacion(cliente, obs, stats)
        except Exception as exc:  # nunca detener el proceso completo
            stats.observaciones_con_error += 1
            stats.errores.append(f"obs {obs_id}: {type(exc).__name__}: {exc}")
            logger.warning("[%4d] obs %-10s ERROR: %s",
                           stats.observaciones_listadas, obs_id, exc)
            continue

        con_datos = [t for t in tramas if t.telemetry_hex != SIN_TELEMETRIA]
        logger.info(
            "[%4d] obs %-10s %-6s %d trama(s)",
            stats.observaciones_listadas, obs_id,
            (obs.get("status") or "?"), len(con_datos),
        )
        filas.extend(tramas)
        if escritor is not None:
            escritor.escribir(tramas)

    return filas, stats


# ─── Salida ─────────────────────────────────────────────────────────────────

COLUMNAS = ["observation_id", "frame_number", "telemetry_hex", "timestamp", "byte_count"]


def leer_ya_extraidas(ruta: Path) -> set[int]:
    """IDs ya presentes en un CSV previo, para poder reanudar sin repetir."""
    if not ruta.exists() or ruta.suffix.lower() != ".csv":
        return set()
    try:
        with ruta.open(newline="", encoding="utf-8") as f:
            return {int(fila["observation_id"]) for fila in csv.DictReader(f)
                    if fila.get("observation_id", "").isdigit()}
    except Exception:
        return set()


class EscritorIncremental:
    """Vuelca cada observacion al CSV en cuanto se extrae.

    Un barrido completo dura horas; si el proceso muere a mitad, lo ya
    descargado tiene que estar en disco. Ademas asi `--reanudar` puede
    aprovecharlo, que es justo lo que un corte a mitad hace necesario.

    Solo aplica a CSV: el formato Excel se escribe de una vez al final.
    """

    def __init__(self, ruta: Path, anexar: bool):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        nuevo = not (anexar and ruta.exists())
        self.archivo = ruta.open("w" if nuevo else "a", newline="", encoding="utf-8")
        self.escritor = csv.DictWriter(self.archivo, fieldnames=COLUMNAS)
        if nuevo:
            self.escritor.writeheader()
            self.archivo.flush()

    def escribir(self, filas: list[Trama]) -> None:
        for t in filas:
            self.escritor.writerow(vars(t))
        self.archivo.flush()
        os.fsync(self.archivo.fileno())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.archivo.close()


def guardar(filas: list[Trama], ruta: Path, anexar: bool = False) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)

    if ruta.suffix.lower() in (".xlsx", ".xls"):
        try:
            import pandas as pd
        except ImportError:
            raise SystemExit(
                "Para escribir Excel hace falta pandas y openpyxl:\n"
                "  pip install pandas openpyxl"
            )
        df = pd.DataFrame([vars(t) for t in filas], columns=COLUMNAS)
        df.to_excel(ruta, index=False)
        return

    modo = "a" if anexar and ruta.exists() else "w"
    with ruta.open(modo, newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        if modo == "w":
            escritor.writeheader()
        for t in filas:
            escritor.writerow(vars(t))


# ─── CLI ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extrae la telemetria hexadecimal de las observaciones de SatNOGS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Uso\n---")[-1],
    )
    parser.add_argument("--sat-id", default="IFDT-2351-8184-5400-1710",
                        help="Identificador de satelite de SatNOGS (por defecto: STRaND-1)")
    parser.add_argument("--norad", type=int, default=None,
                        help="NORAD ID, alternativa a --sat-id")
    parser.add_argument("--estados", default="",
                        help="Filtrar por estado, separados por comas: good,bad,unknown,failed,future. "
                             "Vacio = todos. Ojo: observaciones 'bad' tambien pueden traer telemetria.")
    parser.add_argument("--max", type=int, default=1000, dest="maximo",
                        help="Maximo de observaciones a recorrer (por defecto 1000)")
    parser.add_argument("--salida", type=Path, default=Path("telemetria_satnogs.csv"),
                        help="Archivo de salida (.csv o .xlsx)")
    parser.add_argument("--pausa", type=float, default=0.5,
                        help="Segundos entre peticiones (por defecto 0.5). No lo bajes sin motivo: "
                             "SatNOGS lo mantienen voluntarios.")
    parser.add_argument("--reanudar", action="store_true",
                        help="Omitir las observaciones ya presentes en el CSV de salida")
    # Este script va contra SatNOGS Network, asi que usa el token de Network. El
    # de DB no vale aqui: son instalaciones distintas con cuentas separadas.
    parser.add_argument("--token",
                        default=os.getenv("SATNOGS_NETWORK_TOKEN")
                                or os.getenv("SATNOGS_API_TOKEN", ""),
                        help="Token de SatNOGS Network (o variable "
                             "SATNOGS_NETWORK_TOKEN, con SATNOGS_API_TOKEN de respaldo)")
    parser.add_argument("-v", "--verboso", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )

    estados = [e.strip().lower() for e in args.estados.split(",") if e.strip()] or None
    ya = leer_ya_extraidas(args.salida) if args.reanudar else set()

    print("=" * 72)
    print("EXTRACCION DE TELEMETRIA · SatNOGS Network")
    print("=" * 72)
    print(f"  Satelite  : {args.sat_id or f'NORAD {args.norad}'}")
    print(f"  Estados   : {', '.join(estados) if estados else 'todos'}")
    print(f"  Maximo    : {args.maximo} observaciones")
    print(f"  Salida    : {args.salida}")
    print(f"  Pausa     : {args.pausa}s entre peticiones")
    if ya:
        print(f"  Reanudar  : {len(ya)} observaciones ya extraidas se omitiran")
    print()

    # El CSV se escribe observacion a observacion; Excel necesita todas las
    # filas en memoria, asi que ese formato se guarda al final.
    incremental = args.salida.suffix.lower() not in (".xlsx", ".xls")

    with ClienteSatnogs(token=args.token, pausa=args.pausa) as cliente:
        if incremental:
            with EscritorIncremental(args.salida, anexar=args.reanudar) as escritor:
                filas, stats = extraer(cliente, args.sat_id, args.norad, estados,
                                       args.maximo, ya, escritor)
        else:
            filas, stats = extraer(cliente, args.sat_id, args.norad, estados,
                                   args.maximo, ya)

    if not filas:
        print("\nNo se obtuvo ninguna fila.")
        if stats.errores:
            print("Errores:")
            for e in stats.errores[:10]:
                print(f"  - {e}")
        return 1

    if not incremental:
        guardar(filas, args.salida, anexar=args.reanudar)

    print()
    print("=" * 72)
    print(stats.resumen())
    print(f"Guardado en: {args.salida.resolve()}")
    if stats.errores:
        print(f"\n{len(stats.errores)} incidencias (el proceso continuo pese a ellas):")
        for e in stats.errores[:10]:
            print(f"  - {e}")
        if len(stats.errores) > 10:
            print(f"  ... y {len(stats.errores) - 10} mas")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
