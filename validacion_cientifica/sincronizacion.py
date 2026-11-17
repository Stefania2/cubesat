"""MODULO 4 — Temporal Synchronization Validation.

Comprueba, sobre reconstrucciones concretas, que telemetria, orbita, gemelo y
modelo 3D hablan del MISMO instante UTC y que cada valor dice como se asocio
a ese instante:

    S1  referencia unica    todo componente devuelve el instante solicitado tal cual
    S2  evento del gemelo   el evento elegido es el ultimo ≤ t y el siguiente es > t
    S3  telemetria = gemelo cada lectura retenida coincide con la instantanea del gemelo
    S4  orbita en t         la propagacion se hizo exactamente en t (valor calculado)
    S5  sin interpolacion   ningun valor, y menos un estado discreto, se interpola
    S6  modelo 3D           el estado visual sale del diagnostico del mismo instante
    S7  sin futuro          ninguna medicion asociada es posterior a t

Y una comprobacion global del dato: `empates_ambiguos`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import conjunto as C
from . import estados as E
from . import reconstruccion as R
from .tiempo import instante_utc, iso


def verificar(rec: dict) -> list[E.Resultado]:
    t = rec["instante_utc"]
    tt = instante_utc(t)
    out = []
    instantes = {"reconstruccion": t, "orbita": rec["orbita"]["instante_utc"]}
    prop = rec["orbita"].get("propagacion")
    if prop:
        instantes["propagacion_sgp4"] = prop["instante_propagacion_utc"]
    ok = len(set(instantes.values())) == 1
    out.append(E.ejecutado("SYNC-1", "temporal", "Referencia temporal única (UTC)", ok,
                           esperado=t, obtenido=instantes, tolerancia="igualdad exacta de la cadena ISO"))

    g = rec["gemelo"]
    if g["estado"] == E.NOT_AVAILABLE:
        out.append(E.no_disponible("SYNC-2", "temporal", "Evento del gemelo", g["nota"]))
    else:
        eventos = R._motor()["eventos"]
        i = g["evento"]
        ok = eventos[i] <= tt and (i + 1 == len(eventos) or eventos[i + 1] > tt)
        out.append(E.ejecutado("SYNC-2", "temporal", "Evento del gemelo = último ≤ instante", ok,
                               esperado="evento[i] ≤ t < evento[i+1]",
                               obtenido={"evento": iso(eventos[i]),
                                         "siguiente": iso(eventos[i + 1]) if i + 1 < len(eventos) else None},
                               tolerancia="exacta"))
        foto = g["lecturas_gemelo"]
        distintas = []
        for l in rec["telemetria"]["lecturas"]:
            if l["tipo"] != "continuo" or l["valor"] is None:
                continue
            gm = foto.get(l["campo"])
            if gm is None or gm["valor"] != l["valor"] or gm["medida_utc"] != l["medida_utc"]:
                distintas.append(l["campo"])
        faltan = [c for c in foto if c not in {l["campo"] for l in rec["telemetria"]["lecturas"]
                                                if l["valor"] is not None}]
        out.append(E.ejecutado("SYNC-3", "temporal", "Telemetría coherente con la instantánea del gemelo",
                               not distintas and not faltan, esperado="mismo valor y misma fecha de medición",
                               obtenido={"comparadas": len(foto), "distintas": distintas, "faltan": faltan},
                               tolerancia="exacta"))

    if prop:
        out.append(E.ejecutado("SYNC-4", "temporal", "Órbita calculada exactamente en el instante",
                               prop["instante_propagacion_utc"] == t and
                               rec["orbita"]["asociacion_temporal"] == R.CALCULADO,
                               esperado=t, obtenido=prop["instante_propagacion_utc"], tolerancia="exacta",
                               detalle=f"TLE con {rec['orbita']['antiguedad_dias']} días de antigüedad."))
    else:
        out.append(E.no_disponible("SYNC-4", "temporal", "Órbita en el instante",
                                   rec["orbita"]["evaluacion_antiguedad"]["detalle"]))

    metodos = [l["asociacion"] for l in rec["telemetria"]["lecturas"]]
    discretas_mal = [l["campo"] for l in rec["telemetria"]["lecturas"]
                     if l["tipo"] == "discreto" and l["asociacion"] not in (R.EXACTA, R.ANTERIOR, R.NO_DISPONIBLE)]
    out.append(E.ejecutado("SYNC-5", "temporal", "Sin interpolación (en particular de estados discretos)",
                           R.INTERPOLACION not in metodos and not discretas_mal,
                           esperado="ningún método «interpolacion»",
                           obtenido=pd.Series(metodos).value_counts().to_dict(), tolerancia="exacta"))

    d = rec["diagnostico"]
    ok = rec["modelo3d"]["estado_cubesat"] == d["estado_cubesat_modelo3d"] and (
        d["lectura_diagnosticada_utc"] is None or instante_utc(d["lectura_diagnosticada_utc"]) <= tt)
    out.append(E.ejecutado("SYNC-6", "temporal", "Modelo 3D actualizado con el diagnóstico del instante", ok,
                           esperado="estado visual = diagnóstico de la última lectura ≤ t",
                           obtenido={"estado_visual": rec["modelo3d"]["estado_cubesat"],
                                     "lectura": d["lectura_diagnosticada_utc"]}, tolerancia="exacta"))

    futuras = [l["campo"] for l in rec["telemetria"]["lecturas"]
               if l["medida_utc"] and instante_utc(l["medida_utc"]) > tt]
    out.append(E.ejecutado("SYNC-7", "temporal", "Ninguna medición posterior al instante",
                           not futuras, esperado="medida ≤ t", obtenido={"posteriores": futuras},
                           tolerancia="exacta"))
    return out


def empates_ambiguos() -> E.Resultado:
    """Instantes con dos valores distintos de la misma magnitud.

    El gemelo se queda con el «ultimo» (pivot_table aggfunc='last'). Leyendo de
    la base, «ultimo» depende de un orden que PostgreSQL no garantiza entre
    filas con la misma marca de tiempo; leyendo del archivo, se desempata por
    id y es estable.
    """
    cg = C.campos_gemelo()
    g = cg.groupby(["timestamp", "field_name"], observed=True)["value_numeric"]
    n = g.nunique()
    amb = n[n > 1]
    ejemplos = [{"instante": iso(t), "campo": str(c)} for t, c in amb.index[:10]]
    return E.ejecutado(
        "SYNC-EMPATES", "temporal", "Empates de marca de tiempo con valores distintos", True,
        aviso=len(amb) > 0, esperado="un valor por (instante, magnitud)",
        obtenido={"grupos_con_empate": int((g.size() > 1).sum()), "con_valores_distintos": int(len(amb)),
                  "ejemplos": ejemplos},
        tolerancia="se informan",
        detalle="Dos balizas distintas con la misma marca de tiempo (resolución de 1 s de SatNOGS). "
                "El archivo desempata por id (estable). La consulta del gemelo contra la base ordena "
                "solo por fecha, así que en estos instantes el valor mostrado podría variar entre "
                "ejecuciones. No se cambió el gemelo; queda documentado.")


def instantes_muestra(n: int = 24) -> list[str]:
    """Instantes deterministas repartidos por el archivo: eventos, puntos intermedios y bordes."""
    ev = R._motor()["eventos"]
    idx = np.linspace(0, len(ev) - 1, n // 2).astype(int)
    out = [iso(ev[i]) for i in idx]
    out += [iso(ev[i] + (ev[i + 1] - ev[i]) / 2) for i in idx[:-1]]
    out += [iso(ev[0] - pd.Timedelta(days=1)), iso(ev[-1] + pd.Timedelta(days=30))]
    return sorted(set(out))


def prueba_global(n: int = 24) -> E.Resultado:
    fallos = []
    instantes = instantes_muestra(n)
    for t in instantes:
        for r in verificar(R.reconstruir(t)):
            if r.estado == E.FAILED:
                fallos.append({"instante": t, "prueba": r.id})
    return E.ejecutado("SYNC-GLOBAL", "temporal", "Sincronización en instantes repartidos por el archivo",
                       not fallos, esperado="SYNC-1…7 sin fallos",
                       obtenido={"instantes": len(instantes), "fallos": fallos[:20]},
                       tolerancia="0 fallos",
                       detalle="Incluye eventos exactos, puntos entre eventos, un instante anterior al "
                               "archivo y otro posterior.")
