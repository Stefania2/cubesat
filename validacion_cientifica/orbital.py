"""MODULO 2 — Orbital Validation.

Que se valida y contra que
--------------------------
La plataforma propaga con `orbita_sgp4.py`, que llama a `sgp4.api.Satrec`
(python-sgp4 2.27, extension C++ que compila el codigo de Vallado) y rota
TEME → terrestre con el GMST de la IAU 1982. Este modulo no reescribe nada de
eso: llama a las mismas funciones y las contrasta.

A. Integridad del TLE: formato de columnas fijo, numero de linea, numero de
   catalogo coincidente en ambas lineas, NORAD 39090 y suma de control modulo
   10 (Hoots y Roehrich, Spacetrack Report #3, 1980; CelesTrak, «NORAD
   Two-Line Element Set Format»: digitos por su valor, «-» vale 1, el resto 0).

B. Repetibilidad: mismo TLE, mismo instante, misma version → resultado
   identico bit a bit. Tolerancia 0: el calculo es determinista y no hay
   motivo fisico para admitir diferencia alguna.

C. Validacion independiente, en tres niveles que no prueban lo mismo:
   C1. Vectores de verificacion de Vallado et al. (2006), «Revisiting
       Spacetrack Report #3», AIAA 2006-6753: `SGP4-VER.TLE` y `tcppver.out`,
       generados por la implementacion C++ de los autores (distribuidos con
       python-sgp4). Comprueba que la biblioteca reproduce la referencia.
       Limitacion: la extension C++ de python-sgp4 ES ese mismo codigo
       compilado; C1 descarta errores de empaquetado y de uso, no de algoritmo.
   C2. La traduccion a Python puro de python-sgp4 (`sgp4.model.Satrec`),
       escrita a mano por otro autor, contra los mismos vectores y contra la
       extension C++ sobre los TLE reales de STRaND-1.
   C3. SatNOGS Network calcula por su cuenta (con PyEphem/libastro, otra
       implementacion de SGP4) la elevacion maxima y los azimuts de salida y
       puesta de cada observacion. Se comparan con lo que da la plataforma con
       el mismo TLE y la misma estacion. SatNOGS los publica redondeados a
       grados, y eso fija la tolerancia.

D. Transformacion de coordenadas: TEME → PEF (rotacion GMST IAU-82 alrededor
   de Z) → ITRF (movimiento del polo), con el ejemplo resuelto de Vallado et
   al. (2006), apendice C: r_TEME = (5094,18016210; 6127,64465950;
   6380,34453270) km el 2004-04-06 07:51:28,386009 UTC, UT1−UTC = −0,4399619 s,
   xp = −0,140682″, yp = 0,333309″. Y la conversion ECEF → geodesica WGS-84 de
   la plataforma (iterativa) contra la solucion cerrada de Heikkinen (1982).

E. Antiguedad del TLE: |t − epoca| y un criterio EMPIRICO, no un umbral
   elegido a ojo: se propaga cada TLE historico de STRaND-1 hasta la epoca de
   los posteriores y se mide cuanto se separa de ellos (`estudio_divergencia`).
   La antiguedad admisible para un proposito es la mayor cuya divergencia p95
   no supera la tolerancia de ese proposito.

Modelo de tiempo y de Tierra de la plataforma (documentado, no cambiado)
------------------------------------------------------------------------
* Escala: UTC. SGP4 recibe la fecha juliana UTC; el GMST se evalua con UTC
  tomado como UT1 (|UT1−UTC| < 0,9 s por definicion de UTC, IERS).
* Rotacion terrestre: GMST IAU-82 (Vallado 2006, ec. del apendice C);
  ω⊕ = 7,2921150e-5 rad/s para la velocidad de la estacion.
* Sin movimiento del polo (xp = yp = 0) ni ecuacion de los equinoccios: TEME
  ya es un marco «de fecha» y Vallado define TEME→PEF solo con GMST.
* Tierra: elipsoide WGS-84 (a = 6378,137 km, f = 1/298,257223563) para la
  estacion y la conversion geodesica. SGP4 usa internamente WGS-72, como exige
  la definicion de los TLE.
* Convenciones: ECEF dextrogiro, Z al polo norte, X al meridiano de Greenwich;
  latitud geodesica, longitud positiva al este en (−180°, 180°]; azimut desde
  el norte hacia el este; km y km/s.
El error que introducen esas simplificaciones se acota en la prueba D2.
"""

from __future__ import annotations

import json
import math
import sys
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import estados as E
from .tiempo import a_datetime, instante_utc, iso

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

import orbita_sgp4 as O  # noqa: E402  la implementacion de la plataforma
from sgp4.api import SGP4_ERRORS, Satrec, jday  # noqa: E402

NORAD = 39090
GEOMETRIA = RAIZ_REPO / "telemetria_strand1" / "backend" / "app" / "data" / "geometria_observaciones.json"
TLE_VERSIONADO = RAIZ_REPO / "tle" / "strand1_2026-08-09.tle"
DIVERGENCIA = Path(__file__).resolve().parent / "resultados" / "divergencia_tle.json"
DIR_SGP4 = Path(__import__("sgp4").__file__).resolve().parent

MARCO = "TEME (True Equator, Mean Equinox) — marco de salida de SGP4"
UNIDADES = {"posicion": "km", "velocidad": "km/s", "tiempo": "UTC", "angulos": "grados"}
REF_VALLADO = ("Vallado, D. A., Crawford, P., Hujsak, R. y Kelso, T. S. (2006). Revisiting "
               "Spacetrack Report #3. AIAA/AAS Astrodynamics Specialist Conference, AIAA 2006-6753.")
