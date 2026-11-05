"""Modelos de referencia P, PI y PID sintonizados por Ziegler-Nichols.

Que son y que no son
--------------------
Las dos plantas vienen del trabajo academico de Teoria de Control:

    G1(s) = 8 / (s + 2)^3
    G2(s) = 4 / [s (s^2 + 13.5 s + 38.048)]

**No representan ningun subsistema de STRaND-1.** No hay en la telemetria del
satelite una entrada y una salida de lazo que se puedan identificar con ellas.
En el HMTA sirven para lo que sirve un modelo de referencia: estudiar respuestas
dinamicas y comparar una respuesta «medida» con la esperada (ver
`anomaly_detection.comparar_con_modelo`). Ninguna salida de este modulo es una
orden para el satelite, y una discrepancia con el modelo no diagnostica un fallo:
dice que la respuesta no es la del modelo.

Sintonia
--------
Metodo de la ganancia ultima (oscilacion sostenida) de Ziegler-Nichols, que
vale para las dos plantas --- el de la curva de reaccion no, porque G2 tiene un
integrador y su respuesta en lazo abierto no se estabiliza. Ku y Pu se calculan
numericamente sobre la respuesta en frecuencia y coinciden con el resultado
analitico (criterio de Routh):

    G1: (s+2)^3 + 8K = 0          -> wu = sqrt(12),     Ku = 8
    G2: s^3 + 13.5 s^2 + 38.048 s + 4K = 0
                                   -> wu = sqrt(38.048), Ku = 13.5 * 38.048 / 4

    P    Kp = 0.50 Ku
    PI   Kp = 0.45 Ku   Ti = Pu / 1.2
    PID  Kp = 0.60 Ku   Ti = Pu / 2     Td = Pu / 8

Los parametros se conservan sin retocar: la tabla de Ziegler-Nichols es la que
es, y los sobrepasos grandes que produce son parte del resultado.

Implementacion digital
----------------------
Lazo muestreado: planta discretizada con retenedor de orden cero (exacta en los
instantes de muestreo) y controlador por Tustin. El termino derivativo se filtra
con un polo en N/Td (N = 10): sin filtro, un derivador puro amplifica el ruido
de medida sin limite. La estabilidad se juzga por los polos del lazo cerrado
discreto (|z| < 1) y se informa tambien la del modelo continuo.

Solo usa numpy, a proposito: la funcion de Vercel no lleva scipy. Los tests
contrastan este modulo con `scipy.signal` y con el script de MATLAB
`validacion_matlab/validar_pid_zn.m`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np

PLANTAS: dict[str, dict] = {
    "G1": {"num": [8.0], "den": [1.0, 6.0, 12.0, 8.0], "expresion": "8 / (s + 2)^3",
           "descripcion": "Tercer orden con un polo triple en s = −2; ganancia estática 1."},
    "G2": {"num": [4.0], "den": [1.0, 13.5, 38.048, 0.0],
           "expresion": "4 / [s (s² + 13.5 s + 38.048)]",
           "descripcion": "Tercer orden con un integrador (tipo 1) y dos polos reales "
                          "estables; error nulo ante escalón aun sin acción integral."},
}
CONTROLADORES = ("P", "PI", "PID")

TS_POR_DEFECTO = 0.01      # s: unas cien muestras por periodo ultimo de G2 (Pu ~ 1,02 s)
N_FILTRO = 10.0            # polo del filtro derivativo en N/Td
HORIZONTE_S = 20.0
BANDA_ASENTAMIENTO = 0.02

LIMITACIONES = (
    "G1 y G2 son modelos del trabajo académico de Teoría de Control; no se ha identificado "
    "ningún subsistema de STRaND-1 con ellos.",
    "Los resultados son matemáticos (ESTIMADO): no son mediciones de telemetría.",
    "Ningún controlador de este módulo envía órdenes al satélite.",
    "Ziegler–Nichols da un punto de partida agresivo (sobrepasos del 30-60 %), no una sintonía "
    "óptima.",
    "Una discrepancia con el modelo indica que la respuesta no es la del modelo, no que exista "
    "una avería.",
)


# ─── Utilidades de polinomios y sistemas ───────────────────────────────────

def _evaluar(num, den, s):
    return np.polyval(num, s) / np.polyval(den, s)


def ganancia_ultima(planta: str) -> dict:
    """Ku, wu y Pu: donde la fase de G(jw) cruza −180°."""
    p = PLANTAS[planta]
    w = np.logspace(-3, 3, 200_001)
    fase = np.unwrap(np.angle(_evaluar(p["num"], p["den"], 1j * w)))
    i = np.flatnonzero((fase[:-1] > -np.pi) & (fase[1:] <= -np.pi))[0]
    a, b = w[i], w[i + 1]
    # Biseccion sobre la fase para no depender de la rejilla.
    for _ in range(80):
        m = 0.5 * (a + b)
        fm = np.angle(_evaluar(p["num"], p["den"], 1j * m))
        # Cerca de −180° la fase envuelta salta a +180°: se compara el seno.
        if np.sin(fm) < 0:
            a = m
        else:
            b = m
    wu = 0.5 * (a + b)
    ku = 1.0 / abs(_evaluar(p["num"], p["den"], 1j * wu))
    return {"Ku": float(ku), "wu_rad_s": float(wu), "Pu_s": float(2 * np.pi / wu)}


@dataclass(frozen=True)
class Sintonia:
    planta: str
    controlador: str
    Kp: float
    Ti: float | None
    Td: float | None
    metodo: str = "Ziegler–Nichols, ganancia última"

    def dict(self) -> dict:
        return asdict(self)


def sintonia(planta: str, controlador: str) -> Sintonia:
    u = ganancia_ultima(planta)
    ku, pu = u["Ku"], u["Pu_s"]
    if controlador == "P":
        return Sintonia(planta, "P", 0.5 * ku, None, None)
    if controlador == "PI":
        return Sintonia(planta, "PI", 0.45 * ku, pu / 1.2, None)
    if controlador == "PID":
        return Sintonia(planta, "PID", 0.6 * ku, pu / 2, pu / 8)
    raise KeyError(controlador)


def controlador_continuo(s: Sintonia, n: float = N_FILTRO) -> tuple[np.ndarray, np.ndarray]:
    """C(s) = Kp [1 + 1/(Ti s) + Td s / (Td/N s + 1)] como (num, den)."""
    kp = s.Kp
    if s.controlador == "P":
        return np.array([kp]), np.array([1.0])
    ti = s.Ti
    if s.controlador == "PI":
        return np.array([kp * ti, kp]), np.array([ti, 0.0])
    a = s.Td / n
    num = kp * np.array([ti * a + s.Td * ti, ti + a, 1.0])
    den = np.array([ti * a, ti, 0.0])
    return num, den


def _tustin(num, den, ts: float) -> tuple[np.ndarray, np.ndarray]:
    """Transformacion bilineal s = (2/Ts)(z−1)/(z+1) sobre (num, den) en s."""
    orden = max(len(num), len(den)) - 1
    k = 2.0 / ts

    def transforma(c):
        c = np.concatenate([np.zeros(orden + 1 - len(c)), c])
        total = np.zeros(orden + 1)
        for i, coef in enumerate(c[::-1]):          # coef de s^i
            # Con np.polymul y no con poly1d: un escalar de numpy por un poly1d
            # se trata como array y multiplica coeficiente a coeficiente.
            term = np.array([float(coef) * k ** i])
            for _ in range(i):
                term = np.polymul(term, [1.0, -1.0])
            for _ in range(orden - i):
                term = np.polymul(term, [1.0, 1.0])
            total = np.polyadd(total, term)
        return np.asarray(total, float)

    nz, dz = transforma(np.asarray(num, float)), transforma(np.asarray(den, float))
    return nz / dz[0], dz / dz[0]


def _expm(m: np.ndarray) -> np.ndarray:
    """Exponencial de matriz por escalado y cuadrado con serie de Taylor."""
    norma = np.linalg.norm(m, 1)
    s = max(0, int(np.ceil(np.log2(norma))) + 1) if norma > 0 else 0
    a = m / 2 ** s
    e = np.eye(len(m))
    termino = np.eye(len(m))
    for k in range(1, 25):
        termino = termino @ a / k
        e = e + termino
    for _ in range(s):
        e = e @ e
    return e


def _zoh(num, den, ts: float) -> tuple[np.ndarray, np.ndarray]:
    """Discretizacion exacta con retenedor de orden cero de una planta estrictamente propia."""
    den = np.asarray(den, float)
    num = np.asarray(num, float) / den[0]
    den = den / den[0]
    n = len(den) - 1
    b = np.concatenate([np.zeros(n - len(num)), num])
    a_mat = np.zeros((n, n))
    a_mat[0, :] = -den[1:]
    a_mat[1:, :-1] = np.eye(n - 1)
    b_vec = np.zeros((n, 1))
    b_vec[0, 0] = 1.0
    c_vec = b.reshape(1, n)
    aumentada = np.zeros((n + 1, n + 1))
    aumentada[:n, :n] = a_mat
    aumentada[:n, n:] = b_vec
    e = _expm(aumentada * ts)
    ad, bd = e[:n, :n], e[:n, n:]
    # SISO sin termino directo: N(z) = det(zI − A + BC) − det(zI − A).
    dz = np.poly(ad)
    nz = np.poly(ad - bd @ c_vec) - dz
    return np.real(nz), np.real(dz)


def _filtrar(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Ecuacion en diferencias a[0] y[k] = sum b x − sum a y (como lfilter)."""
    b = np.asarray(b, float) / a[0]
    a = np.asarray(a, float) / a[0]
    nb, na = len(b), len(a)
    y = np.zeros(len(x))
    for k in range(len(x)):
        acc = 0.0
        for i in range(nb):
            if k - i >= 0:
                acc += b[i] * x[k - i]
        for j in range(1, na):
            if k - j >= 0:
                acc -= a[j] * y[k - j]
        y[k] = acc
    return y


