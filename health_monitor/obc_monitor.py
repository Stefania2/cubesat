"""Computador de a bordo (OBC).

Lo unico que la baliza trae del OBC es el canal 0x80/0x0C, que la hoja de
AMSAT-UK llama «4B UNIX TIME». Seria la pieza clave --- un reloj que avanza
dice que el computador funciona, uno que vuelve a cero delata un reinicio ---,
pero solo si se comporta como un reloj. Este monitor **lo comprueba con los
datos antes de usarlo**: entre lecturas cercanas de la misma estacion, el
contador debe avanzar aproximadamente un segundo por segundo.

En el archivo real no lo hace (vale 2 en la mayoria de las lecturas y su ritmo
mediano es 0 s/s), asi que no se cuentan reinicios ni se afirma nada sobre el
funcionamiento del computador. En un escenario simulado con un reloj de verdad,
el mismo codigo detecta las vueltas a cero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .alerts import ADVERTENCIA, DESCONOCIDO, NORMAL, Alerta
from .subsystem_monitor import Indicador, InformeSubsistema, informe
from .telemetry_acquisition import ConjuntoTelemetria

CAMPO_RELOJ = "obc_unix_time"
PAREJA_MAX_S = 300          # lecturas mas separadas no se comparan: puede haber un reinicio entre medias
RITMO_MIN, RITMO_MAX = 0.9, 1.1
FRACCION_MIN_PAREJAS = 0.7

EXPLICACION = (
    "El OBC (On-Board Computer, computador de a bordo) es el ordenador que viaja en el "
    "satélite. Ejecuta los programas que leen los sensores, preparan los paquetes de "
    "telemetría y gestionan las demás operaciones. Si se reinicia de forma inesperada, "
    "conviene investigar por qué."
)


def comportamiento_reloj(serie: pd.Series) -> dict:
    """¿Avanza el contador ~1 s por segundo entre lecturas cercanas?"""
    s = serie.dropna().sort_index()
    s = s[~s.index.duplicated(keep="first")]
    if len(s) < 3:
        return {"parejas": 0, "es_reloj": False, "ritmo_mediano": None,
                "motivo": "Muy pocas lecturas para comprobarlo."}
    dt = s.index.to_series().diff().dt.total_seconds().to_numpy()[1:]
    dv = np.diff(s.to_numpy(float))
    cerca = (dt > 0) & (dt <= PAREJA_MAX_S)
    if cerca.sum() < 3:
        return {"parejas": int(cerca.sum()), "es_reloj": False, "ritmo_mediano": None,
                "motivo": "No hay lecturas suficientemente próximas entre sí."}
    ritmo = dv[cerca] / dt[cerca]
    avanza = ritmo[ritmo >= 0]
    mediano = float(np.median(avanza)) if len(avanza) else 0.0
    frac_ok = float(np.mean((ritmo >= RITMO_MIN) & (ritmo <= RITMO_MAX)))
    es_reloj = bool(RITMO_MIN <= mediano <= RITMO_MAX and frac_ok >= FRACCION_MIN_PAREJAS)
    return {"parejas": int(cerca.sum()), "es_reloj": es_reloj,
            "ritmo_mediano": round(mediano, 4), "fraccion_parejas_a_1s_por_s": round(frac_ok, 4),
            "valor_mas_frecuente": float(pd.Series(s).mode().iloc[0]),
            "motivo": ("Avanza un segundo por segundo: se comporta como un reloj." if es_reloj else
                       f"No avanza al ritmo del tiempo (ritmo mediano {mediano:.3g} s/s): no se "
                       "comporta como un reloj.")}


def reinicios(serie: pd.Series) -> list[dict]:
    """Vueltas atras del contador entre lecturas consecutivas."""
    s = serie.dropna().sort_index()
    s = s[~s.index.duplicated(keep="first")]
    v = s.to_numpy(float)
    fuera = []
    for i in np.flatnonzero(np.diff(v) < 0) + 1:
        fuera.append({"instante": s.index[i].isoformat(), "antes_s": float(v[i - 1]),
                      "despues_s": float(v[i])})
    return fuera


def evaluar(historico: ConjuntoTelemetria, desde: pd.Timestamp | None) -> InformeSubsistema:
    proc = historico.procedencia
    serie = historico.serie(CAMPO_RELOJ)
    ventana = serie if desde is None else serie[serie.index >= desde]
    indicadores, alertas = [], []
    presentes: set[str] = set()
    extra: dict = {}

    if not ventana.empty:
        presentes.add(CAMPO_RELOJ)
        valores = ventana["valor"].astype(float)
        reloj = comportamiento_reloj(valores)
        extra["comprobacion_reloj"] = reloj
        if reloj["es_reloj"]:
            vueltas = reinicios(valores)
            extra["reinicios"] = vueltas
            for r in vueltas:
                alertas.append(Alerta(
                    subsistema="obc", variable=CAMPO_RELOJ, nivel=ADVERTENCIA, mecanismo="obc",
                    inicio=r["instante"], fin=r["instante"],
                    que_ocurrio=f"El reloj del computador volvió atrás de {r['antes_s']:.0f} s a "
                                f"{r['despues_s']:.0f} s: posible reinicio.",
                    componente="Computador de a bordo (OBC)", valor_registrado=r["despues_s"],
                    unidad="s", valor_referencia=r["antes_s"],
                    referencia="Lectura anterior del mismo contador, que avanza 1 s/s.",
                    por_que_importa="Un reinicio inesperado puede indicar un problema de "
                                    "alimentación, de software o de radiación que conviene investigar.",
                    informacion_adicional="Mirar el voltaje y la corriente en el mismo instante y "
                                          "si el reinicio se repite con un periodo fijo (vigilante).",
                    procedencia=proc))
            estado = ADVERTENCIA if vueltas else NORMAL
            motivo = (f"{len(vueltas)} vueltas atrás del contador en el periodo." if vueltas else
                      "El contador avanza sin vueltas atrás en el periodo.")
            indicadores.append(Indicador(
                clave="reboots", nombre="Reinicios del computador", unidad="reinicios",
                que_es="Veces que el reloj del computador volvió a empezar.",
                por_que_importa="Un reinicio inesperado puede ser la señal de un problema.",
                procedencia=proc, estado=estado, estado_motivo=motivo, valor=len(vueltas),
                referencia="Deducido de las vueltas atrás de un contador validado como reloj."))
            presentes.add("reboots")
        else:
            estado, motivo = DESCONOCIDO, (
                reloj["motivo"] + " Por eso no se usa para contar reinicios ni para afirmar "
                "que el computador funciona.")
        ult = valores.index.max()
        indicadores.insert(0, Indicador(
            clave=CAMPO_RELOJ, nombre="Campo de tiempo del OBC", unidad="s",
            que_es="Número que, según la hoja de AMSAT-UK, es el reloj del computador.",
            por_que_importa="Un reloj que avanza indica que el computador funciona.",
            procedencia=proc, estado=estado, estado_motivo=motivo,
            valor=float(valores.iloc[-1]), valor_fecha=ult.isoformat(),
            referencia="Comprobación de ritmo: debe avanzar entre 0,9 y 1,1 s por segundo.",
            estadisticas={"lecturas": len(valores), "mediana": float(valores.median()),
                          "maximo": float(valores.max())},
            serie=[{"t": t.isoformat(), "v": float(v), "valida": True, "motivo": None}
                   for t, v in valores.iloc[::max(1, len(valores) // 600)].items()],
            fuente=historico.fuente))
        indicadores.insert(1, Indicador(
            clave="actividad_obc", nombre="Estado operativo", unidad="lecturas",
            que_es="Cuántas lecturas del nodo del computador llegaron en el periodo.",
            por_que_importa="Que lleguen datos del computador indica que estaba activo en esos "
                            "instantes, pero no dice si funcionaba correctamente.",
            procedencia=proc, estado=DESCONOCIDO,
            estado_motivo="Indicio de actividad, no medida de salud: no hay datos que permitan "
                          "determinar que el computador funciona correctamente.",
            valor=len(valores), valor_fecha=ult.isoformat(),
            referencia="—"))
    notas = [] if indicadores else ["No hay datos del computador de a bordo en esta fuente."]
    return informe("obc", EXPLICACION, indicadores, alertas, extra=extra, notas=notas,
                   presentes=presentes)
