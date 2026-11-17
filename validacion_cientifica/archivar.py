"""Adquisicion: sella una copia de la base en `validacion_cientifica/archivo/`.

    ../strand_api/bin/python -m validacion_cientifica.archivar            # crea o renueva el sello
    ../strand_api/bin/python -m validacion_cientifica.archivar --comparar # solo compara base y archivo

Lee PostgreSQL a traves de `gemelo_digital.datos.dsn()` (la unica capa que
conoce la cadena de conexion; aqui nunca se imprime). Escribe los cuatro
ficheros de `procedencia.FICHEROS` y `sello.json` con sus huellas.

Renovar el sello sobre un archivo existente se niega si el contenido cambia,
salvo con --forzar: un sello que se reescribe en silencio no sella nada.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validacion_cientifica import estados as E  # noqa: E402
from validacion_cientifica import procedencia as P  # noqa: E402
from validacion_cientifica.tiempo import iso  # noqa: E402

# (tabla, columnas, clave de orden). Se lee por paginas de clave creciente:
# una sola consulta larga a traves del pooler de Neon llego a quedarse colgada
# 27 minutos sin devolver nada.
CONSULTAS = {
    "tramas_originales": ("frames", "id, timestamp, raw_hex, norad_id, sat_id, observer, station_id, "
                          "observation_id, app_source, transmitter, version, ingested_at", "id"),
    "observaciones": ("observations", 'observation_id, norad_id, satellite_name, station_id, station_name, '
                      'station_owner, observer, status, frequency_hz, mode, transmitter, "start", "end", '
                      'max_elevation_deg, source, fetched_at', "observation_id"),
    "tramas_clasificacion": ("frames", "id, byte_count, entropy_bits_per_byte, printable_ratio, "
                             "distinct_bytes, status, frame_type, protocol", "id"),
    "campos_decodificados": ("decoded_fields", "id, frame_id, protocol_name, field_name, value_numeric, "
                             "value_text, unit, timestamp", "id"),
}
PAGINA = 10_000
REINTENTOS = 4

# Columnas de fecha: se escriben siempre en la forma de `tiempo.iso`.
FECHAS = {"timestamp", "ingested_at", "start", "end", "fetched_at"}


def _normalizar(fila: dict) -> dict:
    out = {}
    for k, v in fila.items():
        if k in FECHAS:
            out[k] = iso(v)
        elif isinstance(v, Decimal):
            # Solo las columnas NUMERIC llegan como Decimal. Los enteros se
            # dejan como int: convertirlos a float cambiaria su representacion.
            out[k] = float(v)
        else:
            out[k] = v
    return out


def origen_base() -> str:
    """Que base se lee, sin credenciales ni nombre de servidor."""
    from sqlalchemy.engine import make_url

    from gemelo_digital import datos

    host = make_url(datos.dsn()).host or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        return "PostgreSQL local (copia de trabajo)"
    if host.endswith("neon.tech"):
        return "PostgreSQL en Neon (base desplegada)"
    return "PostgreSQL remoto"


def filas_de_base(nombre: str):
    import time

    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DBAPIError

    from gemelo_digital import datos

    tabla, columnas, clave = CONSULTAS[nombre]
    sql = text(f"select {columnas} from {tabla} where {clave} > :ultimo order by {clave} limit {PAGINA}")
    motor = create_engine(datos.dsn(), pool_pre_ping=True,
                          connect_args={"connect_timeout": 30})
    ultimo = -1
    while True:
        for intento in range(REINTENTOS):
            try:
                with motor.connect() as con:
                    filas = con.execute(sql, {"ultimo": ultimo}).mappings().all()
                break
            except DBAPIError:
                if intento == REINTENTOS - 1:
                    raise
                time.sleep(5 * (intento + 1))
        if not filas:
            return
        for fila in filas:
            yield _normalizar(dict(fila))
        ultimo = filas[-1][clave]


def _filas(nombre: str):
    if nombre == "catalogo_tle":
        from validacion_cientifica import orbital as O

        return O.filas_catalogo(O.catalogo_vivo())
    return filas_de_base(nombre)


def comparar_con_base() -> list[E.Resultado]:
    """Recalcula la huella de cada tabla en la base y la compara con el sello."""
    sello = P.leer_sello()
    if sello is None:
        return [E.no_disponible("PROV-BD", "procedencia", "Base frente a archivo",
                                "No hay sello con el que comparar.")]
    fuera = []
    for nombre in P.FICHEROS:
        if nombre not in CONSULTAS:
            continue
        huella, n, _ = P.huella_filas(filas_de_base(nombre))
        meta = sello["ficheros"][nombre]
        ok = huella == meta["sha256_contenido"]
        fuera.append(E.ejecutado(
            f"PROV-BD-{nombre}", "procedencia", f"{origen_base()} = archivo sellado · {nombre}", ok,
            esperado={"sha256": meta["sha256_contenido"], "filas": meta["filas"]},
            obtenido={"sha256": huella, "filas": n}, tolerancia="igualdad exacta",
            detalle="La tabla de la base coincide fila a fila con el archivo." if ok else
                    "La tabla de la base ha cambiado desde el sello: las reconstrucciones del "
                    "archivo siguen siendo reproducibles, pero ya no representan la base actual.",
            referencia="FIPS 180-4 (SHA-256)"))
    return fuera


def sellar(forzar: bool = False) -> dict:
    P.DIR_ARCHIVO.mkdir(parents=True, exist_ok=True)
    previo = P.leer_sello()
    ficheros = {}
    for nombre, capa in P.FICHEROS.items():
        huella, n, contenido = P.huella_filas(_filas(nombre))
        if previo and not forzar:
            antes = previo["ficheros"].get(nombre, {}).get("sha256_contenido")
            if antes and antes != huella:
                raise SystemExit(f"{nombre}: el contenido de la base difiere del sello vigente. "
                                 "Use --forzar para sellar una version nueva.")
        gz = P.comprimir_determinista(contenido)
        ruta = P.DIR_ARCHIVO / f"{nombre}.jsonl.gz"
        ruta.write_bytes(gz)
        ficheros[nombre] = {"capa": capa, "filas": n, "sha256_contenido": huella,
                            "sha256_gz": P.sha256(gz), "bytes_gz": len(gz),
                            "bytes_contenido": len(contenido)}
        print(f"{nombre:24s} {n:7d} filas  {len(gz)/1e6:6.2f} MB  {huella[:16]}…")
    sello = {
        "mision": "STRaND-1", "norad_id": 39090,
        "sellado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "origen": f"{origen_base()} · tablas frames, observations, decoded_fields; catálogo de TLE "
                  "de backend/app/data/geometria_observaciones.json y tle/",
        "origen_de_los_datos": "Red SatNOGS (DB y Network); decodificación AMSAT-UK en la plataforma",
        "formato": "JSON Lines, UTF-8, claves ordenadas, sin espacios; fechas UTC ISO 8601 con "
                   "microsegundos; null = dato ausente. gzip sin fecha ni nombre.",
        "huella": "SHA-256 del contenido sin comprimir (sha256_contenido) y del .gz (sha256_gz)",
        "ficheros": ficheros,
        "versiones_al_sellar": P.versiones(),
    }
    P.SELLO.write_text(json.dumps(sello, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sello


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--comparar", action="store_true", help="solo comparar la base con el sello")
    ap.add_argument("--forzar", action="store_true", help="sellar aunque el contenido haya cambiado")
    args = ap.parse_args()
    if args.comparar:
        resultados = comparar_con_base()
        for r in resultados:
            print(f"{r.estado:13s} {r.nombre}")
        # Se registra con fecha y por base: la API la muestra como la ultima
        # comparacion ejecutada, porque en Vercel no cabe repetirla.
        previo = P.ultima_comparacion_base() or {}
        previo = {k: v for k, v in previo.items() if isinstance(v, dict) and "resultados" in v}
        previo[origen_base()] = {"ejecutado_utc": E.ahora_utc(), "resultados": [r.dict() for r in resultados]}
        P.COMPARACION_BASE.parent.mkdir(parents=True, exist_ok=True)
        P.COMPARACION_BASE.write_text(json.dumps(previo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    sellar(args.forzar)


if __name__ == "__main__":
    main()
