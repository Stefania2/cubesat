"""Sistema de energia (EPS): voltaje de baterias y corriente de paneles."""

from __future__ import annotations

import pandas as pd

from . import catalogo
from .subsystem_monitor import InformeSubsistema, analizar_variable, informe
from .telemetry_acquisition import ConjuntoTelemetria

EXPLICACION = (
    "El satélite necesita electricidad para que funcionen sus computadores, sensores y "
    "sistemas de comunicación. El EPS (Electrical Power System, sistema eléctrico de potencia) "
    "recoge energía del Sol con los paneles solares, la guarda en las baterías y la reparte. "
    "Aquí se observa el voltaje de las dos baterías y la corriente que entrega cada panel."
)

ORDEN = ("battery_0_voltage", "battery_1_voltage", "adc13_px_array_current",
         "adc7_mx_array_current", "adc1_py_array_current", "adc4_my_array_current",
         "adc10_pz_array_current", "adc31_mz_array_current")

NOTAS = [
    "Potencia: no se calcula. La baliza no trae voltaje y corriente de una misma rama del "
    "circuito, y multiplicar magnitudes de ramas distintas no da la potencia de nada.",
    "Nivel de carga: ningún canal lo mide y no se dispone de la curva de descarga de las "
    "celdas, así que no se estima.",
    "Una corriente de panel cercana a cero en la sombra de la Tierra es lo esperado, no una "
    "anomalía.",
]


def evaluar(historico: ConjuntoTelemetria, desde: pd.Timestamp | None) -> InformeSubsistema:
    presentes = set(historico.variables())
    indicadores, alertas = [], []
    for clave in ORDEN:
        if clave not in presentes:
            continue
        ind, al = analizar_variable(historico, clave, desde)
        indicadores.append(ind)
        alertas += al

    extra = {}
    v0 = next((i for i in indicadores if i.clave == "battery_0_voltage"), None)
    v1 = next((i for i in indicadores if i.clave == "battery_1_voltage"), None)
    if v0 and v1 and v0.estadisticas and v1.estadisticas:
        extra["comparacion_baterias"] = {
            "mediana_bateria_0_V": v0.estadisticas["mediana"],
            "mediana_bateria_1_V": v1.estadisticas["mediana"],
            "diferencia_V": round(v0.estadisticas["mediana"] - v1.estadisticas["mediana"], 4),
            "nota": "Dos baterías que se separan mucho pueden indicar un problema de una de "
                    "ellas o de su sensor. No hay un umbral documentado para esa diferencia.",
        }
    return informe("eps", EXPLICACION, indicadores, alertas, extra=extra, notas=NOTAS,
                   presentes={i.clave for i in indicadores})


def variables_eps() -> list[str]:
    return [v.clave for v in catalogo.de_subsistema("eps")]