REF_HOOTS = ("Hoots, F. R. y Roehrich, R. L. (1980). Spacetrack Report No. 3: Models for "
             "Propagation of NORAD Element Sets. Aerospace Defense Command, U.S. Air Force.")
REF_HEIKKINEN = ("Heikkinen, M. (1982). Geschlossene Formeln zur Berechnung räumlicher geodätischer "
                 "Koordinaten aus rechtwinkligen Koordinaten. Zeitschrift für Vermessungswesen, 107, 207-211.")
ARCSEG = math.pi / (180 * 3600)


# ── A. Integridad del TLE ───────────────────────────────────────────────────

def checksum(linea: str) -> int:
    """Suma de control modulo 10 de las 68 primeras columnas."""
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in linea[:68]) % 10


def comprobar_tle(l1: str, l2: str, norad: int | None = NORAD) -> dict:
    """Todas las comprobaciones de formato; devuelve {comprobacion: (ok, detalle)}."""
    c: dict[str, tuple[bool, str]] = {}
    c["longitud"] = (len(l1) == 69 and len(l2) == 69, f"{len(l1)} y {len(l2)} columnas (se esperan 69)")
    c["numero_de_linea"] = (l1[:2] == "1 " and l2[:2] == "2 ", "las líneas empiezan por «1 » y «2 »")
    cat1, cat2 = l1[2:7].strip(), l2[2:7].strip()
    c["catalogo_coincide"] = (cat1 == cat2, f"línea 1: {cat1}, línea 2: {cat2}")
    if norad is not None:
        c["norad"] = (cat1 == str(norad), f"catálogo {cat1}, se espera {norad}")
    for n, l in (("1", l1), ("2", l2)):
        ok = len(l) >= 69 and l[68].isdigit() and int(l[68]) == checksum(l)
        c[f"checksum_linea_{n}"] = (ok, f"declarado {l[68:69] or '—'}, calculado {checksum(l)}")
    try:
        epoca = O.tle_epoch(O.Tle("", l1, l2))
        c["epoca_legible"] = (True, iso(epoca))
    except (ValueError, IndexError) as exc:
        c["epoca_legible"] = (False, str(exc))
    sat = Satrec.twoline2rv(l1, l2)
    c["lectura_sgp4"] = (sat.error == 0, f"código de error de inicialización {sat.error}")
    return c


def resultado_tle(l1: str, l2: str, fuente: str, rid: str = "ORB-A") -> E.Resultado:
    comps = comprobar_tle(l1, l2)
    fallos = [k for k, (ok, _) in comps.items() if not ok]
    return E.ejecutado(rid, "orbital", "Integridad del TLE", not fallos,
                       esperado="todas las comprobaciones de formato superadas",
                       obtenido={k: {"ok": ok, "detalle": d} for k, (ok, d) in comps.items()},
                       tolerancia="ninguna (formato fijo)",
                       detalle=f"Fuente: {fuente}." + (f" Fallan: {', '.join(fallos)}." if fallos else ""),
                       referencia=REF_HOOTS)


# ── Catalogo historico de TLE y seleccion por fecha ─────────────────────────

@dataclass(frozen=True)
class TleRegistro:
    linea1: str
    linea2: str
    epoca: datetime
    fuente: str

    @property
    def tle(self) -> O.Tle:
        return O.Tle(name="STRAND-1", line1=self.linea1, line2=self.linea2, source=self.fuente)

    def dict(self) -> dict:
        return {"linea1": self.linea1, "linea2": self.linea2, "epoca_utc": iso(self.epoca),
                "fuente": self.fuente}


def catalogo_vivo() -> tuple[TleRegistro, ...]:
    """TLE de los ficheros del repositorio TAL COMO ESTAN AHORA, sin repetir, por epoca.

    Ese fichero lo amplia la descarga de SatNOGS, asi que no sirve como entrada
    reproducible: las reconstrucciones usan `catalogo_tle()`, la copia sellada.
    """
    vistos: dict[tuple[str, str], TleRegistro] = {}
    if GEOMETRIA.exists():
        g = json.loads(GEOMETRIA.read_text(encoding="utf-8"))
        for l1, l2 in g.get("tles", []):
            vistos.setdefault((l1, l2), TleRegistro(
                l1, l2, O.tle_epoch(O.Tle("", l1, l2)),
                "SatNOGS Network: TLE con que se programó una observación "
                "(backend/app/data/geometria_observaciones.json)"))
    if TLE_VERSIONADO.exists():
        t = O.load_tle(TLE_VERSIONADO)
        vistos.setdefault((t.line1, t.line2), TleRegistro(
            t.line1, t.line2, O.tle_epoch(t), f"TLE versionado del repositorio ({TLE_VERSIONADO.name})"))
    return tuple(sorted(vistos.values(), key=lambda r: (r.epoca, r.linea1, r.linea2)))


def filas_catalogo(cat: tuple[TleRegistro, ...]) -> list[dict]:
    return [r.dict() for r in cat]


@lru_cache(maxsize=1)
def catalogo_tle() -> tuple[TleRegistro, ...]:
    """Catalogo SELLADO (archivo/catalogo_tle.jsonl.gz); el vivo solo si no hay sello."""
    from . import procedencia as P

    if P.archivo_disponible():
        return tuple(TleRegistro(f["linea1"], f["linea2"], instante_utc(f["epoca_utc"]).to_pydatetime(),
                                 f["fuente"]) for f in P.cargar("catalogo_tle"))
    return catalogo_vivo()


