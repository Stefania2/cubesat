"""MODULO 3 — Telemetry Validation, sobre el archivo sellado.

Que se puede y que no se puede afirmar
--------------------------------------
Lo unico documentado de cada canal es lo que publica AMSAT-UK: nodo, canal,
tamaño del dato, la recta de calibracion y, para los nodos 0x2C y 0x2D, que el
convertidor es de 10 bits (cuentas 0 a 1023). De ahi salen:

  * el DOMINIO del convertidor, que si es un rango documentado: una cuenta
    fuera de 0..1023 no puede venir de ese ADC (posible error de decodificacion);
  * la RESOLUCION, |m| unidades por cuenta, derivada de la recta;
  * el valor con cuenta 0 (la ordenada), que no es una medida.

Lo que NO esta documentado es el rango de OPERACION de ningun componente
(tension minima de bateria, corriente maxima de panel...). Sin el, ningun valor
se declara fisicamente imposible: `estado_fisico` es NOT_VERIFIED en todas las
magnitudes y asi se rotula.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from . import conjunto as C
from . import estados as E
from . import procedencia as P

LANZAMIENTO_UTC = pd.Timestamp("2013-02-25T00:00:00Z")
REF_LANZAMIENTO = "Lanzamiento de STRaND-1 en el PSLV-C20, 25 de febrero de 2013 (AMSAT-UK; SSTL)"
NODOS_ADC = ("0x2C", "0x2D")
ADC_MAX = 1023


def _catalogo_hmta() -> dict:
    """Variables del HMTA indexadas por campo de la base (descripcion y disponibilidad)."""
    try:
        from health_monitor import catalogo
    except ImportError:
        return {}
    por_campo = {}
    for v in catalogo.VARIABLES.values():
        for c in (v.campos or (v.clave,)):
            por_campo.setdefault(c, v)
    return por_campo


@lru_cache(maxsize=1)
def redecodificacion() -> dict:
    """Re-decodifica cada trama distinta con el codigo vigente y la compara con lo almacenado.

    Es la prueba de «errores de conversion»: si el decodificador o una recta
    cambiaran, los valores almacenados dejarian de coincidir.
    """
    t = C.tramas()
    d = C.decodificados()
    cache: dict[str, dict | None] = {}
    incompletas = 0
    detalles: dict[str, dict | None] = {}
    for h in t["raw_hex"].unique():
        cache[h] = P.redecodificar(h)
        det = P.baliza_detalle(h)
        detalles[h] = det
        if det and len(det["datos_hex"]) // 2 < det["data_size"]:
            incompletas += 1
    hex_de = t["raw_hex"].to_dict()
    distintos, ausentes = [], 0
    por_campo_err: dict[str, int] = {}
    for fila in d.itertuples(index=False):
        r = cache.get(hex_de.get(fila.frame_id))
        alm = fila.value_numeric if pd.notna(fila.value_numeric) else fila.value_text
        if not r or fila.field_name not in r:
            ausentes += 1
            por_campo_err[fila.field_name] = por_campo_err.get(fila.field_name, 0) + 1
            continue
        nuevo = r[fila.field_name][0]
        igual = (nuevo == alm) or (isinstance(nuevo, (int, float)) and isinstance(alm, float)
                                   and float(nuevo) == alm)
        if not igual:
            por_campo_err[fila.field_name] = por_campo_err.get(fila.field_name, 0) + 1
            if len(distintos) < 20:
                distintos.append({"campo_id": fila.id, "trama_id": fila.frame_id,
                                  "campo": fila.field_name, "almacenado": alm, "recalculado": nuevo})
    fuera_dominio = sum(1 for det in detalles.values() if det and det["fuera_de_dominio_adc"])
    return {"valores": len(d), "tramas_distintas": len(cache), "distintos": distintos,
            "n_distintos": sum(por_campo_err.values()) - ausentes, "ausentes": ausentes,
            "errores_por_campo": por_campo_err, "incompletas": incompletas,
            "fuera_de_dominio": fuera_dominio}


def controles_globales() -> list[E.Resultado]:
    t, d, cl = C.tramas(), C.decodificados(), C.clasificacion()
    r = redecodificacion()
    out = []

    ok = r["n_distintos"] == 0 and r["ausentes"] == 0
    out.append(E.ejecutado(
        "TEL-CONV", "telemetria", "Errores de conversión (re-decodificación completa)", ok,
        esperado="cada valor almacenado = valor recalculado desde raw_hex con el código vigente",
        obtenido={"valores_comparados": r["valores"], "distintos": r["n_distintos"],
                  "sin_equivalente": r["ausentes"], "ejemplos": r["distintos"]},
        tolerancia="igualdad exacta (mismo float)",
        detalle=f"{r['tramas_distintas']} tramas distintas re-decodificadas con strand_amsat "
                f"(huella {P.versiones()['codigo']['decodificador_amsat']['sha256'][:12]}…).",
        referencia=P.amsat().FUENTE_CALIBRACION))

    dup = d[d.duplicated(["frame_id", "field_name"], keep=False)]
    conflicto = 0
    if not dup.empty:
        g = dup.groupby(["frame_id", "field_name"])
        conflicto = int(((g["value_numeric"].nunique() > 1) | (g["value_text"].nunique() > 1)).sum())
    n_tramas_dup = int(dup["frame_id"].nunique())
    out.append(E.ejecutado(
        "TEL-DUP-PROC", "telemetria", "Duplicados en la capa procesada", conflicto == 0,
        aviso=n_tramas_dup > 0,
        esperado="un valor por (trama, campo)",
        obtenido={"filas_duplicadas": len(dup), "tramas_afectadas": n_tramas_dup,
                  "duplicados_con_valores_distintos": conflicto},
        tolerancia="ningún duplicado con valores distintos",
        detalle=(f"{n_tramas_dup} tramas tienen sus campos decodificados dos veces (la "
                 "decodificación se ejecutó dos veces sobre ellas). Los valores repetidos son "
                 "idénticos, así que no alteran ningún resultado, pero inflan los recuentos por fila; "
                 "la reconstrucción usa el último por instante.") if n_tramas_dup else
                "Sin duplicados."))

    multi = int(t.duplicated(["raw_hex", "timestamp"]).sum())
    out.append(E.ejecutado(
        "TEL-DUP-RX", "telemetria", "Recepciones múltiples de la misma baliza", True,
        esperado="identificadas, no eliminadas",
        obtenido={"tramas_repetidas_por_otra_estacion": multi},
        tolerancia="no aplica (no es un error)",
        detalle="Misma trama y misma marca de tiempo recibida por varias estaciones. Se conservan: "
                "son recepciones distintas de una misma medición; no deben contarse como mediciones "
                "independientes en estadísticas por muestra."))

    antes = int((t["timestamp"] < LANZAMIENTO_UTC).sum())
    despues = int((t["timestamp"] > t["ingested_at"]).sum())
    m = d.merge(t[["id", "timestamp"]].rename(columns={"id": "frame_id", "timestamp": "t_trama"}),
                on="frame_id")
    desfase = int((m["timestamp"] != m["t_trama"]).sum())
    ok = antes == 0 and despues == 0 and desfase == 0
    out.append(E.ejecutado(
        "TEL-TIEMPO", "telemetria", "Inconsistencias temporales", ok,
        esperado="recepción posterior al lanzamiento y anterior a la ingesta; campo con la fecha de su trama",
        obtenido={"antes_del_lanzamiento": antes, "posteriores_a_la_ingesta": despues,
                  "campo_con_fecha_distinta_de_su_trama": desfase,
                  "primera_recepcion": t["timestamp"].min().isoformat(),
                  "ultima_recepcion": t["timestamp"].max().isoformat()},
        tolerancia="0 casos", referencia=REF_LANZAMIENTO,
        detalle="Las marcas de tiempo de SatNOGS tienen resolución de 1 s."))

    out.append(E.ejecutado(
        "TEL-INCOMP", "telemetria", "Datos incompletos (DATA_SIZE mayor que los bytes recibidos)",
        r["incompletas"] == 0, aviso=r["incompletas"] > 0,
        esperado="0 balizas truncadas", obtenido={"balizas_truncadas": r["incompletas"]},
        tolerancia="0", detalle="Baliza cuyo campo DATA_SIZE anuncia más bytes de los que llegaron."))

    st = cl["status"].value_counts().to_dict()
    out.append(E.ejecutado(
        "TEL-DECOD", "telemetria", "Posibles errores de decodificación", True,
        aviso=bool(st.get("error", 0) or r["fuera_de_dominio"]),
        esperado="tramas con estructura de baliza decodificables y cuentas dentro del dominio de 10 bits",
        obtenido={"por_estado": st, "balizas_corruptas": st.get("error", 0),
                  "cuentas_fuera_de_dominio_adc": r["fuera_de_dominio"]},
        tolerancia="se informan; no se corrigen",
        detalle="«error»: tiene la bandera C0 80 pero no encaja en el formato (baliza corrupta). "
                "Cuentas > 1023 en nodos de 10 bits: no pueden venir de ese convertidor; el canal "
                "se deja sin valor físico. «unclassified»: sin estructura reconocible (puede ser otro "
                "tipo de paquete), no se interpreta.",
        referencia=P.amsat().FUENTE_CALIBRACION))
    return out


def variables() -> list[dict]:
    """Ficha de validacion de cada variable presente o definida."""
    cg = C.campos_gemelo()
    txt = C.estados_texto()
    cal = P.amsat().calibraciones()
    hmta = _catalogo_hmta()
    r = redecodificacion()
    fuente = P.amsat().FUENTE_CALIBRACION
    fichas = []

    for campo, g in cg.groupby("field_name", observed=True):
        campo = str(campo)
        v = g["value_numeric"]
        unidad = str(g["unit"].iloc[0])
        es_adc = campo.endswith("_adc")
        base = campo[:-4] if es_adc else campo
        c = cal.get(base)
        h = hmta.get(campo) or hmta.get(base)
        ficha = {
            "campo": campo,
            "descripcion": h.que_es if h else None,
            "nombre": h.nombre if h else None,
            "subsistema": h.subsistema if h else None,
            "fuente_documental": fuente,
            "nodo_canal": f"{c['nodo_i2c']}/{c['canal']}" if c else (h.nodo_canal if h else None),
            "unidad": unidad,
            "n_lecturas": int(len(v)),
            "n_valores_distintos": int(v.nunique()),
            "primera": g["timestamp"].min().isoformat(),
            "ultima": g["timestamp"].max().isoformat(),
            "disponibilidad": {"estado": "emitida", "lecturas": int(len(v))},
            "errores_conversion": r["errores_por_campo"].get(campo, 0),
        }
        if campo == "battery_voltage":
            ficha["metodo_procesamiento"] = ("Parámetro de la interfaz: primera disponible de "
                                             "battery_0_voltage, battery_1_voltage (strand_telemetry.MAPEO)")
        if es_adc:
            ficha.update({"conversion": "ninguna: cuenta tal como llegó", "resolucion": "1 cuenta",
                          "metodo_procesamiento": "lectura del entero little-endian (DATA_SIZE bytes)"})
            if c and c["nodo_i2c"] in NODOS_ADC:
                fuera = int(((v < 0) | (v > ADC_MAX)).sum())
                ficha["rango_referencia"] = {"dominio_convertidor": [0, ADC_MAX],
                                             "documentado": True, "fuera": fuera}
                ficha["estado_integridad"] = E.WARNING if fuera else E.VALIDATED
            else:
                ficha["rango_referencia"] = {"dominio_convertidor": None, "documentado": False}
                ficha["estado_integridad"] = E.VALIDATED
        elif campo == "battery_voltage":
            ords = [cal["battery_0_voltage"]["c"], cal["battery_1_voltage"]["c"]]
            en_ordenada = int(v.isin(ords).sum())
            ficha.update({
                "conversion": f"{cal['battery_0_voltage']['conversion']} ó {cal['battery_1_voltage']['conversion']}",
                "resolucion": f"{abs(cal['battery_0_voltage']['m']):g} V/cuenta (derivada de la recta)",
                "rango_referencia": {"rango_operativo": None,
                                     "nota": "No hay rango de operación documentado de las baterías."},
                "lecturas_en_la_ordenada": en_ordenada,
                "nota_ordenada": (f"{en_ordenada} lecturas valen exactamente la ordenada de su recta "
                                  "(cuenta ADC 0): el canal no mide.") if en_ordenada else None})
            ficha["estado_integridad"] = E.WARNING if en_ordenada else E.VALIDATED
        elif c:
            lo, hi = sorted((c["m"] * ADC_MAX + c["c"], c["c"]))
            en_ordenada = int((v == c["c"]).sum())
            ficha.update({
                "conversion": c["conversion"], "valor_original": c["campo_original"],
                "resolucion": f"{abs(c['m']):g} {c['unidad']}/cuenta (derivada de la recta)",
                "metodo_procesamiento": ficha.get("metodo_procesamiento") or
                                        "recta de calibración publicada aplicada a la cuenta",
                "rango_referencia": {"imagen_del_dominio_adc": [round(lo, 6), round(hi, 6)]
                                     if c["nodo_i2c"] in NODOS_ADC else None,
                                     "rango_operativo": None,
                                     "nota": "No hay rango de operación documentado del componente."},
                "lecturas_en_la_ordenada": en_ordenada,
                "nota_ordenada": (f"{en_ordenada} lecturas valen exactamente {c['c']:g} {unidad}: cuenta "
                                  "ADC 0, el canal no mide.") if en_ordenada else None,
            })
            ficha["estado_integridad"] = E.WARNING if en_ordenada else E.VALIDATED
        else:
            ficha.update({"conversion": "decodificación según la especificación (sin recta publicada)",
                          "resolucion": "1 cuenta" if unidad == "cuenta" else None,
                          "metodo_procesamiento": "entero de 4 bytes little-endian" if unidad in ("cuenta", "s")
                                                  else "decodificación según la especificación",
                          "rango_referencia": {"documentado": False}})
            ficha["estado_integridad"] = E.VALIDATED
            if campo in ("obc_unix_time", "obc_uptime"):
                ficha["nota"] = ("La hoja lo define como tiempo UNIX, pero no se comporta como reloj "
                                 "(vale 2 casi siempre). No se usa como fecha de medición.")
        if ficha["errores_conversion"]:
            ficha["estado_integridad"] = E.FAILED
        ficha["estado_fisico"] = E.NOT_VERIFIED
        ficha["nota_fisica"] = "No validado físicamente: no existe rango de operación documentado."
        fichas.append(ficha)

    for campo, g in txt.groupby("field_name"):
        fichas.append({
            "campo": str(campo), "unidad": None, "tipo": "estado discreto",
            "fuente_documental": fuente, "n_lecturas": int(len(g)),
            "valores": g["value_text"].value_counts().to_dict(),
            "primera": g["timestamp"].min().isoformat(), "ultima": g["timestamp"].max().isoformat(),
            "conversion": "byte de estado → etiqueta (tabla de la hoja)", "resolucion": None,
            "disponibilidad": {"estado": "emitida", "lecturas": int(len(g))},
            "rango_referencia": {"valores_documentados": list(P.amsat().ESTADO_INTERRUPTOR.values())},
            "metodo_procesamiento": "tabla de estados; nunca se interpola",
            "errores_conversion": r["errores_por_campo"].get(str(campo), 0),
            "estado_integridad": E.FAILED if r["errores_por_campo"].get(str(campo)) else E.VALIDATED,
            "estado_fisico": E.NOT_VERIFIED,
            "nota_fisica": "Estado declarado por el satélite; sin documentación con la que contrastarlo.",
        })

    presentes = {f["campo"] for f in fichas}
    for h in {id(v): v for v in hmta.values()}.values():
        if h.disponibilidad == "emitida":
            continue
        campos = [c for c in (h.campos or (h.clave,)) if c not in presentes]
        if not campos:
            continue
        fichas.append({
            "campo": ", ".join(campos), "nombre": h.nombre, "descripcion": h.que_es,
            "subsistema": h.subsistema, "unidad": h.unidad, "fuente_documental": h.fuente,
            "n_lecturas": 0, "disponibilidad": {"estado": h.disponibilidad, "lecturas": 0},
            "estado_integridad": E.NOT_AVAILABLE, "estado_fisico": E.NOT_AVAILABLE,
            "nota_fisica": "La hoja de AMSAT-UK define el canal pero STRaND-1 nunca lo emitió en "
                           "las balizas archivadas. Ausencia de dato, no valor cero.",
        })
    return [E.limpiar(f) for f in fichas]


def resumen() -> dict:
    controles = controles_globales()
    fichas = variables()
    return {"controles": [c.dict() for c in controles], "variables": fichas,
            "recuento_variables": {
                "integridad": E.recuento([{"estado": f["estado_integridad"]} for f in fichas]),
                "fisico": E.recuento([{"estado": f["estado_fisico"]} for f in fichas])}}
