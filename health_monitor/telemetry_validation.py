"""Validacion de lecturas: que se puede sostener como medida y que no.

La validacion no corrige ni borra nada. Anota cada lectura con `valida` y un
`motivo`, y el resto del HMTA solo calcula sobre las validas. El dato original
se conserva tal cual, como en el resto del proyecto.

Reglas, en el orden en que se aplican (la primera que dispara da el motivo):

    no_finito          NaN o infinito
    duplicado          misma marca de tiempo, valor y estacion que otra fila.
                       Suele ser la misma baliza recibida dos veces: no es un
                       error del satelite, pero contarla dos veces sesga la
                       estadistica
    fuera_rango_fisico imposible por definicion: voltaje negativo, temperatura
                       por debajo del cero absoluto, porcentaje fuera de 0-100
    canal_sin_medida   vale exactamente la ordenada de la recta de AMSAT-UK, es
                       decir, la cuenta del ADC es 0. Las rectas son
                       decrecientes, asi que un canal muerto se disfraza de
                       valor maximo (9,75 V de bateria)
    escala_completa    vale exactamente la recta en 1023 cuentas: convertidor
                       saturado. `adc7_mx_array_current` lleva asi desde 2016
    canal_enrielado    la magnitud no se mueve en `MIN_ENRIELADO` lecturas
                       seguidas (regla de `gemelo_digital.anomalias`). Solo se
                       aplica a voltajes y temperaturas: una corriente de panel
                       en la sombra puede quedarse legitimamente en la misma
                       cuenta muchas lecturas
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from gemelo_digital.anomalias import MIN_ENRIELADO, enrielado

ADC_MAX = 1023
TOLERANCIA_RECTA = 1e-6
UNIDADES_ENRIELADO = ("V", "°C")

EXPLICACION = {
    "no_finito": "La lectura no contiene un número válido.",
    "duplicado": "La misma lectura aparece más de una vez (normalmente, la misma baliza "
                 "recibida por dos estaciones). Se cuenta una sola vez.",
    "fuera_rango_fisico": "El valor es físicamente imposible para esta magnitud.",
    "canal_sin_medida": "El valor coincide con el que da la recta de calibración cuando el "
                        "convertidor lee 0: el canal no está midiendo. No es un dato del satélite.",
    "escala_completa": "El convertidor está en su máximo (1023 cuentas): saturado o "
                       "desconectado. El valor no es una medida.",
    "canal_enrielado": "La magnitud no cambia en muchas lecturas seguidas: el sensor parece "
                       "haber dejado de medir.",
}


@dataclass(frozen=True)
class Hallazgo:
    variable: str
    tipo: str
    lecturas: int
    primera: str
    ultima: str
    explicacion: str

    def dict(self) -> dict:
        return asdict(self)


def _rectas() -> dict[str, tuple[float, float]]:
    """(m, c) de cada canal calibrado, de la hoja de AMSAT-UK."""
    from telemetria_strand1.backend.app.services.strand_amsat import calibraciones

    return {k: (v["m"], v["c"]) for k, v in calibraciones().items()}


_RECTAS: dict[str, tuple[float, float]] | None = None


def rectas() -> dict[str, tuple[float, float]]:
    global _RECTAS
    if _RECTAS is None:
        _RECTAS = _rectas()
    return _RECTAS


def _fuera_rango_fisico(valores: pd.Series, unidad: str) -> pd.Series:
    if unidad == "V":
        return valores < 0
    if unidad == "°C":
        return valores < -273.15
    if unidad == "%":
        return (valores < 0) | (valores > 100)
    return pd.Series(False, index=valores.index)


def validar(serie: pd.DataFrame, variable: str) -> pd.DataFrame:
    """Anota una serie (indexada por tiempo, con `valor`) con `valida` y `motivo`."""
    out = serie.copy()
    out["motivo"] = pd.Series(pd.NA, index=out.index, dtype="object")
    if out.empty:
        out["valida"] = pd.Series(dtype=bool)
        return out
    v = out["valor"].astype("float64")
    unidad = str(out["unidad"].dropna().iloc[0]) if out["unidad"].notna().any() else ""

    def marca(mascara: pd.Series, motivo: str):
        libre = out["motivo"].isna()
        out.loc[mascara.to_numpy() & libre.to_numpy(), "motivo"] = motivo

    marca(~np.isfinite(v), "no_finito")
    claves = pd.DataFrame({"t": out.index, "v": v.to_numpy(),
                           "e": out["estacion"].astype("string").fillna("").to_numpy()})
    marca(pd.Series(claves.duplicated(keep="first").to_numpy(), index=out.index), "duplicado")
    marca(_fuera_rango_fisico(v, unidad), "fuera_rango_fisico")

    if variable in rectas():
        m, c = rectas()[variable]
        marca((v - c).abs() <= TOLERANCIA_RECTA, "canal_sin_medida")
        marca((v - (c + m * ADC_MAX)).abs() <= TOLERANCIA_RECTA, "escala_completa")

    if unidad in UNIDADES_ENRIELADO:
        finitos = v[np.isfinite(v)]
        if len(finitos) >= MIN_ENRIELADO:
            quieto = enrielado(finitos)
            # La regla marca el final de cada ventana quieta; se extiende a
            # toda la ventana para no dejar validas las primeras lecturas.
            pos = np.flatnonzero(quieto.to_numpy())
            todo = np.zeros(len(finitos), bool)
            for p in pos:
                todo[max(0, p - MIN_ENRIELADO + 1):p + 1] = True
            m_quieto = pd.Series(False, index=out.index)
            m_quieto.loc[np.isfinite(v).to_numpy()] = todo
            marca(m_quieto, "canal_enrielado")

    out["valida"] = out["motivo"].isna()
    return out


def hallazgos(validada: pd.DataFrame, variable: str) -> list[Hallazgo]:
    """Un hallazgo por motivo, con cuantas lecturas afecta y cuando."""
    fuera = []
    if validada.empty:
        return fuera
    for motivo, g in validada[validada["motivo"].notna()].groupby("motivo"):
        fuera.append(Hallazgo(
            variable=variable, tipo=str(motivo), lecturas=len(g),
            primera=g.index.min().isoformat(), ultima=g.index.max().isoformat(),
            explicacion=EXPLICACION.get(str(motivo), "")))
    return sorted(fuera, key=lambda h: -h.lecturas)


def resumen(validada: pd.DataFrame) -> dict:
    """Cobertura de la serie: cuantas lecturas, cuantas validas y el mayor hueco."""
    n = len(validada)
    if n == 0:
        return {"lecturas": 0, "validas": 0, "fraccion_valida": None,
                "primera": None, "ultima": None, "ultima_valida": None,
                "mayor_hueco_s": None}
    validas = validada[validada["valida"]]
    idx = validada.index.sort_values()
    hueco = idx.to_series().diff().max()
    return {
        "lecturas": n,
        "validas": int(len(validas)),
        "fraccion_valida": round(len(validas) / n, 4),
        "primera": idx[0].isoformat(),
        "ultima": idx[-1].isoformat(),
        "ultima_valida": validas.index.max().isoformat() if not validas.empty else None,
        "mayor_hueco_s": float(hueco.total_seconds()) if pd.notna(hueco) else None,
    }