def comparar_catalogo_vivo() -> E.Resultado:
    """¿Ha cambiado el catalogo de TLE del repositorio desde que se sello?"""
    from . import procedencia as P

    if not P.archivo_disponible():
        return E.no_disponible("PROV-TLE-VIVO", "procedencia", "Catálogo de TLE vivo = sellado",
                               "No hay archivo sellado.")
    sellado = {(r.linea1, r.linea2) for r in catalogo_tle()}
    vivo = {(r.linea1, r.linea2) for r in catalogo_vivo()}
    nuevos, perdidos = len(vivo - sellado), len(sellado - vivo)
    igual = not nuevos and not perdidos
    return E.ejecutado(
        "PROV-TLE-VIVO", "procedencia", "Catálogo de TLE del repositorio = catálogo sellado", True,
        aviso=not igual, esperado={"tle": len(sellado)},
        obtenido={"tle_vivos": len(vivo), "nuevos_sin_sellar": nuevos, "sellados_ausentes": perdidos},
        tolerancia="igualdad de conjuntos",
        detalle="Coinciden." if igual else
                "El fichero de geometría tiene TLE que no están en el sello (la descarga de SatNOGS "
                "lo amplía). Las reconstrucciones usan SOLO el catálogo sellado; para incorporarlos "
                "hay que volver a sellar.",
        referencia="telemetria_strand1/backend/app/data/geometria_observaciones.json y tle/")


def seleccionar_tle(t: datetime) -> tuple[TleRegistro | None, float | None]:
    """TLE de epoca mas cercana a t (antes o despues) y antiguedad t − epoca en dias.

    Nunca se cae a «el TLE mas reciente»: si el mas cercano esta lejos, lo
    decide `evaluar_antiguedad`, que puede negarse a dar posicion.
    """
    cat = catalogo_tle()
    if not cat:
        return None, None
    epocas = [r.epoca for r in cat]
    i = bisect_left(epocas, t)
    candidatos = [cat[j] for j in (i - 1, i) if 0 <= j < len(cat)]
    mejor = min(candidatos, key=lambda r: abs((t - r.epoca).total_seconds()))
    return mejor, (t - mejor.epoca).total_seconds() / 86400


# ── Propagacion con registro completo ───────────────────────────────────────

def _jd(t: datetime) -> tuple[float, float]:
    u = t.astimezone(timezone.utc)
    return jday(u.year, u.month, u.day, u.hour, u.minute, u.second + u.microsecond / 1e6)


def propagar_teme(l1: str, l2: str, t: datetime, satrec_cls=Satrec) -> tuple[int, tuple, tuple]:
    sat = satrec_cls.twoline2rv(l1, l2)
    jd, fr = _jd(t)
    return sat.sgp4(jd, fr)


def teme_a_pef(r, v, jd_ut1: float) -> tuple[np.ndarray, np.ndarray]:
    """TEME → PEF con el GMST de la plataforma (`orbita_sgp4._gmst_rad`)."""
    g = O._gmst_rad(jd_ut1)
    c, s = math.cos(g), math.sin(g)
    rot = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    r_pef = rot @ np.asarray(r, float)
    w = np.array([0.0, 0.0, O.EARTH_ROTATION_RAD_S])
    v_pef = rot @ np.asarray(v, float) - np.cross(w, r_pef)
    return r_pef, v_pef


def pef_a_itrf(r_pef, v_pef, xp_rad: float, yp_rad: float) -> tuple[np.ndarray, np.ndarray]:
    """Movimiento del polo: r_ITRF = R1(yp)·R2(xp)·r_PEF (Vallado 2006, apendice C)."""
    cx, sx = math.cos(xp_rad), math.sin(xp_rad)
    cy, sy = math.cos(yp_rad), math.sin(yp_rad)
    r2 = np.array([[cx, 0.0, sx], [0.0, 1.0, 0.0], [-sx, 0.0, cx]])
    r1 = np.array([[1.0, 0.0, 0.0], [0.0, cy, -sy], [0.0, sy, cy]])
    w = r1 @ r2
    return w @ np.asarray(r_pef, float), w @ np.asarray(v_pef, float)


def geodetica_heikkinen(x: float, y: float, z: float) -> tuple[float, float, float]:
    """ECEF (km) → latitud, longitud (grados) y altura (km) WGS-84, forma cerrada."""
    a, f = O.WGS84_A_KM, O.WGS84_F
    b = a * (1 - f)
    e2 = f * (2 - f)
    ep2 = (a * a - b * b) / (b * b)
    p = math.hypot(x, y)
    F = 54 * b * b * z * z
    G = p * p + (1 - e2) * z * z - e2 * (a * a - b * b)
    c = e2 * e2 * F * p * p / (G ** 3)
    s = (1 + c + math.sqrt(c * c + 2 * c)) ** (1 / 3)
    k = s + 1 + 1 / s
    P = F / (3 * k * k * G * G)
    Q = math.sqrt(1 + 2 * e2 * e2 * P)
    r0 = (-P * e2 * p / (1 + Q)
          + math.sqrt(max(0.0, 0.5 * a * a * (1 + 1 / Q) - P * (1 - e2) * z * z / (Q * (1 + Q)) - 0.5 * P * p * p)))
    U = math.sqrt((p - e2 * r0) ** 2 + z * z)
    V = math.sqrt((p - e2 * r0) ** 2 + (1 - e2) * z * z)
    z0 = b * b * z / (a * V)
    h = U * (1 - b * b / (a * V))
    lat = math.atan2(z + ep2 * z0, p)
    return math.degrees(lat), math.degrees(math.atan2(y, x)), h


