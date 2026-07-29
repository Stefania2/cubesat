#!/usr/bin/env python3
"""Entropia por byte de las tramas, contra el techo que impone su longitud.

Respalda las cifras de la seccion 3.3 de `docs/INFORME_TECNICO_FINAL.md`.

El problema que resuelve
------------------------
La entropia medida sobre las tramas de STRaND-1 ronda los 3 bits/byte. Leida
contra los 8 bits/byte de un byte arbitrario parece baja, y esa lectura invita
a concluir que la trama mezcla cabeceras muy repetitivas con datos de sensores
--- la firma que se espera de AX.25.

La comparacion es incorrecta. Una trama de `n` bytes no puede superar `log2(n)`
bits/byte, porque con n simbolos observados la distribucion mas dispersa
posible es la uniforme sobre n valores distintos. Con una longitud media de 14
bytes el techo esta en 3,6 bits/byte, no en 8. Contra ese techo, lo que se mide
esta al 84 %: casi todos los bytes de casi todas las tramas son distintos entre
si, que es la firma de datos comprimidos o cifrados, no de cabeceras fijas.

Por eso el reparto por tramos de longitud importa mas que el promedio global:
el promedio mezcla tramas de 2 bytes (techo 1 bit/byte) con tramas de 100
(techo 6,6), y su valor depende tanto de la mezcla de longitudes como del
contenido.

Fuente de datos
---------------
El conjunto completo --- las 36 641 tramas que respaldan el capitulo 3 --- vive
en la tabla `frames` de PostgreSQL que alimenta la plataforma de telemetria, en
el repositorio hermano `telemetria_strand1`. Este script la consulta; no la
incluye, porque son medio millon de bytes de tramas crudas.

La cadena de conexion se toma de la variable de entorno `DATABASE_URL` o, si no
esta definida, del `.env` de esa plataforma (`--env-file` lo reubica). Aqui no
hay credenciales escritas: este repositorio es publico.

El modo `--csv` permite comprobar el calculo sin base de datos sobre cualquier
exportacion de tramas, pero **no reproduce las cifras del informe**: los CSV
disponibles son exportaciones parciales que suman 34 963 tramas unicas.

La entropia se recalcula desde el hexadecimal crudo en lugar de leer la columna
`entropy_bits_per_byte`, para que el script valide de paso lo que guardo la
ingesta.

Uso
---
    python analizar_entropia.py
    python analizar_entropia.py --csv ../telemetria_strand1/telemetria_satnogs.csv

Requiere `psycopg` para el modo PostgreSQL (no para `--csv`).
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import Counter
from pathlib import Path

# El .env de la plataforma de telemetria, que vive fuera de este repositorio.
ENV_POR_DEFECTO = Path(__file__).resolve().parent.parent / "telemetria_strand1" / "backend" / ".env"

# Tramos de longitud en bytes. El primero aisla las tramas demasiado cortas
# para que la entropia signifique nada; el ultimo, las que superan la baliza.
TRAMOS = ((1, 4), (5, 12), (13, 24), (25, 48), (49, 200))

# Nombres que las distintas exportaciones dan a las mismas dos columnas.
COL_HEX = ("frame", "telemetry_hex", "hex", "raw_hex")
COL_TS = ("timestamp", "fecha", "time")


def entropia(datos: bytes) -> float:
    """Entropia de Shannon de la distribucion de bytes, en bits/byte."""
    n = len(datos)
    return -sum(c / n * math.log2(c / n) for c in Counter(datos).values())


def dsn(env_file: Path) -> str:
    """Cadena de conexion, del entorno o del .env de la plataforma."""
    url = os.environ.get("DATABASE_URL", "")
    if not url and env_file.exists():
        for linea in env_file.read_text(encoding="utf-8").splitlines():
            if linea.startswith("DATABASE_URL="):
                url = linea.split("=", 1)[1].strip()
                break
    if not url:
        raise SystemExit(
            "No hay cadena de conexion. Define DATABASE_URL o pasa --env-file\n"
            f"apuntando al .env de la plataforma (se busco en {env_file})."
        )
    # psycopg no entiende el prefijo de dialecto que usa SQLAlchemy.
    return url.replace("postgresql+psycopg://", "postgresql://")


def desde_postgres(env_file: Path) -> list[str]:
    """Hexadecimal crudo de todas las tramas ingeridas."""
    try:
        import psycopg
    except ModuleNotFoundError:
        raise SystemExit(
            "Falta psycopg para leer de PostgreSQL: pip install psycopg\n"
            "(o usa --csv para comprobar el calculo sobre una exportacion)."
        )
    url = dsn(env_file)
    print(f"Leyendo de PostgreSQL: {url.rsplit('@', 1)[-1]}")
    with psycopg.connect(url) as con:
        filas = [f[0] for f in con.execute("select raw_hex from frames")]
    print(f"  {len(filas)} tramas")
    return filas


def desde_csv(rutas: list[Path]) -> list[str]:
    """Hexadecimal de los CSV, sin repetir tramas."""
    print("Leyendo de CSV (exportacion parcial, ver docstring):")
    vistos: set[tuple[str, str]] = set()
    crudos: list[str] = []
    for ruta in rutas:
        if not ruta.exists():
            print(f"  aviso: {ruta} no existe, se omite")
            continue
        n = 0
        with ruta.open(newline="", encoding="utf-8", errors="replace") as fh:
            lector = csv.DictReader(fh)
            cabecera = lector.fieldnames or []
            col_hex = next((c for c in COL_HEX if c in cabecera), "")
            col_ts = next((c for c in COL_TS if c in cabecera), "")
            if not col_hex or not col_ts:
                raise SystemExit(f"CSV sin columna de trama o de fecha: {cabecera}")
            for fila in lector:
                hexa = (fila.get(col_hex) or "").strip().upper().replace(" ", "")
                ts = (fila.get(col_ts) or "").strip()
                if not hexa or not ts or len(ts) < 7:
                    continue
                if (hexa, ts) in vistos:
                    continue
                vistos.add((hexa, ts))
                crudos.append(hexa)
                n += 1
        print(f"  {ruta.name}: {n} tramas nuevas")
    print(f"  total: {len(crudos)} tramas unicas")
    return crudos


def medir(crudos: list[str]) -> tuple[list[tuple[int, float, float]], int]:
    """Para cada trama: (longitud, entropia medida, techo log2(longitud))."""
    medidas: list[tuple[int, float, float]] = []
    descartadas = 0
    for hexa in crudos:
        try:
            datos = bytes.fromhex((hexa or "").strip())
        except ValueError:
            descartadas += 1
            continue
        if not datos:
            descartadas += 1
            continue
        medidas.append((len(datos), entropia(datos), math.log2(len(datos))))
    return medidas, descartadas


def informe(medidas: list[tuple[int, float, float]], descartadas: int) -> None:
    n = len(medidas)
    total_bytes = sum(long for long, _, _ in medidas)
    media_ent = sum(e for _, e, _ in medidas) / n
    media_techo = sum(t for _, _, t in medidas) / n

    print("\nConjunto analizado:")
    if descartadas:
        print(f"  tramas con hexadecimal ilegible o vacio : {descartadas} (descartadas)")
    print(f"  tramas                                  : {n}")
    print(f"  bytes totales                           : {total_bytes}")
    print(f"  bits evaluados                          : {total_bytes * 8}")
    print(f"  longitud media                          : {total_bytes / n:.2f} bytes")

    print("\nEntropia:")
    print(f"  medida                                  : {media_ent:.3f} bits/byte")
    print(f"  maximo posible para estas longitudes    : {media_techo:.3f} bits/byte")
    print(f"  proporcion del techo                    : {100 * media_ent / media_techo:.1f} %")
    print("  (comparar con 8 bits/byte no tiene sentido: una trama de n bytes")
    print("   no puede superar log2(n))")

    print("\nPor tramos de longitud:")
    print(f"  {'tramo':>12}  {'tramas':>7}  {'medida':>7}  {'techo':>7}  {'% techo':>7}")
    for lo, hi in TRAMOS:
        tramo = [(e, t) for long, e, t in medidas if lo <= long <= hi]
        if not tramo:
            continue
        ent = sum(e for e, _ in tramo) / len(tramo)
        techo = sum(t for _, t in tramo) / len(tramo)
        etiqueta = f"{lo}-{hi}"
        print(f"  {etiqueta:>12}  {len(tramo):7d}  {ent:7.2f}  {techo:7.2f}  {100 * ent / techo:6.1f} %")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", nargs="+", type=Path, metavar="CSV",
                   help="leer de estos CSV en lugar de PostgreSQL (conjunto parcial)")
    p.add_argument("--env-file", type=Path, default=ENV_POR_DEFECTO,
                   help="donde buscar DATABASE_URL si no esta en el entorno")
    args = p.parse_args(argv)

    crudos = desde_csv(args.csv) if args.csv else desde_postgres(args.env_file)
    medidas, descartadas = medir(crudos)
    if not medidas:
        print("No hay tramas legibles que analizar.")
        return 1
    informe(medidas, descartadas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