def _alinear(num, den):
    """Rellena num por delante para que tenga el grado de den (coeficientes en z^-1)."""
    num = np.asarray(num, float)
    return np.concatenate([np.zeros(len(den) - len(num)), num]), np.asarray(den, float)


# ─── Lazo cerrado ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Respuesta:
    planta: str
    controlador: str
    ts: float
    t: np.ndarray
    y: np.ndarray
    polos_continuos: np.ndarray
    polos_discretos: np.ndarray
    valor_final: float | None


def lazo(planta: str, controlador: str, ts: float = TS_POR_DEFECTO,
         factor_planta: float = 1.0) -> dict:
    """Polinomios del lazo cerrado continuo y discreto."""
    p = PLANTAS[planta]
    ng, dg = np.asarray(p["num"]) * factor_planta, np.asarray(p["den"])
    nc, dc = controlador_continuo(sintonia(planta, controlador))
    den_s = np.polyadd(np.polymul(dc, dg), np.polymul(nc, ng))
    num_s = np.polymul(nc, ng)

    ngz, dgz = _zoh(ng, dg, ts)
    ncz, dcz = _tustin(nc, dc, ts)
    num_z = np.polymul(ncz, ngz)
    den_z = np.polyadd(np.polymul(dcz, dgz), num_z)
    return {"num_s": num_s, "den_s": den_s, "num_z": num_z, "den_z": den_z,
            "planta_z": (ngz, dgz), "controlador_z": (ncz, dcz)}


