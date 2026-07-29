"""Carga de los DataFrames del gemelo digital desde PostgreSQL.

Es la unica capa que habla con la base. Todo lo demas --- reproduccion
temporal, deteccion de anomalias, visualizacion --- consume los DataFrames que
devuelve este modulo, de modo que sustituir la fuente (otro CubeSat, un CSV,
otra base) no obliga a tocar el resto.

Tres tablas, tres granularidades distintas:

  frames         una fila por trama recibida: metadatos de recepcion y calidad
  decoded_fields formato largo, una fila por (trama, campo): las magnitudes
  observations   una fila por pase de una estacion: contexto del enlace

`decoded_fields` esta en formato largo a proposito, y no conviene pivotarlo a
lo ancho sin pensar: una baliza de STRaND-1 transporta **de uno a tres campos**,
nunca el estado completo del satelite. Un pivote crudo produce una matriz casi
toda nula. Ver `estado.py` para la reconstruccion de estado que eso exige.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

# El .env de la plataforma de telemetria, que no se versiona.
ENV_POR_DEFECTO = Path(__file__).resolve().parent.parent / "telemetria_strand1" / "backend" / ".env"

# Campos de `decoded_fields` que son metadatos del protocolo, no magnitudes
# fisicas: numero de secuencia, direccion del nodo I2C y canal. Se excluyen de
# los analisis de comportamiento porque su variacion no dice nada del satelite.
CAMPOS_PROTOCOLO = ("seq_no", "node_channel", "i2c_node_address")


def dsn(env_file: Path = ENV_POR_DEFECTO) -> str:
    """Cadena de conexion, del entorno o del .env de la plataforma."""
    url = os.environ.get("DATABASE_URL", "")
    if not url and env_file.exists():
        for linea in env_file.read_text(encoding="utf-8").splitlines():
            if linea.startswith("DATABASE_URL="):
                url = linea.split("=", 1)[1].strip()
                break
    if not url:
        raise SystemExit(
            "No hay cadena de conexion. Define DATABASE_URL o pasa env_file\n"
            f"apuntando al .env de la plataforma (se busco en {env_file})."
        )
    # Se devuelve en forma SQLAlchemy, con el dialecto explicito. Sin el
    # `+psycopg`, SQLAlchemy asume psycopg2, que no esta instalado.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _leer(sql: str, env_file: Path) -> pd.DataFrame:
    # Via SQLAlchemy y no psycopg a pelo: pandas solo soporta oficialmente lo
    # primero, y con una conexion cruda avisa en cada llamada.
    from sqlalchemy import create_engine, text

    with create_engine(dsn(env_file)).connect() as con:
        return pd.read_sql_query(text(sql), con)


def cargar_frames(env_file: Path = ENV_POR_DEFECTO) -> pd.DataFrame:
    """Una fila por trama recibida, ordenadas en el tiempo."""
    df = _leer(
        """
        select id, timestamp, observation_id, station_id, observer,
               byte_count, entropy_bits_per_byte, distinct_bytes,
               status, frame_type, protocol
        from frames order by timestamp
        """,
        env_file,
    )
    return df.astype({"status": "category", "frame_type": "category", "protocol": "category"})


def cargar_campos(env_file: Path = ENV_POR_DEFECTO, solo_fisicos: bool = True) -> pd.DataFrame:
    """Formato largo: una fila por (trama, campo) con valor numerico.

    Con `solo_fisicos` se excluyen los campos de protocolo y los que no traen
    unidad, que son contadores internos sin significado fisico.
    """
    df = _leer(
        """
        select d.frame_id, d.timestamp, d.field_name, d.value_numeric, d.unit,
               f.observation_id, f.station_id
        from decoded_fields d
        join frames f on f.id = d.frame_id
        where d.value_numeric is not null
        order by d.timestamp
        """,
        env_file,
    )
    if solo_fisicos:
        df = df[~df["field_name"].isin(CAMPOS_PROTOCOLO)]
        df = df[df["unit"].notna() & (df["unit"] != "")]
    return df.astype({"field_name": "category", "unit": "category"})


def cargar_observaciones(env_file: Path = ENV_POR_DEFECTO) -> pd.DataFrame:
    """Una fila por pase observado: contexto del enlace, no telemetria."""
    df = _leer(
        """
        select observation_id, station_id, station_name, observer, status,
               frequency_hz, "start", "end", max_elevation_deg
        from observations order by "start"
        """,
        env_file,
    )
    # El estado vacio significa que SatNOGS no lo publico, no que sea bueno.
    df["status"] = df["status"].replace("", pd.NA).astype("category")
    return df


def serie(campos: pd.DataFrame, nombre: str) -> pd.DataFrame:
    """Serie temporal de un solo campo, indexada por tiempo."""
    s = campos[campos["field_name"] == nombre].copy()
    if s.empty:
        disponibles = sorted(campos["field_name"].unique())
        raise KeyError(f"'{nombre}' no existe. Disponibles: {disponibles}")
    return s.set_index("timestamp").sort_index()
