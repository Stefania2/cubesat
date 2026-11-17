"""Consultas de solo lectura que LIRA puede hacer, con la procedencia de cada valor.

Todas leen el archivo sellado de `validacion_cientifica` (mismos datos que el
gemelo, sin base de datos ni red) y el catalogo de variables del HMTA. Ninguna
calcula nada nuevo: llaman a las funciones que ya usa la plataforma —
reconstruccion por ultimo valor conocido, diagnostico de `gemelo_digital`,
tendencia del HMTA, SGP4 de `orbita_sgp4`— y devuelven su resultado.

Cada respuesta dice que es: MEDIDO (baliza real), CALCULADO (modelo),
DERIVADO (estadistico), SIMULADO o NO_DISPONIBLE. Una variable que STRaND-1
nunca emitio devuelve NO_DISPONIBLE con el motivo, jamas un cero.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

REAL, CALCULADO, DERIVADO, NO_DISPONIBLE = "MEDIDO", "CALCULADO", "DERIVADO", "NO_DISPONIBLE"
FUENTE = ("Balizas de STRaND-1 recibidas por SatNOGS (archivo sellado de la plataforma), "
          "decodificadas con la especificación de AMSAT-UK")


class ConsultaInvalida(ValueError):
    pass


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


# ── Catalogo y sinonimos ────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _catalogo():
    from health_monitor import catalogo

    return catalogo


SINONIMOS: dict[str, tuple[str, ...]] = {
    "temperatura": ("battery_temperature", "panel_temperature", "electronics_temperature"),
    "termico": ("battery_temperature", "panel_temperature", "electronics_temperature"),
    "voltaje": ("battery_0_voltage", "battery_1_voltage"),
    "tension": ("battery_0_voltage", "battery_1_voltage"),
    "bateria": ("battery_0_voltage", "battery_1_voltage", "battery_current", "state_of_charge"),
    "corriente": ("adc1_py_array_current", "adc4_my_array_current", "adc7_mx_array_current",
                  "adc10_pz_array_current", "adc13_px_array_current", "adc31_mz_array_current",
                  "battery_current", "bus_current"),
    "panel": ("adc1_py_array_current", "adc4_my_array_current", "adc7_mx_array_current",
              "adc10_pz_array_current", "adc13_px_array_current", "adc31_mz_array_current"),
    "potencia": ("power",),
    "energia": ("battery_0_voltage", "battery_1_voltage", "power", "state_of_charge"),
    "carga": ("state_of_charge",),
    "actitud": ("attitude",),
    "orientacion": ("attitude",),
    "velocidad angular": ("angular_rate",),
    "giro": ("angular_rate",),
    "magnetometro": ("magnetometer_x", "magnetometer_y", "magnetometer_z"),
    "ruedas": ("reaction_wheels_switch",),
    "reloj": ("obc_unix_time",),
    "procesador": ("cpu_load",),
    "cpu": ("cpu_load",),
    "memoria": ("memory_use",),
    "reinicio": ("reboots",),
}


def resolver(nombre: str) -> list:
    """Variables del catalogo a las que se refiere un nombre o sinonimo."""
    cat = _catalogo().VARIABLES
    n = _norm(nombre)
    if nombre in cat:
        return [cat[nombre]]
    for v in cat.values():
        if nombre in v.campos:
            return [v]
    claves: list[str] = []
    for sin, ks in SINONIMOS.items():
        if sin in n:
            claves += [k for k in ks if k not in claves]
    if not claves:
        claves = [k for k, v in cat.items() if n and n in _norm(v.nombre)]
    return [cat[k] for k in claves if k in cat]


# ── Instante de referencia ──────────────────────────────────────────────────

def _motor():
    from validacion_cientifica import reconstruccion as R

    return R._motor()


def instante(fecha: str | None) -> pd.Timestamp:
    """El instante pedido, o el ultimo evento del archivo si no se pide ninguno."""
    from validacion_cientifica.tiempo import FechaInvalida, instante_utc

    if not fecha:
        return _motor()["eventos"][-1]
    try:
        return instante_utc(fecha, exigir_zona=False)
    except FechaInvalida as exc:
        raise ConsultaInvalida(str(exc)) from exc


def _iso(t) -> str | None:
    from validacion_cientifica.tiempo import iso

    return iso(t)


def _validez(campo: str, valor: Any) -> str | None:
    """Advierte si el valor es la ordenada de su recta (cuenta ADC 0): no es una medida."""
    from validacion_cientifica import procedencia as P

    cal = P.amsat().calibraciones()
    c = cal.get(campo)
    if c and isinstance(valor, (int, float)) and valor == c["c"]:
        return (f"Vale exactamente la ordenada de la recta ({c['c']:g} {c['unidad']}): la cuenta del "
                "ADC es 0, el canal no está midiendo. No es una medida física.")
    return None


def _lectura(campo: str, t: pd.Timestamp) -> dict:
    from validacion_cientifica import reconstruccion as R

    s = _motor()["series"].get(campo)
    if s is None:
        return {"campo": campo, "estado": NO_DISPONIBLE, "valor": None,
                "nota": "STRaND-1 no emitió este campo en ninguna baliza archivada."}
    l = R._lectura(campo, s, t)
    out = {k: l.get(k) for k in ("campo", "valor", "unidad", "medida_utc", "desfase_s", "frescura",
                                 "asociacion", "trama_id")}
    if l.get("desfase_s") is not None:
        # La misma cantidad en las unidades en que se dice: el verificador de cifras
        # solo acepta numeros que aparezcan en los resultados.
        out["desfase_horas"] = round(l["desfase_s"] / 3600, 2)
        out["desfase_dias"] = round(l["desfase_s"] / 86400, 2)
    out["naturaleza"] = REAL if l["valor"] is not None else NO_DISPONIBLE
    aviso = _validez(campo, l["valor"])
    if aviso:
        out["validez"] = aviso
    if l["valor"] is not None and l.get("frescura") != "fresca":
        out["nota"] = (f"Última medición {l['desfase_s'] / 86400:.1f} días antes del instante: "
                       "describe el pasado del satélite, no su estado en ese instante.")
    if l["valor"] is None:
        out["nota"] = "No hay ninguna medición anterior al instante."
    return out


# ── Consultas ───────────────────────────────────────────────────────────────

def consultar_variable(nombre: str, fecha: str | None = None) -> dict:
    """Valor de una variable (o de las que abarca un sinonimo) en un instante."""
    variables = resolver(nombre)
    if not variables:
        disponibles = sorted(SINONIMOS)
        return {"consulta": nombre, "estado": NO_DISPONIBLE, "variables": [],
                "nota": f"No reconozco «{nombre}» como variable de STRaND-1. Puedo consultar: "
                        + ", ".join(disponibles) + "."}
    t = instante(fecha)
    fichas = []
    for v in variables:
        ficha = {"clave": v.clave, "nombre": v.nombre, "subsistema": v.subsistema, "unidad": v.unidad,
                 "disponibilidad": v.disponibilidad}
        if v.disponibilidad == "emitida":
            ficha["lecturas"] = [_lectura(c, t) for c in v.campos]
        else:
            motivo = {"definida_no_emitida": "La hoja de AMSAT-UK define el canal, pero STRaND-1 nunca lo "
                                             "emitió en las balizas archivadas.",
                      "no_existe": "Ningún canal de STRaND-1 mide esta magnitud.",
                      "derivada": "Se calcularía a partir de otras variables que no están disponibles."
                      }.get(v.disponibilidad, "No disponible.")
            ficha.update({"estado": NO_DISPONIBLE, "valor": None, "nota": motivo})
        fichas.append(ficha)
    return {"consulta": nombre, "instante_utc": _iso(t), "fuente": FUENTE, "variables": fichas}


def explicar_variable(nombre: str) -> dict:
    variables = resolver(nombre)
    if not variables:
        return {"consulta": nombre, "estado": NO_DISPONIBLE, "nota": f"No reconozco «{nombre}»."}
    return {"consulta": nombre, "variables": [
        {"nombre": v.nombre, "unidad": v.unidad, "que_es": v.que_es, "por_que_importa": v.por_que_importa,
         "disponibilidad": v.disponibilidad, "fuente": v.fuente, "notas": list(v.notas)} for v in variables]}


CAMPOS_RESUMEN = ("battery_voltage", "adc1_py_array_current", "adc4_my_array_current",
                  "adc7_mx_array_current", "adc10_pz_array_current", "adc13_px_array_current",
                  "adc31_mz_array_current", "magnetometer_x", "magnetometer_y", "magnetometer_z")


def estado_en_instante(fecha: str | None = None) -> dict:
    """Resumen del CubeSat en un instante: lecturas, diagnostico, orbita y lo que no existe."""
    from validacion_cientifica import reconstruccion as R

    t = instante(fecha)
    rec = R.reconstruir(_iso(t))
    lect = {l["campo"]: l for l in rec["telemetria"]["lecturas"]}
    lecturas = [_lectura(c, t) for c in CAMPOS_RESUMEN if c in lect]
    interruptores = [{"campo": c, "valor": l["valor"], "medida_utc": l["medida_utc"], "naturaleza": REAL}
                     for c, l in lect.items() if l["tipo"] == "discreto" and l["valor"] is not None]
    orb = rec["orbita"]
    prop = orb.get("propagacion") or {}
    terrestre = prop.get("terrestre") or {}
    return {
        "instante_utc": rec["instante_utc"], "fuente": FUENTE,
        "lecturas": lecturas, "interruptores": interruptores,
        "diagnostico": {k: rec["diagnostico"].get(k) for k in
                        ("campo", "etiqueta", "interpretacion", "z", "lectura_diagnosticada_utc")}
                       | {"naturaleza": DERIVADO,
                          "nota": "Diagnóstico estadístico (mediana móvil y MAD); no confirma fallas."},
        "orbita": {"estado": orb["estado"], "antiguedad_tle_dias": orb.get("antiguedad_dias"),
                   "latitud_deg": terrestre.get("latitud_deg"), "longitud_deg": terrestre.get("longitud_deg"),
                   "altura_km": terrestre.get("altura_km"), "rapidez_km_s": prop.get("rapidez_km_s"),
                   "hemisferios": _hemisferios(terrestre.get("latitud_deg"), terrestre.get("longitud_deg")),
                   "naturaleza": CALCULADO,
                   "nota": orb["evaluacion_antiguedad"]["detalle"]},
        "no_disponible": ["temperaturas (nunca emitidas)", "actitud y velocidad angular (no se transmiten)",
                          "corrientes de batería y de bus (nunca emitidas)", "potencia y estado de carga"],
    }


def estado_subsistema(subsistema: str, fecha: str | None = None) -> dict:
    cat = _catalogo()
    s = _norm(subsistema)
    alias = {"energia": "eps", "potencia": "eps", "eps": "eps", "termico": "termico", "temperatura": "termico",
             "comunicaciones": "comunicaciones", "enlace": "comunicaciones", "obc": "obc",
             "computador": "obc", "adcs": "adcs", "actitud": "adcs", "orientacion": "adcs"}
    clave = next((v for k, v in alias.items() if k in s), None)
    if clave is None:
        raise ConsultaInvalida(f"Subsistema «{subsistema}» desconocido. Opciones: "
                               + ", ".join(cat.SUBSISTEMAS) + ".")
    t = instante(fecha)
    vars_ = [v for v in cat.VARIABLES.values() if v.subsistema == clave]
    fichas = []
    for v in vars_:
        fichas += consultar_variable(v.clave, _iso(t))["variables"]
    out = {"subsistema": clave, "descripcion": cat.SUBSISTEMAS[clave], "instante_utc": _iso(t),
           "variables": fichas}
    if clave == "comunicaciones":
        out["nota"] = ("El enlace se caracteriza con las observaciones reales de SatNOGS (página "
                       "Observaciones) y con la simulación RF (página Enlace RF, datos SIMULADOS).")
    return out


def _serie(campo: str, desde: str | None, hasta: str | None) -> pd.Series:
    from validacion_cientifica.tiempo import FechaInvalida, instante_utc

    campos = _motor()["campos"]
    if campo not in set(campos["field_name"].astype(str)):
        variables = resolver(campo)
        cand = [c for v in variables for c in v.campos if c in set(campos["field_name"].astype(str))]
        if not cand:
            raise ConsultaInvalida(f"«{campo}» no tiene serie en el archivo (no emitida o desconocida).")
        campo = cand[0]
    s = campos[campos["field_name"] == campo].set_index("timestamp")["value_numeric"].astype(float).sort_index()
    try:
        if desde:
            s = s[s.index >= instante_utc(desde, exigir_zona=False)]
        if hasta:
            s = s[s.index <= instante_utc(hasta, exigir_zona=False)]
    except FechaInvalida as exc:
        raise ConsultaInvalida(str(exc)) from exc
    s.name = campo
    return s


def _describir(s: pd.Series) -> dict:
    if s.empty:
        return {"lecturas": 0, "estado": NO_DISPONIBLE, "nota": "Sin lecturas en el intervalo."}
    from validacion_cientifica import procedencia as P

    c = P.amsat().calibraciones().get(str(s.name))
    en_ordenada = int((s == c["c"]).sum()) if c else 0
    return {"lecturas": int(len(s)), "desde": _iso(s.index[0]), "hasta": _iso(s.index[-1]),
            "mediana": round(float(s.median()), 4), "minimo": round(float(s.min()), 4),
            "maximo": round(float(s.max()), 4), "lecturas_en_la_ordenada": en_ordenada,
            "naturaleza": DERIVADO}


def tendencia(campo: str, desde: str | None = None, hasta: str | None = None) -> dict:
    """Tendencia lineal con el criterio documentado del HMTA (t ≥ 5, varios pases)."""
    from health_monitor import anomaly_detection as AD

    from validacion_cientifica import procedencia as P

    s = _serie(campo, desde, hasta)
    # Las lecturas que valen la ordenada de la recta (cuenta ADC 0) no son
    # medidas: una tendencia calculada con ellas describe el fallo del canal,
    # no la magnitud. Se excluyen y se dice cuantas.
    c = P.amsat().calibraciones().get(str(s.name))
    medidas = s[s != c["c"]] if c else s
    t = AD.tendencia(medidas)
    out = {"campo": s.name, "resumen": _describir(s), "naturaleza": DERIVADO,
           "lecturas_excluidas_de_la_tendencia": int(len(s) - len(medidas)),
           "criterio": (f"Regresión lineal; significativa si |pendiente|/error ≥ {AD.T_MIN_TENDENCIA:g}, el "
                        f"cambio supera {AD.CAMBIO_MIN_SIGMAS:g}σ del residuo, ≥ {AD.MIN_LECTURAS_TENDENCIA} lecturas, "
                        f"≥ {AD.MIN_DIAS_TENDENCIA:g} día y ≥ {AD.MIN_PASES_TENDENCIA} pases "
                        "(health_monitor/anomaly_detection.py).")}
    if t is None:
        out["tendencia"] = None
        out["nota"] = "No hay lecturas suficientes (o abarcan muy pocos pases) para estimar una tendencia."
    else:
        out["tendencia"] = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in t.items()}
    return out


def comparar_intervalos(campo: str, a_desde: str, a_hasta: str, b_desde: str, b_hasta: str) -> dict:
    a, b = _serie(campo, a_desde, a_hasta), _serie(campo, b_desde, b_hasta)
    ra, rb = _describir(a), _describir(b)
    dif = None
    if ra.get("lecturas") and rb.get("lecturas"):
        dif = round(rb["mediana"] - ra["mediana"], 4)
    return {"campo": a.name, "intervalo_a": ra, "intervalo_b": rb, "diferencia_de_medianas": dif,
            "diferencia_absoluta": None if dif is None else abs(dif),
            "naturaleza": DERIVADO,
            "nota": "Comparación de medianas; no implica causa. Revise «lecturas_en_la_ordenada»: esas "
                    "lecturas no son medidas."}


def anomalias(campo: str = "battery_voltage", desde: str | None = None, hasta: str | None = None,
              limite: int = 10) -> dict:
    """Tramos anomalos segun las reglas documentadas del gemelo, con su interpretacion."""
    from gemelo_digital import anomalias as A
    from validacion_cientifica import diagnosticos as D

    s = _serie(campo, None, None)
    clas = D.clasificacion(str(s.name))
    evs = A.eventos(clas, str(s.name))
    if desde or hasta:
        from validacion_cientifica.tiempo import instante_utc

        t0 = instante_utc(desde, exigir_zona=False) if desde else None
        t1 = instante_utc(hasta, exigir_zona=False) if hasta else None
        evs = [e for e in evs if (t0 is None or pd.Timestamp(e.fin) >= t0)
               and (t1 is None or pd.Timestamp(e.inicio) <= t1)]
    cronologico = sorted(evs, key=lambda e: e.inicio)
    evs.sort(key=lambda e: e.duracion_s, reverse=True)

    def ficha(e):
        return {**e.dict(), "interpretacion": D.INTERPRETACION.get(e.etiqueta)} if e else None
    return {
        "campo": s.name, "eventos_total": len(evs), "naturaleza": DERIVADO,
        "primer_evento": ficha(cronologico[0] if cronologico else None),
        "ultimo_evento": ficha(cronologico[-1] if cronologico else None),
        "nota_lista": f"«eventos» son los {limite} más largos; «primer_evento» y «ultimo_evento», los extremos en el tiempo.",
        "reglas": {"z_robusto": f"|z| ≥ {A.UMBRAL_ADVERTENCIA:g} comportamiento inusual (Iglewicz y Hoaglin, "
                                f"1993); |z| ≥ {A.UMBRAL_ANOMALIA:g} anomalía estadística (umbral del proyecto)",
                   "canal_enrielado": f"{A.MIN_ENRIELADO} lecturas con amplitud ≤ {A.TOLERANCIA_ENRIELADO:g} "
                                      "de la escala: posible anomalía operacional (instrumentación)",
                   "ventana": f"{A.VENTANA} lecturas"},
        "eventos": [{**e.dict(), "interpretacion": D.INTERPRETACION.get(e.etiqueta)} for e in evs[:limite]],
        "falla_confirmada": D.FALLA_CONFIRMADA["detalle"],
    }


def _hemisferios(lat: float | None, lon: float | None) -> dict | None:
    if lat is None or lon is None:
        return None
    return {"latitud": {"grados": round(abs(lat), 4), "hemisferio": "N" if lat >= 0 else "S"},
            "longitud": {"grados": round(abs(lon), 4), "hemisferio": "E" if lon >= 0 else "O"}}


def posicion_orbital(fecha: str | None = None) -> dict:
    from validacion_cientifica import orbital as O
    from validacion_cientifica.tiempo import a_datetime

    t = instante(fecha)
    p = O.posicion_en(a_datetime(t))
    prop = p.get("propagacion") or {}
    return {"instante_utc": p["instante_utc"], "estado": p["estado"], "naturaleza": CALCULADO,
            "tle_epoca_utc": (p.get("tle") or {}).get("epoca_utc"), "antiguedad_tle_dias": p.get("antiguedad_dias"),
            "posicion_teme_km": prop.get("posicion_km"), "velocidad_teme_km_s": prop.get("velocidad_km_s"),
            "rapidez_km_s": prop.get("rapidez_km_s"), "terrestre": prop.get("terrestre"),
            "hemisferios": _hemisferios((prop.get("terrestre") or {}).get("latitud_deg"),
                                        (prop.get("terrestre") or {}).get("longitud_deg")),
            "nota": p["evaluacion_antiguedad"]["detalle"]}


def limites() -> dict:
    """Qué se puede pedir: rango del archivo, velocidades, SNR, vistas."""
    from . import acciones as AC

    ini, fin, magnitudes = AC._limites_archivo()
    return {"archivo_desde": _iso(ini), "archivo_hasta": _iso(fin), "velocidades": list(AC._velocidades()),
            "snr_db": [AC.SNR_MIN_DB, AC.SNR_MAX_DB], "vistas": list(AC.VISTAS), "camaras": list(AC.CAMARAS),
            "magnitudes": list(magnitudes)}


# ── Registro para Claude ────────────────────────────────────────────────────

_FECHA = {"type": "string", "description": "Instante ISO 8601 (UTC). Si se omite: el instante del gemelo en "
                                           "pantalla o, sin él, la última baliza del archivo."}
HERRAMIENTAS: dict[str, tuple[Any, dict]] = {
    "consultar_variable": (consultar_variable, {
        "description": "Valor medido de una variable de STRaND-1 en un instante, con procedencia. Acepta "
                       "nombres del catálogo o palabras como temperatura, voltaje, corriente, actitud.",
        "properties": {"nombre": {"type": "string"}, "fecha": _FECHA}, "required": ["nombre"]}),
    "explicar_variable": (explicar_variable, {
        "description": "Qué es una variable, para qué sirve y si STRaND-1 la emite.",
        "properties": {"nombre": {"type": "string"}}, "required": ["nombre"]}),
    "estado_en_instante": (estado_en_instante, {
        "description": "Resumen del CubeSat en un instante: lecturas, interruptores, diagnóstico, órbita.",
        "properties": {"fecha": _FECHA}, "required": []}),
    "estado_subsistema": (estado_subsistema, {
        "description": "Variables de un subsistema (eps, termico, comunicaciones, obc, adcs) en un instante.",
        "properties": {"subsistema": {"type": "string"}, "fecha": _FECHA}, "required": ["subsistema"]}),
    "tendencia": (tendencia, {
        "description": "Tendencia y estadísticas de una magnitud en un intervalo (criterio documentado del HMTA).",
        "properties": {"campo": {"type": "string"}, "desde": _FECHA, "hasta": _FECHA}, "required": ["campo"]}),
    "comparar_intervalos": (comparar_intervalos, {
        "description": "Compara la mediana de una magnitud en dos intervalos.",
        "properties": {"campo": {"type": "string"}, "a_desde": _FECHA, "a_hasta": _FECHA,
                       "b_desde": _FECHA, "b_hasta": _FECHA},
        "required": ["campo", "a_desde", "a_hasta", "b_desde", "b_hasta"]}),
    "anomalias": (anomalias, {
        "description": "Tramos anómalos de una magnitud según las reglas documentadas (z robusto, canal enrielado): "
                       "los más largos y, aparte, el primero y el último en el tiempo.",
        "properties": {"campo": {"type": "string"}, "desde": _FECHA, "hasta": _FECHA}, "required": ["campo"]}),
    "posicion_orbital": (posicion_orbital, {
        "description": "Posición y velocidad SGP4 en un instante con el TLE histórico más cercano, o por qué no.",
        "properties": {"fecha": _FECHA}, "required": []}),
    "limites": (limites, {
        "description": "Rango de fechas del archivo, velocidades, límites de SNR y vistas disponibles.",
        "properties": {}, "required": []}),
}


def esquemas_para_claude() -> list[dict]:
    return [{"name": n, "description": d["description"],
             "input_schema": {"type": "object", "properties": d["properties"], "required": d["required"],
                              "additionalProperties": False}}
            for n, (_, d) in HERRAMIENTAS.items()]


def ejecutar(nombre: str, argumentos: dict, contexto: dict | None = None) -> dict:
    """Ejecuta una consulta por nombre. Rellena la fecha con la del gemelo si no se dio."""
    if nombre not in HERRAMIENTAS:
        raise ConsultaInvalida(f"Herramienta «{nombre}» desconocida.")
    fn, spec = HERRAMIENTAS[nombre]
    args = {k: v for k, v in (argumentos or {}).items() if k in spec["properties"]}
    momento = (contexto or {}).get("momento_utc")
    if "fecha" in spec["properties"] and not args.get("fecha") and momento:
        args["fecha"] = momento
    faltan = [r for r in spec["required"] if r not in args]
    if faltan:
        raise ConsultaInvalida(f"Faltan parámetros: {', '.join(faltan)}.")
    return _limpio(fn(**args))


def _limpio(x: Any) -> Any:
    from validacion_cientifica.estados import limpiar

    return limpiar(x)