def respuesta(planta: str, controlador: str, ts: float = TS_POR_DEFECTO,
              horizonte: float = HORIZONTE_S, factor_planta: float = 1.0) -> Respuesta:
    """Respuesta a un escalon unitario de referencia del lazo muestreado."""
    l = lazo(planta, controlador, ts, factor_planta)
    t = np.arange(0.0, horizonte + ts / 2, ts)
    b, a = _alinear(l["num_z"], l["den_z"])
    y = _filtrar(b, a, np.ones(len(t)))
    polos_z = np.roots(l["den_z"])
    estable = bool(np.all(np.abs(polos_z) < 1 - 1e-9))
    final = float(np.sum(l["num_z"]) / np.sum(l["den_z"])) if estable else None
    return Respuesta(planta, controlador, ts, t, y, np.roots(l["den_s"]), polos_z, final)


def metricas(r: Respuesta) -> dict:
    """Sobrepaso, tiempos de subida (10-90 %), pico y asentamiento (2 %), error estacionario."""
    estable_z = bool(np.all(np.abs(r.polos_discretos) < 1 - 1e-9))
    estable_s = bool(np.all(np.real(r.polos_continuos) < 0))
    base = {"estable_discreto": estable_z, "estable_continuo": estable_s,
            "max_modulo_polo_z": float(np.max(np.abs(r.polos_discretos))),
            "max_parte_real_polo_s": float(np.max(np.real(r.polos_continuos)))}
    if not estable_z or r.valor_final is None:
        return {**base, "sobrepaso_pct": None, "tiempo_subida_s": None, "tiempo_pico_s": None,
                "tiempo_asentamiento_s": None, "error_estacionario": None, "valor_final": None}
    yf = r.valor_final
    y, t = r.y, r.t

    def cruce(nivel):
        i = np.flatnonzero(y >= nivel * yf)
        return float(t[i[0]]) if len(i) else None

    t10, t90 = cruce(0.1), cruce(0.9)
    fuera = np.flatnonzero(np.abs(y - yf) > BANDA_ASENTAMIENTO * abs(yf))
    if len(fuera) == 0:
        t_as = 0.0
    elif fuera[-1] + 1 < len(t):
        t_as = float(t[fuera[-1] + 1])
    else:
        t_as = None                     # no asienta dentro del horizonte
    i_pico = int(np.argmax(y))
    return {**base,
            "sobrepaso_pct": round(float(max(0.0, (y[i_pico] - yf) / yf * 100)), 2),
            "tiempo_subida_s": round(t90 - t10, 4) if t10 is not None and t90 is not None else None,
            "tiempo_pico_s": round(float(t[i_pico]), 4),
            "tiempo_asentamiento_s": round(t_as, 4) if t_as is not None else None,
            # + 0.0 convierte el cero negativo de coma flotante en 0.
            "error_estacionario": round(1.0 - yf, 6) + 0.0,
            "valor_final": round(yf, 6)}


