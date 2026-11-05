"""Deteccion de anomalias: cinco mecanismos, cada uno con su referencia explicita.

    A. Limites          comparacion con rangos documentados (`Limite`, con fuente)
    B. Tendencias       regresion lineal sobre el periodo, con prueba de significancia
    C. Modelo           respuesta medida frente a la de un modelo dinamico (PID)
    D. Validacion       lecturas que no son medidas (ver `telemetry_validation`)
    E. Registro         las alertas se guardan con `alerts.RegistroEventos`

Ademas, la **desviacion respecto al historial propio** (z robusto, mediana +
MAD) se toma tal cual de `gemelo_digital.anomalias`, que ya resolvia el
problema de los datos irregulares; aqui solo se traduce su salida a alertas.

Lo que este modulo no hace es declarar averias. CRITICO solo sale del
mecanismo A, y solo con un limite cuya fuente lo acredite como critico. Para
STRaND-1 no hay ninguno documentado (ver `catalogo`), asi que sobre datos
reales ninguna alerta llega a CRITICO: una desviacion de 6 sigmas sigue siendo
una ADVERTENCIA, porque sin especificacion del componente no hay base para mas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gemelo_digital import anomalias as _anom

from . import pid_reference as pid
from .alerts import ADVERTENCIA, CRITICO, Alerta
from .telemetry_acquisition import Limite

# Tendencia: minimo de lecturas y significancia exigida a la pendiente.
MIN_LECTURAS_TENDENCIA = 20
T_MIN_TENDENCIA = 5.0          # |pendiente| / error tipico
# Una pendiente ajustada sobre lecturas de un solo pase extrapola a «V/dia» lo
# que es una variacion de minutos. Se exige recorrido y varios pases.
MIN_DIAS_TENDENCIA = 1.0
MIN_PASES_TENDENCIA = 3
HUECO_PASE = pd.Timedelta("30min")
CAMBIO_MIN_SIGMAS = 2.0        # el cambio en el periodo debe superar 2 sigmas del residuo
UNIDADES_TENDENCIA = ("V", "°C")

# Comparacion con modelo: RMS del residuo normalizado por el valor final de
# referencia. Es un parametro de la comparacion elegido para este modulo, no
# un limite del satelite: con ruido de medida del 1 % el residuo tipico es
# ~0,01, y 0,05 deja margen de sobra antes de dar el aviso.
TOLERANCIA_MODELO = 0.05

# Desviacion: un evento necesita persistir. Con miles de lecturas, un |z| de
# 3,5 aislado aparece por puro azar (lo produce el escenario nominal); solo se
# avisa si dura al menos 3 lecturas seguidas o si una sola llega a |z| >= 6.
MIN_LECTURAS_DESVIACION = 3


def _iso(t) -> str:
    return pd.Timestamp(t).isoformat()


# ─── A. Limites ─────────────────────────────────────────────────────────────

def comparar_limites(valores: pd.Series, limites: list[Limite], *, subsistema: str,
                     componente: str, unidad: str | None, por_que: str,
                     procedencia: str) -> list[Alerta]:
    fuera = []
    for lim in limites:
        bajo = valores < lim.minimo if lim.minimo is not None else pd.Series(False, index=valores.index)
        alto = valores > lim.maximo if lim.maximo is not None else pd.Series(False, index=valores.index)
        sel = valores[bajo | alto]
        if sel.empty:
            continue
        extremo = float(sel.max() if alto.any() else sel.min())
        rango = f"[{lim.minimo if lim.minimo is not None else '−∞'}, " \
                f"{lim.maximo if lim.maximo is not None else '+∞'}] {unidad or ''}".strip()
        fuera.append(Alerta(
            subsistema=subsistema, variable=lim.variable, nivel=lim.nivel, mecanismo="limite",
            inicio=_iso(sel.index.min()), fin=_iso(sel.index.max()),
            que_ocurrio=f"{len(sel)} lecturas fuera del rango de referencia {rango}.",
            componente=componente, valor_registrado=round(extremo, 4), unidad=unidad,
            valor_referencia=rango, referencia=lim.fuente, por_que_importa=por_que,
            informacion_adicional="Confirmar el rango en la hoja de datos del componente y "
                                  "revisar si la lectura coincide con otros sensores.",
            procedencia=procedencia, lecturas=len(sel),
            detalle={"nivel_limite": lim.nivel, "minimo": lim.minimo, "maximo": lim.maximo}))
    # El limite critico manda: si se cruza, la advertencia del mismo tramo sobra.
    if any(a.nivel == CRITICO for a in fuera):
        fuera = [a for a in fuera if a.nivel == CRITICO]
    return fuera


# ─── B. Tendencias ──────────────────────────────────────────────────────────

def tendencia(valores: pd.Series) -> dict | None:
    """Pendiente por dia, cambio en el periodo y si es significativa."""
    v = valores.dropna()
    if len(v) < MIN_LECTURAS_TENDENCIA:
        return None
    x = (v.index - v.index[0]).total_seconds().to_numpy() / 86400.0
    pases = int((v.index.to_series().diff() > HUECO_PASE).sum()) + 1
    if x[-1] < MIN_DIAS_TENDENCIA or pases < MIN_PASES_TENDENCIA:
        return None
    y = v.to_numpy(float)
    pendiente, ordenada = np.polyfit(x, y, 1)
    residuo = y - (pendiente * x + ordenada)
    sxx = np.sum((x - x.mean()) ** 2)
    sigma = float(np.sqrt(np.sum(residuo ** 2) / (len(y) - 2)))
    error = sigma / np.sqrt(sxx) if sxx > 0 else np.inf
    t_est = abs(pendiente) / error if error > 0 else np.inf
    cambio = float(pendiente * x[-1])
    significativa = bool(t_est >= T_MIN_TENDENCIA and abs(cambio) >= CAMBIO_MIN_SIGMAS * sigma)
    return {"pendiente_por_dia": float(pendiente), "cambio_en_periodo": cambio,
            "sigma_residuo": sigma, "t": float(t_est), "dias": float(x[-1]), "pases": pases,
            "lecturas": len(y), "significativa": significativa,
            "inicial": float(ordenada), "final": float(pendiente * x[-1] + ordenada)}


def alerta_tendencia(valores: pd.Series, *, subsistema: str, variable: str, componente: str,
                     unidad: str | None, por_que: str, procedencia: str) -> Alerta | None:
    if unidad not in UNIDADES_TENDENCIA:
        return None
    t = tendencia(valores)
    if t is None or not t["significativa"]:
        return None
    sentido = "un aumento progresivo" if t["cambio_en_periodo"] > 0 else "una disminución progresiva"
    u = unidad or ""
    return Alerta(
        subsistema=subsistema, variable=variable, nivel=ADVERTENCIA, mecanismo="tendencia",
        inicio=_iso(valores.index.min()), fin=_iso(valores.index.max()),
        que_ocurrio=f"Se detectó {sentido} de {abs(t['cambio_en_periodo']):.3g} {u} "
                    f"en {t['dias']:.1f} días ({t['pendiente_por_dia']:+.3g} {u}/día).",
        componente=componente, valor_registrado=round(t["final"], 4), unidad=unidad,
        valor_referencia=round(t["inicial"], 4),
        referencia="Valor ajustado al inicio del periodo (regresión lineal sobre las lecturas "
                   "válidas); la pendiente es significativa (|t| ≥ 5).",
        por_que_importa=por_que,
        informacion_adicional="Comparar con periodos anteriores y con la iluminación y la "
                              "estación del año, que también producen cambios lentos.",
        procedencia=procedencia, lecturas=t["lecturas"],
        detalle={k: round(v, 6) if isinstance(v, float) else v for k, v in t.items()})


# ─── Desviacion respecto al historial (gemelo_digital.anomalias) ───────────

def desviaciones(valores: pd.Series, desde: pd.Timestamp | None, *, subsistema: str,
                 variable: str, componente: str, unidad: str | None, por_que: str,
                 procedencia: str) -> tuple[list[Alerta], pd.DataFrame]:
    """Z robusto sobre las lecturas validas; alertas solo desde `desde`.

    La serie que entra llega hasta el final del periodo pero empieza antes: la
    referencia de cada punto son las lecturas previas, y al principio del
    periodo esas lecturas estan fuera de el.
    """
    v = valores.dropna().astype("float64")
    v = v[~v.index.duplicated(keep="last")]
    if len(v) < _anom.VENTANA // 2:
        return [], pd.DataFrame()
    out = _anom.zscore_robusto(v)
    out["valor"] = v
    span = v.index.to_series().diff(_anom.VENTANA - 1)
    sin_ref = (span > _anom.MAX_SPAN_VENTANA) | out["mediana"].isna()
    et = pd.Series("normal", index=v.index, dtype="object")
    et[out["z"].abs() >= _anom.UMBRAL_ADVERTENCIA] = "advertencia"
    et[out["z"].abs() >= _anom.UMBRAL_ANOMALIA] = "anomalia"
    et[sin_ref] = "sin_referencia"
    out["etiqueta"] = et
    eventos = [ev for ev in _anom.eventos(out, variable, de_interes=("advertencia", "anomalia"))
               if (desde is None or pd.Timestamp(ev.fin) >= desde)
               and (ev.n_lecturas >= MIN_LECTURAS_DESVIACION or ev.etiqueta == "anomalia")]
    # Episodios: eventos separados menos de un dia son el mismo suceso. Sin
    # esto, la fase intermitente de 2020-11 a 2021-01 da cientos de alertas
    # de pocas lecturas cada una, que juntas cuentan una sola historia.
    episodios: list[list] = []
    for ev in eventos:
        if episodios and (pd.Timestamp(ev.inicio) - pd.Timestamp(episodios[-1][-1].fin)
                          <= _anom.MAX_HUECO_EVENTO):
            episodios[-1].append(ev)
        else:
            episodios.append([ev])
    fuera = []
    u = unidad or ""
    for ep in episodios:
        peor_ev = max(ep, key=lambda e: e.z_max if np.isfinite(e.z_max) else 0)
        fuerte = any(e.etiqueta == "anomalia" for e in ep)
        lecturas = sum(e.n_lecturas for e in ep)
        tramos = f" en {len(ep)} tramos" if len(ep) > 1 else ""
        fuera.append(Alerta(
            subsistema=subsistema, variable=variable, nivel=ADVERTENCIA, mecanismo="desviacion",
            inicio=ep[0].inicio, fin=ep[-1].fin,
            que_ocurrio=(f"{'Fuerte d' if fuerte else 'D'}esviación respecto al comportamiento "
                         f"reciente: {lecturas} lecturas{tramos} con |z| hasta {peor_ev.z_max}."),
            componente=componente, valor_registrado=peor_ev.valor_registrado, unidad=unidad,
            valor_referencia=peor_ev.valor_esperado,
            referencia=f"Mediana de las {_anom.VENTANA} lecturas válidas anteriores "
                       f"(z robusto, mediana ± 1,4826·MAD; aviso desde |z| ≥ "
                       f"{_anom.UMBRAL_ADVERTENCIA}). No es un límite del fabricante.",
            por_que_importa=por_que,
            informacion_adicional=(f"Diferencia {peor_ev.diferencia:+} {u} en el tramo más "
                                   "desviado. Comprobar si coincide con un cambio de iluminación, "
                                   "de estación receptora o con lecturas de otros canales en el "
                                   "mismo pase."),
            procedencia=procedencia, lecturas=lecturas,
            detalle={"z_max": peor_ev.z_max, "diferencia": peor_ev.diferencia,
                     "tramos": len(ep), "etiqueta_gemelo": peor_ev.etiqueta}))
    return fuera, out


# ─── C. Comparacion con modelo dinamico ────────────────────────────────────

def comparar_con_modelo(t: np.ndarray, y: np.ndarray, planta: str, controlador: str,
                        procedencia: str, tolerancia: float = TOLERANCIA_MODELO) -> dict:
    """Residuo entre una respuesta medida y la del lazo de referencia."""
    ref = pid.respuesta(planta, controlador)
    y_ref = np.interp(t, ref.t, ref.y)
    escala = abs(ref.valor_final) if ref.valor_final else 1.0
    residuo = (np.asarray(y, float) - y_ref) / escala
    rms = float(np.sqrt(np.mean(residuo ** 2)))
    i_max = int(np.argmax(np.abs(residuo)))
    m_ref = pid.metricas(ref)
    sobrepaso_med = float(max(0.0, (np.max(y) - escala) / escala * 100))
    resultado = {
        "planta": planta, "controlador": controlador, "procedencia_medida": procedencia,
        "rms_residuo_normalizado": round(rms, 5), "tolerancia": tolerancia,
        "max_residuo": round(float(residuo[i_max]), 5), "t_max_residuo": round(float(t[i_max]), 4),
        "sobrepaso_medido_pct": round(sobrepaso_med, 2),
        "sobrepaso_modelo_pct": m_ref["sobrepaso_pct"],
        "fuera_de_tolerancia": rms > tolerancia,
        "referencia": [{"t": round(float(a), 4), "y": round(float(b), 5)}
                       for a, b in zip(t[::5], y_ref[::5])],
        "medida": [{"t": round(float(a), 4), "y": round(float(b), 5)}
                   for a, b in zip(t[::5], np.asarray(y)[::5])],
    }
    alerta = None
    if resultado["fuera_de_tolerancia"]:
        alerta = Alerta(
            subsistema="anomalias", variable=f"respuesta_{planta}_{controlador}",
            nivel=ADVERTENCIA, mecanismo="modelo", inicio="t=0 s", fin=f"t={t[-1]:.2f} s",
            que_ocurrio=f"La respuesta medida se aparta del modelo de referencia: residuo RMS "
                        f"{rms:.3f} (tolerancia {tolerancia}). Sobrepaso medido "
                        f"{sobrepaso_med:.1f} % frente a {m_ref['sobrepaso_pct']} % del modelo.",
            componente=f"Lazo de referencia {planta} con controlador {controlador}",
            valor_registrado=round(rms, 4), unidad=None, valor_referencia=tolerancia,
            referencia=f"Respuesta al escalón del modelo {pid.PLANTAS[planta]['expresion']} con "
                       f"{controlador} de Ziegler–Nichols (pid_reference).",
            por_que_importa="Una respuesta dinámica distinta de la esperada puede indicar que la "
                            "planta ha cambiado (ganancia, retardo) o que el modelo no la describe.",
            informacion_adicional="Identificar la planta real con un ensayo independiente; el "
                                  "modelo G1/G2 no está identificado con ningún subsistema de STRaND-1.",
            procedencia=procedencia, lecturas=len(t),
            detalle={k: v for k, v in resultado.items() if k not in ("referencia", "medida")})
    resultado["alerta"] = alerta
    return resultado


# ─── D. Validacion ──────────────────────────────────────────────────────────

MOTIVOS_CON_ALERTA = {
    "canal_sin_medida": "El canal dejó de medir (cuenta del convertidor en 0).",
    "escala_completa": "El convertidor está saturado en su máximo (1023 cuentas).",
    "canal_enrielado": "La magnitud dejó de variar: el sensor parece no estar midiendo.",
    "fuera_rango_fisico": "Lecturas físicamente imposibles.",
}


def alertas_validacion(hallazgos, *, subsistema: str, componente: str, unidad: str | None,
                       procedencia: str, referencia_recta: float | None) -> list[Alerta]:
    fuera = []
    for h in hallazgos:
        if h.tipo not in MOTIVOS_CON_ALERTA:
            continue
        fuera.append(Alerta(
            subsistema=subsistema, variable=h.variable, nivel=ADVERTENCIA, mecanismo="validacion",
            inicio=h.primera, fin=h.ultima,
            que_ocurrio=f"{MOTIVOS_CON_ALERTA[h.tipo]} {h.lecturas} lecturas afectadas.",
            componente=componente, valor_registrado=h.tipo, unidad=unidad,
            valor_referencia=referencia_recta if referencia_recta is not None else "—",
            referencia="Recta de calibración de AMSAT-UK y dominio del ADC de 10 bits (0-1023)"
                       if referencia_recta is not None else "Reglas de validación del HMTA",
            por_que_importa="Una lectura que no es una medida puede parecer un valor sano: el "
                            "voltaje de un canal muerto sale 9,75 V. Sin esta regla se tomaría "
                            "la pérdida del sensor por una batería en perfecto estado.",
            informacion_adicional=h.explicacion + " Hace falta otra fuente (otro canal, otra "
                                  "estación) para saber qué hacía la magnitud real.",
            procedencia=procedencia, lecturas=h.lecturas, detalle={"motivo": h.tipo}))
    return fuera
