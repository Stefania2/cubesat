"""
Modelo avanzado de simulacion del enlace RF CubeSat (BPSK, banda base).

BPSK coherente es aqui un **modelo comparativo**: la modulacion documentada de
STRaND-1 es FSK a 9600 bit/s con NRZI (ver `parametros_enlace.py`). El modelo
sirve para estudiar conformado de pulso, sincronizacion, desvanecimiento,
Doppler residual, FEC y tramas AX.25 bajo condiciones controladas.

Incorpora:
  1. Filtrado conformador RRC (Root Raised Cosine) en TX y RX
  2. Recuperacion de portadora (Costas) y de reloj (Gardner)
  3. Desvanecimiento Rice de potencia media unitaria (escenario hipotetico)
  4. Doppler **residual** tras la precompensacion, constante o con deriva
     lineal. No es el Doppler orbital completo: ese (±9.8 kHz) se calcula con
     SGP4 en `margen_paso_sgp4.py`, de donde salen los residuales usados aqui.
  5. Codificacion convolucional (r=1/2, K=7) + Viterbi de decision dura
  6. Tramas AX.25 con FCS CRC-16/X-25

Todas las configuraciones se comparan a la misma Eb/N0 por bit de informacion,
sobre los mismos bits, con el mismo ruido y el mismo desvanecimiento (semillas
comunes) y con varios ensayos por punto. Se informan BER, PER y FER con
intervalos de confianza.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# ─── Constantes del sistema ────────────────────────────────────────────────

INPUT_PATH = Path("frames_STRAND1_gnuradio.bin")
OUTPUT_DIR = Path("resultados_simulacion")

SYMBOL_RATE = 9_600
SAMPLES_PER_SYMBOL = 8
SAMPLE_RATE = SYMBOL_RATE * SAMPLES_PER_SYMBOL
# Barrido en Eb/N0 por bit de informacion. La version anterior barria la SNR
# por muestra, que para una misma cifra significa 9 dB menos de Eb/N0 sin
# codigo y 12 dB menos con el codigo r=1/2: comparar a igual SNR por muestra
# regalaba 3 dB al FEC.
EBN0_DB_VALUES = [0.0, 1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0]
N_ENSAYOS = 6               # realizaciones independientes de canal por punto
RNG_SEED = 20260701
SYNC_BITS = 64              # palabra de sincronismo para resolver la polaridad
PACKET_BYTES = 64           # bloque de telemetria = carga util de una trama AX.25
BER_OBJETIVO_GANANCIA = 1e-3  # BER a la que se mide la ganancia de codificacion
FER_OBJETIVO = 0.10           # FER a la que se mide el umbral de tramas

# RRC
RRC_ROLLOFF = 0.35
RRC_TAPS = 32  # Taps a cada lado del pulso

# Desvanecimiento. K y la dispersion Doppler NO proceden de medidas del enlace
# de STRaND-1: definen un escenario hipotetico de multitrayecto cerca de la
# estacion. La dispersion Doppler del desvanecimiento no es el Doppler orbital.
RICE_K_FACTOR_DB = 10.0           # K = P_LOS / P_difusa
FADING_DOPPLER_SPREAD_HZ = 150.0  # frecuencia Doppler maxima de la componente difusa

# Doppler residual tras la precompensacion por TLE. Valores tomados del analisis
# del paso SGP4 (`margen_paso_sgp4.py`): en la culminacion el Doppler cambia a
# ~97 Hz/s, de modo que un error de tiempo de 0.1 s deja ~10 Hz.
RESIDUAL_ESCENARIO_HZ = 10.0
DERIVA_SIN_COMPENSAR_HZ_S = 97.0

# Sincronizacion de receptor. El modelo anterior suponia que los limites de
# simbolo y la fase de portadora eran conocidos de forma exacta. Aqui se
# introduce un desfase fraccional reproducible y se recuperan con un lazo de
# Costas (portadora) y Gardner (temporizacion). El objetivo no es modelar un
# SDR concreto, sino dejar de conceder sincronizacion ideal al demodulador.
TIMING_OFFSET_SAMPLES = 0.35
COSTAS_LOOP_BW_HZ = 80.0
TIMING_LOOP_GAIN = 0.015

# Convolutional code (r=1/2, K=7, polinomios 171, 133 octal)
CC_K = 7
CC_GENERATORS = (0o171, 0o133)
CC_RATE = 2  # 1 bit in, 2 bits out

# FCS de AX.25 = CRC-16/X-25: polinomio 0x1021 en forma reflejada (0x8408),
# valor inicial 0xFFFF, salida complementada y transmitida con el byte bajo
# primero (ITU-T X.25 / ISO 3309, adoptado por AX.25 2.2).
CRC_POLY_REFLECTED = 0x8408


@dataclass(frozen=True)
class AX25Frame:
    destination: str
    source: str
    control: int
    pid: int
    info: bytes

    def campos(self) -> bytes:
        """Campos que cubre el FCS: direcciones, control, PID e informacion."""
        return (
            _encode_ax25_call(self.destination)
            + _encode_ax25_call(self.source, last=True)
            + bytes([self.control, self.pid])
            + self.info
        )

    def build(self) -> bytes:
        """Trama UI completa delimitada por banderas.

        El FCS cubre unicamente los campos entre banderas; las banderas 0x7E
        quedan fuera, como exige AX.25. No se aplica bit stuffing: es una
        limitacion declarada del modelo (ver README) que no afecta al calculo
        del FCS porque el canal simulado es transparente a nivel de bit.
        """
        flag = b"\x7e"
        campos = self.campos()
        return flag + campos + _ax25_fcs(campos) + flag


def _encode_ax25_call(call: str, last: bool = False) -> bytes:
    """Codifica un indicativo en el formato de direccion AX.25.

    Cada caracter va desplazado un bit a la izquierda. El septimo byte lleva el
    SSID en los bits 1-4 y el bit 0 marca el final del campo de direcciones.
    El indicativo se rellena o trunca a 6 caracteres: la norma fija el campo de
    direccion en 7 bytes y `ljust` por si solo no acota los nombres largos.
    """
    if "-" in call:
        base, ssid = call.split("-", 1)
        ssid = int(ssid)
    else:
        base = call
        ssid = 0
    b = base[:6].ljust(6, " ").encode("ascii")
    b = bytes([c << 1 for c in b])
    b += bytes([0x60 | ((ssid & 0x0F) << 1) | (1 if last else 0)])
    return b


def _ax25_fcs(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ CRC_POLY_REFLECTED
            else:
                crc >>= 1
    crc ^= 0xFFFF
    return crc.to_bytes(2, "little")


def build_ax25_frames(telemetry_bytes: bytes, frame_size: int = 64) -> list[AX25Frame]:
    frames = []
    for i in range(0, len(telemetry_bytes), frame_size):
        chunk = telemetry_bytes[i : i + frame_size]
        frame = AX25Frame(
            destination="CQ",
            source="STRAND-1",
            control=0x03,
            pid=0xF0,
            info=chunk,
        )
        frames.append(frame)
    return frames


def frames_to_bits(frames: list[AX25Frame]) -> np.ndarray:
    raw = b"".join(f.build() for f in frames)
    return np.unpackbits(np.frombuffer(raw, dtype=np.uint8)).astype(np.uint8)


def check_ax25_crc(frame_bytes: bytes) -> bool:
    """Verifica el FCS de una trama delimitada por banderas 0x7E.

    Longitud minima: 2 banderas + 14 bytes de direcciones + control + PID +
    2 bytes de FCS = 20 bytes.
    """
    if len(frame_bytes) < 20:
        return False
    if frame_bytes[0] != 0x7E or frame_bytes[-1] != 0x7E:
        return False
    campos = frame_bytes[1:-3]
    fcs_recibido = frame_bytes[-3:-1]
    return _ax25_fcs(campos) == fcs_recibido


# ─── Filtro RRC ────────────────────────────────────────────────────────────

def rrc_pulse(rolloff: float, taps: int, samples_per_symbol: int) -> np.ndarray:
    t = np.arange(-taps, taps + 1, dtype=np.float64) / samples_per_symbol
    pulse = np.zeros_like(t)
    idx_zero = np.abs(t) < 1e-12
    idx_denom = np.abs(np.abs(t) - 1.0 / (4.0 * rolloff)) < 1e-12

    pulse[idx_zero] = 1.0 - rolloff + 4.0 * rolloff / np.pi
    pulse[idx_denom] = (
        rolloff / np.sqrt(2.0)
        * (
            (1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * rolloff))
            + (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * rolloff))
        )
    )
    mask = ~idx_zero & ~idx_denom
    num = np.sin(np.pi * t[mask] * (1.0 - rolloff)) + 4.0 * rolloff * t[mask] * np.cos(
        np.pi * t[mask] * (1.0 + rolloff)
    )
    den = np.pi * t[mask] * (1.0 - (4.0 * rolloff * t[mask]) ** 2)
    pulse[mask] = num / den
    # Normalizacion a energia unitaria: mantiene la potencia de la señal
    # conformada comparable con la de la señal rectangular.
    pulse /= np.sqrt(np.sum(pulse ** 2))
    return pulse.astype(np.float64)


# ─── Modulacion BPSK rectangular (linea base) ──────────────────────────────

def modulate_bpsk_rect(bits: np.ndarray) -> np.ndarray:
    """BPSK con pulso rectangular NRZ: el simbolo ocupa todo su periodo.

    Sobremuestrear insertando ceros en lugar de repetir da un tren de impulsos,
    no un pulso rectangular: deja 7 de cada 8 muestras sin energia y cuesta
    10*log10(8) ≈ 9 dB de Eb/N0 frente a la NRZ real.
    """
    symbols = (bits.astype(np.float64) * 2.0) - 1.0
    return np.repeat(symbols, SAMPLES_PER_SYMBOL).astype(np.complex128)


def demodulate_bpsk_rect(samples: np.ndarray) -> np.ndarray:
    """Filtro adaptado al pulso rectangular: integracion sobre el simbolo."""
    usable = samples[: len(samples) // SAMPLES_PER_SYMBOL * SAMPLES_PER_SYMBOL]
    integrated = usable.real.reshape(-1, SAMPLES_PER_SYMBOL).mean(axis=1)
    return (integrated >= 0.0).astype(np.uint8)


# ─── Modulacion BPSK (con RRC) ─────────────────────────────────────────────

def modulate_bpsk_rrc(bits: np.ndarray, pulse: np.ndarray) -> np.ndarray:
    """Sobremuestreo con ceros + conformado RRC (aqui los ceros SI son correctos:
    el filtro es el que reparte la energia del simbolo sobre su periodo)."""
    symbols = (bits.astype(np.float64) * 2.0) - 1.0
    upsampled = np.zeros(len(symbols) * SAMPLES_PER_SYMBOL, dtype=np.float64)
    upsampled[::SAMPLES_PER_SYMBOL] = symbols
    shaped = np.convolve(upsampled, pulse, mode="same")
    return (shaped + 1j * 0.0).astype(np.complex128)


def demodulate_bpsk_rrc(samples: np.ndarray, pulse: np.ndarray) -> np.ndarray:
    """Filtro adaptado + muestreo en el instante de simbolo.

    La cascada RRC(TX) * RRC(RX) da un coseno alzado cuyos picos caen en los
    indices multiplos de SAMPLES_PER_SYMBOL, que es donde `modulate_bpsk_rrc`
    insertó los simbolos. Promediar la ventana completa del simbolo en lugar de
    muestrear ese instante mezcla el pico con las colas de los simbolos vecinos
    e introduce ISI: la BER se estanca en ~0.15 por muy alto que sea el SNR.
    """
    matched = np.convolve(np.real(samples), pulse[::-1], mode="same")
    decisions = matched[::SAMPLES_PER_SYMBOL]
    return (decisions >= 0.0).astype(np.uint8)


# ─── Sincronizacion de receptor ────────────────────────────────────────────

def fractional_delay(samples: np.ndarray, delay_samples: float) -> np.ndarray:
    """Desplaza una señal compleja una fracción de muestra mediante interpolación.

    Un desplazamiento positivo retrasa la señal. Se usa para que el barrido no
    parta de un instante de muestreo artificialmente perfecto; los extremos se
    rellenan con cero para no introducir una condición periódica inexistente.
    """
    if abs(delay_samples) < 1e-12:
        return samples.astype(np.complex128, copy=True)
    indices = np.arange(len(samples), dtype=np.float64) - delay_samples
    base = np.arange(len(samples), dtype=np.float64)
    real = np.interp(indices, base, samples.real, left=0.0, right=0.0)
    imag = np.interp(indices, base, samples.imag, left=0.0, right=0.0)
    return (real + 1j * imag).astype(np.complex128)


def costas_loop_bpsk(
    samples: np.ndarray,
    sample_rate: float,
    loop_bandwidth_hz: float = COSTAS_LOOP_BW_HZ,
    damping: float = 0.707,
) -> np.ndarray:
    """Recupera la fase y frecuencia de una señal BPSK con un lazo de Costas.

    El detector `sign(I) * Q` no necesita conocer los bits transmitidos. Los
    coeficientes se obtienen de un PLL discreto de segundo orden; el ancho de
    banda se expresa en Hz para que el parámetro conserve significado al cambiar
    la tasa de muestreo.
    """
    if len(samples) == 0:
        return samples.astype(np.complex128, copy=True)
    omega = 2.0 * np.pi * loop_bandwidth_hz / sample_rate
    denom = 1.0 + 2.0 * damping * omega + omega * omega
    alpha = 4.0 * damping * omega / denom
    beta = 4.0 * omega * omega / denom

    # Mismo lazo que antes, con aritmetica real escalar: evita crear un
    # complejo de numpy por muestra, que dominaba el tiempo de la simulacion.
    re = np.ascontiguousarray(samples.real, dtype=np.float64).tolist()
    im = np.ascontiguousarray(samples.imag, dtype=np.float64).tolist()
    out_re = [0.0] * len(re)
    out_im = [0.0] * len(re)
    phase = 0.0
    frequency = 0.0
    pi, two_pi = math.pi, 2.0 * math.pi
    cos, sin = math.cos, math.sin
    for i in range(len(re)):
        c, s = cos(phase), sin(phase)
        rot_re = re[i] * c + im[i] * s
        rot_im = im[i] * c - re[i] * s
        out_re[i] = rot_re
        out_im[i] = rot_im
        error = rot_im if rot_re >= 0.0 else -rot_im
        frequency += beta * error
        phase += frequency + alpha * error
        phase = (phase + pi) % two_pi - pi
    return np.array(out_re) + 1j * np.array(out_im)


def _linear_sample(samples: np.ndarray, position: float) -> complex:
    """Interpolación lineal compleja con cero fuera de la captura."""
    left = int(np.floor(position))
    if left < 0 or left + 1 >= len(samples):
        return 0.0j
    fraction = position - left
    return complex((1.0 - fraction) * samples[left] + fraction * samples[left + 1])


def gardner_timing_recovery(
    samples: np.ndarray,
    samples_per_symbol: int = SAMPLES_PER_SYMBOL,
    loop_gain: float = TIMING_LOOP_GAIN,
) -> np.ndarray:
    """Extrae símbolos con detector Gardner no asistido por decisión.

    El detector compara las muestras temprana y tardía, separadas medio símbolo,
    con la muestra central. Funciona con señal compleja y no requiere conocer la
    secuencia transmitida. Se limita el avance para mantener estable el lazo ante
    ruido intenso.
    """
    if samples_per_symbol < 2:
        raise ValueError("samples_per_symbol debe ser al menos 2")
    position = 0.0
    half = samples_per_symbol / 2.0
    symbols: list[complex] = []
    while position + half + 1 < len(samples):
        mid = _linear_sample(samples, position)
        early = _linear_sample(samples, position - half)
        late = _linear_sample(samples, position + half)
        symbols.append(mid)
        error = float(np.real((late - early) * np.conj(mid)))
        correction = float(np.clip(loop_gain * error, -0.25, 0.25))
        position += samples_per_symbol + correction
    return np.asarray(symbols, dtype=np.complex128)


def demodulate_bpsk_rect_synced(samples: np.ndarray) -> np.ndarray:
    """Demodulación BPSK rectangular con recuperación de portadora y reloj."""
    recovered = costas_loop_bpsk(samples, SAMPLE_RATE)
    symbols = gardner_timing_recovery(recovered)
    return (symbols.real >= 0.0).astype(np.uint8)


def demodulate_bpsk_rrc_synced(samples: np.ndarray, pulse: np.ndarray) -> np.ndarray:
    """Filtro adaptado RRC seguido de Costas y recuperación Gardner."""
    recovered = costas_loop_bpsk(samples, SAMPLE_RATE)
    matched = np.convolve(np.real(recovered), pulse[::-1], mode="same")
    symbols = gardner_timing_recovery(matched.astype(np.complex128))
    return (symbols.real >= 0.0).astype(np.uint8)


# ─── Fading Rice/Rayleigh + Doppler ────────────────────────────────────────

def gen_rice_fading(
    num_samples: int,
    sample_rate: float,
    doppler_hz: float,
    k_factor_db: float,
    rng: np.random.Generator,
    n_osc: int = 64,
) -> np.ndarray:
    """Ganancia compleja de un canal Rice de potencia media unitaria.

    K es el cociente (lineal) entre la potencia de la componente directa y la
    de la componente difusa: K = P_LOS / P_dif, con K_dB = 10 log10 K. Con
    potencia total 1, P_LOS = K/(K+1) y P_dif = 1/(K+1).

    La componente difusa es una suma de `n_osc` sinusoides complejas de igual
    amplitud, con angulos de llegada y fases uniformes en [0, 2π) (modelo de
    Clarke por Monte Carlo): frecuencias f_n = f_d cos(θ_n), espectro Doppler
    simetrico en ±f_d. La dependencia temporal queda fijada por `doppler_hz`:
    el tiempo de coherencia es del orden de 1/f_d.

    La version anterior escalaba cada cuadratura por 1/sqrt(2(K+1)) siendo su
    varianza ya 1/2, de modo que la potencia difusa salia a la mitad: el canal
    tenia potencia media (2K+1)/(2K+2) y un K efectivo de 2K (13 dB cuando se
    declaraban 10). Tambien usaba solo frecuencias positivas.
    """
    K = 10.0 ** (k_factor_db / 10.0)
    theta = rng.uniform(0.0, 2.0 * np.pi, n_osc)
    phases = rng.uniform(0.0, 2.0 * np.pi, n_osc)
    freqs = doppler_hz * np.cos(theta)
    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    difusa = np.zeros(num_samples, dtype=np.complex128)
    for f, ph in zip(freqs, phases):
        difusa += np.exp(1j * (2.0 * np.pi * f * t + ph))
    difusa /= np.sqrt(n_osc)                     # E{|difusa|^2} = 1
    los = np.sqrt(K / (K + 1.0))
    return (los + np.sqrt(1.0 / (K + 1.0)) * difusa).astype(np.complex128)


def apply_doppler(
    samples: np.ndarray,
    doppler_hz: float,
    sample_rate: float,
    rate_hz_s: float = 0.0,
) -> np.ndarray:
    """Desplaza la señal en frecuencia: f(t) = doppler_hz + rate_hz_s * t."""
    t = np.arange(len(samples), dtype=np.float64) / sample_rate
    phase = 2.0 * np.pi * (doppler_hz * t + 0.5 * rate_hz_s * t * t)
    return (samples * np.exp(1j * phase)).astype(np.complex128)


def compensate_doppler(
    samples: np.ndarray,
    doppler_hz: float,
    sample_rate: float,
) -> np.ndarray:
    """Pre-compensacion de Doppler en el receptor a partir de la prediccion
    orbital (TLE). Si `doppler_hz` coincide exactamente con el desplazamiento
    aplicado el canal queda intacto; la diferencia entre ambos es el residual
    que realmente degrada la deteccion coherente."""
    return apply_doppler(samples, -doppler_hz, sample_rate)


# ─── Codificacion convolutional (r=1/2, K=7) ───────────────────────────────

def _poly_to_mask(poly: int, length: int) -> np.ndarray:
    mask = np.zeros(length, dtype=np.uint8)
    for i in range(length):
        mask[length - 1 - i] = (poly >> i) & 1
    return mask


CC_MASK0 = _poly_to_mask(CC_GENERATORS[0], CC_K)
CC_MASK1 = _poly_to_mask(CC_GENERATORS[1], CC_K)


def convolutional_encode(bits: np.ndarray) -> np.ndarray:
    """Codificador r=1/2, K=7 (171, 133 octal), terminado con K-1 ceros.

    El registro guarda el bit mas reciente en la posicion 0, asi que cada
    salida es la convolucion binaria de la entrada con la mascara del
    polinomio. Equivale al bucle bit a bit original, sin su coste.
    """
    entrada = np.concatenate([bits.astype(np.int64), np.zeros(CC_K - 1, dtype=np.int64)])
    out = np.empty(len(entrada) * CC_RATE, dtype=np.uint8)
    out[0::2] = np.convolve(entrada, CC_MASK0.astype(np.int64))[: len(entrada)] % 2
    out[1::2] = np.convolve(entrada, CC_MASK1.astype(np.int64))[: len(entrada)] % 2
    return out


def _tablas_viterbi() -> tuple[np.ndarray, np.ndarray]:
    """Para cada estado destino: sus dos predecesores y la salida esperada."""
    n_states = 1 << (CC_K - 1)
    pred = np.zeros((n_states, 2), dtype=np.int64)
    salida = np.zeros((n_states, 2), dtype=np.int64)
    cuenta = np.zeros(n_states, dtype=np.int64)
    for s in range(n_states):
        for inp in (0, 1):
            reg = np.zeros(CC_K, dtype=np.uint8)
            reg[0] = inp
            for j in range(1, CC_K):
                reg[j] = (s >> (CC_K - 1 - j)) & 1
            out0 = int((reg & CC_MASK0).sum() % 2)
            out1 = int((reg & CC_MASK1).sum() % 2)
            ns = (s >> 1) | (inp << (CC_K - 2))
            pred[ns, cuenta[ns]] = s
            salida[ns, cuenta[ns]] = (out0 << 1) | out1
            cuenta[ns] += 1
    return pred, salida


_VIT_PRED, _VIT_SALIDA = _tablas_viterbi()


def viterbi_decode(hard_bits: np.ndarray) -> np.ndarray:
    """Viterbi de decision dura (metrica de Hamming), vectorizado por estado.

    Devuelve un bit por cada par recibido, incluidos los K-1 de cola. El bit
    de entrada de cada transicion es el mas significativo del estado destino.
    """
    n_states = 1 << (CC_K - 1)
    n_bits = len(hard_bits) // CC_RATE
    r = np.asarray(hard_bits[: n_bits * CC_RATE], dtype=np.int64).reshape(-1, 2)
    # Distancia de Hamming a cada una de las 4 salidas posibles (o0 o1).
    esperados = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=np.int64)
    metrica_rama = np.abs(r[:, None, :] - esperados[None, :, :]).sum(axis=2)

    metrica = np.full(n_states, 1e9)
    metrica[0] = 0.0
    eleccion = np.zeros((n_bits, n_states), dtype=np.uint8)
    idx = np.arange(n_states)
    for paso in range(n_bits):
        candidatas = metrica[_VIT_PRED] + metrica_rama[paso][_VIT_SALIDA]
        sel = np.argmin(candidatas, axis=1)
        eleccion[paso] = sel
        metrica = candidatas[idx, sel]

    estado = int(np.argmin(metrica))
    decoded = np.zeros(n_bits, dtype=np.uint8)
    for paso in range(n_bits - 1, -1, -1):
        decoded[paso] = estado >> (CC_K - 2)
        estado = int(_VIT_PRED[estado, eleccion[paso, estado]])
    return decoded


# ─── Canal AWGN ─────────────────────────────────────────────────────────────

def add_awgn(samples: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """AWGN complejo con la SNR **por muestra** indicada, medida sobre `samples`."""
    signal_power = float(np.mean(np.abs(samples) ** 2))
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    sigma = np.sqrt(noise_power / 2.0)
    noise = sigma * (
        rng.standard_normal(samples.shape) + 1j * rng.standard_normal(samples.shape)
    )
    return (samples + noise).astype(np.complex128)


def snr_muestra_desde_ebn0(ebn0_db: float, tasa_codigo: float = 1.0) -> float:
    """SNR por muestra (dB) equivalente a una Eb/N0 por bit de informacion.

    Con ruido complejo de varianza σ² por muestra (N0 = σ² en unidades de
    muestra), la energia de un simbolo de canal es Es = P · sps y la de un bit
    de informacion Eb = Es / tasa_codigo. Por tanto

        SNR_muestra = P/σ² = (Eb/N0) · tasa_codigo / sps.

    Sin codigo y con 8 muestras por simbolo: SNR_muestra = Eb/N0 − 9.03 dB.
    Con el codigo r = 1/2 hay 3.01 dB menos de SNR por muestra para la misma
    Eb/N0: cada bit de informacion reparte su energia en dos simbolos.
    """
    return ebn0_db + 10.0 * math.log10(tasa_codigo / SAMPLES_PER_SYMBOL)


def canal_enlace(
    clean: np.ndarray,
    ebn0_db: float,
    tasa_codigo: float,
    fading: bool,
    residual_hz: float,
    deriva_hz_s: float,
    semilla_ruido: tuple[int, ...],
    semilla_fading: tuple[int, ...],
    desfase_muestras: float = TIMING_OFFSET_SAMPLES,
) -> np.ndarray:
    """Canal comun a todas las configuraciones, en el orden fisico.

    1. Desvanecimiento Rice de potencia media unitaria (opcional).
    2. Desplazamiento Doppler residual tras la precompensacion de la estacion,
       con deriva lineal opcional. Aplicar el Doppler completo y restar la
       prediccion equivale exactamente a aplicar solo su diferencia.
    3. Ruido termico del receptor. Su nivel se fija con la potencia de la señal
       **transmitida** y la Eb/N0 pedida, no con la potencia de la realizacion
       desvanecida: asi la Eb/N0 es la media del canal y un desvanecimiento
       profundo baja de verdad la SNR instantanea.
    4. Desfase fraccional de reloj.

    Las semillas de ruido y de desvanecimiento se pasan explicitas para que
    dos configuraciones comparadas vean el mismo canal (numeros aleatorios
    comunes): el ruido de la corrida mas corta es el prefijo del de la larga.
    """
    rx = clean
    if fading:
        rng_f = np.random.default_rng(semilla_fading)
        rx = rx * gen_rice_fading(len(rx), SAMPLE_RATE, FADING_DOPPLER_SPREAD_HZ,
                                  RICE_K_FACTOR_DB, rng_f)
    if residual_hz or deriva_hz_s:
        rx = apply_doppler(rx, residual_hz, SAMPLE_RATE, deriva_hz_s)
    potencia_tx = float(np.mean(np.abs(clean) ** 2))
    snr_muestra = 10.0 ** (snr_muestra_desde_ebn0(ebn0_db, tasa_codigo) / 10.0)
    sigma = math.sqrt(potencia_tx / snr_muestra / 2.0)
    rng_n = np.random.default_rng(semilla_ruido)
    ruido = rng_n.standard_normal((len(rx), 2))
    rx = rx + sigma * (ruido[:, 0] + 1j * ruido[:, 1])
    return fractional_delay(rx, desfase_muestras)


# ─── Metricas ──────────────────────────────────────────────────────────────

def bit_error_rate(reference: np.ndarray, recovered: np.ndarray) -> tuple[int, float]:
    n = min(len(reference), len(recovered))
    errors = int(np.count_nonzero(reference[:n] != recovered[:n]))
    return errors, errors / max(n, 1)


def intervalo_wilson(errores: int, n: int, z: float = 1.959964) -> tuple[float | None, float | None]:
    """Intervalo de confianza de Wilson al 95 % para una proporcion.

    Con cero errores el limite inferior es 0 y el superior no lo es: es la
    cota que la muestra permite afirmar (≈ 3.84/n), no «BER = 0».
    """
    if n <= 0:
        return None, None
    p = errores / n
    den = 1.0 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    semi = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - semi), min(1.0, centro + semi)


def tasa(errores: int, n: int) -> float | None:
    """Proporcion, o None si no hay nada evaluable (nunca un cero inventado)."""
    return errores / n if n > 0 else None


def resolver_polaridad(reference: np.ndarray, recovered: np.ndarray,
                       n_sync: int = SYNC_BITS) -> tuple[np.ndarray, bool]:
    """Resuelve la ambiguedad de 180° del lazo de Costas.

    Un Costas BPSK engancha indistintamente en 0° o 180°; en el segundo caso
    entrega todos los bits invertidos. Los receptores reales lo resuelven con
    codificacion diferencial (el NRZI de STRaND-1) o con una palabra de
    sincronismo. Aqui se usan los primeros `n_sync` bits como palabra conocida:
    si mas de la mitad llegan invertidos, se invierte el flujo completo.
    Un salto de ciclo posterior NO se corrige: sigue contando como error.
    """
    n = min(n_sync, len(reference), len(recovered))
    if n == 0:
        return recovered, False
    invertido = np.count_nonzero(reference[:n] != recovered[:n]) > n / 2
    return (recovered ^ 1 if invertido else recovered), bool(invertido)


def errores_por_bloque(reference: np.ndarray, recovered: np.ndarray,
                       bits_bloque: int) -> tuple[int, int, int]:
    """Cuenta bloques (paquetes) con al menos un bit erroneo.

    Devuelve (paquetes evaluables, erroneos, no recuperados). Un paquete es
    evaluable si el receptor entrego todos sus bits; si la salida se queda
    corta, el paquete cuenta como no recuperado y tambien como error.

    Un paquete que llega integro pero con la polaridad invertida (salto de
    ciclo del Costas antes de el) se da por bueno: es lo que entregaria un
    receptor con codificacion diferencial, como el NRZI de STRaND-1.
    """
    total = math.ceil(len(reference) / bits_bloque)
    erroneos = no_recuperados = 0
    for k in range(total):
        a, b = k * bits_bloque, min((k + 1) * bits_bloque, len(reference))
        if b > len(recovered):
            no_recuperados += 1
        else:
            distintos = int(np.count_nonzero(reference[a:b] != recovered[a:b]))
            if distintos not in (0, b - a):
                erroneos += 1
    return total, erroneos, no_recuperados


def errores_diferenciales(reference: np.ndarray, recovered: np.ndarray) -> tuple[int, int]:
    """Errores tras decodificacion diferencial (d[n] = b[n] xor b[n-1]).

    Es la BER que veria un receptor insensible a la polaridad: un salto de
    ciclo de 180° deja un unico error en lugar de invertir el resto del flujo,
    a cambio de que cada error de canal aislado cuente dos veces.
    Devuelve (errores, bits comparados).
    """
    n = min(len(reference), len(recovered))
    if n < 2:
        return 0, 0
    a = reference[1:n] ^ reference[: n - 1]
    b = recovered[1:n] ^ recovered[: n - 1]
    return int(np.count_nonzero(a != b)), n - 1


def estimate_bandwidth(samples: np.ndarray, fraction: float = 0.99,
                       nfft: int = 4096) -> float:
    """Ancho de banda ocupado que contiene `fraction` de la potencia total.

    Es el criterio de la UIT-R SM.328 (ancho de banda ocupado al 99 %). Sustituye
    al criterio previo de -20 dB respecto al pico, que era inestable para el
    pulso rectangular: los lobulos laterales del sinc² cruzan justo esa cota, de
    modo que la medida saltaba entre 27 kHz y 70 kHz segun los datos de entrada.
    Se promedian periodogramas por bloques (Bartlett) para reducir la varianza.
    """
    if len(samples) < nfft:
        nfft = 1 << int(np.floor(np.log2(max(len(samples), 2))))
    n_blocks = max(len(samples) // nfft, 1)
    psd = np.zeros(nfft, dtype=np.float64)
    for i in range(n_blocks):
        block = samples[i * nfft : (i + 1) * nfft]
        psd += np.abs(np.fft.fft(block, n=nfft)) ** 2
    psd = np.fft.fftshift(psd / n_blocks)
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / SAMPLE_RATE))

    total = psd.sum()
    if total <= 0.0:
        return 0.0
    cumulative = np.cumsum(psd) / total
    tail = (1.0 - fraction) / 2.0
    lo = int(np.searchsorted(cumulative, tail))
    hi = int(np.searchsorted(cumulative, 1.0 - tail))
    hi = min(hi, nfft - 1)
    return float(freqs[hi] - freqs[lo])


# ─── Configuraciones ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Canal:
    clave: str
    nombre: str
    fading: bool
    residual_hz: float
    deriva_hz_s: float
    respaldo: str


@dataclass(frozen=True)
class Esquema:
    clave: str
    nombre: str
    rrc: bool
    fec: bool
    ax25: bool
    sincronizacion: str = "Costas+Gardner"   # o "ideal"

    @property
    def tasa_codigo(self) -> float:
        return 0.5 if self.fec else 1.0


CANALES = {
    "awgn": Canal("awgn", "AWGN (referencia)", False, 0.0, 0.0,
                  "caso de referencia: sin desvanecimiento ni Doppler residual"),
    "rice": Canal("rice", f"Rice K={RICE_K_FACTOR_DB:g} dB + residual {RESIDUAL_ESCENARIO_HZ:g} Hz",
                  True, RESIDUAL_ESCENARIO_HZ, 0.0,
                  "escenario hipotetico: K y dispersion Doppler no proceden de medidas de "
                  "STRaND-1; el residual corresponde a ~0.1 s de error de tiempo del TLE en "
                  "la culminacion (margen_paso_sgp4.json)"),
}

ESQUEMAS = [
    Esquema("ideal_rrc", "BPSK + RRC, sincronizacion ideal", True, False, False, "ideal"),
    Esquema("nrz", "BPSK rectangular (NRZ)", False, False, False),
    Esquema("rrc", "BPSK + RRC", True, False, False),
    Esquema("rrc_fec", "BPSK + RRC + FEC conv. r=1/2 K=7", True, True, False),
    Esquema("ax25", "AX.25 sobre BPSK + RRC", True, False, True),
    Esquema("ax25_fec", "AX.25 + FEC conv. sobre BPSK + RRC", True, True, True),
]

# Barrido de Doppler residual sobre un mismo esquema y canal AWGN. Los valores
# salen del analisis del paso SGP4: un error de tiempo de 0.1, 0.5 y 1 s en la
# culminacion deja ~10, ~50 y ~100 Hz; la deriva es la del Doppler sin corregir.
BARRIDO_DOPPLER = [
    Canal("res10", "AWGN + residual 10 Hz", False, 10.0, 0.0, "error de tiempo ~0.1 s"),
    Canal("res50", "AWGN + residual 50 Hz", False, 50.0, 0.0, "error de tiempo ~0.5 s"),
    Canal("res100", "AWGN + residual 100 Hz", False, 100.0, 0.0, "error de tiempo ~1 s"),
    Canal("deriva", f"AWGN + deriva {DERIVA_SIN_COMPENSAR_HZ_S:g} Hz/s", False, 0.0,
          DERIVA_SIN_COMPENSAR_HZ_S,
          "portadora centrada pero sin seguir la deriva del Doppler en la culminacion"),
]


def lista_configuraciones() -> list[tuple[Esquema, Canal]]:
    configs = [(e, c) for c in CANALES.values() for e in ESQUEMAS
               if not (e.sincronizacion == "ideal" and c.clave != "awgn")]
    rrc = next(e for e in ESQUEMAS if e.clave == "rrc")
    configs += [(rrc, c) for c in BARRIDO_DOPPLER]
    return configs


# ─── Una corrida ───────────────────────────────────────────────────────────

def _transmitir(esquema: Esquema, bits: np.ndarray, telemetry_bytes: bytes,
                pulse: np.ndarray) -> dict:
    """Bits de usuario -> bits de canal -> señal limpia, con lo necesario para evaluar."""
    info: dict = {}
    if esquema.ax25:
        frames = build_ax25_frames(telemetry_bytes, PACKET_BYTES)
        usuario = frames_to_bits(frames)
        info["longitudes"] = [len(f.build()) for f in frames]
        info["cargas"] = [f.info for f in frames]
    else:
        usuario = bits
    canal_bits = convolutional_encode(usuario) if esquema.fec else usuario
    clean = modulate_bpsk_rrc(canal_bits, pulse) if esquema.rrc else modulate_bpsk_rect(canal_bits)
    info.update(usuario=usuario, clean=clean, n_canal=len(canal_bits))
    return info


def _recibir(esquema: Esquema, rx: np.ndarray, pulse: np.ndarray) -> np.ndarray:
    if esquema.sincronizacion == "ideal":
        # Fase, frecuencia y reloj conocidos: deshace el desfase y muestrea.
        return demodulate_bpsk_rrc(fractional_delay(rx, -TIMING_OFFSET_SAMPLES), pulse)
    if esquema.rrc:
        return demodulate_bpsk_rrc_synced(rx, pulse)
    return demodulate_bpsk_rect_synced(rx)


def _evaluar_ax25(tx: dict, usuario_rx: np.ndarray) -> dict:
    """Recuento de tramas AX.25 por FCS.

    Delimitacion de trama ideal (desplazamiento conocido, sin busqueda de
    banderas ni bit stuffing): es una limitacion declarada. Lo que si es real
    es el calculo del FCS sobre los bytes recibidos. Se prueban las dos
    polaridades por trama, como hace de forma natural un receptor NRZI.
    """
    rx_bytes = np.packbits(usuario_rx[: len(usuario_rx) // 8 * 8]).tobytes()
    rx_bytes_inv = bytes(b ^ 0xFF for b in rx_bytes)
    validas = invalidas = descartadas = no_detectados = 0
    offset = 0
    for n, carga in zip(tx["longitudes"], tx["cargas"]):
        if offset + n > len(rx_bytes):
            descartadas += 1          # el receptor no entrego la trama completa
        else:
            trozo, trozo_inv = rx_bytes[offset:offset + n], rx_bytes_inv[offset:offset + n]
            ok = next((t for t in (trozo, trozo_inv) if check_ax25_crc(t)), None)
            if ok is None:
                invalidas += 1
            else:
                validas += 1
                if ok[17:-3] != carga:   # FCS correcto con carga distinta
                    no_detectados += 1
        offset += n
    return {"tramas_tx": len(tx["longitudes"]), "tramas_validas": validas,
            "tramas_invalidas": invalidas, "tramas_descartadas": descartadas,
            "tramas_error_no_detectado": no_detectados}


def simular_corrida(tarea: tuple) -> dict:
    """Una corrida: (esquema, canal, Eb/N0, ensayo). Independiente y reproducible."""
    esquema, canal, ebn0_db, ensayo, i_ebn0, bits, telemetry_bytes = tarea
    pulse = rrc_pulse(RRC_ROLLOFF, RRC_TAPS, SAMPLES_PER_SYMBOL)
    tx = _transmitir(esquema, bits, telemetry_bytes, pulse)
    rx = canal_enlace(
        tx["clean"], ebn0_db, esquema.tasa_codigo, canal.fading,
        canal.residual_hz, canal.deriva_hz_s,
        semilla_ruido=(RNG_SEED, 1, ensayo, i_ebn0),
        semilla_fading=(RNG_SEED, 2, ensayo),
    )
    canal_rx = _recibir(esquema, rx, pulse)
    invertido = False
    if esquema.fec:
        # La palabra de sincronismo va en bits de canal: se resuelve la
        # polaridad antes del Viterbi (un flujo invertido no es decodificable).
        canal_tx = convolutional_encode(tx["usuario"])
        canal_rx, invertido = resolver_polaridad(canal_tx, canal_rx)
        if len(canal_rx) < tx["n_canal"]:
            canal_rx = np.concatenate([canal_rx, np.zeros(tx["n_canal"] - len(canal_rx), np.uint8)])
        usuario_rx = viterbi_decode(canal_rx[: tx["n_canal"]])[: len(tx["usuario"])]
    else:
        usuario_rx, invertido = resolver_polaridad(tx["usuario"], canal_rx)

    usuario = tx["usuario"]
    n = min(len(usuario), len(usuario_rx))
    errores = int(np.count_nonzero(usuario[:n] != usuario_rx[:n]))
    err_dif, n_dif = errores_diferenciales(usuario, usuario_rx)
    fila = {
        "errores_bit_dif": err_dif, "bits_dif": n_dif,
        "esquema": esquema.clave, "canal": canal.clave, "ebn0_db": ebn0_db, "ensayo": ensayo,
        "bits_evaluados": n, "errores_bit": errores, "fase_invertida": invertido,
        "bits_no_recuperados": len(usuario) - n,
    }
    if esquema.ax25:
        fila.update(_evaluar_ax25(tx, usuario_rx))
        # El paquete es la carga util de cada trama (el bloque de telemetria).
        total = len(tx["cargas"])
        erroneos, offset = 0, 0
        rx_bytes = np.packbits(usuario_rx[: len(usuario_rx) // 8 * 8]).tobytes()
        for nbytes, carga in zip(tx["longitudes"], tx["cargas"]):
            recibido = rx_bytes[offset + 17: offset + nbytes - 3]
            if recibido != carga and recibido != bytes(b ^ 0xFF for b in carga):
                erroneos += 1
            offset += nbytes
        fila.update(paquetes=total, paquetes_erroneos=erroneos)
    else:
        total, erroneos, perdidos = errores_por_bloque(usuario, usuario_rx, PACKET_BYTES * 8)
        fila.update(paquetes=total, paquetes_erroneos=erroneos + perdidos)
    return fila


# ─── Agregacion ────────────────────────────────────────────────────────────

@dataclass
class SimResult:
    esquema: str
    esquema_nombre: str
    canal: str
    canal_nombre: str
    rrc: bool
    fading: bool
    fec: bool
    ax25: bool
    sincronizacion: str
    doppler_residual_hz: float
    doppler_deriva_hz_s: float
    ebn0_db: float
    snr_muestra_db: float
    ensayos: int
    bits_evaluados: int
    errores_bit: int
    ber: float | None
    ber_ic95_inf: float | None
    ber_ic95_sup: float | None
    ber_teorica_bpsk: float
    # BER tras decodificacion diferencial: insensible a saltos de polaridad.
    errores_bit_dif: int
    ber_diferencial: float | None
    ensayos_fase_invertida: int
    paquetes: int
    paquetes_erroneos: int
    per: float | None
    per_ic95_inf: float | None
    per_ic95_sup: float | None
    # Solo con tramas AX.25; en el resto de esquemas no hay trama que evaluar.
    ax25_frames_tx: int | None
    ax25_frames_validos: int | None
    ax25_frames_invalidos: int | None
    ax25_frames_descartados: int | None
    ax25_errores_no_detectados: int | None
    fer: float | None
    fer_ic95_inf: float | None
    fer_ic95_sup: float | None
    ancho_banda_hz: float


def agregar(filas: list[dict], anchos: dict[str, float]) -> list[SimResult]:
    esquemas = {e.clave: e for e in ESQUEMAS}
    canales = {c.clave: c for c in list(CANALES.values()) + BARRIDO_DOPPLER}
    grupos: dict[tuple, list[dict]] = {}
    for f in filas:
        grupos.setdefault((f["esquema"], f["canal"], f["ebn0_db"]), []).append(f)
    resultados = []
    for (ke, kc, ebn0), g in grupos.items():
        e, c = esquemas[ke], canales[kc]
        bits_ev = sum(f["bits_evaluados"] for f in g)
        # Los bits que el receptor no entrego no se pueden comparar: no entran
        # en el denominador de la BER (se reflejan en PER/FER).
        err = sum(f["errores_bit"] for f in g)
        paq, paq_err = sum(f["paquetes"] for f in g), sum(f["paquetes_erroneos"] for f in g)
        ber_inf, ber_sup = intervalo_wilson(err, bits_ev)
        per_inf, per_sup = intervalo_wilson(paq_err, paq)
        if e.ax25:
            tx = sum(f["tramas_tx"] for f in g)
            val = sum(f["tramas_validas"] for f in g)
            inv = sum(f["tramas_invalidas"] for f in g)
            des = sum(f["tramas_descartadas"] for f in g)
            nd = sum(f["tramas_error_no_detectado"] for f in g)
            fer = tasa(inv + des, tx)
            fer_inf, fer_sup = intervalo_wilson(inv + des, tx)
        else:
            tx = val = inv = des = nd = fer = fer_inf = fer_sup = None
        resultados.append(SimResult(
            esquema=ke, esquema_nombre=e.nombre, canal=kc, canal_nombre=c.nombre,
            rrc=e.rrc, fading=c.fading, fec=e.fec, ax25=e.ax25,
            sincronizacion=e.sincronizacion,
            doppler_residual_hz=c.residual_hz, doppler_deriva_hz_s=c.deriva_hz_s,
            ebn0_db=ebn0,
            snr_muestra_db=round(snr_muestra_desde_ebn0(ebn0, e.tasa_codigo), 2),
            ensayos=len(g), bits_evaluados=bits_ev, errores_bit=err,
            ber=tasa(err, bits_ev), ber_ic95_inf=ber_inf, ber_ic95_sup=ber_sup,
            ber_teorica_bpsk=0.5 * math.erfc(math.sqrt(10.0 ** (ebn0 / 10.0))),
            errores_bit_dif=sum(f["errores_bit_dif"] for f in g),
            ber_diferencial=tasa(sum(f["errores_bit_dif"] for f in g),
                                 sum(f["bits_dif"] for f in g)),
            ensayos_fase_invertida=sum(1 for f in g if f["fase_invertida"]),
            paquetes=paq, paquetes_erroneos=paq_err, per=tasa(paq_err, paq),
            per_ic95_inf=per_inf, per_ic95_sup=per_sup,
            ax25_frames_tx=tx, ax25_frames_validos=val, ax25_frames_invalidos=inv,
            ax25_frames_descartados=des, ax25_errores_no_detectados=nd,
            fer=fer, fer_ic95_inf=fer_inf, fer_ic95_sup=fer_sup,
            ancho_banda_hz=anchos[ke],
        ))
    orden_e = {e.clave: i for i, e in enumerate(ESQUEMAS)}
    orden_c = {k: i for i, k in enumerate(canales)}
    resultados.sort(key=lambda r: (orden_c[r.canal], orden_e[r.esquema], r.ebn0_db))
    return resultados


def cruce_umbral(puntos: list[tuple[float, float | None]], objetivo: float) -> float | None:
    """Eb/N0 (dB) en que una tasa de error decreciente cruza `objetivo`.

    Interpola linealmente en log10 entre los dos puntos que encierran el
    objetivo. Devuelve None si el barrido no lo encierra o si el punto inferior
    no tiene errores (un cero no se puede interpolar en escala logaritmica).
    """
    pts = sorted((x, y) for x, y in puntos if y is not None)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 > objetivo >= y1 and y1 > 0.0:
            return x0 + (x1 - x0) * (math.log10(y0) - math.log10(objetivo)) / (
                math.log10(y0) - math.log10(y1))
    return None


def analizar(resultados: list[SimResult]) -> dict:
    """Umbrales del receptor simulado y ganancia de codificacion medida."""
    def curva(esquema: str, canal: str, campo: str) -> list[tuple[float, float | None]]:
        return [(r.ebn0_db, getattr(r, campo)) for r in resultados
                if r.esquema == esquema and r.canal == canal]

    paso = EBN0_DB_VALUES[1] - EBN0_DB_VALUES[0]
    ganancias = []
    for canal in CANALES:
        sin = cruce_umbral(curva("rrc", canal, "ber"), BER_OBJETIVO_GANANCIA)
        con = cruce_umbral(curva("rrc_fec", canal, "ber"), BER_OBJETIVO_GANANCIA)
        ganancias.append({
            "canal": canal,
            "ber_objetivo": BER_OBJETIVO_GANANCIA,
            "ebn0_sin_codigo_db": None if sin is None else round(sin, 2),
            "ebn0_con_codigo_db": None if con is None else round(con, 2),
            "ganancia_db": None if None in (sin, con) else round(sin - con, 2),
            "estado": "medida" if None not in (sin, con) else
                      "no estimable: el barrido no encierra la BER objetivo en ambas curvas",
            "resolucion_db": paso,
        })
    ganancias_fer = []
    for canal in CANALES:
        sin = cruce_umbral(curva("ax25", canal, "fer"), FER_OBJETIVO)
        con = cruce_umbral(curva("ax25_fec", canal, "fer"), FER_OBJETIVO)
        ganancias_fer.append({
            "canal": canal, "fer_objetivo": FER_OBJETIVO,
            "ebn0_sin_codigo_db": None if sin is None else round(sin, 2),
            "ebn0_con_codigo_db": None if con is None else round(con, 2),
            "ganancia_db": None if None in (sin, con) else round(sin - con, 2),
            "estado": "medida" if None not in (sin, con) else
                      "no estimable: el barrido no encierra la FER objetivo en ambas curvas",
            "resolucion_db": paso,
        })
    umbrales = {}
    for clave, esquema, campo, objetivo, texto in [
        ("ber1e-3_rrc", "rrc", "ber", 1e-3, "BER 1e-3, BPSK+RRC sin codificar"),
        ("fer10_ax25", "ax25", "fer", 0.10, "FER 10 %, AX.25 sobre BPSK+RRC"),
        ("fer10_ax25_fec", "ax25_fec", "fer", 0.10, "FER 10 %, AX.25 + FEC sobre BPSK+RRC"),
    ]:
        x = cruce_umbral(curva(esquema, "awgn", campo), objetivo)
        umbrales[clave] = {
            "descripcion": f"receptor simulado (Costas+Gardner), AWGN: {texto}",
            "eb_n0_db": None if x is None else round(x, 2),
        }
    return {"ganancia_codificacion": ganancias, "ganancia_codificacion_fer": ganancias_fer,
            "umbrales": umbrales}


# ─── Graficas ───────────────────────────────────────────────────────────────

def _curva(ax, resultados, esquema, canal, campo, etiqueta, **kw):
    pts = [r for r in resultados if r.esquema == esquema and r.canal == canal
           and getattr(r, campo) is not None]
    if not pts:
        return
    x = [p.ebn0_db for p in pts]
    y = np.array([getattr(p, campo) for p in pts], dtype=float)
    sup = np.array([getattr(p, campo + "_ic95_sup") for p in pts], dtype=float)
    inf = np.array([getattr(p, campo + "_ic95_inf") for p in pts], dtype=float)
    # Un cero observado se dibuja en su cota superior, con marcador hueco.
    cero = y == 0.0
    y_plot = np.where(cero, sup, y)
    linea, = ax.semilogy(x, y_plot, marker="o", ms=4, label=etiqueta, **kw)
    ax.fill_between(x, np.maximum(inf, 1e-7), sup, alpha=0.12, color=linea.get_color())
    if cero.any():
        ax.semilogy(np.array(x)[cero], y_plot[cero], "v", mfc="white",
                    color=linea.get_color(), ms=6)


def plot_results(results: list[SimResult]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10.5))
    fig.suptitle("Modelo avanzado (BPSK, modelo comparativo): resultados simulados\n"
                 "banda = IC 95 % de Wilson · ▽ = cero errores, dibujado en su cota superior",
                 fontsize=12, fontweight="bold")
    teo_x = np.linspace(min(EBN0_DB_VALUES), max(EBN0_DB_VALUES), 100)
    teo_y = [0.5 * math.erfc(math.sqrt(10 ** (x / 10))) for x in teo_x]

    ax = axes[0, 0]
    ax.semilogy(teo_x, teo_y, "k--", lw=1, label="Teoria BPSK coherente")
    _curva(ax, results, "ideal_rrc", "awgn", "ber", "RRC, sincronizacion ideal")
    _curva(ax, results, "rrc", "awgn", "ber", "RRC, Costas+Gardner")
    _curva(ax, results, "nrz", "awgn", "ber", "NRZ, Costas+Gardner")
    ax.set_title("AWGN: validacion frente a la teoria y coste de la sincronizacion")

    ax = axes[0, 1]
    ax.semilogy(teo_x, teo_y, "k--", lw=1, label="Teoria BPSK (AWGN)")
    for canal in CANALES.values():
        _curva(ax, results, "rrc", canal.clave, "ber", f"Sin codigo · {canal.nombre}")
        _curva(ax, results, "rrc_fec", canal.clave, "ber", f"FEC · {canal.nombre}")
    ax.set_title("FEC convolucional a igual Eb/N0 por bit de informacion")

    ax = axes[1, 0]
    _curva(ax, results, "rrc", "awgn", "ber", "Residual 0 Hz")
    for canal in BARRIDO_DOPPLER:
        _curva(ax, results, "rrc", canal.clave, "ber", canal.nombre.replace("AWGN + ", ""))
    ax.set_title("Doppler residual tras la precompensacion (BPSK+RRC, AWGN)")

    ax = axes[1, 1]
    for canal in CANALES.values():
        _curva(ax, results, "ax25", canal.clave, "fer", f"AX.25 · {canal.nombre}")
        _curva(ax, results, "ax25_fec", canal.clave, "fer", f"AX.25+FEC · {canal.nombre}")
    ax.set_title("FER de tramas AX.25 (FCS CRC-16/X-25)")
    ax.set_ylabel("FER")

    for ax in axes.flat:
        ax.set_xlabel("Eb/N0 (dB)")
        if not ax.get_ylabel():
            ax.set_ylabel("BER")
        ax.set_ylim(1e-6, 1.0)
        ax.grid(True, which="both", linestyle=":")
        ax.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "simulacion_avanzada_resultados.png", dpi=170)
    plt.close()


def plot_spectrum_comparison() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle("Comparacion de espectro: BPSK sin y con filtrado RRC", fontsize=13, fontweight="bold")

    pulse = rrc_pulse(RRC_ROLLOFF, RRC_TAPS, SAMPLES_PER_SYMBOL)
    rng = np.random.default_rng(RNG_SEED)
    bits = rng.integers(0, 2, 1000, dtype=np.uint8)

    for idx, (use_rrc, title) in enumerate([(False, "BPSK rectangular (NRZ)"), (True, "BPSK con RRC (α=0.35)")]):
        clean = modulate_bpsk_rrc(bits, pulse) if use_rrc else modulate_bpsk_rect(bits)

        spectrum = np.fft.fftshift(np.fft.fft(clean, n=4096))
        power_db = 20.0 * np.log10(np.abs(spectrum) / max(np.abs(spectrum)) + 1e-12)
        freqs = np.fft.fftshift(np.fft.fftfreq(4096, d=1.0 / SAMPLE_RATE)) / 1000.0

        axes[idx].plot(freqs, power_db, linewidth=1.0)
        axes[idx].set_title(title)
        axes[idx].set_xlabel("Frecuencia (kHz)")
        axes[idx].set_ylabel("Magnitud (dB)")
        axes[idx].grid(True, linestyle=":")
        axes[idx].set_xlim(-30, 30)
        axes[idx].set_ylim(-60, 5)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "espectro_rrc_comparacion.png", dpi=150)
    plt.close()


# ─── Exportacion ────────────────────────────────────────────────────────────

def _commit() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, check=True, cwd=Path(__file__).parent).stdout.strip()
        # Solo cuenta el codigo: los propios resultados cambian al regenerarse.
        sucio = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no",
                                "--", "*.py"],
                               capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip()
        return rev + ("+cambios sin confirmar" if sucio else "")
    except Exception:
        return "desconocido"


def metadatos(n_bits: int, n_ensayos: int) -> dict:
    return {
        "tipo_de_dato": "simulado (modelo de banda base; no es una medicion del enlace real)",
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "modulacion_del_modelo": "BPSK coherente (modelo comparativo; la modulacion "
                                 "documentada de STRaND-1 es FSK 9600 con NRZI)",
        "entrada": {"archivo": str(INPUT_PATH), "bits": n_bits,
                    "origen": "bytes de 100 tramas reales de STRaND-1 (SatNOGS)"},
        "semilla_base": RNG_SEED,
        "semillas": "ruido = (semilla_base, 1, ensayo, indice_EbN0); "
                    "desvanecimiento = (semilla_base, 2, ensayo). Comunes a todas las "
                    "configuraciones: comparacion pareada.",
        "ensayos_por_punto": n_ensayos,
        "ebn0_db": EBN0_DB_VALUES,
        "definicion_ebn0": "Eb/N0 por bit de informacion (antes del FEC; en AX.25, por bit de "
                           "trama incluida la cabecera). SNR por muestra = Eb/N0 + "
                           "10 log10(tasa_codigo / 8).",
        "tasa_simbolo_baud": SYMBOL_RATE,
        "muestras_por_simbolo": SAMPLES_PER_SYMBOL,
        "rrc": {"rolloff": RRC_ROLLOFF, "semilongitud_muestras": RRC_TAPS},
        "sincronizacion": {
            "costas_bw_hz": COSTAS_LOOP_BW_HZ, "gardner_ganancia": TIMING_LOOP_GAIN,
            "desfase_reloj_muestras": TIMING_OFFSET_SAMPLES,
            "ambiguedad_de_fase": f"resuelta con los primeros {SYNC_BITS} bits como palabra "
                                  "de sincronismo conocida; los saltos de ciclo posteriores "
                                  "cuentan como error",
            "trama": "delimitacion ideal por desplazamiento conocido; sin busqueda de "
                     "banderas ni bit stuffing",
        },
        "canal_rice": {
            "k_db": RICE_K_FACTOR_DB,
            "definicion_k": "P_LOS / P_difusa (lineal); potencia media total = 1",
            "dispersion_doppler_hz": FADING_DOPPLER_SPREAD_HZ,
            "generacion": "suma de 64 sinusoides, angulos y fases uniformes (Clarke)",
            "respaldo": "escenario hipotetico; sin medidas de canal de STRaND-1",
        },
        "canales": {c.clave: {"nombre": c.nombre, "fading": c.fading,
                              "residual_hz": c.residual_hz, "deriva_hz_s": c.deriva_hz_s,
                              "respaldo": c.respaldo}
                    for c in list(CANALES.values()) + BARRIDO_DOPPLER},
        "esquemas": {e.clave: {"nombre": e.nombre, "rrc": e.rrc, "fec": e.fec,
                               "ax25": e.ax25, "sincronizacion": e.sincronizacion,
                               "tasa_codigo": e.tasa_codigo} for e in ESQUEMAS},
        "definiciones": {
            "ber": "bits erroneos / bits efectivamente comparados (los que el receptor entrego)",
            "ber_diferencial": "BER tras decodificar diferencialmente ambos flujos: insensible "
                               "a la polaridad, como un receptor NRZI; cada error aislado "
                               "cuenta dos veces",
            "paquete": f"bloque de {PACKET_BYTES} bytes de telemetria (carga util de una trama "
                       "AX.25); erroneo si tiene al menos un bit incorrecto o no se recupero; "
                       "un paquete integro con polaridad invertida se da por bueno",
            "per": "paquetes erroneos / paquetes transmitidos",
            "fer": "(tramas con FCS invalido + tramas no recuperadas) / tramas transmitidas; "
                   "solo en esquemas con trama AX.25, N/A en el resto",
            "intervalos": "Wilson al 95 %; con cero errores el limite superior es la cota "
                          "que la muestra permite afirmar",
        },
        "limitaciones": [
            "Receptor BPSK: los umbrales medidos no son los de un receptor FSK G3RUH real.",
            "Viterbi de decision dura.",
            "Sin busqueda de banderas ni bit stuffing en AX.25.",
            "Parametros del canal Rice sin respaldo experimental.",
            "Sin ruido de fase, no linealidad del amplificador ni desbalance I/Q (ver informe).",
        ],
    }


def export_results(results: list[SimResult], analisis: dict, meta: dict) -> None:
    with (OUTPUT_DIR / "resultados_simulacion_avanzada.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        # Una celda vacia es «no aplica / no evaluable», nunca un cero.
        writer.writerows({k: ("" if v is None else v) for k, v in asdict(r).items()}
                         for r in results)

    with (OUTPUT_DIR / "resultados_simulacion_avanzada.json").open("w", encoding="utf-8") as f:
        json.dump({"metadatos": meta, "analisis": analisis,
                   "resultados": [asdict(r) for r in results]}, f, indent=2, ensure_ascii=False)

    with (OUTPUT_DIR / "umbrales_receptor_simulado.json").open("w", encoding="utf-8") as f:
        json.dump({"generado_utc": meta["generado_utc"], "commit": meta["commit"],
                   "nota": "Eb/N0 medida en el receptor BPSK simulado; incluye la "
                           "degradacion de sincronizacion, por lo que no se le suma reserva "
                           "de implementacion.",
                   "umbrales": analisis["umbrales"]}, f, indent=2, ensure_ascii=False)


def _fmt(v: float | None) -> str:
    return "N/A" if v is None else f"{v:.2e}"


def print_summary(results: list[SimResult], analisis: dict) -> None:
    print("=" * 96)
    print("MODELO AVANZADO DEL ENLACE (BPSK, modelo comparativo) — resultados simulados")
    print("=" * 96)
    grupos: dict[tuple[str, str], list[SimResult]] = {}
    for r in results:
        grupos.setdefault((r.canal_nombre, r.esquema_nombre), []).append(r)
    for (canal, esquema), pts in grupos.items():
        print(f"\n--- {esquema} · {canal} ---")
        print(f"{'Eb/N0':>6} {'BER':>10} {'BER dif':>10} {'PER':>10} {'FER':>10} {'validas':>9} {'inv.fase':>8}")
        for p in pts:
            val = "N/A" if p.ax25_frames_validos is None else f"{p.ax25_frames_validos}/{p.ax25_frames_tx}"
            print(f"{p.ebn0_db:>6.1f} {_fmt(p.ber):>10} {_fmt(p.ber_diferencial):>10} "
                  f"{_fmt(p.per):>10} {_fmt(p.fer):>10} {val:>9} {p.ensayos_fase_invertida:>8}")
    print("\nGanancia de codificacion (a igual Eb/N0 por bit de informacion):")
    for g in analisis["ganancia_codificacion"]:
        print(f"  {g['canal']}: {g['ganancia_db']} dB a BER {g['ber_objetivo']:g} "
              f"({g['estado']}; resolucion del barrido {g['resolucion_db']} dB)")
    for g in analisis["ganancia_codificacion_fer"]:
        print(f"  {g['canal']}: {g['ganancia_db']} dB a FER {g['fer_objetivo']:g} en tramas AX.25 "
              f"({g['estado']})")
    print("Umbrales del receptor simulado (AWGN):")
    for k, u in analisis["umbrales"].items():
        print(f"  {k}: {u['eb_n0_db']} dB — {u['descripcion']}")
    print("=" * 96)


# ─── Main ───────────────────────────────────────────────────────────────────

def ejecutar(bits: np.ndarray, telemetry_bytes: bytes, n_ensayos: int = N_ENSAYOS,
             ebn0_values: list[float] | None = None,
             configs: list[tuple[Esquema, Canal]] | None = None,
             procesos: int | None = None) -> tuple[list[SimResult], dict]:
    ebn0_values = EBN0_DB_VALUES if ebn0_values is None else ebn0_values
    configs = lista_configuraciones() if configs is None else configs
    tareas = [(e, c, x, k, i, bits, telemetry_bytes)
              for e, c in configs for i, x in enumerate(ebn0_values) for k in range(n_ensayos)]
    if procesos == 1:
        filas = [simular_corrida(t) for t in tareas]
    else:
        with ProcessPoolExecutor(max_workers=procesos) as pool:
            filas = list(pool.map(simular_corrida, tareas, chunksize=4))
    pulse = rrc_pulse(RRC_ROLLOFF, RRC_TAPS, SAMPLES_PER_SYMBOL)
    anchos = {e.clave: round(estimate_bandwidth(_transmitir(e, bits, telemetry_bytes, pulse)["clean"]), 2)
              for e in ESQUEMAS}
    resultados = agregar(filas, anchos)
    return resultados, analizar(resultados)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensayos", type=int, default=N_ENSAYOS)
    parser.add_argument("--procesos", type=int, default=None)
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"No existe {INPUT_PATH}. Ejecuta decodificar_frames_STRAND1.py primero.")
    telemetry_bytes = INPUT_PATH.read_bytes()
    bits = np.unpackbits(np.frombuffer(telemetry_bytes, dtype=np.uint8)).astype(np.uint8)
    print(f"Datos cargados: {len(telemetry_bytes)} bytes, {len(bits)} bits")

    OUTPUT_DIR.mkdir(exist_ok=True)
    results, analisis = ejecutar(bits, telemetry_bytes, args.ensayos, procesos=args.procesos)
    export_results(results, analisis, metadatos(len(bits), args.ensayos))
    plot_results(results)
    plot_spectrum_comparison()
    print_summary(results, analisis)

    print(f"\nArchivos generados en {OUTPUT_DIR.resolve()}/")
    for nombre in ("resultados_simulacion_avanzada.csv", "resultados_simulacion_avanzada.json",
                   "umbrales_receptor_simulado.json", "simulacion_avanzada_resultados.png",
                   "espectro_rrc_comparacion.png"):
        print(f"  - {nombre}")


if __name__ == "__main__":
    main()
