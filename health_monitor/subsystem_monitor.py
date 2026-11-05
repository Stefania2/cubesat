"""Piezas comunes de los monitores de subsistema.

Cada monitor (`energy_monitor`, `thermal_monitor`, ...) produce un
`InformeSubsistema`: una explicacion para principiantes, una lista de
`Indicador` con su valor, unidad, procedencia, estado y serie, las variables
que no estan disponibles y por que, y las alertas.

`analizar_variable` es el camino comun para una serie numerica:

    validar  ->  descartar lo que no es medida
             ->  limites documentados (A)
             ->  tendencia (B)
             ->  desviacion respecto al historial (z robusto)
             ->  alertas de validacion (D)
             ->  estado del indicador

Estado de un indicador
----------------------
    sin lecturas en el periodo               DESCONOCIDO
    lecturas, pero ninguna valida            DESCONOCIDO (y alerta de validacion)
    limite critico documentado superado      CRITICO
    cualquier alerta                         ADVERTENCIA
    nada de lo anterior                      NORMAL

NORMAL nunca significa «dentro de especificacion» cuando no hay especificacion:
el campo `referencia` dice contra que se comparo (casi siempre, el propio
historial de la variable), y `rango_documentado` queda en None.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from . import anomaly_detection as ad
from . import catalogo
from . import telemetry_validation as val
from .alerts import ADVERTENCIA, CRITICO, DESCONOCIDO, NORMAL, Alerta, peor
from .telemetry_acquisition import NO_DISPONIBLE, ConjuntoTelemetria

MAX_PUNTOS_SERIE = 600


@dataclass
class Indicador:
    clave: str
    nombre: str
    unidad: str | None
    que_es: str
    por_que_importa: str
    procedencia: str
    estado: str
    estado_motivo: str
    valor: float | str | None = None
    valor_fecha: str | None = None
    referencia: str = ""
    rango_documentado: tuple[float, float] | None = None
    estadisticas: dict = field(default_factory=dict)
    validacion: dict = field(default_factory=dict)
    hallazgos: list = field(default_factory=list)
    tendencia: dict | None = None
    serie: list = field(default_factory=list)
    notas: list = field(default_factory=list)
    fuente: str = ""

    def dict(self) -> dict:
        return asdict(self)


@dataclass
class InformeSubsistema:
    clave: str
    nombre: str
    explicacion: str
    estado: str
    resumen: str
    indicadores: list[Indicador]
    no_disponibles: list[dict]
    alertas: list[Alerta]
    procedencias: list[str]
    extra: dict = field(default_factory=dict)
    notas: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        return {
            "clave": self.clave, "nombre": self.nombre, "explicacion": self.explicacion,
            "estado": self.estado, "resumen": self.resumen,
            "indicadores": [i.dict() for i in self.indicadores],
            "no_disponibles": self.no_disponibles,
            "alertas": [a.dict() for a in self.alertas],
            "procedencias": self.procedencias, "extra": self.extra, "notas": self.notas,
        }


def no_disponibles(subsistema: str, presentes: set[str]) -> list[dict]:
    """Variables del catalogo que no llegan en esta fuente, con el motivo."""
    motivo = {
        catalogo.DEFINIDA_NO_EMITIDA: "La hoja de AMSAT-UK define este canal, pero la baliza de "
                                      "STRaND-1 nunca lo transmite.",
        catalogo.NO_EXISTE: "Ningún canal de STRaND-1 mide esta magnitud.",
        catalogo.DERIVADA: "No se puede calcular con los datos disponibles.",
        catalogo.EMITIDA: "No hay lecturas de esta variable en el periodo consultado.",
    }
    fuera = []
    for v in catalogo.de_subsistema(subsistema):
        if v.clave in presentes:
            continue
        fuera.append({"clave": v.clave, "nombre": v.nombre, "unidad": v.unidad,
                      "que_es": v.que_es, "por_que_importa": v.por_que_importa,
                      "disponibilidad": v.disponibilidad, "procedencia": NO_DISPONIBLE,
                      "motivo": motivo[v.disponibilidad], "notas": list(v.notas),
                      "nodo_canal": v.nodo_canal})
    return fuera


def _submuestrear(validada: pd.DataFrame) -> list[dict]:
    if validada.empty:
        return []
    paso = max(1, int(np.ceil(len(validada) / MAX_PUNTOS_SERIE)))
    sub = validada.iloc[::paso]
    return [{"t": t.isoformat(), "v": (None if not np.isfinite(v) else round(float(v), 5)),
             "valida": bool(ok), "motivo": (None if pd.isna(m) else str(m))}
            for t, v, ok, m in zip(sub.index, sub["valor"].astype(float), sub["valida"], sub["motivo"])]


def analizar_variable(historico: ConjuntoTelemetria, clave: str, desde: pd.Timestamp | None,
                      *, campo: str | None = None, nombre: str | None = None,
                      unidad: str | None = None, que_es: str | None = None,
                      por_que: str | None = None, componente: str | None = None,
                      subsistema: str | None = None) -> tuple[Indicador, list[Alerta]]:
    """Indicador y alertas de una variable numerica.

    `historico` llega hasta el final del periodo; `desde` marca su inicio. Lo
    anterior a `desde` solo se usa como referencia del z robusto.
    """
    v_def = catalogo.VARIABLES.get(clave)
    campo = campo or clave
    nombre = nombre or (v_def.nombre if v_def else clave)
    que_es = que_es or (v_def.que_es if v_def else "")
    por_que = por_que or (v_def.por_que_importa if v_def else "")
    subsistema = subsistema or (v_def.subsistema if v_def else "")
    componente = componente or nombre
    procedencia = historico.procedencia

    serie = historico.serie(campo)
    if unidad is None and not serie.empty and serie["unidad"].notna().any():
        unidad = str(serie["unidad"].dropna().iloc[0])
    validada_todo = val.validar(serie, campo)
    ventana = validada_todo if desde is None else validada_todo[validada_todo.index >= desde]

    base = dict(clave=clave, nombre=nombre, unidad=unidad, que_es=que_es,
                por_que_importa=por_que, procedencia=procedencia,
                rango_documentado=v_def.rango_documentado if v_def else None,
                notas=list(v_def.notas) if v_def else [], fuente=historico.fuente)

    if ventana.empty:
        return Indicador(**base, estado=DESCONOCIDO,
                         estado_motivo="No hay lecturas de esta variable en el periodo consultado. "
                                       "La falta de datos no indica un fallo del satélite.",
                         referencia="—"), []

    hall = val.hallazgos(ventana, campo)
    validas = ventana[ventana["valida"]]["valor"].astype(float)
    recta = val.rectas().get(campo)
    alertas = ad.alertas_validacion(hall, subsistema=subsistema, componente=componente,
                                    unidad=unidad, procedencia=procedencia,
                                    referencia_recta=recta[1] if recta else None)

    limites = historico.limites.get(campo, [])
    if limites:
        referencia = "; ".join(f"[{l.minimo}, {l.maximo}] {unidad or ''} ({l.nivel}, {l.fuente})"
                               for l in limites)
    else:
        referencia = ("Sin rango de operación documentado para STRaND-1. Se compara con su "
                      "propio historial (mediana ± MAD de las lecturas anteriores).")

    estad = {}
    tend = None
    if not validas.empty:
        estad = {k: round(float(x), 5) for k, x in {
            "mediana": validas.median(), "minimo": validas.min(), "maximo": validas.max(),
            "p05": validas.quantile(0.05), "p95": validas.quantile(0.95),
            "desviacion_tipica": validas.std() if len(validas) > 1 else 0.0}.items()}
        if limites:
            alertas += ad.comparar_limites(validas, limites, subsistema=subsistema,
                                           componente=componente, unidad=unidad,
                                           por_que=por_que, procedencia=procedencia)
        a_t = ad.alerta_tendencia(validas, subsistema=subsistema, variable=campo,
                                  componente=componente, unidad=unidad, por_que=por_que,
                                  procedencia=procedencia)
        tend = ad.tendencia(validas)
        if a_t:
            alertas.append(a_t)
        hist_validas = validada_todo[validada_todo["valida"]]["valor"].astype(float)
        desv, _ = ad.desviaciones(hist_validas, desde, subsistema=subsistema, variable=campo,
                                  componente=componente, unidad=unidad, por_que=por_que,
                                  procedencia=procedencia)
        alertas += desv

    ult = validas.index.max() if not validas.empty else None
    if validas.empty:
        motivo_principal = hall[0].tipo if hall else "sin_validas"
        estado = DESCONOCIDO
        motivo = (f"Hay {len(ventana)} lecturas pero ninguna es una medida válida "
                  f"(motivo principal: {motivo_principal}). No se puede saber el valor real.")
    elif any(a.nivel == CRITICO for a in alertas):
        estado, motivo = CRITICO, "Se superó un límite crítico documentado."
    elif alertas:
        estado = ADVERTENCIA
        mecs = sorted({a.mecanismo for a in alertas})
        motivo = f"Hay desviaciones que conviene seguir (mecanismos: {', '.join(mecs)})."
    else:
        estado = NORMAL
        motivo = ("Sin desviaciones respecto a los límites documentados." if limites else
                  "Sin desviaciones respecto a su propio historial. No hay rango documentado "
                  "con el que compararla.")

    ind = Indicador(
        **base, estado=estado, estado_motivo=motivo,
        valor=round(float(validas.iloc[-1]), 5) if ult is not None else None,
        valor_fecha=ult.isoformat() if ult is not None else None,
        referencia=referencia, estadisticas=estad, validacion=val.resumen(ventana),
        hallazgos=[h.dict() for h in hall], tendencia=tend, serie=_submuestrear(ventana))
    return ind, alertas


def informe(clave: str, explicacion: str, indicadores: list[Indicador], alertas: list[Alerta],
            *, extra: dict | None = None, notas: list[str] | None = None,
            presentes: set[str] | None = None) -> InformeSubsistema:
    estados = [i.estado for i in indicadores]
    if any(a.nivel == CRITICO for a in alertas):
        estados.append(CRITICO)
    elif alertas:
        estados.append(ADVERTENCIA)
    estado = peor(estados)
    n_ok = sum(1 for e in estados if e != DESCONOCIDO)
    if not indicadores:
        resumen = "No hay información disponible para este subsistema en esta fuente de datos."
    elif n_ok == 0:
        resumen = "Hay lecturas, pero ninguna permite conocer el estado del subsistema."
    else:
        resumen = {NORMAL: "Los indicadores disponibles no muestran desviaciones.",
                   ADVERTENCIA: "Hay desviaciones que requieren seguimiento.",
                   CRITICO: "Al menos un indicador supera un límite crítico documentado."}[estado]
    procs = sorted({i.procedencia for i in indicadores})
    nd = no_disponibles(clave, presentes if presentes is not None else {i.clave for i in indicadores})
    if nd:
        procs = sorted(set(procs) | {NO_DISPONIBLE})
    return InformeSubsistema(
        clave=clave, nombre=catalogo.SUBSISTEMAS[clave], explicacion=explicacion, estado=estado,
        resumen=resumen, indicadores=indicadores, no_disponibles=nd, alertas=alertas,
        procedencias=procs, extra=extra or {}, notas=notas or [])