def registro_propagacion(reg: TleRegistro, t: datetime) -> dict:
    """Todo lo que el encargo pide registrar de una propagacion."""
    import sgp4

    from sgp4.api import accelerated

    error, r, v = propagar_teme(reg.linea1, reg.linea2, t)
    base = {
        "norad_id": NORAD, "tle": {"linea1": reg.linea1, "linea2": reg.linea2},
        "fuente_tle": reg.fuente, "epoca_tle_utc": iso(reg.epoca),
        "instante_propagacion_utc": iso(t),
        "antiguedad_tle_dias": round((t - reg.epoca).total_seconds() / 86400, 6),
        "implementacion_sgp4": {"biblioteca": "python-sgp4", "version": sgp4.__version__,
                                "extension_cpp_vallado": accelerated, "modo": "i (mejorado, por defecto)",
                                "constantes_gravitatorias": "WGS-72"},
        "marco_referencia": MARCO, "unidades": UNIDADES, "codigo_error_sgp4": error,
    }
    if error:
        return {**base, "posicion_km": None, "velocidad_km_s": None,
                "error": SGP4_ERRORS.get(error, str(error))}
    sub = O.subsatellite_point(reg.tle, t)
    return E.limpiar({
        **base,
        "posicion_km": {"x": r[0], "y": r[1], "z": r[2]},
        "velocidad_km_s": {"vx": v[0], "vy": v[1], "vz": v[2]},
        "rapidez_km_s": math.sqrt(sum(c * c for c in v)),
        "terrestre": {"marco": "ECEF ≈ PEF (GMST IAU-82, UT1≈UTC, sin movimiento del polo)",
                      "ecef_km": dict(zip("xyz", sub["ecef_km"])),
                      "latitud_deg": sub["lat_deg"], "longitud_deg": sub["lon_deg"],
                      "altura_km": sub["alt_km"], "elipsoide": "WGS-84"},
    })


# ── B. Repetibilidad ────────────────────────────────────────────────────────

def prueba_repetibilidad(reg: TleRegistro, t: datetime, repeticiones: int = 5) -> E.Resultado:
    salidas = [propagar_teme(reg.linea1, reg.linea2, t) for _ in range(repeticiones)]
    subs = [O.subsatellite_point(reg.tle, t) for _ in range(repeticiones)]
    iguales = all(s == salidas[0] for s in salidas) and all(s == subs[0] for s in subs)
    return E.ejecutado("ORB-B", "orbital", "Repetibilidad de la propagación", iguales,
                       esperado="resultados idénticos bit a bit",
                       obtenido=f"{repeticiones} ejecuciones {'idénticas' if iguales else 'DISTINTAS'}",
                       tolerancia="0 (cálculo determinista, misma versión)",
                       detalle=f"TLE de época {iso(reg.epoca)} propagado a {iso(t)}.",
                       datos={"r_km": list(salidas[0][1]), "v_km_s": list(salidas[0][2])})


# ── C. Validacion independiente ─────────────────────────────────────────────

TOL_VALLADO = 2e-7  # km y km/s por componente: resolucion de impresion de tcppver.out


def _vectores_vallado():
    """(linea1, linea2, [(tsince_min, r, v), ...]) de SGP4-VER.TLE + tcppver.out."""
    tles = {}
    lineas = (DIR_SGP4 / "SGP4-VER.TLE").read_text(encoding="ascii").splitlines()
    for i, l in enumerate(lineas):
        if l.startswith("1 ") and i + 1 < len(lineas) and lineas[i + 1].startswith("2 "):
            tles[int(l[2:7])] = (l, lineas[i + 1])
    casos, actual = [], None
    for l in (DIR_SGP4 / "tcppver.out").read_text(encoding="ascii").splitlines():
        partes = l.split()
        if len(partes) == 2 and partes[1] == "xx":
            actual = (int(partes[0]), [])
            casos.append(actual)
        elif len(partes) >= 7 and actual is not None:
            vals = [float(x) for x in partes[:7]]
            actual[1].append((vals[0], vals[1:4], vals[4:7]))
    return [(tles[n][0], tles[n][1], filas) for n, filas in casos if n in tles]


def comparar_vallado(satrec_cls) -> dict:
    max_r = max_v = 0.0
    n = errores = 0
    peor = None
    for l1, l2, filas in _vectores_vallado():
        sat = satrec_cls.twoline2rv(l1, l2)
        for tsince, r_ref, v_ref in filas:
            e, r, v = sat.sgp4_tsince(tsince)
            n += 1
            if e != 0 or any(math.isnan(c) for c in r):
                errores += 1
                continue
            dr = max(abs(a - b) for a, b in zip(r, r_ref))
            dv = max(abs(a - b) for a, b in zip(v, v_ref))
            if dr > max_r:
                max_r, peor = dr, (l1[2:7].strip(), tsince)
            max_v = max(max_v, dv)
    return {"puntos": n, "errores_propagacion": errores, "max_diff_pos_km": max_r,
            "max_diff_vel_km_s": max_v, "peor_caso": peor}


@lru_cache(maxsize=1)
def prueba_vallado() -> list[E.Resultado]:
    from sgp4.api import accelerated
    from sgp4.model import Satrec as SatrecPython

    fuera = []
    for rid, cls, nombre, nota in (
        ("ORB-C1", Satrec, "Vectores de Vallado · propagador de la plataforma",
         "python-sgp4 con extensión C++ (es el código de Vallado compilado)" if accelerated
         else "python-sgp4 sin extensión C++ (Python puro)"),
        ("ORB-C2", SatrecPython, "Vectores de Vallado · traducción independiente a Python",
         "sgp4.model.Satrec: traducción a Python escrita por B. Rhodes"),
    ):
        c = comparar_vallado(cls)
        # tcppver.out incluye casos que deben fallar (satelites decaidos): se
        # cuentan aparte y no entran en la comparacion.
        ok = c["max_diff_pos_km"] <= TOL_VALLADO and c["max_diff_vel_km_s"] <= TOL_VALLADO
        fuera.append(E.ejecutado(
            rid, "orbital", nombre, ok,
            esperado="vectores r, v de tcppver.out (Vallado et al. 2006)",
            obtenido={"puntos_comparados": c["puntos"] - c["errores_propagacion"],
                      "max_diff_posicion_km": c["max_diff_pos_km"],
                      "max_diff_velocidad_km_s": c["max_diff_vel_km_s"],
                      "peor_caso": c["peor_caso"]},
            tolerancia=f"{TOL_VALLADO:g} km y km/s por componente (resolución de impresión del fichero)",
            detalle=f"{nota}. {c['errores_propagacion']} instantes con error SGP4 esperado "
                    "(casos de decaimiento incluidos a propósito en el fichero) no se comparan.",
            referencia=REF_VALLADO))
    return fuera