def margenes(planta: str, controlador: str) -> dict:
    """Margen de ganancia y de fase del lazo abierto continuo C(s)G(s)."""
    p = PLANTAS[planta]
    nc, dc = controlador_continuo(sintonia(planta, controlador))
    num, den = np.polymul(nc, p["num"]), np.polymul(dc, p["den"])
    w = np.logspace(-3, 3, 200_001)
    l = _evaluar(num, den, 1j * w)
    mag, fase = np.abs(l), np.unwrap(np.angle(l))
    out = {"margen_ganancia_db": None, "margen_fase_deg": None,
           "w_cruce_ganancia": None, "w_cruce_fase": None}
    i = np.flatnonzero((mag[:-1] >= 1) & (mag[1:] < 1))
    if len(i):
        out["w_cruce_ganancia"] = float(w[i[0]])
        out["margen_fase_deg"] = round(float(np.degrees(fase[i[0]]) + 180), 2)
    j = np.flatnonzero((fase[:-1] > -np.pi) & (fase[1:] <= -np.pi))
    if len(j):
        out["w_cruce_fase"] = float(w[j[0]])
        out["margen_ganancia_db"] = round(float(-20 * np.log10(mag[j[0]])), 2)
    return out


def _submuestrear(t: np.ndarray, y: np.ndarray, max_puntos: int = 400) -> list[dict]:
    paso = max(1, len(t) // max_puntos)
    return [{"t": round(float(a), 4), "y": round(float(b), 5)} for a, b in zip(t[::paso], y[::paso])]


@lru_cache(maxsize=16)
def informe(ts: float = TS_POR_DEFECTO) -> dict:
    """Todo lo que la interfaz «Modelos PID» necesita, en un diccionario serializable."""
    modelos = []
    for planta, p in PLANTAS.items():
        u = ganancia_ultima(planta)
        filas = []
        for c in CONTROLADORES:
            r = respuesta(planta, c, ts)
            filas.append({
                "controlador": c,
                "sintonia": sintonia(planta, c).dict(),
                "metricas": metricas(r),
                "margenes": margenes(planta, c),
                "polos_discretos": [{"re": float(z.real), "im": float(z.imag), "modulo": float(abs(z))}
                                    for z in r.polos_discretos],
                "respuesta": _submuestrear(r.t, r.y),
            })
        modelos.append({"planta": planta, "expresion": p["expresion"],
                        "descripcion": p["descripcion"], "ganancia_ultima": u,
                        "controladores": filas})
    return {
        "procedencia": "ESTIMADO",
        "ts_s": ts,
        "n_filtro_derivativo": N_FILTRO,
        "discretizacion": "Planta: retenedor de orden cero (exacta en el muestreo). "
                          "Controlador: Tustin (bilineal).",
        "entrada": "Escalón unitario de referencia en t = 0",
        "banda_asentamiento": BANDA_ASENTAMIENTO,
        "limitaciones": list(LIMITACIONES),
        "modelos": modelos,
    }
