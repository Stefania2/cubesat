"""Adquisicion de telemetria: cualquier fuente, una sola forma, y su procedencia.

Todo lo que entra al HMTA pasa por aqui y sale como un `ConjuntoTelemetria`:
una tabla larga de mediciones mas, si existen, las tablas de recepcion (tramas,
contadores de secuencia y observaciones). Cada fila lleva su **procedencia**:

    REAL           medicion de una fuente verificable (balizas de SatNOGS)
    SIMULADO       dato generado por una simulacion o un escenario de prueba
    ESTIMADO       calculado a partir de un modelo o de otros datos
    DOCUMENTADO    tomado de documentacion tecnica
    NO_DISPONIBLE  la fuente consultada no tiene ese dato

La procedencia no se infiere despues: se fija en el momento de adquirir y
viaja con la fila. Un escenario simulado nunca puede acabar pintado como real
porque `simular_escenario` escribe SIMULADO en todas sus filas y el informe
de salud lo hereda.

Fuentes
-------
`cargar_real()` lee PostgreSQL a traves de `gemelo_digital.datos`, la unica
capa del proyecto que habla con la base. `desde_campos()` hace lo mismo a
partir de un DataFrame ya cargado, para reutilizar la cache del router del
gemelo. `simular_escenario()` genera los escenarios de prueba de la seccion 9
del encargo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

REAL = "REAL"
SIMULADO = "SIMULADO"
ESTIMADO = "ESTIMADO"
DOCUMENTADO = "DOCUMENTADO"
NO_DISPONIBLE = "NO_DISPONIBLE"
PROCEDENCIAS = (REAL, SIMULADO, ESTIMADO, DOCUMENTADO, NO_DISPONIBLE)

FUENTE_REAL = ("Balizas de STRaND-1 recibidas por la red SatNOGS (DB y Network), "
               "decodificadas con la especificación de AMSAT-UK")
FUENTE_SIMULADA = "Escenario de prueba generado por health_monitor.telemetry_acquisition"

COLUMNAS = ("timestamp", "variable", "valor", "texto", "unidad", "procedencia", "fuente",
            "estacion")


@dataclass(frozen=True)
class Limite:
    """Rango de referencia de una variable, con su fuente.

    `nivel` dice que significa salirse: ADVERTENCIA o CRITICO. Un limite sin
    fuente no puede crearse: es exactamente lo que el encargo prohibe inventar.
    """

    variable: str
    minimo: float | None
    maximo: float | None
    nivel: str
    fuente: str

    def __post_init__(self):
        if not self.fuente.strip():
            raise ValueError("Un límite necesita una fuente documentada.")
        if self.nivel not in ("ADVERTENCIA", "CRITICO"):
            raise ValueError(f"Nivel de límite no válido: {self.nivel}")


@dataclass
class ConjuntoTelemetria:
    mediciones: pd.DataFrame
    procedencia: str
    fuente: str
    descripcion: str = ""
    # Recepcion: una fila por trama (timestamp, estado, estacion, observacion).
    tramas: pd.DataFrame | None = None
    # Contador de secuencia de 8 bits por trama (timestamp, estacion, seq).
    secuencias: pd.DataFrame | None = None
    # Observaciones de SatNOGS (inicio, estado, elevacion_max_deg).
    observaciones: pd.DataFrame | None = None
    limites: dict[str, list[Limite]] = field(default_factory=dict)
    # Respuesta medida que se compara contra un modelo dinamico (t, y, modelo).
    respuesta_dinamica: dict | None = None
    escenario: str | None = None

    @property
    def simulado(self) -> bool:
        return self.procedencia == SIMULADO

    @property
    def vacio(self) -> bool:
        return self.mediciones.empty and (self.tramas is None or self.tramas.empty)

    def serie(self, variable: str) -> pd.DataFrame:
        m = self.mediciones
        s = m[m["variable"] == variable]
        return s.set_index("timestamp").sort_index()

    def variables(self) -> list[str]:
        return sorted(self.mediciones["variable"].unique().tolist())

    def recortar(self, desde: pd.Timestamp | None, hasta: pd.Timestamp | None) -> "ConjuntoTelemetria":
        """Copia restringida a [desde, hasta]. Los limites y el modelo se conservan."""
        def corta(df, col="timestamp"):
            if df is None or df.empty:
                return df
            sel = pd.Series(True, index=df.index)
            if desde is not None:
                sel &= df[col] >= desde
            if hasta is not None:
                sel &= df[col] <= hasta
            return df[sel]
        return ConjuntoTelemetria(
            mediciones=corta(self.mediciones), procedencia=self.procedencia,
            fuente=self.fuente, descripcion=self.descripcion, tramas=corta(self.tramas),
            secuencias=corta(self.secuencias), observaciones=corta(self.observaciones, "inicio"),
            limites=self.limites, respuesta_dinamica=self.respuesta_dinamica,
            escenario=self.escenario)


def tabla_vacia() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNAS}).astype(
        {"valor": "float64", "timestamp": "datetime64[ns, UTC]"})


def _utc(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, utc=True)


# ─── Fuente real ────────────────────────────────────────────────────────────

def desde_campos(campos: pd.DataFrame, estados: pd.DataFrame | None = None,
                 tramas: pd.DataFrame | None = None, secuencias: pd.DataFrame | None = None,
                 observaciones: pd.DataFrame | None = None) -> ConjuntoTelemetria:
    """Conjunto REAL a partir de los DataFrames de `gemelo_digital.datos`.

    `campos` es lo que devuelve `datos.cargar_campos()`; `estados`, el texto de
    los interruptores (`datos.cargar_estados()`); `tramas`, `datos.cargar_frames()`;
    `secuencias`, `datos.cargar_secuencias()`; `observaciones`,
    `datos.cargar_observaciones()`. Solo `campos` es obligatorio.
    """
    est = campos["station_id"] if "station_id" in campos else pd.Series(pd.NA, index=campos.index)
    med = pd.DataFrame({
        "timestamp": _utc(campos["timestamp"]),
        "variable": campos["field_name"].astype(str),
        "valor": campos["value_numeric"].astype("float64"),
        "texto": None,
        "unidad": campos["unit"].astype(str),
        "procedencia": REAL,
        "fuente": FUENTE_REAL,
        "estacion": est.astype("string"),
    })
    if estados is not None and not estados.empty:
        txt = pd.DataFrame({
            "timestamp": _utc(estados["timestamp"]),
            "variable": estados["field_name"].astype(str),
            "valor": np.nan,
            "texto": estados["value_text"].astype(str),
            "unidad": None,
            "procedencia": REAL,
            "fuente": FUENTE_REAL,
            "estacion": estados.get("station_id", pd.Series(pd.NA, index=estados.index)).astype("string"),
        })
        med = pd.concat([med, txt], ignore_index=True)

    tr = None
    if tramas is not None:
        tr = pd.DataFrame({
            "timestamp": _utc(tramas["timestamp"]),
            "estado": tramas["status"].astype(str),
            "estacion": tramas["observer"].astype("string"),
            "observacion": tramas["observation_id"],
            "tipo": tramas["frame_type"].astype(str),
        })
    sq = None
    if secuencias is not None:
        sq = pd.DataFrame({
            "timestamp": _utc(secuencias["timestamp"]),
            "estacion": secuencias["observer"].astype("string"),
            "seq": secuencias["seq_no"].astype("int64"),
        })
    ob = None
    if observaciones is not None:
        ob = pd.DataFrame({
            "inicio": _utc(observaciones["start"]),
            "estado": observaciones["status"].astype("string"),
            "elevacion_max_deg": observaciones["max_elevation_deg"],
        })
    return ConjuntoTelemetria(
        mediciones=med.sort_values("timestamp", ignore_index=True),
        procedencia=REAL, fuente=FUENTE_REAL,
        descripcion="Archivo histórico de SatNOGS. STRaND-1 está inactivo: no hay enlace en vivo.",
        tramas=tr, secuencias=sq, observaciones=ob)


def cargar_real(env_file=None) -> ConjuntoTelemetria:
    """Lee PostgreSQL (local o Neon, segun `DATABASE_URL`) y devuelve el conjunto REAL."""
    from gemelo_digital import datos

    kw = {} if env_file is None else {"env_file": env_file}
    return desde_campos(
        datos.cargar_campos(**kw), estados=datos.cargar_estados(**kw),
        tramas=datos.cargar_frames(**kw), secuencias=datos.cargar_secuencias(**kw),
        observaciones=datos.cargar_observaciones(**kw))


# ─── Escenarios simulados ───────────────────────────────────────────────────

ESCENARIOS = {
    "nominal": "Funcionamiento sin perturbaciones: sirve de referencia.",
    "caida_voltaje": "El voltaje de la batería cae de forma brusca en el último tercio.",
    "aumento_temperatura": "La temperatura de la batería sube de forma progresiva pase a pase.",
    "perdida_paquetes": "En los últimos pases se pierde la mayoría de los paquetes.",
    "errores_comunicacion": "Aumenta la proporción de tramas recibidas con error.",
    "reinicios_obc": "El contador de tiempo del computador vuelve a cero varias veces.",
    "datos_inconsistentes": "Lecturas duplicadas, saturadas, fuera de dominio y un canal que deja de medir.",
    "sin_telemetria": "No llega ninguna medición.",
    "respuesta_dinamica_anormal": "La respuesta medida de un lazo se aparta del modelo PID de referencia.",
}

# Rango de prueba para el escenario termico. Es un limite inventado para
# ejercitar el detector y lo dice su fuente: nunca se aplica a STRaND-1.
LIMITES_PRUEBA = {
    "battery_temperature": [
        Limite("battery_temperature", 0.0, 40.0, "ADVERTENCIA",
               "Límite de prueba del escenario simulado (no es de STRaND-1)"),
        Limite("battery_temperature", -10.0, 50.0, "CRITICO",
               "Límite de prueba del escenario simulado (no es de STRaND-1)"),
    ],
}

T0_ESCENARIO = pd.Timestamp("2030-01-01T00:00:00Z")
PASES = 30
LECTURAS_POR_PASE = 60
PASO_LECTURA_S = 10
PERIODO_ORBITA_S = 6000


def simular_escenario(nombre: str, semilla: int = 0) -> ConjuntoTelemetria:
    """Escenario de prueba. Todas las filas salen marcadas SIMULADO.

    Treinta pases de diez minutos separados por una orbita, con una lectura
    cada diez segundos. Las fechas estan en 2030 a proposito: un escenario no
    puede confundirse con el archivo real, que acaba en 2023, ni siquiera
    mirando solo el eje de tiempo.
    """
    if nombre not in ESCENARIOS:
        raise KeyError(f"Escenario desconocido: {nombre}. Disponibles: {sorted(ESCENARIOS)}")
    rng = np.random.default_rng(semilla)

    def vacio() -> ConjuntoTelemetria:
        return ConjuntoTelemetria(
            mediciones=tabla_vacia(), procedencia=SIMULADO, fuente=FUENTE_SIMULADA,
            descripcion=ESCENARIOS[nombre], tramas=pd.DataFrame(
                columns=["timestamp", "estado", "estacion", "observacion", "tipo"]),
            secuencias=None, observaciones=None, escenario=nombre)

    if nombre == "sin_telemetria":
        return vacio()

    instantes = []
    for p in range(PASES):
        t_pase = T0_ESCENARIO + pd.Timedelta(seconds=p * PERIODO_ORBITA_S)
        instantes += [t_pase + pd.Timedelta(seconds=k * PASO_LECTURA_S)
                      for k in range(LECTURAS_POR_PASE)]
    t = pd.DatetimeIndex(instantes)
    n = len(t)
    fase = 2 * np.pi * ((t - T0_ESCENARIO).total_seconds().to_numpy() % PERIODO_ORBITA_S) / PERIODO_ORBITA_S
    pase = np.repeat(np.arange(PASES), LECTURAS_POR_PASE)

    filas: list[pd.DataFrame] = []

    def agrega(variable, valores, unidad, idx=None):
        sel = slice(None) if idx is None else idx
        filas.append(pd.DataFrame({
            "timestamp": t[sel], "variable": variable, "valor": np.asarray(valores, float),
            "texto": None, "unidad": unidad, "procedencia": SIMULADO,
            "fuente": FUENTE_SIMULADA, "estacion": "SIM-1"}))

    v0 = 7.8 + 0.15 * np.sin(fase) + rng.normal(0, 0.02, n)
    v1 = 7.75 + 0.15 * np.sin(fase) + rng.normal(0, 0.02, n)
    if nombre == "caida_voltaje":
        corte = int(0.7 * n)
        v0[corte:] -= 1.2
    corriente = np.clip(400 * np.sin(fase + 0.3), 0, None) + rng.normal(0, 3, n)
    temp = 18 + 2 * np.sin(fase) + rng.normal(0, 0.3, n)
    if nombre == "aumento_temperatura":
        temp += 1.1 * pase          # +1,1 °C por pase: de 18 °C a ~50 °C

    agrega("battery_0_voltage", v0, "V")
    agrega("battery_1_voltage", v1, "V")
    agrega("adc13_px_array_current", corriente, "mA")
    agrega("battery_temperature", temp, "°C")

    # Contador de tiempo del OBC: avanza 1 s/s y, en el escenario, se reinicia.
    reloj = (t - T0_ESCENARIO).total_seconds().to_numpy() + 100.0
    if nombre == "reinicios_obc":
        for p_reinicio in (12, 19, 25):
            i0 = p_reinicio * LECTURAS_POR_PASE + 20
            reloj[i0:] = reloj[i0:] - reloj[i0] + 3.0
    agrega("obc_unix_time", reloj, "s")

    if nombre == "datos_inconsistentes":
        # Canal muerto desde la mitad: la cuenta 0 da la ordenada de la recta.
        m = filas[0]
        m.loc[m.index[n // 2:], "valor"] = 9.7488
        # Saturacion a fondo de escala (cuenta 1023) en la corriente de panel.
        c = filas[2]
        c.loc[c.index[100:160], "valor"] = 512.807352 - 0.518702129 * 1023
        # Duplicados exactos y un valor no finito.
        filas.append(filas[1].iloc[200:230].copy())
        filas[1].loc[filas[1].index[300], "valor"] = np.nan

    med = pd.concat(filas, ignore_index=True).sort_values("timestamp", ignore_index=True)

    # Recepcion: una trama por lectura, contador de secuencia de 8 bits.
    seq = np.arange(n) % 256
    estado = np.full(n, "decoded", dtype=object)
    recibida = np.ones(n, bool)
    if nombre == "perdida_paquetes":
        perdidas = (pase >= 24) & (rng.random(n) < 0.7)
        recibida &= ~perdidas
    if nombre == "errores_comunicacion":
        p_err = np.where(pase >= 20, 0.35, 0.01)
        estado[rng.random(n) < p_err] = "error"
    else:
        estado[rng.random(n) < 0.01] = "error"
    tramas = pd.DataFrame({"timestamp": t, "estado": estado, "estacion": "SIM-1",
                           "observacion": pase, "tipo": "beacon"})[recibida]
    secuencias = pd.DataFrame({"timestamp": t, "estacion": "SIM-1", "seq": seq})[recibida & (estado != "error")]
    observaciones = pd.DataFrame({
        "inicio": [T0_ESCENARIO + pd.Timedelta(seconds=p * PERIODO_ORBITA_S) for p in range(PASES)],
        "estado": "good", "elevacion_max_deg": 45.0})

    conjunto = ConjuntoTelemetria(
        mediciones=med, procedencia=SIMULADO, fuente=FUENTE_SIMULADA,
        descripcion=ESCENARIOS[nombre], tramas=tramas.reset_index(drop=True),
        secuencias=secuencias.reset_index(drop=True), observaciones=observaciones,
        limites=dict(LIMITES_PRUEBA), escenario=nombre)

    if nombre == "respuesta_dinamica_anormal":
        from health_monitor import pid_reference as pid
        ref = pid.respuesta("G1", "PID")
        tt = np.asarray(ref.t)
        # Lazo «medido» con un 60 % mas de ganancia de planta: mas sobrepaso y
        # oscilacion que la referencia. Ruido de medida pequeño.
        medida = pid.respuesta("G1", "PID", factor_planta=1.6).y + rng.normal(0, 0.01, len(tt))
        conjunto.respuesta_dinamica = {"modelo": "G1", "controlador": "PID",
                                       "t": tt, "y": np.asarray(medida),
                                       "procedencia": SIMULADO}
    elif nombre == "nominal":
        from health_monitor import pid_reference as pid
        ref = pid.respuesta("G1", "PID")
        conjunto.respuesta_dinamica = {"modelo": "G1", "controlador": "PID",
                                       "t": np.asarray(ref.t),
                                       "y": np.asarray(ref.y) + rng.normal(0, 0.01, len(ref.t)),
                                       "procedencia": SIMULADO}
    return conjunto