def prueba_cpp_vs_python(muestras: int = 60) -> E.Resultado:
    """Las dos implementaciones de python-sgp4 sobre los TLE reales de STRaND-1."""
    from sgp4.model import Satrec as SatrecPython

    cat = catalogo_tle()
    if not cat:
        return E.no_disponible("ORB-C2b", "orbital", "C++ frente a Python sobre TLE de STRaND-1",
                               "No hay TLE en el catálogo.")
    paso = max(1, len(cat) // muestras)
    max_r = 0.0
    n = 0
    for reg in cat[::paso]:
        for horas in (0, 6, 24, 72):
            t = reg.epoca + timedelta(hours=horas)
            _, r1, _ = propagar_teme(reg.linea1, reg.linea2, t)
            _, r2, _ = propagar_teme(reg.linea1, reg.linea2, t, SatrecPython)
            max_r = max(max_r, max(abs(a - b) for a, b in zip(r1, r2)))
            n += 1
    tol = 1e-6
    return E.ejecutado("ORB-C2b", "orbital", "C++ frente a Python puro · TLE reales de STRaND-1",
                       max_r <= tol, esperado="misma posición", obtenido={"propagaciones": n,
                       "max_diff_posicion_km": max_r}, tolerancia=f"{tol:g} km (1 mm)",
                       detalle="Época y +6 h, +24 h, +72 h de una muestra del catálogo histórico.",
                       referencia=REF_VALLADO)


# Tolerancias de la comparacion con SatNOGS. SatNOGS publica los angulos en
# grados enteros (redondeo: ±0,5°); se suma 1° por las diferencias de modelo
# documentadas entre implementaciones (PyEphem usa su propio tiempo sidereo y
# corrige la refraccion si la estacion declara presion; la plataforma no).
TOL_SATNOGS_DEG = 1.5


def prueba_satnogs(observaciones: list[dict]) -> E.Resultado:
    """C3: elevacion maxima y azimuts de SatNOGS frente a la plataforma."""
    if not GEOMETRIA.exists():
        return E.no_disponible("ORB-C3", "orbital", "Contraste con SatNOGS Network",
                               "Falta geometria_observaciones.json.")
    g = json.loads(GEOMETRIA.read_text(encoding="utf-8"))
    dif_el, dif_az, filas = [], [], []
    for o in observaciones:
        meta = g["observaciones"].get(str(o["observation_id"]))
        if meta is None or not o.get("start") or not o.get("end") or o.get("max_elevation_deg") is None:
            continue
        est = g["estaciones"][str(meta["estacion"])]
        l1, l2 = g["tles"][meta["tle"]]
        tle = O.Tle("STRAND-1", l1, l2, "SatNOGS Network")
        obs = O.Observer(est["lat"], est["lng"], est["alt_m"] or 0.0)
        t0, t1 = a_datetime(instante_utc(o["start"])), a_datetime(instante_utc(o["end"]))
        # Maximo DENTRO de la ventana programada: es lo que publica SatNOGS
        # (comprobado: con el maximo del pase completo la discrepancia crece,
        # p95 1,2° frente a 0,5°, aunque los azimuts de los extremos coincidan).
        pts, t = [], t0
        while t <= t1:
            pts.append(O.propagate_point(tle, obs, t, 437.568e6))
            t += timedelta(seconds=5)
        if not pts:
            continue
        el = max(p.elevation_deg for p in pts)
        d_el = el - o["max_elevation_deg"]
        dif_el.append(d_el)
        fila = {"observacion": o["observation_id"], "elev_max_satnogs": o["max_elevation_deg"],
                "elev_max_plataforma": round(el, 2), "dif_elev": round(d_el, 2),
                "estado_satnogs": o.get("status")}
        for clave, p in (("azimut_salida", pts[0]), ("azimut_puesta", pts[-1])):
            if meta.get(clave) is not None:
                d = (p.azimuth_deg - meta[clave] + 180) % 360 - 180
                dif_az.append(d)
                fila[f"dif_{clave}"] = round(d, 2)
        filas.append(fila)
    if not filas:
        return E.no_disponible("ORB-C3", "orbital", "Contraste con SatNOGS Network",
                               "Ninguna observación tiene a la vez geometría (TLE y estación) y "
                               "elevación máxima publicada.")
    el = np.abs(np.array(dif_el))
    az = np.abs(np.array(dif_az)) if dif_az else np.array([])
    frac_el = float(np.mean(el <= TOL_SATNOGS_DEG))
    frac_az = float(np.mean(az <= TOL_SATNOGS_DEG)) if az.size else None
    ok = frac_el >= 0.95
    aviso = ok and frac_az is not None and frac_az < 0.95
    atipicas = [f for f in filas if abs(f["dif_elev"]) > TOL_SATNOGS_DEG]
    analisis_atipicas = {
        "n": len(atipicas),
        "marcadas_bad_por_satnogs": sum(1 for f in atipicas if f["estado_satnogs"] == "bad"),
        "con_azimut_tambien_discrepante": sum(
            1 for f in atipicas if any(abs(f.get(k, 0)) > TOL_SATNOGS_DEG
                                       for k in ("dif_azimut_salida", "dif_azimut_puesta"))),
        "bad_en_todas_las_comparadas": sum(1 for f in filas if f["estado_satnogs"] == "bad"),
    }
    return E.ejecutado(
        "ORB-C3", "orbital", "Contraste con SatNOGS Network (implementación independiente)", ok,
        aviso=aviso,
        esperado="elevación máxima y azimuts publicados por SatNOGS para la misma observación",
        obtenido={"observaciones": len(filas),
                  "elevacion": {"mediana_abs": float(np.median(el)), "p95_abs": float(np.percentile(el, 95)),
                                "max_abs": float(el.max()), "fraccion_en_tolerancia": frac_el},
                  "azimut": None if not az.size else {
                      "mediana_abs": float(np.median(az)), "p95_abs": float(np.percentile(az, 95)),
                      "max_abs": float(az.max()), "fraccion_en_tolerancia": frac_az},
                  "atipicas": analisis_atipicas},
        tolerancia=f"±{TOL_SATNOGS_DEG}° en al menos el 95 % de las observaciones",
        detalle="SatNOGS redondea a grados enteros. Se compara el máximo de elevación dentro de la "
                "ventana programada (paso 5 s) y los azimuts en sus extremos. «atipicas» desglosa las "
                "observaciones fuera de tolerancia y en cuántas discrepan también los azimuts, lo que "
                "apunta a una ventana o geometría del registro distinta de la usada al calcular. El "
                "estado «bad» de SatNOGS no discrimina: STRaND-1 está inactivo y casi todas sus "
                "observaciones lo llevan (ver datos.mayores_diferencias)."
                + (" Los azimuts quedan fuera de tolerancia con más frecuencia: ver datos." if aviso else ""),
        referencia="SatNOGS Network API, /api/observations/ (campos max_altitude, rise_azimuth, set_azimuth)",
        datos={"muestra": filas[:200],
               "mayores_diferencias": sorted(filas, key=lambda f: -abs(f["dif_elev"]))[:25]})


# ── D. Transformaciones de coordenadas ──────────────────────────────────────

# Vallado et al. (2006), apendice C (ejemplo TEME → ITRF).
EJEMPLO_D = {
    "utc": "2004-04-06T07:51:28.386009Z",
    "ut1_menos_utc_s": -0.4399619,
    "xp_arcsec": -0.140682, "yp_arcsec": 0.333309,
    "r_teme_km": (5094.18016210, 6127.64465950, 6380.34453270),
    "v_teme_km_s": (-4.746131487, 0.785818041, 5.531931288),
    "r_itrf_km": (-1033.4793830, 7901.2952754, 6380.3565958),
    "v_itrf_km_s": (-3.225636520, -2.872451450, 5.531924446),
}
TOL_D1_KM = 1e-3       # 1 m: el ejemplo esta impreso a 0,1 mm; se admite el redondeo de jd en float64
UT1_UTC_MAX_S = 0.9    # IERS: UTC se mantiene a menos de 0,9 s de UT1
POLO_MAX_ARCSEC = 0.6  # amplitud tipica del movimiento del polo (IERS, serie EOP C04)


def prueba_transformaciones() -> list[E.Resultado]:
    ex = EJEMPLO_D
    t = instante_utc(ex["utc"]).to_pydatetime()
    jd, fr = _jd(t)
    jd_utc = jd + fr
    jd_ut1 = jd_utc + ex["ut1_menos_utc_s"] / 86400
    r_pef, v_pef = teme_a_pef(ex["r_teme_km"], ex["v_teme_km_s"], jd_ut1)
    r_itrf, v_itrf = pef_a_itrf(r_pef, v_pef, ex["xp_arcsec"] * ARCSEG, ex["yp_arcsec"] * ARCSEG)
    dr = float(np.max(np.abs(r_itrf - np.array(ex["r_itrf_km"]))))
    dv = float(np.max(np.abs(v_itrf - np.array(ex["v_itrf_km_s"]))))
    fuera = [E.ejecutado(
        "ORB-D1", "orbital", "TEME → PEF → ITRF (ejemplo resuelto de Vallado)",
        dr <= TOL_D1_KM and dv <= 1e-6,
        esperado={"r_itrf_km": ex["r_itrf_km"], "v_itrf_km_s": ex["v_itrf_km_s"]},
        obtenido={"r_itrf_km": r_itrf.tolist(), "v_itrf_km_s": v_itrf.tolist(),
                  "max_diff_pos_km": dr, "max_diff_vel_km_s": dv},
        tolerancia=f"{TOL_D1_KM:g} km y 1e-6 km/s por componente",
        detalle="Usa el GMST de la plataforma (orbita_sgp4._gmst_rad) con UT1 y movimiento del polo "
                "del ejemplo. Valida la rotación terrestre que aplica la plataforma.",
        referencia=REF_VALLADO + " Apéndice C.")]

    # D2: la plataforma no aplica UT1−UTC ni movimiento del polo. Cota del error.
    r_app, _ = teme_a_pef(ex["r_teme_km"], ex["v_teme_km_s"], jd_utc)
    err = float(np.linalg.norm(r_app - np.array(ex["r_itrf_km"])))
    rxy = math.hypot(*ex["r_teme_km"][:2])
    cota = UT1_UTC_MAX_S * O.EARTH_ROTATION_RAD_S * rxy + POLO_MAX_ARCSEC * ARCSEG * float(np.linalg.norm(ex["r_teme_km"]))
    fuera.append(E.ejecutado(
        "ORB-D2", "orbital", "Error de la simplificación UT1≈UTC y sin movimiento del polo",
        err <= cota, esperado=f"error ≤ cota analítica {cota:.3f} km",
        obtenido={"error_km": err}, tolerancia=f"{cota:.3f} km = |UT1−UTC|max·ω⊕·r_xy + polo_max·|r|",
        detalle="Error de la cadena de la plataforma en el ejemplo de Vallado. Con |UT1−UTC| ≤ 0,9 s "
                "(definición de UTC) el error de posición terrestre de un satélite LEO queda por debajo "
                "de ~0,5 km: despreciable frente al error del propio TLE (prueba E).",
        referencia=REF_VALLADO))

    # D3: geodesica de la plataforma frente a la forma cerrada de Heikkinen.
    # El ECEF de referencia se recalcula sin redondear (misma rotacion GMST que
    # la plataforma, prueba D1); la plataforma redondea su salida, y eso es lo
    # unico que debe separar ambos resultados.
    max_lat = max_h = max_ecef = 0.0
    n = 0
    for reg in catalogo_tle()[::max(1, len(catalogo_tle()) // 50)] or ():
        for minutos in range(0, 101, 10):
            tt = reg.epoca + timedelta(minutes=minutos)
            s = O.subsatellite_point(reg.tle, tt)
            _, r, v = propagar_teme(reg.linea1, reg.linea2, tt)
            jd, fr = _jd(tt)
            ecef, _ = teme_a_pef(r, v, jd + fr)
            lat, lon, h = geodetica_heikkinen(*ecef)
            max_ecef = max(max_ecef, float(np.max(np.abs(ecef - np.array(s["ecef_km"])))))
            max_lat = max(max_lat, abs(lat - s["lat_deg"]))
            max_h = max(max_h, abs(h - s["alt_km"]))
            n += 1
    for lat0 in (-90.0, -45.0, 0.0, 30.0, 89.999):
        for h0 in (0.0, 775.0):
            la, lo = math.radians(lat0), math.radians(37.0)
            e2 = O.WGS84_F * (2 - O.WGS84_F)
            N = O.WGS84_A_KM / math.sqrt(1 - e2 * math.sin(la) ** 2)
            xyz = ((N + h0) * math.cos(la) * math.cos(lo), (N + h0) * math.cos(la) * math.sin(lo),
                   (N * (1 - e2) + h0) * math.sin(la))
            lat, _, h = geodetica_heikkinen(*xyz)
            max_lat = max(max_lat, abs(lat - lat0))
            max_h = max(max_h, abs(h - h0))
            n += 1
    # La plataforma redondea la salida a 1e-4 grados y 1e-3 km: medio paso de
    # redondeo mas 1e-9 de holgura numerica.
    tol_lat, tol_km = 0.5e-4 + 1e-9, 0.5e-3 + 1e-9
    fuera.append(E.ejecutado(
        "ORB-D3", "orbital", "ECEF → geodésica WGS-84 (iterativa frente a forma cerrada)",
        max_lat <= tol_lat and max_h <= tol_km and max_ecef <= tol_km,
        esperado="misma latitud y altura", obtenido={"puntos": n, "max_diff_lat_deg": max_lat,
                                                     "max_diff_altura_km": max_h,
                                                     "max_diff_ecef_km": max_ecef},
        tolerancia="medio paso de redondeo de la plataforma: 5e-5° y 5e-4 km",
        detalle="Puntos de STRaND-1 a lo largo de una órbita para una muestra de TLE, más casos "
                "analíticos (polo, ecuador, 45°) construidos con la fórmula directa.",
        referencia=REF_HEIKKINEN))
    return fuera


# ── E. Antiguedad del TLE: criterio empirico ────────────────────────────────

# Propositos de uso y su tolerancia de posicion, derivada de la resolucion de
# 1° con que SatNOGS publica los angulos (la referencia externa del proyecto).
ALTURA_KM = 775.0
PROPOSITOS = {
    "geometria_estacion": {
        "descripcion": "Azimut y elevación vistos desde una estación (resolución de SatNOGS: 1°)",
        # Peor caso: satelite en el cenit, distancia = altura. 1° de angulo ↔ h·tan(1°).
        "tolerancia_km": round(ALTURA_KM * math.tan(math.radians(1.0)), 1),
    },
    "trazado_globo": {
        "descripcion": "Punto subsatélite sobre el globo 3D (1° de arco geocéntrico)",
        "tolerancia_km": round((O.WGS84_A_KM + ALTURA_KM) * math.radians(1.0), 1),
    },
}


def estudio_divergencia(max_dias: float = 30.0) -> dict:
    """Separacion entre un TLE propagado y los TLE posteriores, por antiguedad.

    Para cada par (i, j) con 0 < epoca_j − epoca_i ≤ max_dias se propaga el TLE
    i hasta la epoca de j y se compara con j en su propia epoca, y al reves
    (j hacia atras hasta i). Mide la consistencia entre TLE, que es una cota
    inferior razonable del error real (el TLE de referencia tambien yerra) —
    es una ESTIMACION, y asi se rotula.
    """
    from . import procedencia as P

    cat = catalogo_tle()
    pos = {}
    for r in cat:
        _, rr, _ = propagar_teme(r.linea1, r.linea2, r.epoca)
        pos[r] = np.array(rr)
    bordes = [0, 0.5, 1, 2, 3, 5, 7, 10, 14, 21, 30]
    bordes = [b for b in bordes if b <= max_dias]
    difs: dict[int, list[float]] = {i: [] for i in range(len(bordes) - 1)}
    for i, ri in enumerate(cat):
        for rj in cat[i + 1:]:
            dias = (rj.epoca - ri.epoca).total_seconds() / 86400
            if dias > max_dias:
                break
            if dias <= 0:
                continue
            k = bisect_left(bordes, dias) - 1
            k = min(max(k, 0), len(bordes) - 2)
            for a, b in ((ri, rj), (rj, ri)):
                e, r, _ = propagar_teme(a.linea1, a.linea2, b.epoca)
                if not e:
                    difs[k].append(float(np.linalg.norm(np.array(r) - pos[b])))
    tramos = []
    for k, v in difs.items():
        if not v:
            continue
        a = np.array(v)
        tramos.append({"desde_dias": bordes[k], "hasta_dias": bordes[k + 1], "pares": len(a),
                       "mediana_km": round(float(np.median(a)), 3),
                       "p95_km": round(float(np.percentile(a, 95)), 3),
                       "max_km": round(float(a.max()), 3)})
    criterios = {}
    for clave, p in PROPOSITOS.items():
        admisible = 0.0
        for tr in tramos:
            if tr["p95_km"] <= p["tolerancia_km"]:
                admisible = tr["hasta_dias"]
            else:
                break
        criterios[clave] = {**p, "antiguedad_admisible_dias": admisible}
    return {
        "generado_utc": E.ahora_utc(), "tle_en_catalogo": len(cat),
        "catalogo_sha256": P.huella_filas(filas_catalogo(cat))[0],
        "epoca_min": iso(cat[0].epoca) if cat else None, "epoca_max": iso(cat[-1].epoca) if cat else None,
        "max_dias_estudiados": max_dias, "tramos": tramos, "criterios": criterios,
        "metodo": "Propagación de cada TLE histórico de STRaND-1 a la época de los TLE de los "
                  f"{max_dias:g} días siguientes (y viceversa); norma de la diferencia de posición "
                  "TEME. Percentil 95 por tramo de antigüedad.",
        "naturaleza": E.ESTIMADO,
    }


@lru_cache(maxsize=1)
def divergencia() -> dict | None:
    if not DIVERGENCIA.exists():
        return None
    return json.loads(DIVERGENCIA.read_text(encoding="utf-8"))


def evaluar_antiguedad(antiguedad_dias: float | None) -> dict:
    """Estado de la posicion segun la antiguedad del TLE y el criterio empirico."""
    if antiguedad_dias is None:
        return {"estado": E.NOT_AVAILABLE, "detalle": "No hay TLE en el catálogo.", "por_proposito": {}}
    d = divergencia()
    a = abs(antiguedad_dias)
    if d is None:
        return {"estado": E.NOT_VERIFIED, "detalle": "Falta el estudio de divergencia "
                "(resultados/divergencia_tle.json); la antigüedad no puede evaluarse.",
                "por_proposito": {}}
    max_estudiado = d["max_dias_estudiados"]
    if a > max_estudiado:
        return {"estado": E.NOT_AVAILABLE,
                "detalle": f"El TLE más cercano dista {a:.1f} días del instante: fuera de los "
                           f"{max_estudiado:g} días en que el error está caracterizado. No se "
                           "presenta posición: propagar tanto daría un resultado sin cota de error.",
                "por_proposito": {}}
    por = {}
    for clave, c in d["criterios"].items():
        ok = a <= c["antiguedad_admisible_dias"]
        tramo = next((t for t in d["tramos"] if t["desde_dias"] <= a <= t["hasta_dias"]), None)
        por[clave] = {"descripcion": c["descripcion"], "tolerancia_km": c["tolerancia_km"],
                      "antiguedad_admisible_dias": c["antiguedad_admisible_dias"],
                      "divergencia_p95_km_en_tramo": tramo["p95_km"] if tramo else None,
                      "estado": E.VALIDATED if ok else E.WARNING}
    peor = E.WARNING if any(p["estado"] == E.WARNING for p in por.values()) else E.VALIDATED
    return {"estado": peor, "detalle": f"Antigüedad {a:.2f} días; criterio empírico por propósito.",
            "por_proposito": por}


def posicion_en(t: datetime) -> dict:
    """Posicion historica en t con el TLE mas cercano, o la razon de no darla."""
    reg, edad = seleccionar_tle(t)
    evaluacion = evaluar_antiguedad(edad)
    salida = {"instante_utc": iso(t), "tle": reg.dict() if reg else None,
              "antiguedad_dias": None if edad is None else round(edad, 4),
              "evaluacion_antiguedad": evaluacion, "naturaleza": E.CALCULADO,
              "asociacion_temporal": "valor_calculado"}
    if reg is None or evaluacion["estado"] == E.NOT_AVAILABLE:
        salida.update({"estado": E.NOT_AVAILABLE, "propagacion": None})
        return salida
    salida["propagacion"] = registro_propagacion(reg, t)
    salida["estado"] = evaluacion["estado"] if salida["propagacion"]["posicion_km"] else E.FAILED
    return salida


def resultados_catalogo() -> E.Resultado:
    """Integridad (A) de todos los TLE del catalogo historico."""
    cat = catalogo_tle()
    if not cat:
        return E.no_disponible("ORB-A-CAT", "orbital", "Integridad del catálogo de TLE",
                               "No hay TLE históricos.")
    fallos = []
    for r in cat:
        comps = comprobar_tle(r.linea1, r.linea2)
        malos = [k for k, (ok, _) in comps.items() if not ok]
        if malos:
            fallos.append({"epoca": iso(r.epoca), "fallan": malos})
    return E.ejecutado("ORB-A-CAT", "orbital", "Integridad de todos los TLE históricos", not fallos,
                       esperado=f"{len(cat)} TLE válidos", obtenido={"validos": len(cat) - len(fallos),
                       "invalidos": fallos[:20]}, tolerancia="ninguna",
                       detalle=f"Catálogo de {len(cat)} TLE únicos, épocas {iso(cat[0].epoca)} a "
                               f"{iso(cat[-1].epoca)}.", referencia=REF_HOOTS)
