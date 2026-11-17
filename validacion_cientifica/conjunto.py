"""El archivo sellado cargado en DataFrames, con la misma forma que usa el gemelo.

`campos_gemelo()` reproduce `gemelo_digital.datos.cargar_campos()` (misma
consulta, mismos filtros) pero leyendo del archivo, de modo que
`gemelo_digital.estado.reconstruir` y `gemelo_digital.anomalias.clasificar`
corren SIN base de datos y SIN SatNOGS. Es lo que hace reproducible una
reconstruccion: las entradas estan selladas en el repositorio.

Diferencia deliberada con la consulta de la base: alli el orden es solo
`order by d.timestamp`, y PostgreSQL no garantiza el orden entre empates (dos
estaciones que reciben la misma baliza). Aqui se desempata por `id` del campo
decodificado, que es estable. `sincronizacion.empates_ambiguos` mide si esos
empates pueden cambiar algun valor.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from . import procedencia as P

CAMPOS_PROTOCOLO = ("seq_no", "node_channel", "i2c_node_address")


def _fechas(df: pd.DataFrame, columnas: tuple[str, ...]) -> pd.DataFrame:
    for c in columnas:
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True, format="ISO8601")
    return df


@lru_cache(maxsize=1)
def tramas() -> pd.DataFrame:
    df = pd.DataFrame(P.cargar("tramas_originales"))
    return _fechas(df, ("timestamp", "ingested_at")).set_index("id", drop=False).rename_axis(None).sort_index()


@lru_cache(maxsize=1)
def clasificacion() -> pd.DataFrame:
    return pd.DataFrame(P.cargar("tramas_clasificacion")).set_index("id", drop=False).rename_axis(None).sort_index()


@lru_cache(maxsize=1)
def decodificados() -> pd.DataFrame:
    df = pd.DataFrame(P.cargar("campos_decodificados"))
    return _fechas(df, ("timestamp",)).sort_values("id", kind="stable").reset_index(drop=True)


@lru_cache(maxsize=1)
def observaciones() -> pd.DataFrame:
    return _fechas(pd.DataFrame(P.cargar("observaciones")), ("start", "end", "fetched_at"))


@lru_cache(maxsize=1)
def campos_gemelo() -> pd.DataFrame:
    """Equivalente de `datos.cargar_campos(solo_fisicos=True)` sobre el archivo."""
    d = decodificados()
    d = d[d["value_numeric"].notna()]
    t = tramas()[["id", "observation_id", "station_id"]].rename(columns={"id": "frame_id"})
    df = d.merge(t, on="frame_id", how="inner")
    df = df.sort_values(["timestamp", "id"], kind="stable")
    df = df[~df["field_name"].isin(CAMPOS_PROTOCOLO)]
    df = df[df["unit"].notna() & (df["unit"] != "")]
    df = df[["frame_id", "timestamp", "field_name", "value_numeric", "unit",
             "observation_id", "station_id", "id"]].rename(columns={"id": "campo_id"})
    return df.reset_index(drop=True).astype({"field_name": "category", "unit": "category"})


@lru_cache(maxsize=1)
def estados_texto() -> pd.DataFrame:
    """Campos de texto (estado de los interruptores): estados DISCRETOS."""
    d = decodificados()
    d = d[d["value_text"].notna()]
    return d.sort_values(["timestamp", "id"], kind="stable").reset_index(drop=True)


def precargar() -> None:
    for f in (tramas, clasificacion, decodificados, observaciones, campos_gemelo, estados_texto):
        f()
