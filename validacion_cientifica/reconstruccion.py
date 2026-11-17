"""MODULO 5 y 7 — Scientific Replay y Reproducibility Manifest.

Una reconstruccion responde a «¿que se sabe de STRaND-1 en el instante t?»
usando SOLO entradas selladas:

    telemetria   archivo sellado (procedencia.py) → mismo DataFrame que el gemelo
    estado 3D    gemelo_digital.estado.reconstruir + anomalias.clasificar (codigo de la plataforma)
    orbita       TLE historico mas cercano (orbital.py) → SGP4 de la plataforma
    diagnostico  gemelo_digital.anomalias, con la escala de diagnosticos.py

No consulta PostgreSQL ni SatNOGS: funciona aunque ambos desaparezcan, porque
el archivo y el catalogo de TLE viven en el repositorio.

Cada valor sale con su metodo de asociacion temporal (ver sincronizacion.py) y
su procedencia; nada se interpola y nada se rellena. Lo que no existe sale
como NOT_AVAILABLE.

El manifest (`manifest`) lista todas las entradas con su huella y las
versiones de cada pieza de codigo. `verificar_manifest` repite la
reconstruccion desde el y compara la huella de los resultados.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from gemelo_digital import anomalias as A
from gemelo_digital import estado as S

from . import MISION, NORAD_ID, VERSION
from . import conjunto as C
from . import diagnosticos as D
from . import estados as E
from . import orbital as O
from . import procedencia as P
from .tiempo import ESCALA, a_datetime, instante_utc, iso

CAMPO_POR_DEFECTO = "battery_voltage"
VERSION_MANIFEST = "1.0"

# Metodos de asociacion temporal (seccion 7 del encargo).
EXACTA = "coincidencia_exacta"
ANTERIOR = "muestra_anterior_mas_cercana"
INTERPOLACION = "interpolacion"
CALCULADO = "valor_calculado"
NO_DISPONIBLE = "no_disponible"
METODOS = {
    EXACTA: "La medición tiene exactamente la marca de tiempo solicitada.",
    ANTERIOR: "Última medición anterior al instante (retención de muestra, como el gemelo). Se "
              "informa su desfase; la medición siguiente se muestra aparte, sin combinarlas.",
    INTERPOLACION: "No se aplica a ninguna variable: la telemetría llega a ráfagas separadas por "
                   "días y los estados de interruptores son discretos.",
    CALCULADO: "Calculado exactamente en el instante (posición SGP4).",
    NO_DISPONIBLE: "No hay medición anterior al instante.",
}


@dataclass
class _Serie:
    t: np.ndarray        # datetime64[ns], ordenado
    valor: np.ndarray
    trama: np.ndarray
    unidad: str | None
    discreta: bool


@lru_cache(maxsize=1)
def _motor() -> dict:
    """Todo lo que no depende del instante: se calcula una vez por proceso."""
    campos = C.campos_gemelo()
    est = S.reconstruir(campos)
    series: dict[str, _Serie] = {}
    for campo, g in campos.groupby("field_name", observed=True):
        series[str(campo)] = _Serie(g["timestamp"].to_numpy("datetime64[ns]"),
                                    g["value_numeric"].to_numpy(), g["frame_id"].to_numpy(),
                                    str(g["unit"].iloc[0]), False)
    for campo, g in C.estados_texto().groupby("field_name"):
        series[str(campo)] = _Serie(g["timestamp"].to_numpy("datetime64[ns]"),
                                    g["value_text"].to_numpy(), g["frame_id"].to_numpy(), None, True)
    return {"campos": campos, "estado": est, "unidades": S.unidades(campos), "series": series,
            "eventos": pd.DatetimeIndex(est.index)}


def _lectura(nombre: str, s: _Serie, t: pd.Timestamp) -> dict:
    t64 = np.datetime64(t.tz_convert("UTC").tz_localize(None), "ns")
    i = int(np.searchsorted(s.t, t64, side="right")) - 1
    sig = i + 1
    siguiente = None
    if sig < len(s.t):
        siguiente = {"medida_utc": iso(pd.Timestamp(s.t[sig], tz="UTC")),
                     "desfase_s": float((s.t[sig] - t64) / np.timedelta64(1, "s"))}
    base = {"campo": nombre, "unidad": s.unidad, "tipo": "discreto" if s.discreta else "continuo",
            "siguiente_medicion": siguiente}
    if i < 0:
        return {**base, "valor": None, "estado": E.NOT_AVAILABLE, "asociacion": NO_DISPONIBLE,
                "medida_utc": None, "desfase_s": None, "trama_id": None, "naturaleza": None,
                "nota": "Sin medición anterior al instante. No se toma la siguiente ni se extrapola."}
    desfase = float((t64 - s.t[i]) / np.timedelta64(1, "s"))
    valor = s.valor[i]
    frescura = ("fresca" if desfase <= S.EDADES_UMBRAL["fresca"] else
                "vieja" if desfase <= S.EDADES_UMBRAL["vieja"] else "obsoleta")
    return {**base, "valor": valor if s.discreta else float(valor),
            "estado": E.VALIDATED if frescura == "fresca" else E.WARNING,
            "asociacion": EXACTA if desfase == 0 else ANTERIOR,
            "medida_utc": iso(pd.Timestamp(s.t[i], tz="UTC")), "desfase_s": desfase,
            "frescura": frescura, "trama_id": int(s.trama[i]), "naturaleza": E.MEDIDO,
            "nota": None if frescura == "fresca" else
                    f"La medición tiene {desfase / 86400:.2f} días respecto al instante: describe el "
                    "pasado del satélite, no su estado en el instante."}


def _diagnostico(campo: str, t: pd.Timestamp) -> dict:
    clas = D.clasificacion(campo)
    et = clas["etiqueta"].astype(str)
    et = et[~et.index.duplicated(keep="last")]
    previas = et[et.index <= t]
    if previas.empty:
        etiqueta, cuando, z, med = "sin_referencia", None, None, None
    else:
        etiqueta, cuando = str(previas.iloc[-1]), previas.index[-1]
        fila = clas.loc[[cuando]].iloc[-1]
        z = None if pd.isna(fila["z"]) else float(fila["z"])
        med = None if pd.isna(fila["mediana"]) else float(fila["mediana"])
    return {"campo": campo, "etiqueta": etiqueta, "interpretacion": D.INTERPRETACION.get(etiqueta),
            "estado_cubesat_modelo3d": A.estado_cubesat(etiqueta),
            "lectura_diagnosticada_utc": iso(cuando) if cuando is not None else None,
            "z": z, "mediana_movil": med, "naturaleza": E.DERIVADO,
            "parametros": parametros_estadisticos(), "falla_confirmada": D.FALLA_CONFIRMADA}


def parametros_estadisticos() -> dict:
    return {"ventana_lecturas": A.VENTANA, "min_lecturas": A.VENTANA // 2,
            "umbral_advertencia": A.UMBRAL_ADVERTENCIA, "umbral_anomalia": A.UMBRAL_ANOMALIA,
            "escala_mad": A.ESCALA_MAD, "max_amplitud_ventana": str(A.MAX_SPAN_VENTANA),
            "enrielado_lecturas": A.MIN_ENRIELADO, "enrielado_tolerancia_relativa": A.TOLERANCIA_ENRIELADO}


def reconstruir(instante: str, campo: str = CAMPO_POR_DEFECTO) -> dict:
    """Reconstruccion completa en `instante` (ISO 8601 con zona). Determinista."""
    t = instante_utc(instante)
    m = _motor()
    if campo not in m["series"] or m["series"][campo].discreta:
        raise KeyError(f"«{campo}» no es una magnitud numérica del archivo")
    eventos = m["eventos"]
    i = int(eventos.searchsorted(t, side="right")) - 1

    lecturas = [_lectura(n, s, t) for n, s in sorted(m["series"].items())]

    if i < 0:
        gemelo = {"estado": E.NOT_AVAILABLE, "evento": None,
                  "nota": "El instante es anterior a la primera baliza decodificada."}
    else:
        momento = eventos[i]
        foto = S.instantanea(m["estado"], i, m["unidades"])
        gemelo = {
            "estado": E.VALIDATED, "evento": i, "total_eventos": len(eventos),
            "momento_evento_utc": iso(momento),
            "desfase_evento_s": (t - momento).total_seconds(),
            "pase": int(m["estado"]["pase"].iloc[i]),
            "regla": "último evento con marca ≤ instante (misma regla que /api/gemelo/indice)",
            "lecturas_gemelo": {l.campo: {"valor": l.valor, "medida_utc": iso(l.medida_en),
                                          "edad_s": l.edad_s} for l in foto},
        }
    diag = _diagnostico(campo, t)
    visual = {"campo_gobernante": campo, "etiqueta": diag["etiqueta"],
              "estado_cubesat": diag["estado_cubesat_modelo3d"],
              "nota": "Codificación visual del modelo 3D. STRaND-1 no transmite actitud: la "
                      "orientación del modelo no es un dato."}

    orbita = O.posicion_en(a_datetime(t))
    tramas_usadas = sorted({l["trama_id"] for l in lecturas if l["trama_id"] is not None})
    tr = C.tramas()
    entradas = [{"trama_id": int(k), "raw_hex": tr.at[k, "raw_hex"],
                 "sha256": P.sha256(bytes.fromhex(tr.at[k, "raw_hex"])),
                 "recibida_utc": iso(tr.at[k, "timestamp"]),
                 "observacion_id": None if pd.isna(tr.at[k, "observation_id"]) else int(tr.at[k, "observation_id"]),
                 "fuente": P.FUENTE_SATNOGS.get(tr.at[k, "app_source"], P.FUENTE_SATNOGS[None])}
                for k in tramas_usadas]
    disponibles = sum(1 for l in lecturas if l["estado"] != E.NOT_AVAILABLE)
    return E.limpiar({
        "mision": MISION, "norad_id": NORAD_ID,
        "referencia_temporal": ESCALA, "instante_utc": iso(t),
        "parametros": {"campo_gobernante": campo},
        "telemetria": {"lecturas": lecturas, "disponibles": disponibles, "total": len(lecturas),
                       "metodos_asociacion": METODOS},
        "gemelo": gemelo, "modelo3d": visual, "orbita": orbita, "diagnostico": diag,
        "procedencia": {"tramas": entradas, "archivo_huella": P.huella_conjunto()},
    })


def huella_resultados(rec: dict) -> str:
    return P.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8"))


def manifest(rec: dict) -> dict:
    """Expediente reproducible de una reconstruccion (manifest.json)."""
    sello = P.leer_sello() or {}
    vers = P.versiones()
    orb = rec["orbita"]
    tle = orb.get("tle")
    entradas = {
        "instante_utc": rec["instante_utc"], "campo_gobernante": rec["parametros"]["campo_gobernante"],
        "archivo": P.huella_conjunto(), "codigo": {k: v["sha256"] for k, v in vers["codigo"].items()},
        "tle": [tle["linea1"], tle["linea2"]] if tle else None,
    }
    id_rec = P.sha256(json.dumps(entradas, sort_keys=True).encode())[:16]
    usados = {l["metodo"] if "metodo" in l else l["asociacion"] for l in rec["telemetria"]["lecturas"]}
    return E.limpiar({
        "manifest_version": VERSION_MANIFEST,
        "mision": {"nombre": MISION, "norad_id": NORAD_ID},
        "reconstruccion": {"id": id_rec, "instante_utc": rec["instante_utc"],
                           "generado_utc": E.ahora_utc(), "referencia_temporal": ESCALA,
                           "parametros": rec["parametros"]},
        "fuente_telemetria": {
            "descripcion": "Balizas de STRaND-1 recibidas por la red SatNOGS, decodificadas con la "
                           "especificación de AMSAT-UK",
            "observaciones": sorted({e["observacion_id"] for e in rec["procedencia"]["tramas"]
                                     if e["observacion_id"] is not None}),
            "tramas": rec["procedencia"]["tramas"]},
        "datos": {"huella_conjunto_sha256": P.huella_conjunto(), "sellado_utc": sello.get("sellado_utc"),
                  "ficheros": {n: {"ruta": f"validacion_cientifica/archivo/{n}.jsonl.gz",
                                   "capa": f["capa"], "filas": f["filas"],
                                   "sha256_contenido": f["sha256_contenido"], "sha256_gz": f["sha256_gz"]}
                               for n, f in (sello.get("ficheros") or {}).items()}},
        "orbita": {"tle": tle, "epoca_tle_utc": tle["epoca_utc"] if tle else None,
                   "fuente_orbital": tle["fuente"] if tle else None,
                   "antiguedad_dias": orb.get("antiguedad_dias"), "estado": orb.get("estado"),
                   "sgp4": (orb.get("propagacion") or {}).get("implementacion_sgp4"),
                   "marco_referencia": O.MARCO,
                   "modelo_tiempo": "UTC; GMST IAU-82 con UT1≈UTC; sin movimiento del polo",
                   "modelo_tierra": "WGS-84 (estación y geodésica); WGS-72 interno de SGP4",
                   "criterio_antiguedad": "validacion_cientifica/resultados/divergencia_tle.json"},
        "versiones": vers,
        "parametros_estadisticos": parametros_estadisticos(),
        "sincronizacion": {"referencia": ESCALA, "metodos_usados": sorted(usados),
                           "interpolacion": "no aplicada", "descripcion": METODOS},
        "aplicacion": {"nombre": "STRaND-1 Telemetría · Scientific Validation",
                       "version_modulo": VERSION, "commit": vers["aplicacion"]["commit"],
                       "cambios_sin_confirmar": vers["aplicacion"]["cambios_sin_confirmar"]},
        "resultados": {"sha256": huella_resultados(rec),
                       "nota": "SHA-256 del JSON canónico de la reconstrucción (sin fechas de generación)."},
        "archivos": {
            "originales": ["validacion_cientifica/archivo/tramas_originales.jsonl.gz",
                           "validacion_cientifica/archivo/observaciones.jsonl.gz",
                           "validacion_cientifica/archivo/catalogo_tle.jsonl.gz (TLE históricos sellados)"],
            "derivados": ["validacion_cientifica/archivo/tramas_clasificacion.jsonl.gz",
                          "validacion_cientifica/archivo/campos_decodificados.jsonl.gz",
                          "validacion_cientifica/resultados/divergencia_tle.json"]},
        "como_reproducir": "python -m validacion_cientifica.reproducir manifest.json",
    })


def verificar_manifest(man: dict) -> list[E.Resultado]:
    """Repite la reconstruccion del manifest y la compara."""
    out = []
    try:
        instante = man["reconstruccion"]["instante_utc"]
        campo = man["reconstruccion"]["parametros"]["campo_gobernante"]
        huella_esperada = man["resultados"]["sha256"]
    except (KeyError, TypeError) as exc:
        return [E.ejecutado("REP-FORMATO", "reproducibilidad", "Formato del manifest", False,
                            detalle=f"Falta el campo {exc}.")]
    sello_ok = man.get("datos", {}).get("huella_conjunto_sha256") == P.huella_conjunto()
    out.append(E.ejecutado("REP-DATOS", "reproducibilidad", "Mismas entradas (huella del archivo)", sello_ok,
                           esperado=man.get("datos", {}).get("huella_conjunto_sha256"),
                           obtenido=P.huella_conjunto(), tolerancia="igualdad exacta"))
    integ = P.verificar_archivo()
    out.append(E.ejecutado("REP-INTEG", "reproducibilidad", "Archivo íntegro",
                           all(r.estado == E.VALIDATED for r in integ),
                           obtenido={r.id: r.estado for r in integ}))
    vers_m = (man.get("versiones") or {}).get("codigo", {})
    vers_a = P.versiones()["codigo"]
    distintos = [k for k, v in vers_a.items() if (vers_m.get(k) or {}).get("sha256") != v["sha256"]]
    out.append(E.ejecutado("REP-VERS", "reproducibilidad", "Mismas versiones de procesamiento",
                           not distintos, aviso=bool(distintos), esperado="huellas del manifest",
                           obtenido={"distintas": distintos},
                           detalle="Si alguna pieza cambió, una diferencia en el resultado es esperable "
                                   "y debe explicarse por ese cambio." if distintos else ""))
    for e in (man.get("fuente_telemetria") or {}).get("tramas", []):
        if P.sha256(bytes.fromhex(e["raw_hex"])) != e["sha256"]:
            out.append(E.ejecutado("REP-TRAMA", "reproducibilidad", f"Trama {e['trama_id']}", False,
                                   detalle="El raw_hex del manifest no corresponde a su huella."))
    rec = reconstruir(instante, campo)
    obtenida = huella_resultados(rec)
    out.append(E.ejecutado("REP-RESULT", "reproducibilidad", "Resultado idéntico al re-ejecutar",
                           obtenida == huella_esperada, esperado=huella_esperada, obtenido=obtenida,
                           tolerancia="igualdad exacta del JSON canónico"))
    return out
