"""FASE 2 --- Modelo de datos: reconstruccion del estado del CubeSat.

El problema que resuelve
------------------------
La fase 1 dejo dos hechos que impiden usar los DataFrames tal cual:

  1. Cada baliza transporta de una a tres magnitudes, nunca el estado completo.
     Un pivote crudo a formato ancho da una matriz con un 95 % de huecos.
  2. Las tramas llegan a rafagas durante los pases --- mediana de 1 segundo
     entre tramas consecutivas --- separadas por huecos de hasta 365 dias.

De ahi las dos construcciones de este modulo:

**Estado por ultimo valor conocido.** Para cada instante y cada magnitud se
arrastra la ultima lectura recibida. Esto es una reconstruccion, no una medida,
y por eso cada valor viaja con su **edad**: los segundos transcurridos desde que
se midio de verdad. Un panel que muestre 7,4 V sin decir que esa lectura tiene
ocho meses esta mintiendo. `EDADES_UMBRAL` marca a partir de cuando una lectura
deja de ser representativa.

**Pases.** Los eventos se agrupan en sesiones de recepcion separadas por huecos
grandes. Es lo que permite despues reproducir el tiempo sin pasar el 81 % de la
proyeccion en negro: dentro del pase el tiempo corre real, entre pases se salta.

Uso
---
    from gemelo_digital import datos, estado
    campos = datos.cargar_campos()
    est = estado.reconstruir(campos)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Hueco a partir del cual dos tramas pertenecen a pases distintos. Un pase de
# STRaND-1 dura unos 10 minutos de horizonte a horizonte, asi que 30 minutos
# separa sesiones de recepcion sin trocear una sola.
HUECO_ENTRE_PASES = pd.Timedelta("30min")

# Edad de una lectura arrastrada, en segundos, a partir de la cual deja de
# representar el estado actual. El primer umbral es un pase; el segundo, un dia.
EDADES_UMBRAL = {"fresca": 600, "vieja": 86_400}


@dataclass(frozen=True)
class Lectura:
    """Una magnitud reconstruida en un instante, con su procedencia."""

    campo: str
    valor: float
    unidad: str
    medida_en: pd.Timestamp
    edad_s: float

    @property
    def frescura(self) -> str:
        if self.edad_s <= EDADES_UMBRAL["fresca"]:
            return "fresca"
        if self.edad_s <= EDADES_UMBRAL["vieja"]:
            return "vieja"
        return "obsoleta"


def indice_eventos(campos: pd.DataFrame) -> pd.DatetimeIndex:
    """Instantes distintos con al menos una medida, ordenados."""
    return pd.DatetimeIndex(campos["timestamp"].drop_duplicates().sort_values())


def marcar_pases(eventos: pd.DatetimeIndex,
                 hueco: pd.Timedelta = HUECO_ENTRE_PASES) -> pd.Series:
    """Numera las sesiones de recepcion: +1 cada vez que hay un hueco grande."""
    salto = eventos.to_series().diff() > hueco
    return salto.cumsum().rename("pase")


def reconstruir(campos: pd.DataFrame) -> pd.DataFrame:
    """Estado en formato ancho: valor arrastrado y edad, por magnitud.

    Devuelve un DataFrame indexado por instante con, para cada magnitud `X`,
    las columnas `X` (ultimo valor conocido) y `X__edad_s` (antiguedad de esa
    lectura en segundos). Anade `pase` con el numero de sesion.
    """
    if campos.empty:
        raise ValueError("No hay campos que reconstruir.")

    # Si una magnitud aparece dos veces en el mismo instante --- ocurre cuando
    # dos estaciones reciben la misma baliza --- se queda la ultima.
    tabla = campos.pivot_table(index="timestamp", columns="field_name",
                               values="value_numeric", aggfunc="last",
                               observed=True)

    # Misma forma, pero guardando *cuando* se midio cada celda, para poder
    # calcular la edad despues de arrastrar. La resta se hace entre datetime64
    # y se divide por un timedelta64: nunca sobre los enteros subyacentes, cuya
    # unidad aqui es el microsegundo y no el nanosegundo que uno supondria.
    momentos = tabla.index.to_numpy()[:, None]
    marcas = np.where(tabla.notna().to_numpy(), momentos, np.datetime64("NaT"))
    medidas = pd.DataFrame(marcas, index=tabla.index, columns=tabla.columns).ffill()

    valores = tabla.ffill()
    edades = (momentos - medidas.to_numpy()) / np.timedelta64(1, "s")

    estado = valores.copy()
    estado.columns = [str(c) for c in estado.columns]
    for i, col in enumerate(estado.columns):
        estado[f"{col}__edad_s"] = edades[:, i]

    estado["pase"] = marcar_pases(pd.DatetimeIndex(estado.index)).to_numpy()
    return estado.sort_index(axis=1)


def unidades(campos: pd.DataFrame) -> dict[str, str]:
    """Unidad declarada de cada magnitud, para rotular sin inventar."""
    u = campos.groupby("field_name", observed=True)["unit"].first()
    return {str(k): ("" if pd.isna(v) else str(v)) for k, v in u.items()}


def instantanea(estado: pd.DataFrame, i: int,
                unidades_por_campo: dict[str, str] | None = None) -> list[Lectura]:
    """Todas las magnitudes reconstruidas en el evento `i`, con su edad."""
    fila = estado.iloc[i]
    momento = pd.Timestamp(estado.index[i])
    unidades_por_campo = unidades_por_campo or {}
    fuera = []
    for col in estado.columns:
        if col.endswith("__edad_s") or col == "pase":
            continue
        valor = fila[col]
        if pd.isna(valor):
            continue
        edad = float(fila[f"{col}__edad_s"])
        fuera.append(Lectura(
            campo=col,
            valor=float(valor),
            unidad=unidades_por_campo.get(col, ""),
            medida_en=momento - pd.Timedelta(seconds=edad),
            edad_s=edad,
        ))
    return sorted(fuera, key=lambda l: l.edad_s)


def cobertura(estado: pd.DataFrame) -> pd.DataFrame:
    """Cuantos eventos tiene cada magnitud en cada grado de frescura.

    Es el diagnostico que dice si un panel puede presumir de mostrar el estado
    del satelite o si en realidad esta ensenando fosiles.
    """
    filas = {}
    for col in estado.columns:
        if col.endswith("__edad_s") or col == "pase":
            continue
        edad = estado[f"{col}__edad_s"]
        filas[col] = {
            "fresca": int((edad <= EDADES_UMBRAL["fresca"]).sum()),
            "vieja": int(((edad > EDADES_UMBRAL["fresca"]) & (edad <= EDADES_UMBRAL["vieja"])).sum()),
            "obsoleta": int((edad > EDADES_UMBRAL["vieja"]).sum()),
            "sin_dato": int(edad.isna().sum()),
        }
    out = pd.DataFrame(filas).T
    out["%_fresca"] = (100 * out["fresca"] / len(estado)).round(1)
    return out.sort_values("%_fresca", ascending=False)
