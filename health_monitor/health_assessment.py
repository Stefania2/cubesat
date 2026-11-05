"""Informe de salud: los seis subsistemas, el estado general y la procedencia.

    from health_monitor import health_assessment, telemetry_acquisition as ta
    informe = health_assessment.evaluar(ta.cargar_real(), ventana_dias=30)
    informe = health_assessment.evaluar(ta.simular_escenario("caida_voltaje"))

Periodo evaluado
----------------
Se evalua una ventana que termina en `hasta` (por defecto, el ultimo dato de
la fuente) y dura `ventana_dias`. Lo anterior a la ventana no se evalua, pero
se usa como referencia: el z robusto compara cada lectura con las previas, y la
perdida de paquetes reciente se compara con la de antes.

Que significa el estado general
-------------------------------
El peor estado de los subsistemas evaluables. DESCONOCIDO solo si ninguno lo
es: la falta de datos de un subsistema no empeora el estado de los demas, y
tampoco se toma por un fallo. El informe dice ademas, aparte del estado,
**cuan viejos son los datos**: el estado de un archivo de 2023 no es el estado
actual del satelite, y el campo `vigencia` lo deja escrito.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

import pandas as pd

from . import (adcs_monitor, anomaly_detection, catalogo, communication_monitor,
               energy_monitor, obc_monitor, thermal_monitor)
from .alerts import ADVERTENCIA, CRITICO, DESCONOCIDO, NORMAL, Alerta, peor
from .telemetry_acquisition import ConjuntoTelemetria

VENTANA_DIAS = 30

MONITORES = (
    ("eps", energy_monitor.evaluar),
    ("termico", thermal_monitor.evaluar),
    ("comunicaciones", communication_monitor.evaluar),
    ("obc", obc_monitor.evaluar),
    ("adcs", adcs_monitor.evaluar),
)

EXPLICACION_ANOMALIAS = (
    "Una anomalía es un comportamiento que se aleja de lo que normalmente se espera. Por "
    "ejemplo, una batería cuyo voltaje cae, un componente que se calienta, paquetes que se "
    "pierden o un computador que se reinicia. Detectar una desviación no significa que haya "
    "una avería: significa que conviene mirarla con más atención."
)

TEXTO_GENERAL = {
    NORMAL: "Los subsistemas con datos no muestran desviaciones en el periodo evaluado.",
    ADVERTENCIA: "Hay desviaciones que requieren seguimiento. Ninguna supera un límite crítico "
                 "documentado.",
    CRITICO: "Al menos una medición supera un límite crítico documentado.",
    DESCONOCIDO: "No hay información suficiente para evaluar el estado.",
}


def _ultimo_dato(c: ConjuntoTelemetria) -> pd.Timestamp | None:
    marcas = []
    if not c.mediciones.empty:
        marcas.append(c.mediciones["timestamp"].max())
    if c.tramas is not None and not c.tramas.empty:
        marcas.append(c.tramas["timestamp"].max())
    return max(marcas) if marcas else None


def _ultimo_dato_telemetria(c: ConjuntoTelemetria) -> pd.Timestamp | None:
    return c.mediciones["timestamp"].max() if not c.mediciones.empty else None


def _resumen_alertas(alertas: list[Alerta]) -> dict:
    return {"total": len(alertas),
            "por_nivel": dict(Counter(a.nivel for a in alertas)),
            "por_mecanismo": dict(Counter(a.mecanismo for a in alertas)),
            "por_subsistema": dict(Counter(a.subsistema for a in alertas))}


def evaluar(conjunto: ConjuntoTelemetria, hasta: pd.Timestamp | str | None = None,
            ventana_dias: float = VENTANA_DIAS, ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now(timezone.utc)
    hasta = pd.Timestamp(hasta) if hasta is not None else None
    if hasta is None:
        # Por defecto, el ultimo dato de telemetria. Las tramas pueden seguir
        # llegando cuando ya no hay balizas decodificables (2023-2026 en el
        # archivo real): el periodo debe cubrir la ultima telemetria.
        hasta = _ultimo_dato_telemetria(conjunto) or _ultimo_dato(conjunto)
    if hasta is not None and hasta.tzinfo is None:
        hasta = hasta.tz_localize("UTC")
    desde = hasta - pd.Timedelta(days=ventana_dias) if hasta is not None else None
    if conjunto.simulado and conjunto.escenario:
        desde = None                                  # el escenario se evalua entero
    historico = conjunto.recortar(None, hasta)

    subsistemas = {}
    alertas: list[Alerta] = []
    for clave, fn in MONITORES:
        inf = fn(historico, desde)
        subsistemas[clave] = inf
        alertas += inf.alertas

    modelo = None
    if conjunto.respuesta_dinamica is not None:
        r = conjunto.respuesta_dinamica
        modelo = anomaly_detection.comparar_con_modelo(
            r["t"], r["y"], r["modelo"], r["controlador"], r.get("procedencia", conjunto.procedencia))
        if modelo["alerta"] is not None:
            alertas.append(modelo["alerta"])
        modelo["alerta"] = modelo["alerta"].dict() if modelo["alerta"] else None

    validacion = []
    for inf in subsistemas.values():
        for ind in inf.indicadores:
            for h in ind.hallazgos:
                validacion.append(h)

    estado_anom = peor([a.nivel for a in alertas]) if alertas else (
        NORMAL if any(i.estado != DESCONOCIDO for s in subsistemas.values() for i in s.indicadores)
        else DESCONOCIDO)
    estado_general = peor([s.estado for s in subsistemas.values()] + [estado_anom])

    ultimo = _ultimo_dato(conjunto)
    ultimo_tlm = _ultimo_dato_telemetria(conjunto)
    edad_dias = (pd.Timestamp(ahora) - ultimo_tlm).total_seconds() / 86400 if ultimo_tlm is not None else None
    if conjunto.simulado:
        vigencia = ("Escenario SIMULADO: estos resultados no describen el estado de STRaND-1.")
    elif edad_dias is None:
        vigencia = "No hay telemetría: el estado actual del satélite es desconocido."
    elif edad_dias > 1:
        vigencia = (f"La última telemetría decodificada tiene {edad_dias:.0f} días. El estado "
                    "evaluado es el de ese periodo, no el actual: STRaND-1 está inactivo y no "
                    "hay enlace en vivo, así que su estado actual es DESCONOCIDO.")
    else:
        vigencia = "Datos de las últimas 24 horas."

    conteo_proc = Counter()
    for inf in subsistemas.values():
        for ind in inf.indicadores:
            conteo_proc[ind.procedencia] += 1
        conteo_proc["NO_DISPONIBLE"] += len(inf.no_disponibles)

    alertas_orden = sorted(alertas, key=lambda a: str(a.fin), reverse=True)
    anomalias = {
        "clave": "anomalias", "nombre": catalogo.SUBSISTEMAS["anomalias"],
        "explicacion": EXPLICACION_ANOMALIAS, "estado": estado_anom,
        "resumen": _resumen_alertas(alertas),
        "mecanismos": {
            "limite": "Comparación con rangos documentados (solo con fuente; ninguno publicado "
                      "para STRaND-1).",
            "tendencia": "Cambios progresivos significativos (regresión lineal, |t| ≥ 5).",
            "desviacion": "Desviación respecto al historial propio (z robusto, gemelo digital).",
            "modelo": "Respuesta medida frente a un modelo dinámico de referencia (PID).",
            "validacion": "Lecturas que no son medidas: canal muerto, saturado o enrielado.",
        },
        "comparacion_modelo": modelo,
        "validacion": validacion,
        "alertas": [a.dict() for a in alertas_orden],
    }

    return {
        "proyecto": "STRaND-1 · Health Monitoring & Telemetry Analysis (HMTA)",
        "solo_supervision": True,
        "generado_utc": ahora.isoformat(),
        "procedencia": conjunto.procedencia,
        "fuente": conjunto.fuente,
        "descripcion_fuente": conjunto.descripcion,
        "escenario": conjunto.escenario,
        "simulado": conjunto.simulado,
        "periodo": {"desde": desde.isoformat() if desde is not None else None,
                    "hasta": hasta.isoformat() if hasta is not None else None,
                    "ventana_dias": None if desde is None else ventana_dias},
        "ultima_actualizacion": ultimo_tlm.isoformat() if ultimo_tlm is not None else None,
        "ultima_trama": ultimo.isoformat() if ultimo is not None else None,
        "antiguedad_dias": round(edad_dias, 1) if edad_dias is not None else None,
        "vigencia": vigencia,
        "estado_general": estado_general,
        "estado_general_texto": TEXTO_GENERAL[estado_general],
        "indicadores_por_procedencia": dict(conteo_proc),
        "subsistemas": {k: v.dict() for k, v in subsistemas.items()},
        "anomalias": anomalias,
        "alertas_recientes": [a.dict() for a in alertas_orden[:10]],
        "_alertas": alertas,
    }


def sin_objetos(informe: dict) -> dict:
    """Copia serializable (sin la lista interna de objetos Alerta)."""
    return serializable({k: v for k, v in informe.items() if not k.startswith("_")})


def serializable(obj):
    """Tipos de numpy/pandas a tipos de JSON; NaN e infinito a None."""
    import math

    import numpy as np

    if isinstance(obj, dict):
        return {str(k): serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serializable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [serializable(v) for v in obj.tolist()]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is pd.NA or obj is pd.NaT:
        return None
    return obj


def historial_mensual(conjunto: ConjuntoTelemetria,
                      variables: tuple[str, ...] = ("battery_0_voltage", "battery_1_voltage",
                                                    "adc13_px_array_current")) -> list[dict]:
    """Por mes y variable: lecturas recibidas, validas y motivo dominante de las invalidas.

    Es la vista que cuenta la historia del archivo real: sano hasta 2020-10,
    intermitente hasta 2021-01 y sin medida desde 2021-02.
    """
    from . import telemetry_validation as val

    filas = []
    for var in variables:
        s = conjunto.serie(var)
        if s.empty:
            continue
        v = val.validar(s, var)
        mes = v.index.tz_convert("UTC").strftime("%Y-%m") if v.index.tz is not None else v.index.strftime("%Y-%m")
        for m, g in v.groupby(mes):
            invalidas = g[~g["valida"]]
            filas.append({
                "mes": m, "variable": var, "lecturas": len(g), "validas": int(g["valida"].sum()),
                "fraccion_valida": round(float(g["valida"].mean()), 4),
                "mediana_valida": (round(float(g.loc[g["valida"], "valor"].median()), 4)
                                   if g["valida"].any() else None),
                "motivo_dominante": (str(invalidas["motivo"].mode().iloc[0])
                                     if not invalidas.empty else None),
                "procedencia": conjunto.procedencia})
    return filas
