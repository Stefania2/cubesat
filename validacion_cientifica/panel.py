"""Validation Overview: ejecuta las comprobaciones y las agrupa por modulo.

Dos origenes de resultados, rotulados para no confundirlos:

  * `en_servidor`: comprobaciones ejecutadas en este proceso, ahora (con su
    `ejecutado_utc`). Se cachean mientras viva el proceso.
  * `registrados`: resultados que no caben en una funcion de 60 s y se
    ejecutaron fuera (la suite de pytest y la comparacion base↔archivo). Se
    muestran con la fecha y el commit en que se ejecutaron. Si el fichero no
    existe, el estado es NOT_VERIFIED: nunca se presume que pasaron.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import conjunto as C
from . import diagnosticos as D
from . import estados as E
from . import orbital as O
from . import procedencia as P
from . import reconstruccion as R
from . import sincronizacion as S
from . import telemetria as T
from .tiempo import a_datetime, iso

PRUEBAS_REGISTRADAS = Path(__file__).resolve().parent / "resultados" / "pruebas_automatizadas.json"
INSTANTE_REFERENCIA = "2021-03-01T12:00:00Z"   # caso de regresion documentado en docs/


def cobertura_tle() -> E.Resultado:
    """Que fraccion del archivo de telemetria tiene un TLE dentro de la antiguedad admisible."""
    ev = R._motor()["eventos"]
    div = O.divergencia()
    if div is None:
        return E.no_verificado("ORB-E", "orbital", "Cobertura de TLE históricos", "Falta el estudio de divergencia.")
    cat = O.catalogo_tle()
    epocas = pd.DatetimeIndex([r.epoca for r in cat])
    pos = epocas.searchsorted(ev)
    edades = []
    for t, p in zip(ev, pos):
        cand = [abs((t - epocas[j]).total_seconds()) / 86400 for j in (p - 1, p) if 0 <= j < len(epocas)]
        edades.append(min(cand))
    edades = np.array(edades)
    crit = div["criterios"]
    frac = {k: float(np.mean(edades <= c["antiguedad_admisible_dias"])) for k, c in crit.items()}
    return E.ejecutado(
        "ORB-E", "orbital", "Antigüedad del TLE: cobertura del archivo de telemetría", True,
        aviso=min(frac.values()) < 0.95,
        esperado="TLE dentro de la antigüedad admisible para cada evento de telemetría",
        obtenido={"eventos": len(ev), "fraccion_cubierta": frac,
                  "antiguedad_mediana_dias": float(np.median(edades)),
                  "tle_epoca_min": iso(cat[0].epoca), "tle_epoca_max": iso(cat[-1].epoca),
                  "telemetria_desde": iso(ev[0]), "telemetria_hasta": iso(ev[-1]),
                  "criterios": {k: c["antiguedad_admisible_dias"] for k, c in crit.items()}},
        tolerancia="criterio empírico (estudio de divergencia, p95 ≤ tolerancia del propósito)",
        detalle="Los TLE históricos del proyecto proceden de las observaciones de SatNOGS Network, "
                "que no conserva observaciones anteriores a finales de 2022. Para la telemetría de "
                "2016-2022 no hay TLE cercano: la posición se informa como NOT_AVAILABLE en lugar de "
                "propagar un TLE de años después. Obtener TLE de esa época exige otra fuente "
                "(Space-Track, con cuenta).",
        referencia="validacion_cientifica/resultados/divergencia_tle.json")


def estudio_vigente() -> E.Resultado:
    """El criterio de antiguedad se calculo con el catalogo sellado vigente."""
    div = O.divergencia()
    sello = (P.leer_sello() or {}).get("ficheros", {}).get("catalogo_tle", {})
    if div is None:
        return E.no_verificado("ORB-E-ESTUDIO", "orbital", "Estudio de divergencia vigente", "Falta el estudio.")
    ok = div.get("catalogo_sha256") == sello.get("sha256_contenido")
    return E.ejecutado("ORB-E-ESTUDIO", "orbital", "Criterio de antigüedad calculado con el catálogo sellado",
                       True, aviso=not ok, esperado=sello.get("sha256_contenido"),
                       obtenido=div.get("catalogo_sha256"), tolerancia="igualdad exacta",
                       detalle="Coinciden." if ok else "El estudio se calculó con otro catálogo: regenérelo.")


def pruebas_registradas() -> dict:
    if not PRUEBAS_REGISTRADAS.exists():
        return {"estado": E.NOT_VERIFIED, "detalle": "La suite no se ha ejecutado con "
                "validacion_cientifica/ejecutar_pruebas.py; no hay resultados registrados.", "casos": []}
    return json.loads(PRUEBAS_REGISTRADAS.read_text(encoding="utf-8"))


def comparacion_base() -> list[dict]:
    """Ultima comparacion registrada de cada base (local, Neon) con el sello vigente."""
    reg = P.ultima_comparacion_base()
    if not reg:
        return [E.no_verificado("PROV-BD", "procedencia", "Base de datos = archivo sellado",
                                "No se ha ejecutado `archivar.py --comparar`. En Vercel no puede "
                                "ejecutarse (leer la base tarda minutos).").dict()]
    sello = P.leer_sello() or {}
    out = []
    for origen, run in reg.items():
        for r in run["resultados"]:
            tabla = r["id"].replace("PROV-BD-", "")
            vigente = sello.get("ficheros", {}).get(tabla, {}).get("sha256_contenido")
            # Una comparacion contra un sello distinto del vigente ya no dice nada.
            if vigente and (r.get("esperado") or {}).get("sha256") != vigente:
                r = {**r, "estado": E.NOT_VERIFIED, "detalle": "Comparación hecha contra un sello anterior."}
            out.append({**r, "id": f"{r['id']}·{'neon' if 'Neon' in origen else 'local'}",
                        "origen": "registrado", "nota_origen": f"{origen}; ejecutado localmente el {run['ejecutado_utc']}"})
    if not any("Neon" in o for o in reg):
        out.append(E.no_verificado(
            "PROV-BD·neon", "procedencia", "Base desplegada (Neon) = archivo sellado",
            "La comparación completa con Neon no se ha completado: leer la base a través del pooler "
            "tarda minutos y la conexión se colgó en los intentos del 2026-11-17. Las huellas de "
            "tramas_originales, observaciones y tramas_clasificacion leídas desde Neon ese día "
            "coincidieron con las del sello; campos_decodificados queda sin comparar.").dict())
    return out


@lru_cache(maxsize=1)
def ejecutar() -> dict:
    """Todas las comprobaciones de servidor. Tarda ~15 s la primera vez."""
    if not P.archivo_disponible():
        integ = [r.dict() for r in P.verificar_archivo()]
        return {"secciones": {"procedencia": integ}, "recuento": E.recuento(integ),
                "generado_utc": E.ahora_utc()}
    sec: dict[str, list[dict]] = {}
    sec["procedencia"] = ([r.dict() for r in P.verificar_archivo()] + comparacion_base()
                          + [O.comparar_catalogo_vivo().dict()])

    orb = [O.resultados_catalogo()]
    reg_ver = next((r for r in O.catalogo_tle() if "versionado" in r.fuente), O.catalogo_tle()[-1])
    orb.append(O.resultado_tle(reg_ver.linea1, reg_ver.linea2, reg_ver.fuente))
    orb.append(O.prueba_repetibilidad(reg_ver, reg_ver.epoca + pd.Timedelta(hours=3).to_pytimedelta()))
    orb += O.prueba_vallado()
    orb.append(O.prueba_cpp_vs_python())
    orb.append(O.prueba_satnogs(P.cargar("observaciones")))
    orb += O.prueba_transformaciones()
    orb.append(cobertura_tle())
    orb.append(estudio_vigente())
    sec["orbital"] = [r.dict() for r in orb]

    sec["telemetria"] = [r.dict() for r in T.controles_globales()]
    sec["temporal"] = [S.prueba_global().dict(), S.empates_ambiguos().dict()]
    sec["diagnosticos"] = [D.prueba_reproducibilidad().dict(), D.prueba_ventanas_incompletas().dict()]
    rec = R.reconstruir(INSTANTE_REFERENCIA)
    sec["reproducibilidad"] = [r.dict() for r in R.verificar_manifest(R.manifest(rec))]
    todos = [r for lista in sec.values() for r in lista]
    return {"secciones": sec, "recuento": E.recuento(todos), "generado_utc": E.ahora_utc()}


def resumen() -> dict:
    res = ejecutar()
    pr = pruebas_registradas()
    return {**res, "pruebas_automatizadas": {k: v for k, v in pr.items() if k != "casos"},
            "recuento_pruebas_automatizadas": pr.get("recuento"),
            "versiones": P.versiones(), "sello": P.leer_sello()}
