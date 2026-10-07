"""Configuracion del backend del dashboard STRAND-1.

Todos los valores proceden de la cadena de simulacion validada del proyecto.
Ninguno se inventa: los 18.776 bits son la cantidad real de `frames_STRAND1_bits.bin`
y las constantes RF son las usadas por `cadena_strand1_awgn.py`.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# ── Fuentes de datos (copia de lectura, nunca sobreescritas) ────────────────
BITS_TX = RAIZ / "frames_STRAND1_bits.bin"
BITS_RX = RAIZ / "frames_STRAND1_bits_rx.bin"
FRAMES_CSV = RAIZ / "frames_STRAND1.csv"
RESUMEN_JSON = RAIZ / "resumen_telemetria_STRAND1.json"
GNURADIO_BIN = RAIZ / "frames_STRAND1_gnuradio.bin"
CADENA_GR = RAIZ / "cadena_strand1_awgn.py"
RUTA_STRAND_AMSAT = RAIZ / "telemetria_strand1" / "backend" / "app" / "services" / "strand_amsat.py"

TMP = RAIZ / "backend" / "_estado"
TMP.mkdir(exist_ok=True)
BITS_RX_SIM = TMP / "bits_rx_sim.bin"
IQ_SIM = TMP / "iq_sim.c64"

# ── Cadena de simulacion (constantes de cadena_strand1_awgn.py) ─────────────
N_BITS = 18_776
SYMBOL_RATE = 9_600
SAMPLES_PER_SYMBOL = 8
SAMPLE_RATE = SYMBOL_RATE * SAMPLES_PER_SYMBOL
MODULATION = "BPSK"
ROLLOFF = 0.35
FREQ_HZ = 437_568_000  # 437.568 MHz UHF (banda de bajada)

# Ruta del interpretador con GNU Radio + FastAPI.
PYTHON = str(Path(__file__).resolve().parent.parent.parent / "strand" / "bin" / "python")

SNR_DEFAULT_DB = 10.0
SNR_MIN_DB = 0.0
SNR_MAX_DB = 12.0
GR_SEED = 11

# Limites de ingenieria documentados para marcar estado NORMAL/ALERTA en la tabla.
# Las claves son las del decodificador AMSAT (strand_amsat.py); los rangos se
# deducen de la calibracion publicada (p. ej. battery voltage ~ 9.75 V nominal).
LIMITES_TELEMETRIA = {
    "battery_0_voltage": (8.0, 9.9),
    "battery_1_voltage": (8.0, 9.9),
    "battery_0_temperature": (0.0, 45.0),
    "battery_1_temperature": (0.0, 45.0),
}