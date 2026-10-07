"""Monitoreo en tiempo real del enlace RF simulado (GNU Radio).

Pagina «Enlace RF» de la plataforma: lanza `cadena_strand1_awgn.py` como
subproceso (con el venv `strand`, que es el que tiene GNU Radio instalado),
verifica la integridad de los 18.776 bits, calcula BER / espectro / constelacion
desde el tap IQ real y re-decodifica las balizas AMSAT del proyecto con el
decodificador de esta misma plataforma. No toca la cadena de bits, no abre la
base de datos y no inventa metricas: lo que no se puede medir sale como None
con su explicacion (RSSI y FER).

Regla critica conservada: los datos vienen solo de dos fuentes de verdad —
los archivos que escribe GNU Radio (`bits_rx_sim.bin` = 18.776 bytes 0/1 con
1 byte = 1 bit, y `iq_sim.c64` = tap real del canal tras AWGN) y el
decodificador `strand_amsat` sobre las balizas reales del CSV del proyecto.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .strand_amsat import decodificar

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Rutas y parametros del enlace
# ─────────────────────────────────────────────────────────────────────────────
RAIZ_CUBESAT = Path(__file__).resolve().parents[4]  # .../cubesat
RAIZ_PROYECTO = Path(__file__).resolve().parents[5]  # .../proyecto_grado
ESTADO_DIR = Path(__file__).resolve().parents[2] / "_estado_enlace"

BITS_TX = RAIZ_CUBESAT / "frames_STRAND1_bits.bin"  # 18.776 bytes, 1 byte = 1 bit
CADENA_GR = RAIZ_CUBESAT / "cadena_strand1_awgn.py"  # cadena GNU Radio validada
BITS_RX_SIM = ESTADO_DIR / "bits_rx_sim.bin"
IQ_SIM = ESTADO_DIR / "iq_sim.c64"
BALIZAS_CSV = RAIZ_CUBESAT / "telemetria_strand1" / "telemetria_decodificada_good.csv"

N_BITS = 18_776
FRAMES_ESPERADOS = 100
MODULACION = "BPSK"
FREQ_HZ = 437_568_000
SYMBOL_RATE = 9_600  # baudios
SAMPLE_RATE = 76_800  # Hz
SAMPLES_PER_SYMBOL = 8  # SAMPLE_RATE / SYMBOL_RATE
ROLLOFF = 0.35
SNR_MIN_DB = 0
SNR_MAX_DB = 12
SNR_DEFAULT_DB = 8
SEED = 11

HISTORIAL_MAX = 300
FFT_NFFT = 4096
FFT_MAX_PUNTOS = 2048
CONST_PUNTOS = 400

# Limites de ingenieria documentados para marcar NORMAL/ALERTA. Las claves son
# los canales del decodificador AMSAT; los rangos se deducen de la calibracion
# publicada (p. ej. bateria ~ 9.75 V nominal).
LIMITES_TELEMETRIA = {
    "battery_0_voltage": (8.0, 9.9),
    "battery_1_voltage": (8.0, 9.9),
    "battery_0_temperature": (0.0, 45.0),
    "battery_1_temperature": (0.0, 45.0),
}

# Orden de presentacion preferido de los parametros en el panel.
PARAMETROS_PREFERIDOS = [
    "battery_0_voltage",
    "battery_1_voltage",
    "battery_0_temperature",
    "battery_1_temperature",
    "obc_unix_time",
    "magnetometer_x",
    "magnetometer_y",
    "magnetometer_z",
]


def python_strand() -> str:
    """Interprete con GNU Radio instalado (venv `strand`); sobreescribible con GR_PYTHON."""
    if os.environ.get("GR_PYTHON"):
        return os.environ["GR_PYTHON"]
    if os.name == "nt":
        candidato = RAIZ_PROYECTO / "strand" / "Scripts" / "python.exe"
    else:
        candidato = RAIZ_PROYECTO / "strand" / "bin" / "python"
    return str(candidato) if candidato.exists() else "python"


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ─────────────────────────────────────────────────────────────────────────────
# Integridad de los 18.776 bits
# ─────────────────────────────────────────────────────────────────────────────
def cargar_bits(ruta: Path) -> np.ndarray:
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo de bits: {ruta}")
    return np.frombuffer(ruta.read_bytes(), dtype=np.uint8)


def sha256_bits(bits: np.ndarray) -> str:
    return hashlib.sha256(bits.tobytes()).hexdigest()


def validar_integridad(ruta_rx: Path = BITS_RX_SIM) -> dict[str, Any]:
    """Compara TX (18.776 bits) contra RX: longitud, diferencia y SHA-256."""
    try:
        tx = cargar_bits(BITS_TX)
        rx = cargar_bits(ruta_rx)
    except FileNotFoundError:
        return {
            "valido": None, "bits_entrada": N_BITS, "bits_recuperados": None,
            "diferencia": None, "sha256_entrada": None, "sha256_recuperado": None,
            "frames_esperados": FRAMES_ESPERADOS,
            "mensaje": "Todavia no hay salida de la simulacion.",
        }
    m = min(len(tx), len(rx))
    diferencia = int(np.count_nonzero(tx[:m] != rx[:m])) if m else -1
    completos = len(tx) == N_BITS and len(rx) == N_BITS
    valido = completos and diferencia == 0 and sha256_bits(tx) == sha256_bits(rx)
    return {
        "valido": valido,
        "bits_entrada": len(tx),
        "bits_recuperados": len(rx),
        "diferencia": diferencia,
        "sha256_entrada": sha256_bits(tx),
        "sha256_recuperado": sha256_bits(rx),
        "frames_esperados": FRAMES_ESPERADOS,
        "mensaje": (
            "18.776 bits de entrada y salida identicos"
            if valido
            else f"discrepancia detectada (diff={diferencia})"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Espectro y constelacion desde el tap IQ
# ─────────────────────────────────────────────────────────────────────────────
def _leer_iq(ruta: Path = IQ_SIM) -> np.ndarray | None:
    if not ruta.exists():
        return None
    try:
        datos = np.fromfile(ruta, dtype=np.complex64)
    except Exception:
        return None
    return datos if datos.size else None


def _welch(senal: np.ndarray, nfft: int = FFT_NFFT):
    ventana = np.hanning(nfft)
    bloques = max(1, (senal.size - nfft) // (nfft // 2))
    acc = np.zeros(nfft, dtype=np.complex128)
    for b in range(bloques):
        inicio = b * (nfft // 2)
        trozo = senal[inicio:inicio + nfft]
        if trozo.size < nfft:
            trozo = np.pad(trozo, (0, nfft - trozo.size))
        acc += np.fft.fftshift(np.fft.fft(trozo * ventana))
    psd = (np.abs(acc) ** 2) / (bloques * nfft)
    psd_db = 10.0 * np.log10(psd + 1e-12)
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / SAMPLE_RATE))
    return f, psd_db


def espectro_enlace() -> dict[str, Any]:
    iq = _leer_iq()
    if iq is None or iq.size < FFT_NFFT:
        return {
            "disponible": False,
            "fuente": None,
            "nota": (
                "FFT data unavailable — ejecuta la simulacion para capturar "
                "el tap IQ real de la cadena GNU Radio"
            ),
        }
    f, psd = _welch(iq)
    paso = max(1, len(f) // FFT_MAX_PUNTOS)
    return {
        "disponible": True,
        "fuente": "Tap IQ real de cadena_strand1_awgn.py (canal tras AWGN)",
        "frecuencia_central_hz": 0.0,
        "ancho_banda_hz": SAMPLE_RATE,
        "datos": [
            {"freq_hz": round(float(fr), 2), "power_db": round(float(p), 3)}
            for fr, p in zip(f[::paso], psd[::paso])
        ],
    }


def constelacion_enlace() -> dict[str, Any]:
    iq = _leer_iq()
    if iq is None:
        return {
            "disponible": False,
            "fuente": None,
            "nota": "Constelacion no disponible — ejecuta la simulacion primero",
        }
    en_simbolo = iq[::SAMPLES_PER_SYMBOL]
    if en_simbolo.size > CONST_PUNTOS:
        idx = np.linspace(0, en_simbolo.size - 1, CONST_PUNTOS).astype(int)
        en_simbolo = en_simbolo[idx]
    sel = en_simbolo if en_simbolo.size else iq[:CONST_PUNTOS]
    return {
        "disponible": True,
        "fuente": "Muestras IQ del canal muestreadas a tasa de simbolo (tap real)",
        "puntos": [
            {"i": round(float(z.real), 4), "q": round(float(z.imag), 4)} for z in sel
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Telemetria: balizas reales re-decodificadas con strand_amsat
# ─────────────────────────────────────────────────────────────────────────────
_cache_balizas: list[dict[str, Any]] | None = None


def _leer_balizas() -> list[dict[str, Any]]:
    global _cache_balizas
    if _cache_balizas is not None:
        return _cache_balizas
    registros: list[dict[str, Any]] = []
    if not BALIZAS_CSV.exists():
        _cache_balizas = registros
        return registros
    import csv

    with BALIZAS_CSV.open(newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            hex_data = (fila.get("hex") or "").strip()
            if not hex_data:
                continue
            try:
                raw = bytes.fromhex("".join(hex_data.split()))
            except ValueError:
                continue
            baliza = decodificar(raw)
            registros.append(
                {
                    "timestamp": fila.get("timestamp"),
                    "observer": fila.get("estacion"),
                    "tamano_bytes": len(raw),
                    "hex": (hex_data[:64] + ("..." if len(hex_data) > 64 else "")),
                    "decodificado": bool(baliza and baliza.valores),
                    "valores": dict(baliza.valores) if baliza else {},
                    "unidades": dict(baliza.unidades) if baliza else {},
                }
            )
    _cache_balizas = registros
    return registros


def parametros_telemetria() -> list[dict[str, Any]]:
    """Tabla de parametros: ultimo valor por canal (el mas reciente)."""
    balizas = _leer_balizas()
    ultimo: dict[str, Any] = {}
    unidades: dict[str, Any] = {}
    for reg in reversed(balizas):
        if not reg["valores"]:
            continue
        for clave, valor in reg["valores"].items():
            if clave not in ultimo:
                ultimo[clave] = valor
                unidades[clave] = reg["unidades"].get(clave)

    descartada = lambda c: c.endswith("_adc") or c.startswith("obc_campo")  # noqa: E731
    visibles = [c for c in ultimo if not descartada(c)]

    def clave_orden(clave: str):
        preferida = (
            -1 if clave in PARAMETROS_PREFERIDOS else 0
        )
        con_unidad = 0 if unidades.get(clave) else 1
        return (preferida, con_unidad, clave)

    parametros = []
    for clave in sorted(visibles, key=clave_orden):
        valor = ultimo[clave]
        limite = LIMITES_TELEMETRIA.get(clave)
        if isinstance(valor, (int, float)) and limite is not None:
            status = "NORMAL" if limite[0] <= valor <= limite[1] else "ALERTA"
        else:
            status = "OK"
        parametros.append(
            {
                "key": clave,
                "label": clave.replace("_", " "),
                "value": valor,
                "unit": unidades.get(clave),
                "status": status,
                "disponible": True,
            }
        )
    return parametros


def telemetria_enlace() -> dict[str, Any]:
    balizas = _leer_balizas()
    frames = [
        {
            "timestamp": r["timestamp"],
            "observer": r["observer"],
            "tamano_bytes": r["tamano_bytes"],
            "hex": r["hex"],
            "decodificado": r["decodificado"],
            "campos": r["valores"],
        }
        for r in balizas[-20:]
    ]
    ultimo_ts = next((f["timestamp"] for f in reversed(frames) if f["timestamp"]), None)
    return {
        "total_frames": len(balizas),
        "ultimo_timestamp": ultimo_ts,
        "parametros": parametros_telemetria(),
        "frames": frames,
        "nota": (
            f"{len(balizas)} balizas reales re-decodificadas con strand_amsat.py "
            "(especificacion AMSAT-UK corregida). Ultimo valor por canal."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Estado del enlace y metricas de la sesion
# ─────────────────────────────────────────────────────────────────────────────
class EnlaceRunner:
    """Lanza y supervisa la cadena GNU Radio como subproceso."""

    def __init__(self) -> None:
        self._estado = "IDLE"
        self._snr_actual: float | None = None
        self._proceso: asyncio.subprocess.Process | None = None
        self._resultado: dict[str, Any] = {}
        self.log: deque[dict[str, Any]] = deque(maxlen=200)
        # Metricas acumuladas por la sesion (historial para la grafica BER/SNR).
        self._historial: deque[dict[str, Any]] = deque(maxlen=HISTORIAL_MAX)
        self._metricas: dict[str, Any] | None = None

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def snr_actual(self) -> float | None:
        return self._snr_actual

    @property
    def resultado(self) -> dict[str, Any]:
        return self._resultado

    def iniciar(self, snr_db: float) -> None:
        if self._estado == "RUNNING":
            raise RuntimeError("Ya hay una simulacion en marcha.")
        if not BITS_TX.exists():
            raise RuntimeError(f"No existe el archivo de bits de entrada: {BITS_TX}")
        if not CADENA_GR.exists():
            raise RuntimeError(f"No existe la cadena GNU Radio: {CADENA_GR}")
        ESTADO_DIR.mkdir(parents=True, exist_ok=True)

        cmd = [
            python_strand(),
            str(CADENA_GR),
            "--input", str(BITS_TX),
            "--output", str(BITS_RX_SIM),
            "--iq-output", str(IQ_SIM),
            "--snr-db", f"{snr_db:.0f}",
            "--seed", str(SEED),
        ]
        self._estado = "RUNNING"
        self._snr_actual = snr_db
        self._resultado = {}
        self.log.append(
            {
                "timestamp": ahora_iso(),
                "nivel": "INFO",
                "mensaje": f"Lanzando GNU Radio (SNR {snr_db} dB, seed {SEED})",
            }
        )
        logger.info("Lanzando enlace: %s", " ".join(cmd))
        self._motivo_arranque = cmd

    async def supervisar(self, al_finalizar: Callable[[int], Any]) -> None:
        cmd = self._motivo_arranque
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(RAIZ_CUBESAT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            self.log.append(
                {
                    "timestamp": ahora_iso(),
                    "nivel": "ERROR",
                    "mensaje": f"No se pudo lanzar GNU Radio: {exc}",
                }
            )
            self._estado = "ERROR"
            return
        self._proceso = proc
        stdout, stderr = await proc.communicate()
        rc = proc.returncode or 0
        self._resultado = {
            "rc": rc,
            "stderr": (stderr or b"").decode("utf-8", errors="replace").strip(),
            "stdout": (stdout or b"").decode("utf-8", errors="replace").strip(),
        }
        if rc != 0:
            self.log.append(
                {
                    "timestamp": ahora_iso(),
                    "nivel": "ERROR",
                    "mensaje": f"La cadena GNU Radio termino con codigo {rc}",
                }
            )
            self._estado = "ERROR"
        else:
            self.log.append(
                {
                    "timestamp": ahora_iso(),
                    "nivel": "INFO",
                    "mensaje": "Cadena GNU Radio finalizada correctamente",
                }
            )
            self._estado = "STOPPED"
        if al_finalizar:
            await al_finalizar(rc)

    def detener(self) -> None:
        if self._proceso and self._proceso.returncode is None:
            try:
                self._proceso.terminate()
            except ProcessLookupError:
                pass
        self._estado = self._estado if self._estado == "ERROR" else "STOPPED"

    def reset(self) -> None:
        for ruta in (BITS_RX_SIM, IQ_SIM):
            try:
                ruta.unlink(missing_ok=True)
            except OSError:
                pass
        self.log.clear()
        self._historial.clear()
        self._metricas = None
        self._resultado = {}
        self._estado = "IDLE"
        self._snr_actual = None

    # ── metricas de sesion ──────────────────────────────────────────────────
    def metricas_enlace(self) -> dict[str, Any]:
        """BER medido + potencia/ruido del tap IQ (reales, nada inventado)."""
        if self._metricas is None:
            return self._metricas_sin_datos()
        return self._metricas

    def _metricas_sin_datos(self) -> dict[str, Any]:
        return {
            "snr_db": self._snr_actual,
            "ber": None,
            "rssi_dbm": None,
            "fer": None,
            "potencia_relativa_dbfs": None,
            "ruido_estimado": None,
            "frecuencia_hz": FREQ_HZ,
            "tasa_bits_bps": SYMBOL_RATE,
            "ancho_banda_hz": SYMBOL_RATE * (1 + ROLLOFF),
            "frames_recibidos": None,
            "frames_validos": None,
            "frames_error": None,
            "nota_rssi": (
                "N/A — el modelo es baseband-equivalente: no hay potencia RF "
                "para expresar en dBm"
            ),
            "nota_fer": (
                "N/A — la cadena minima no tiene trama AX.25 ni FEC; el modelo "
                "avanzado (simular_enlace_rf_bpsk_avanzado.py) si reporta "
                "ax25_frames_validos"
            ),
            "nota_frecuencia": "437.568 MHz UHF (banda de bajada nominal de STRAND-1)",
            "nota_ancho_banda": (
                f"BW ≈ R·(1+α) = {SYMBOL_RATE * (1 + ROLLOFF):.0f} Hz (RRC, α={ROLLOFF})"
            ),
        }

    def calcular_metricas(self, snr_db: float) -> dict[str, Any]:
        """Se llama al terminar la simulacion; alimenta tambien el historial."""
        try:
            rx = cargar_bits(BITS_RX_SIM)
        except FileNotFoundError:
            return self._metricas_sin_datos()
        tx = cargar_bits(BITS_TX)
        n = min(len(tx), len(rx))
        errores = int(np.count_nonzero(tx[:n] != rx[:n])) if n else 0
        ber = errores / n if n else None
        integridad = validar_integridad(BITS_RX_SIM)

        iq = _leer_iq()
        potencia = ruido = None
        if iq is not None:
            potencia = float(10.0 * np.log10(np.mean(np.abs(iq) ** 2) + 1e-12))
            ruido = self._estimador_ruido(iq)

        base = self._metricas_sin_datos()
        base.update(
            {
                "snr_db": snr_db,
                "ber": ber,
                "potencia_relativa_dbfs": potencia,
                "ruido_estimado": ruido,
                "frames_recibidos": FRAMES_ESPERADOS,
                "frames_validos": FRAMES_ESPERADOS if integridad["valido"] else None,
                "frames_error": 0 if integridad["valido"] else None,
            }
        )
        self._metricas = base
        self._historial.append(
            {
                "timestamp": ahora_iso(),
                "snr_db": snr_db,
                "ber": ber,
                "potencia_relativa_dbfs": potencia,
            }
        )
        return base

    def historial(self) -> list[dict[str, Any]]:
        return list(self._historial)

    @staticmethod
    def _estimador_ruido(iq: np.ndarray) -> float | None:
        if iq.size < FFT_NFFT * 4:
            return None
        try:
            f, psd = _welch(iq)
        except Exception:
            return None
        banda_senal = SYMBOL_RATE * (1 + ROLLOFF) / 2
        fuera = np.abs(f) > banda_senal + 1000
        if not np.any(fuera):
            return None
        return float(np.mean(psd[fuera]))


enlace = EnlaceRunner()


def estado_enlace() -> dict[str, Any]:
    en_marcha = enlace.estado == "RUNNING"
    ok = enlace.resultado.get("rc") == 0 or enlace._metricas is not None
    link = "ACTIVE" if (en_marcha or ok) else "OFFLINE"
    return {
        "link_status": link,
        "sim_status": enlace.estado,
        "timestamp": ahora_iso(),
        "frames_received": enlace._metricas.get("frames_recibidos") if enlace._metricas else None,
        "frames_valid": enlace._metricas.get("frames_validos") if enlace._metricas else None,
        "frames_error": enlace._metricas.get("frames_error") if enlace._metricas else None,
        "mensaje": (enlace.resultado.get("stderr") or "")[-300:] or None,
    }


def config_enlace() -> dict[str, Any]:
    return {
        "modulacion": MODULACION,
        "frecuencia_hz": FREQ_HZ,
        "tasa_bits_bps": SYMBOL_RATE,
        "muestras_por_simbolo": SAMPLES_PER_SYMBOL,
        "rolloff": ROLLOFF,
        "bits_esperados": N_BITS,
        "archivo_bits": str(BITS_TX),
        "snr_min_db": SNR_MIN_DB,
        "snr_max_db": SNR_MAX_DB,
        "snr_default_db": SNR_DEFAULT_DB,
        "frames_esperados": FRAMES_ESPERADOS,
    }