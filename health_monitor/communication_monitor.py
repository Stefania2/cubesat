"""Comunicaciones: lo que se recibio de verdad, y aparte, lo que se simulo.

Tres familias de datos que no se mezclan:

    REAL         tramas recibidas por SatNOGS, su estado de decodificacion y
                 las observaciones (pases) con su resultado
    ESTIMADO     paquetes perdidos, deducidos del contador de secuencia de 8
                 bits; y el margen del enlace del presupuesto de potencia
    SIMULADO     BER de la cadena GNU Radio (modelo BPSK comparativo en banda
                 base: no es la modulacion del satelite, que es FSK 9600)
    DOCUMENTADO  potencia de transmision (eoPortal)

Que no hay: RSSI ni SNR por trama --- SatNOGS no los registra ---, ni el numero
de tramas que el satelite emitio en un pase entero, que es lo que haria falta
para una tasa de error de trama verdadera. La perdida por secuencia es una cota
inferior: solo ve lo que falta *entre* paquetes recibidos de la misma rafaga.

Perdida por secuencia
---------------------
Mismo criterio que `telemetria_strand1/tools/analizar_recepcion.py`, que es el
que respalda la cifra del informe (36,8 %): rafagas por estacion con huecos de
hasta 30 s y saltos de contador de hasta 32; el contador se desenrolla con
signo y se cuentan valores distintos; un contador repetido tras mas de 2 s es
un reinicio del OBC y corta la rafaga en lugar de contarse como perdida.

Estado del enlace en el periodo
-------------------------------
    Sin información suficiente  ni tramas ni observaciones
    Interrumpido                hubo observaciones pero ninguna baliza valida
    Degradado                   la perdida estimada de la mitad reciente supera
                                en 15 puntos a la de referencia (todo lo anterior)
    Activo                      se recibieron balizas validas y no hay degradacion

«Disponible» (el satelite sobrevuela y se podria recibir) exige una prediccion
de pases en vivo; para un archivo historico no se usa. El umbral de 15 puntos
es un criterio de este modulo, no un requisito de la mision.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .alerts import ADVERTENCIA, DESCONOCIDO, NORMAL, Alerta
from .subsystem_monitor import Indicador, InformeSubsistema, informe
from .telemetry_acquisition import (DOCUMENTADO, ESTIMADO, NO_DISPONIBLE, SIMULADO,
                                    ConjuntoTelemetria)

RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "resultados_simulacion"

HUECO_RAFAGA_S = 30
SALTO_MAX = 32
TOLERANCIA_S = 2
DEGRADACION_PUNTOS = 0.15
AUMENTO_ERRORES_PUNTOS = 0.10
ESTADOS_VALIDOS = ("decoded", "partially_decoded")

EXPLICACION = (
    "El satélite envía su información hacia la Tierra con señales de radio. Una estación "
    "terrena la recibe en forma de paquetes: conjuntos organizados de datos, cada uno con su "
    "número de orden. Contando los paquetes que llegan, los que llegan con errores y los "
    "números que faltan se puede saber cómo se comporta el enlace de comunicación."
)

NO_DISPONIBLES_ENLACE = [
    {"clave": "rssi", "nombre": "RSSI (intensidad de señal recibida)", "unidad": "dBm",
     "que_es": "Potencia de la señal de radio que llega a la antena de la estación.",
     "por_que_importa": "Una señal débil se confunde con el ruido y produce errores.",
     "motivo": "SatNOGS no registra la intensidad de la señal por trama."},
    {"clave": "snr", "nombre": "SNR por trama (relación señal-ruido)", "unidad": "dB",
     "que_es": "Cuántas veces es más fuerte la señal que el ruido de fondo.",
     "por_que_importa": "Es el factor que más determina la cantidad de errores.",
     "motivo": "SatNOGS no registra la SNR de cada trama recibida."},
    {"clave": "fer", "nombre": "Tasa de error de trama del pase completo", "unidad": None,
     "que_es": "Fracción de las tramas emitidas en un pase que no llegaron bien.",
     "por_que_importa": "Mide la calidad del enlace de extremo a extremo.",
     "motivo": "Se desconoce cuántas tramas emitió el satélite en cada pase: SatNOGS solo "
               "guarda las que se demodularon."},
]


def perdida_por_secuencia(secuencias: pd.DataFrame | None) -> dict:
    """Paquetes emitidos (estimados), recibidos y perdidos dentro de las rafagas."""
    vacio = {"rafagas": 0, "paquetes_emitidos_estimados": 0, "paquetes_recibidos": 0,
             "paquetes_perdidos": 0, "perdida": None, "tramos": []}
    if secuencias is None or secuencias.empty:
        return vacio
    tramos = []
    for est, g in secuencias.sort_values("timestamp", kind="stable").groupby("estacion", dropna=True):
        if not str(est):
            continue
        ts = g["timestamp"].to_numpy()
        seq = g["seq"].to_numpy(int)
        actual, u = [], 0
        inicio = ts[0]

        def cerrar(fin):
            if len(set(actual)) >= 2:
                tramos.append({"inicio": pd.Timestamp(inicio), "fin": pd.Timestamp(fin),
                               "emitidos": max(actual) - min(actual) + 1,
                               "recibidos": len(set(actual))})

        for i in range(len(seq)):
            if i > 0:
                delta = (seq[i] - seq[i - 1] + 128) % 256 - 128
                gap = (ts[i] - ts[i - 1]) / np.timedelta64(1, "s")
                reinicio = delta == 0 and gap > TOLERANCIA_S
                if gap > HUECO_RAFAGA_S or abs(delta) > SALTO_MAX or reinicio:
                    cerrar(ts[i - 1])
                    actual, u, inicio = [], 0, ts[i]
                else:
                    u += delta
            actual.append(u)
        cerrar(ts[-1])
    emitidos = sum(t["emitidos"] for t in tramos)
    recibidos = sum(t["recibidos"] for t in tramos)
    return {"rafagas": len(tramos), "paquetes_emitidos_estimados": emitidos,
            "paquetes_recibidos": recibidos, "paquetes_perdidos": emitidos - recibidos,
            "perdida": round(1 - recibidos / emitidos, 4) if emitidos else None,
            "tramos": tramos}


def _perdida_de(tramos: list[dict]) -> float | None:
    e = sum(t["emitidos"] for t in tramos)
    return 1 - sum(t["recibidos"] for t in tramos) / e if e else None


def _ber_simulada() -> dict | None:
    ruta = RESULTADOS / "ber_strand1_sweep.csv"
    if not ruta.exists():
        return None
    with ruta.open(encoding="utf-8") as f:
        filas = [{"snr_db": float(r["snr_db"]), "ber_empirica": float(r["ber_empirica"]),
                  "ber_teorica": float(r["ber_teorica"]), "bits": int(r["bits_totales"])}
                 for r in csv.DictReader(f)]
    return {"procedencia": SIMULADO, "puntos": filas,
            "fuente": "resultados_simulacion/ber_strand1_sweep.csv (barrido_ber_strand1.py sobre "
                      "la cadena GNU Radio cadena_strand1_awgn.py)",
            "nota": "BPSK en banda base con ruido AWGN: es un modelo comparativo, no la "
                    "modulación del satélite (FSK 9600). Señal simulada, no recibida."}


def _margen_estimado() -> dict | None:
    ruta = RESULTADOS / "link_budget_completo.json"
    if not ruta.exists():
        return None
    d = json.loads(ruta.read_text(encoding="utf-8"))
    return {"procedencia": ESTIMADO, "esquema": d["resumen"].get("esquema_margen_principal"),
            "por_elevacion": [{"elevacion_deg": r["elevacion_deg"], "margen_db": r["margen_db"]}
                              for r in d["resultados"]],
            "fuente": "resultados_simulacion/link_budget_completo.json (calcular_link_budget.py)",
            "nota": "Predicción del presupuesto de potencia con parámetros documentados y "
                    "supuestos (ver parametros_enlace.py). No es una medida del enlace."}


def _potencia_tx() -> Indicador:
    try:
        import parametros_enlace as pe
        p = pe.PARAMETROS["p_tx_dbm"]
        valor, fuente = p.valor, p.fuente
    except Exception:          # el modulo vive en la raiz del repo
        valor, fuente = 30.0, "eoPortal, «STRaND-1»: 1 W nominal; 0.25 W en modo baliza/CW"
    return Indicador(
        clave="potencia_tx", nombre="Potencia de transmisión", unidad="dBm",
        que_es="Cuánta potencia usa el transmisor para enviar la señal de radio. 30 dBm = 1 W.",
        por_que_importa="A más potencia, la señal llega más fuerte a la estación y hay menos "
                        "errores; pero consume más energía de la batería.",
        procedencia=DOCUMENTADO, estado=DESCONOCIDO,
        estado_motivo="Es un valor de diseño documentado, no una medida: la baliza no informa "
                      "de la potencia emitida.",
        valor=valor, referencia="Valor nominal de la misión", fuente=fuente,
        notas=["En modo baliza/CW la documentación indica 0,25 W (24 dBm); no está confirmado "
               "en qué modo emite la baliza de telemetría."])


def _ind(clave, nombre, unidad, que_es, por_que, procedencia, estado, motivo, valor, **kw):
    return Indicador(clave=clave, nombre=nombre, unidad=unidad, que_es=que_es,
                     por_que_importa=por_que, procedencia=procedencia, estado=estado,
                     estado_motivo=motivo, valor=valor, **kw)


def evaluar(historico: ConjuntoTelemetria, desde: pd.Timestamp | None) -> InformeSubsistema:
    proc = historico.procedencia
    tramas = historico.tramas if historico.tramas is not None else pd.DataFrame(
        columns=["timestamp", "estado"])
    tramas_v = tramas if desde is None else tramas[tramas["timestamp"] >= desde]
    obs = historico.observaciones
    obs_v = None if obs is None else (obs if desde is None else obs[obs["inicio"] >= desde])

    n = len(tramas_v)
    validas = int(tramas_v["estado"].isin(ESTADOS_VALIDOS).sum()) if n else 0
    errores = int((tramas_v["estado"] == "error").sum()) if n else 0
    indicadores = [_potencia_tx()]
    alertas: list[Alerta] = []
    fin = tramas["timestamp"].max() if not tramas.empty else None

    indicadores.append(_ind(
        "tramas_recibidas", "Tramas recibidas", "tramas",
        "Número de paquetes que las estaciones terrenas recibieron en el periodo.",
        "Si no llega nada, no se puede saber nada del satélite.", proc,
        NORMAL if validas else DESCONOCIDO,
        f"{validas} de {n} tramas son balizas decodificables." if n else
        "No se recibió ninguna trama en el periodo.", n))
    pct = round(validas / n * 100, 2) if n else None
    indicadores.append(_ind(
        "recepcion_correcta", "Recepción correcta", "%",
        "Porcentaje de tramas recibidas que se pudieron decodificar.",
        "Mide cuántos de los paquetes que llegan son aprovechables.", proc,
        NORMAL if pct is not None else DESCONOCIDO,
        "Proporción de tramas decodificadas o parcialmente decodificadas." if n else
        "Sin tramas, no hay proporción.", pct,
        estadisticas={"validas": validas, "con_error": errores,
                      "sin_clasificar": n - validas - errores}))

    # Errores: mitad reciente frente a lo anterior.
    estado_err, motivo_err = (NORMAL, "Sin aumento de tramas con error.") if n else (
        DESCONOCIDO, "Sin tramas.")
    if n >= 20:
        corte = tramas_v["timestamp"].min() + (tramas_v["timestamp"].max() - tramas_v["timestamp"].min()) / 2
        recientes = tramas_v[tramas_v["timestamp"] >= corte]
        previas = tramas[tramas["timestamp"] < corte]
        f_rec = float((recientes["estado"] == "error").mean()) if len(recientes) else 0.0
        f_ref = float((previas["estado"] == "error").mean()) if len(previas) else 0.0
        if f_rec - f_ref >= AUMENTO_ERRORES_PUNTOS:
            estado_err = ADVERTENCIA
            motivo_err = (f"Las tramas con error pasan del {f_ref:.1%} al {f_rec:.1%} en la "
                          "mitad reciente del periodo.")
            alertas.append(Alerta(
                subsistema="comunicaciones", variable="tramas_con_error", nivel=ADVERTENCIA,
                mecanismo="tendencia", inicio=pd.Timestamp(corte).isoformat(),
                fin=pd.Timestamp(tramas_v["timestamp"].max()).isoformat(),
                que_ocurrio=f"Aumentó la proporción de tramas con error: {f_rec:.1%} frente al "
                            f"{f_ref:.1%} anterior.",
                componente="Enlace de bajada (satélite → estación)",
                valor_registrado=round(f_rec, 4), unidad="fracción",
                valor_referencia=round(f_ref, 4),
                referencia="Proporción de tramas con error antes de la mitad reciente del periodo "
                           f"(aviso si sube {AUMENTO_ERRORES_PUNTOS:.0%} o más; criterio del HMTA).",
                por_que_importa="Más errores significan menos información útil y pueden indicar "
                                "una señal más débil o interferencias.",
                informacion_adicional="Comparar por estación: un aumento ligado a una sola "
                                      "estación apunta a la estación, no al satélite.",
                procedencia=proc, lecturas=len(recientes)))
    indicadores.append(_ind(
        "tramas_con_error", "Tramas con error", "tramas",
        "Paquetes que llegaron pero no se pudieron interpretar por errores.",
        "Un aumento de errores puede indicar que la señal llega más débil.", proc,
        estado_err, motivo_err, errores))

    # Perdida de paquetes por secuencia.
    sec = historico.secuencias
    sec_v = None if sec is None else (sec if desde is None else sec[sec["timestamp"] >= desde])
    perd = perdida_por_secuencia(sec_v)
    tramos = perd.pop("tramos")
    estado_p = NORMAL if perd["perdida"] is not None else DESCONOCIDO
    motivo_p = ("Cota inferior de la pérdida: solo cuenta lo que falta entre paquetes recibidos "
                "de una misma ráfaga." if perd["perdida"] is not None else
                "No hay ráfagas con al menos dos paquetes para estimar la pérdida.")
    degradado = False
    referencia_p = None
    if len(tramos) >= 4:
        corte = tramos[len(tramos) // 2]["inicio"]
        recientes = [t for t in tramos if t["inicio"] >= corte]
        previos_todo = perdida_por_secuencia(sec[sec["timestamp"] < corte]) if sec is not None else None
        previos = previos_todo["tramos"] if previos_todo else []
        p_rec, p_ref = _perdida_de(recientes), _perdida_de(previos)
        referencia_p = p_ref
        if p_rec is not None and p_ref is not None and p_rec - p_ref >= DEGRADACION_PUNTOS:
            degradado = True
            estado_p = ADVERTENCIA
            motivo_p = (f"La pérdida estimada sube del {p_ref:.1%} al {p_rec:.1%} en la mitad "
                        "reciente del periodo.")
            alertas.append(Alerta(
                subsistema="comunicaciones", variable="perdida_paquetes", nivel=ADVERTENCIA,
                mecanismo="tendencia", inicio=pd.Timestamp(corte).isoformat(),
                fin=pd.Timestamp(recientes[-1]["fin"]).isoformat(),
                que_ocurrio=f"Se pierden más paquetes: {p_rec:.1%} estimado frente a {p_ref:.1%} "
                            "de referencia.",
                componente="Enlace de bajada (satélite → estación)",
                valor_registrado=round(p_rec, 4), unidad="fracción",
                valor_referencia=round(p_ref, 4),
                referencia="Pérdida por contador de secuencia de todo lo anterior a la mitad "
                           f"reciente (aviso si sube {DEGRADACION_PUNTOS:.0%} o más; criterio del HMTA).",
                por_que_importa="Si se pierden demasiados paquetes, se pierde la información de "
                                "estado del satélite que viajaba en ellos.",
                informacion_adicional="Revisar la elevación de los pases y qué estaciones "
                                      "recibieron: la pérdida depende también de la estación.",
                procedencia=ESTIMADO, lecturas=perd["paquetes_recibidos"]))
    indicadores.append(_ind(
        "perdida_paquetes", "Paquetes perdidos (estimado)", "%",
        "Paquetes que faltan entre los recibidos, deducidos del número de orden de cada paquete.",
        "Indica si el enlace deja escapar información.", ESTIMADO, estado_p, motivo_p,
        round(perd["perdida"] * 100, 2) if perd["perdida"] is not None else None,
        estadisticas={**perd, "referencia_perdida": (round(referencia_p, 4)
                                                     if referencia_p is not None else None)},
        referencia="Hipótesis: el contador de 8 bits sube 1 por paquete emitido "
                   "(analizar_recepcion.py)."))

    # Observaciones.
    n_obs = len(obs_v) if obs_v is not None else 0
    buenas = int((obs_v["estado"] == "good").sum()) if n_obs else 0
    malas = int((obs_v["estado"] == "bad").sum()) if n_obs else 0
    indicadores.append(_ind(
        "observaciones", "Pases observados", "pases",
        "Veces que una estación de la red SatNOGS apuntó al satélite para escucharlo.",
        "Sin pases observados no puede llegar ningún dato.",
        proc, NORMAL if n_obs else DESCONOCIDO,
        f"{buenas} pases con señal válida y {malas} sin señal útil, según SatNOGS." if n_obs
        else "No hay observaciones registradas en el periodo.", n_obs,
        estadisticas={"good": buenas, "bad": malas, "otros": n_obs - buenas - malas}))

    # Estado del enlace.
    if n == 0 and n_obs == 0:
        enlace = "Sin información suficiente"
    elif validas == 0:
        enlace = "Interrumpido"
        alertas.append(Alerta(
            subsistema="comunicaciones", variable="balizas_validas", nivel=ADVERTENCIA,
            mecanismo="comunicaciones",
            inicio=(desde.isoformat() if desde is not None else "inicio"),
            fin=(fin.isoformat() if fin is not None else "fin"),
            que_ocurrio=f"Hubo {n_obs} pases observados y {n} tramas, pero ninguna baliza válida.",
            componente="Enlace de bajada (satélite → estación)", valor_registrado=0,
            unidad="balizas", valor_referencia="≥ 1",
            referencia="Una observación con éxito entrega al menos una baliza decodificable.",
            por_que_importa="Sin balizas no hay telemetría: no se puede supervisar el satélite.",
            informacion_adicional="La causa puede ser la estación, la geometría del pase o que el "
                                  "transmisor esté apagado (SatNOGS lo marca «inactive»). No "
                                  "demuestra por sí sola un fallo del satélite.",
            procedencia=proc, lecturas=n_obs))
    elif degradado:
        enlace = "Degradado"
    else:
        enlace = "Activo"
    indicadores.append(_ind(
        "estado_enlace", "Estado del enlace en el periodo", None,
        "Resumen de si llegaron datos y con qué calidad.",
        "Es la primera pregunta: ¿se está oyendo al satélite?",
        proc, {"Activo": NORMAL, "Degradado": ADVERTENCIA, "Interrumpido": ADVERTENCIA}
        .get(enlace, DESCONOCIDO), _MOTIVO_ENLACE[enlace], enlace))

    extra = {"estado_enlace": enlace,
             "ultima_trama": fin.isoformat() if fin is not None else None,
             "simulacion_ber": _ber_simulada(),
             "margen_enlace": _margen_estimado(),
             "tipo_de_senal": {
                 "REAL": "Tramas recibidas por estaciones de SatNOGS (comunicación real "
                         "documentada, ya terminada).",
                 "SIMULADO": "Escenario de prueba o cadena GNU Radio: ninguna señal real.",
             }[proc] if proc in ("REAL", "SIMULADO") else proc}
    inf = informe("comunicaciones", EXPLICACION, indicadores, alertas, extra=extra,
                  presentes={i.clave for i in indicadores})
    inf.no_disponibles += [{**d, "procedencia": NO_DISPONIBLE, "disponibilidad": "no_existe",
                            "notas": [], "nodo_canal": None} for d in NO_DISPONIBLES_ENLACE]
    if NO_DISPONIBLE not in inf.procedencias:
        inf.procedencias = sorted(set(inf.procedencias) | {NO_DISPONIBLE})
    inf.procedencias = sorted(set(inf.procedencias) | {DOCUMENTADO, ESTIMADO, SIMULADO})
    return inf


_MOTIVO_ENLACE = {
    "Activo": "Se recibieron balizas válidas y la pérdida no empeora.",
    "Degradado": "Se reciben balizas, pero la pérdida estimada empeora en la mitad reciente.",
    "Interrumpido": "Hubo intentos de recepción sin ninguna baliza válida.",
    "Sin información suficiente": "No hay tramas ni observaciones en el periodo. Ausencia de "
                                  "datos no es lo mismo que un fallo.",
}
