"""Estado termico: cualquier variable en grados Celsius que traiga la fuente.

STRaND-1 no transmite ninguna temperatura (la hoja de AMSAT-UK define ocho
canales termicos y la baliza no rota ninguno), asi que sobre el archivo real
esta seccion sale vacia y lo dice. El monitor no esta escrito contra nombres
concretos sino contra la unidad, para que un escenario simulado o una fuente
futura que si los traiga se analicen sin tocar codigo.
"""

from __future__ import annotations

import pandas as pd

from . import catalogo
from .subsystem_monitor import InformeSubsistema, analizar_variable, informe
from .telemetry_acquisition import ConjuntoTelemetria

EXPLICACION = (
    "En el espacio un satélite pasa del sol directo a la sombra de la Tierra cada órbita, y sus "
    "componentes pueden calentarse y enfriarse mucho. Las baterías y la electrónica necesitan "
    "trabajar dentro de ciertos rangos de temperatura para funcionar bien. Aquí se mostraría la "
    "temperatura de cada componente y su evolución."
)

SIN_DATOS = ("Información térmica no disponible en esta fuente de datos. La hoja de AMSAT-UK "
             "define sensores de temperatura en las baterías y en los paneles, pero la baliza "
             "de STRaND-1 nunca los transmite. No es un fallo del sensor ni del decodificador: "
             "el satélite no envía ese dato.")

NOMBRES = {
    "battery_temperature": "Temperatura de la batería",
    "battery_0_temperature": "Temperatura de la batería 0",
    "battery_1_temperature": "Temperatura de la batería 1",
}


def evaluar(historico: ConjuntoTelemetria, desde: pd.Timestamp | None) -> InformeSubsistema:
    m = historico.mediciones
    termicas = sorted(m.loc[m["unidad"] == "°C", "variable"].unique().tolist()) if not m.empty else []
    indicadores, alertas = [], []
    for var in termicas:
        nombre = NOMBRES.get(var) or (catalogo.VARIABLES[var].nombre
                                      if var in catalogo.VARIABLES else var)
        ind, al = analizar_variable(
            historico, var, desde, nombre=nombre, unidad="°C", subsistema="termico",
            que_es="Temperatura registrada en el componente, en grados Celsius.",
            por_que="Fuera de su rango de trabajo un componente puede perder prestaciones o "
                    "dañarse. Sin la hoja de datos del componente no se puede decir si una "
                    "temperatura es peligrosa.")
        indicadores.append(ind)
        alertas += al
    extra = {}
    if len(indicadores) > 1:
        extra["comparacion_componentes"] = [
            {"componente": i.nombre, "mediana_C": i.estadisticas.get("mediana"),
             "maximo_C": i.estadisticas.get("maximo")} for i in indicadores]
    notas = [] if indicadores else [SIN_DATOS]
    presentes = {"battery_temperature"} if "battery_temperature" in termicas else set()
    presentes |= set(termicas)
    return informe("termico", EXPLICACION, indicadores, alertas, extra=extra, notas=notas,
                   presentes=presentes)
