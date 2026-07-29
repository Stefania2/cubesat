"""FASE 5 --- API del gemelo digital.

Expone el motor de `gemelo_digital/` --- que vive en la raiz del repositorio,
junto al informe --- para que el frontend 3D lo consuma. La capa es delgada a
proposito: aqui no hay logica de analisis, solo cache y serializacion.

Cache
-----
Reconstruir el estado cuesta unos 4 s sobre las 71 631 lecturas, y no depende
de la peticion: es el mismo DataFrame para todos. Se calcula una vez, de forma
perezosa, en la primera peticion que lo necesite. La clasificacion de anomalias
cuesta 0,2 s por magnitud y se memoiza por nombre de campo.

Sin la cache, cada movimiento del cursor de reproduccion recalcularia el
DataFrame entero y la interfaz iria a un cuadro cada cinco segundos.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

# `gemelo_digital` vive en la raiz del repositorio. Desde este archivo:
#   parents[0] routers  [1] app  [2] backend  [3] telemetria_strand1  [4] cubesat
RAIZ_REPO = Path(__file__).resolve().parents[4]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from gemelo_digital import anomalias, datos, estado, reproduccion  # noqa: E402

router = APIRouter(prefix="/api/gemelo", tags=["gemelo digital"])

# Magnitud que gobierna el estado visual del CubeSat mientras no se pida otra.
CAMPO_POR_DEFECTO = "battery_voltage"

# Tope de puntos que se mandan al navegador para una grafica. Por encima de esto
# el trazo no gana informacion y la carga util se dispara.
MAX_PUNTOS_SERIE = 4000


@lru_cache(maxsize=1)
def _campos() -> pd.DataFrame:
    return datos.cargar_campos()


@lru_cache(maxsize=1)
def _estado() -> pd.DataFrame:
    return estado.reconstruir(_campos())


@lru_cache(maxsize=1)
def _unidades() -> dict[str, str]:
    return estado.unidades(_campos())


@lru_cache(maxsize=32)
def _clasificacion(campo: str) -> pd.DataFrame:
    try:
        return anomalias.clasificar(_campos(), campo)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@lru_cache(maxsize=32)
def _etiquetas_por_evento(campo: str) -> pd.Series:
    """Etiqueta vigente de `campo` en cada evento del eje de reproduccion.

    La clasificacion vive en los instantes en que esa magnitud se midio, que
    son menos que los eventos totales. Se arrastra hacia adelante: entre dos
    lecturas, el diagnostico sigue siendo el ultimo emitido.
    """
    clas = _clasificacion(campo)
    et = clas["etiqueta"].astype(str)
    # Un mismo instante puede traer la magnitud dos veces, cuando dos estaciones
    # reciben la misma baliza. `reindex` no admite indices con repetidos, y para
    # el diagnostico vale el ultimo: si una de las dos ya lo da por enrielado,
    # el estado del satelite no depende de cual de las dos se mire.
    et = et[~et.index.duplicated(keep="last")]
    return et.reindex(_estado().index, method="ffill")


def _magnitudes() -> list[str]:
    return [c for c in _estado().columns
            if not c.endswith("__edad_s") and c != "pase"]


@router.get("/resumen")
def resumen() -> dict:
    """Que hay para reproducir: magnitudes, eventos, pases y ejes."""
    est = _estado()
    idx = pd.DatetimeIndex(est.index)
    rep = reproduccion.Reproductor(est)
    unidades = _unidades()
    return {
        "eventos": len(est),
        "pases": int(est["pase"].max()) + 1,
        "inicio": idx[0].isoformat(),
        "fin": idx[-1].isoformat(),
        "duracion_real_dias": round((idx[-1] - idx[0]).total_seconds() / 86400, 1),
        "duracion_virtual_s": round(rep.duracion_virtual_s, 1),
        "velocidades": list(reproduccion.VELOCIDADES),
        "campo_por_defecto": CAMPO_POR_DEFECTO,
        "magnitudes": [{"campo": m, "unidad": unidades.get(m, "")} for m in _magnitudes()],
    }


@router.get("/estado")
def estado_en(indice: int = Query(0, ge=0),
              campo: str = CAMPO_POR_DEFECTO) -> dict:
    """Instantanea reconstruida en un evento, con la edad de cada lectura."""
    est = _estado()
    if indice >= len(est):
        raise HTTPException(status_code=404, detail=f"Solo hay {len(est)} eventos.")

    lecturas = estado.instantanea(est, indice, _unidades())
    etiqueta = str(_etiquetas_por_evento(campo).iloc[indice])
    if etiqueta == "nan":
        etiqueta = "sin_referencia"

    return {
        "indice": indice,
        "total": len(est),
        "momento": pd.Timestamp(est.index[indice]).isoformat(),
        "pase": int(est["pase"].iloc[indice]),
        "campo_gobernante": campo,
        "etiqueta": etiqueta,
        "estado_cubesat": anomalias.estado_cubesat(etiqueta),
        "lecturas": [
            {
                "campo": l.campo,
                "valor": l.valor,
                "unidad": l.unidad,
                "medida_en": l.medida_en.isoformat(),
                "edad_s": round(l.edad_s, 1),
                "frescura": l.frescura,
            }
            for l in lecturas
        ],
    }


@router.get("/serie/{campo}")
def serie(campo: str) -> dict:
    """Serie temporal de una magnitud, ya clasificada, para la grafica."""
    clas = _clasificacion(campo)

    # Se submuestrea por paso fijo, no por agregacion: promediar borraria justo
    # los picos que la grafica debe ensenar.
    paso = max(1, len(clas) // MAX_PUNTOS_SERIE)
    vista = clas.iloc[::paso]

    stats = clas["valor"].describe()
    return {
        "campo": campo,
        "unidad": _unidades().get(campo, ""),
        "n_total": len(clas),
        "n_enviados": len(vista),
        "submuestreo": paso,
        "estadisticas": {
            "media": round(float(stats["mean"]), 4),
            "minimo": round(float(stats["min"]), 4),
            "maximo": round(float(stats["max"]), 4),
        },
        "puntos": [
            {
                "t": t.isoformat(),
                "valor": None if pd.isna(f["valor"]) else round(float(f["valor"]), 4),
                "mediana": None if pd.isna(f["mediana"]) else round(float(f["mediana"]), 4),
                "z": None if pd.isna(f["z"]) else round(float(f["z"]), 2),
                "etiqueta": str(f["etiqueta"]),
            }
            for t, f in vista.iterrows()
        ],
    }


@router.get("/eventos/{campo}")
def eventos(campo: str, limite: int = Query(50, ge=1, le=500)) -> dict:
    """Tramos anomalos detectados, del mas largo al mas corto."""
    clas = _clasificacion(campo)
    evs = anomalias.eventos(clas, campo)
    evs.sort(key=lambda e: e.duracion_s, reverse=True)
    return {
        "campo": campo,
        "unidad": _unidades().get(campo, ""),
        "n_total": len(evs),
        "eventos": [e.dict() for e in evs[:limite]],
    }
