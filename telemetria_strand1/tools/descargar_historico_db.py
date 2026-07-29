#!/usr/bin/env python3
"""Descarga del historico de telemetria de SatNOGS DB para un satelite.

Por que hace falta, si ya se extrae telemetria de Network
--------------------------------------------------------
`extraer_telemetria_satnogs.py` recorre las **observaciones** de SatNOGS
Network, y Network solo conserva observaciones recientes: para STRaND-1 eso
son unos meses de 2022-2023. SatNOGS **DB** es la otra instalacion, la que
archiva las tramas demoduladas desde que existe el proyecto, y ahi si esta la
decada anterior.

La diferencia importa para el diagnostico de salud. En las balizas de 2022 los
convertidores analogico-digitales del subsistema de energia devuelven cero en
todas las lecturas; en las de 2016 a 2020 devuelven cuentas que varian de una
baliza a otra (el voltaje de bateria recorre 226-364, las corrientes de panel
121-976). Sin el historico no se puede distinguir «el satelite nunca instrumento
esos canales» de «los instrumento y dejo de hacerlo», que es la conclusion que
el informe necesita sostener con fechas.

Lo que decide no es una trama suelta sino la **dispersion sobre una muestra**:
una cuenta aislada de 1023 —el tope de escala de un convertidor de 10 bits— es
tan compatible con un canal sano como con uno enrielado, y de hecho
`adc7_mx_array_current` esta clavado en 1023 desde 2016. Por eso el muestreo
busca varias lecturas por canal y mes, no ejemplares individuales.

Como pagina la API
------------------
El endpoint `/api/telemetry/` devuelve 25 elementos por pagina y usa paginacion
por cursor, con el enlace siguiente en la cabecera `Link`. El recorrido va de
mas reciente a mas antiguo, y admite acotar por fecha con `start` y `end`. El
cursor conserva esos filtros, asi que acotar la primera peticion acota el
recorrido entero.

Aplica limite de tasa de forma constante: responde 429 con `Retry-After` y hay
que esperar lo que pida. El script lo respeta, escribe cada pagina a disco y
puede reanudarse, porque una descarga de este tamano tarda horas y no conviene
que un corte obligue a empezar de nuevo.

Uso
---
    # Todo lo anterior a la cobertura de Network
    python descargar_historico_db.py --fin 2022-11-16 --salida historico.csv

    # Un ano concreto
    python descargar_historico_db.py --inicio 2018-01-01 --fin 2019-01-01

    # Reanudar una descarga interrumpida (continua desde la trama mas antigua)
    python descargar_historico_db.py --fin 2022-11-16 --reanudar

El token se lee de `SATNOGS_DB_TOKEN`, del entorno o de `backend/.env`. Es el
token de db.satnogs.org: el de Network no vale aqui, y uno invalido es peor que
ninguno porque DB responde 401 a la peticion entera.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path

import httpx

API_DB = "https://db.satnogs.org/api/telemetry/"
SAT_ID_STRAND1 = "IFDT-2351-8184-5400-1710"
CAMPOS = ["timestamp", "observer", "observation_id", "station_id", "frame"]

logger = logging.getLogger("historico")


def leer_token() -> str:
    """Token de DB, del entorno o de `backend/.env`."""
    tok = os.environ.get("SATNOGS_DB_TOKEN", "").strip()
    if tok:
        return tok
    env = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if linea.startswith("SATNOGS_DB_TOKEN="):
                return linea.split("=", 1)[1].strip()
    return ""


def iso(fecha: str) -> str:
    """Normaliza `2018-01-01` a la forma que espera la API."""
    return fecha if "T" in fecha else f"{fecha}T00:00:00Z"


def claves_existentes(salida: Path) -> tuple[set[tuple[str, str]], str | None]:
    """Lee un CSV previo y devuelve sus claves y la marca de tiempo mas antigua.

    Sirve para reanudar: las claves evitan reescribir tramas ya guardadas y la
    marca mas antigua indica desde donde seguir pidiendo.
    """
    if not salida.exists() or salida.stat().st_size == 0:
        return set(), None
    vistos: set[tuple[str, str]] = set()
    mas_antigua: str | None = None
    with salida.open(newline="", encoding="utf-8") as fh:
        for fila in csv.DictReader(fh):
            ts = fila.get("timestamp") or ""
            vistos.add((fila.get("frame", ""), ts))
            if ts and (mas_antigua is None or ts < mas_antigua):
                mas_antigua = ts
    return vistos, mas_antigua


def descargar(
    salida: Path,
    sat_id: str,
    token: str,
    inicio: str | None,
    fin: str | None,
    reanudar: bool,
    espera_min: float = 0.5,
) -> int:
    """Recorre el historico y lo escribe en CSV. Devuelve las tramas nuevas."""
    vistos: set[tuple[str, str]] = set()
    if reanudar:
        vistos, mas_antigua = claves_existentes(salida)
        if mas_antigua:
            # El recorrido va hacia atras: se retoma en la mas antigua guardada.
            fin = mas_antigua
            logger.info("Reanudando: %d tramas ya en disco, sigo desde %s",
                        len(vistos), mas_antigua)

    cabeceras = {"User-Agent": "strand1-telemetry/1.0 (proyecto academico)"}
    if token:
        cabeceras["Authorization"] = f"Token {token}"
    cli = httpx.Client(timeout=90, follow_redirects=True, headers=cabeceras)

    params: dict[str, str] = {"format": "json", "sat_id": sat_id}
    if inicio:
        params["start"] = iso(inicio)
    if fin:
        params["end"] = iso(fin)

    nuevo = not salida.exists() or salida.stat().st_size == 0 or not reanudar
    modo = "w" if nuevo else "a"
    pagina: str | None = API_DB
    primera = True
    nuevas = balizas = limites = 0
    ultima_ts = ""

    with salida.open(modo, newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        if nuevo:
            w.writeheader()
        while pagina:
            try:
                r = cli.get(pagina, params=params if primera else None)
            except Exception as exc:
                logger.warning("Red: %s - espero 10 s", type(exc).__name__)
                time.sleep(10)
                continue

            if r.status_code == 429:
                espera = float(r.headers.get("Retry-After", 60))
                limites += 1
                logger.debug("Limite de tasa, espero %.0f s", espera)
                time.sleep(espera)
                continue
            if r.status_code != 200:
                logger.error("HTTP %s: %s", r.status_code, r.text[:200])
                break
            # Solo tras una respuesta valida: si se marca antes, un reintento
            # por limite de tasa repetiria la peticion sin `sat_id`.
            primera = False

            elementos = r.json()
            if isinstance(elementos, dict):
                elementos = elementos.get("results", [])
            if not elementos:
                logger.info("Fin del archivo: la API no devuelve mas tramas")
                break

            for e in elementos:
                trama = (e.get("frame") or "").upper()
                ts = e.get("timestamp") or ""
                if not trama or (trama, ts) in vistos:
                    continue
                vistos.add((trama, ts))
                w.writerow({
                    "timestamp": ts,
                    "observer": e.get("observer"),
                    "observation_id": e.get("observation_id"),
                    "station_id": e.get("station_id"),
                    "frame": trama,
                })
                nuevas += 1
                # Las balizas de STRaND-1 empiezan por el flag HDLC C0 80. Se
                # cuentan aparte porque son las unicas tramas decodificables.
                if trama.startswith("C080"):
                    balizas += 1
                ultima_ts = ts
            fh.flush()

            if nuevas and nuevas % 500 < 25:
                logger.info("%d tramas (%d balizas) · voy por %s · %d limites de tasa",
                            nuevas, balizas, ultima_ts, limites)

            pagina = (r.links.get("next") or {}).get("url")
            if not pagina and isinstance(r.json(), dict):
                pagina = r.json().get("next")
            time.sleep(espera_min)

    logger.info("TOTAL: %d tramas nuevas, %d balizas C080, hasta %s",
                nuevas, balizas, ultima_ts or "(nada)")
    return nuevas


def meses(inicio: str, fin: str, cada: int = 1) -> list[tuple[str, str, str]]:
    """Ventanas mensuales de `fin` a `inicio`, de la mas reciente a la mas antigua.

    `cada` permite barrer de forma gruesa antes de afinar: `cada=12` toma un mes
    por ano, que basta para acotar en que ano dejo de medir un canal; una pasada
    posterior con `cada=1` rellena la resolucion sin volver a pedir lo ya
    descargado, porque la salida se acumula y se deduplica.

    Devuelve `(etiqueta, inicio_iso, fin_iso)`.
    """
    from datetime import date

    a0, m0 = int(inicio[:4]), int(inicio[5:7])
    a1, m1 = int(fin[:4]), int(fin[5:7])
    salida = []
    a, m = a1, m1
    paso = 0
    while (a, m) >= (a0, m0):
        if paso % cada:
            paso += 1
            a, m = a - (m == 1), 12 if m == 1 else m - 1
            continue
        paso += 1
        ini = date(a, m, 1)
        sig = date(a + (m == 12), 1 if m == 12 else m + 1, 1)
        salida.append((f"{a:04d}-{m:02d}",
                       f"{ini.isoformat()}T00:00:00Z",
                       f"{sig.isoformat()}T00:00:00Z"))
        a, m = a - (m == 1), 12 if m == 1 else m - 1
    return salida


def muestrear_por_mes(
    salida: Path,
    sat_id: str,
    token: str,
    inicio: str,
    fin: str,
    max_por_mes: int,
    cada: int = 1,
) -> int:
    """Descarga hasta `max_por_mes` tramas de cada mes del intervalo.

    Recorrer el archivo entero trama a trama son dias de descarga por el limite
    de tasa. Para fechar cuando dejo de dar lectura cada canal no hace falta el
    archivo completo: basta una muestra de cada mes, que da resolucion mensual
    sobre diez anos a un coste manejable.

    La muestra de cada mes son sus ultimas `max_por_mes` tramas, porque la API
    recorre de mas reciente a mas antiguo. Es una regla fija, igual para todos
    los meses, de modo que las series resultantes son comparables entre si.
    """
    vistos, _ = claves_existentes(salida)
    nuevo = not salida.exists() or salida.stat().st_size == 0
    cabeceras = {"User-Agent": "strand1-telemetry/1.0 (proyecto academico)"}
    if token:
        cabeceras["Authorization"] = f"Token {token}"
    cli = httpx.Client(timeout=90, follow_redirects=True, headers=cabeceras)

    ventanas = meses(inicio, fin, cada)
    logger.info("Muestreo mensual: %d meses de %s a %s, hasta %d tramas por mes",
                len(ventanas), inicio, fin, max_por_mes)

    total = balizas_total = 0
    with salida.open("w" if nuevo else "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        if nuevo:
            w.writeheader()
        for etiqueta, ini, fin_mes in ventanas:
            params: dict[str, str] = {"format": "json", "sat_id": sat_id,
                                      "start": ini, "end": fin_mes}
            pagina: str | None = API_DB
            primera = True
            n = balizas = 0
            # El presupuesto cuenta tramas *recorridas*, no solo las nuevas: si
            # solo contara las nuevas, un mes ya descargado se paginaria entero
            # sin avanzar nunca, que es justo lo que hace lenta una pasada de
            # refinamiento sobre material ya bajado.
            recorridas = 0
            while pagina and recorridas < max_por_mes:
                try:
                    r = cli.get(pagina, params=params if primera else None)
                except Exception as exc:
                    logger.warning("Red: %s - espero 10 s", type(exc).__name__)
                    time.sleep(10)
                    continue
                if r.status_code == 429:
                    time.sleep(float(r.headers.get("Retry-After", 60)))
                    continue
                if r.status_code != 200:
                    logger.error("%s: HTTP %s %s", etiqueta, r.status_code, r.text[:120])
                    break
                # Ver la nota en `descargar`: marcarlo antes rompe el reintento.
                primera = False

                cuerpo = r.json()
                elementos = cuerpo.get("results", []) if isinstance(cuerpo, dict) else cuerpo
                if not elementos:
                    break
                for e in elementos:
                    trama = (e.get("frame") or "").upper()
                    ts = e.get("timestamp") or ""
                    recorridas += 1
                    if not trama or (trama, ts) in vistos:
                        continue
                    vistos.add((trama, ts))
                    w.writerow({"timestamp": ts, "observer": e.get("observer"),
                                "observation_id": e.get("observation_id"),
                                "station_id": e.get("station_id"), "frame": trama})
                    n += 1
                    if trama.startswith("C080"):
                        balizas += 1
                fh.flush()
                # El enlace siguiente va en la cabecera Link; algunas respuestas
                # lo traen ademas en el cuerpo.
                pagina = (r.links.get("next") or {}).get("url")
                if not pagina and isinstance(cuerpo, dict):
                    pagina = cuerpo.get("next")
                time.sleep(0.5)

            total += n
            balizas_total += balizas
            logger.info("%s: %3d tramas nuevas, %3d balizas  (acumulado %d/%d)",
                        etiqueta, n, balizas, balizas_total, total)

    logger.info("TOTAL muestreo: %d tramas, %d balizas C080", total, balizas_total)
    return total


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sat-id", default=SAT_ID_STRAND1, help="sat_id de SatNOGS DB")
    p.add_argument("--inicio", help="fecha mas antigua a pedir (AAAA-MM-DD)")
    p.add_argument("--fin", help="fecha mas reciente a pedir (AAAA-MM-DD)")
    p.add_argument("--salida", default="telemetria_db_historico.csv", type=Path)
    p.add_argument("--reanudar", action="store_true",
                   help="continuar una descarga previa en lugar de reescribirla")
    p.add_argument("--muestreo-mensual", action="store_true",
                   help="en vez del archivo completo, tomar una muestra de cada mes")
    p.add_argument("--max-por-mes", type=int, default=200,
                   help="tramas por mes en el muestreo (por defecto 200)")
    p.add_argument("--cada", type=int, default=1,
                   help="muestrear uno de cada N meses (12 = un mes por ano)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="registrar tambien las esperas por limite de tasa")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    # httpx registra cada peticion en INFO; en una descarga de horas eso son
    # decenas de miles de lineas que tapan el progreso.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    token = leer_token()
    if not token:
        logger.warning("Sin SATNOGS_DB_TOKEN: la API limitara mucho mas la tasa")

    if args.muestreo_mensual:
        if not (args.inicio and args.fin):
            p.error("--muestreo-mensual exige --inicio y --fin")
        muestrear_por_mes(args.salida, args.sat_id, token,
                          args.inicio, args.fin, args.max_por_mes, args.cada)
    else:
        descargar(args.salida, args.sat_id, token, args.inicio, args.fin, args.reanudar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
