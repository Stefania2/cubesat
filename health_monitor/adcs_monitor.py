"""Orientacion y estabilidad (ADCS): solo lo que hay, sin orientaciones ficticias.

STRaND-1 tiene magnetometros y ruedas de reaccion, pero la baliza no trae
ninguna estimacion de actitud. Llegan:

  - los tres ejes del magnetometro (nodo 0x89) como **enteros sin calibrar**:
    AMSAT-UK no publica la conversion a microteslas ni como estan orientados
    los ejes respecto al cuerpo del satelite;
  - el estado del interruptor de las ruedas de reaccion (nodo 0x66, 0xA4).

Con eso no se puede calcular hacia donde apunta el satelite ni como gira, y el
monitor no lo intenta. Muestra la actividad de los sensores y el estado de las
ruedas, y deja la orientacion como NO DISPONIBLE.
"""

from __future__ import annotations

import pandas as pd

from .alerts import DESCONOCIDO
from .subsystem_monitor import Indicador, InformeSubsistema, informe
from .telemetry_acquisition import ConjuntoTelemetria

EJES = ("magnetometer_x", "magnetometer_y", "magnetometer_z")
CAMPO_RUEDAS = "switch_7_reaction_wheels_estado"
ESTADOS_DOCUMENTADOS = ("OFF", "ON", "OFF (sobrecorriente)", "ON en sobrecorriente",
                        "OFF por tiempo maximo", "OFF por causa desconocida")

SIN_ACTITUD = "Información ADCS no disponible en esta fuente de datos."

EXPLICACION = (
    "Un satélite necesita saber hacia dónde está orientado: sus antenas y paneles funcionan "
    "mejor apuntando en ciertas direcciones. El ADCS (Attitude Determination and Control "
    "System, sistema de determinación y control de actitud) usa sensores, como los "
    "magnetómetros que miden el campo magnético de la Tierra, y actuadores, como las ruedas de "
    "reacción. Este módulo solo supervisa: no mueve el satélite."
)


def evaluar(historico: ConjuntoTelemetria, desde: pd.Timestamp | None) -> InformeSubsistema:
    proc = historico.procedencia
    indicadores, presentes = [], set()
    for eje in EJES:
        s = historico.serie(eje)
        v = s if desde is None else s[s.index >= desde]
        if v.empty:
            continue
        presentes.add(eje)
        valores = v["valor"].astype(float)
        distintos = int(valores.nunique())
        indicadores.append(Indicador(
            clave=eje, nombre=f"Magnetómetro, eje {eje[-1].upper()} (cuenta cruda)", unidad="cuenta",
            que_es="Lectura sin convertir del sensor de campo magnético en una dirección.",
            por_que_importa="Que el valor cambie indica que el sensor está entregando lecturas; "
                            "sin calibración no se puede convertir en orientación.",
            procedencia=proc, estado=DESCONOCIDO,
            estado_motivo=f"El sensor entregó {len(valores)} lecturas con {distintos} valores "
                          "distintos. Sin calibración ni orientación de los ejes documentadas no "
                          "hay referencia para evaluarlo.",
            valor=float(valores.iloc[-1]), valor_fecha=valores.index.max().isoformat(),
            referencia="Sin calibración publicada (AMSAT-UK).",
            estadisticas={"lecturas": len(valores), "valores_distintos": distintos,
                          "mediana": float(valores.median()), "p05": float(valores.quantile(.05)),
                          "p95": float(valores.quantile(.95))},
            serie=[{"t": t.isoformat(), "v": float(x), "valida": True, "motivo": None}
                   for t, x in valores.iloc[::max(1, len(valores) // 600)].items()],
            fuente=historico.fuente,
            notas=["Es el entero recibido; no está en microteslas."]))

    m = historico.mediciones
    ruedas = m[(m["variable"] == CAMPO_RUEDAS)] if not m.empty else m
    if desde is not None and not ruedas.empty:
        ruedas = ruedas[ruedas["timestamp"] >= desde]
    if not ruedas.empty:
        presentes.add("reaction_wheels_switch")
        conteo = ruedas["texto"].value_counts().to_dict()
        no_doc = {k: int(n) for k, n in conteo.items() if k not in ESTADOS_DOCUMENTADOS}
        ultimo = ruedas.sort_values("timestamp").iloc[-1]
        indicadores.append(Indicador(
            clave="reaction_wheels_switch", nombre="Interruptor de las ruedas de reacción",
            unidad=None,
            que_es="Si la alimentación de las ruedas que giran el satélite está encendida.",
            por_que_importa="Con las ruedas apagadas el satélite no controla activamente su "
                            "orientación.",
            procedencia=proc, estado=DESCONOCIDO,
            estado_motivo="Dato informativo: no hay documentación de en qué estado deberían "
                          "estar las ruedas en cada momento de la misión.",
            valor=str(ultimo["texto"]), valor_fecha=pd.Timestamp(ultimo["timestamp"]).isoformat(),
            referencia="Códigos de estado de la hoja de AMSAT-UK.",
            estadisticas={"conteo_estados": {k: int(n) for k, n in conteo.items()},
                          "codigos_no_documentados": no_doc},
            notas=(["Algunos códigos (p. ej. 0x9A) no figuran en la hoja de AMSAT-UK: se "
                    "muestran tal cual, sin interpretarlos."] if no_doc else []),
            fuente=historico.fuente))
    notas = [SIN_ACTITUD + " La baliza no trae orientación, velocidad de giro ni estado de "
             "estabilización, y no se generan valores ficticios ni se afirma que el satélite "
             "esté estabilizado."]
    return informe("adcs", EXPLICACION, indicadores, [], notas=notas, presentes=presentes)
