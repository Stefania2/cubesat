"""
Modelo avanzado de simulacion del enlace RF CubeSat.

Incorpora:
  1. Filtrado conformador RRC (Root Raised Cosine) en TX y RX
  2. Desvanecimiento Rice/Rayleigh con perfil Jakes
  3. Desplazamiento Doppler orbital variable
  4. Codificacion convolutional (r=1/2, K=7) + Viterbi
  5. Tramas AX.25 completas con CRC-16-CCITT
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np

# ─── Constantes del sistema ────────────────────────────────────────────────

INPUT_PATH = Path("frames_STRAND1_gnuradio.bin")
OUTPUT_DIR = Path("resultados_simulacion")

SYMBOL_RATE = 9_600
SAMPLES_PER_SYMBOL = 8
SAMPLE_RATE = SYMBOL_RATE * SAMPLES_PER_SYMBOL
# Con conformado de pulso correcto la region de interes cae ~9 dB respecto al
# modelo basico: a partir de 4 dB de SNR por muestra el enlace ya no comete
# errores ni siquiera sin codificar, y el FEC solo se distingue por debajo de
# -2 dB. Los cuatro puntos superiores solapan con el barrido del modelo basico
# (-2, 0, 2 y 4 dB) para poder contrastar ambos modelos.
SNR_DB_VALUES = [-10, -8, -6, -4, -2, 0, 2, 4]
RNG_SEED = 20260701

# RRC
RRC_ROLLOFF = 0.35
RRC_TAPS = 32  # Taps a cada lado del pulso

# Fading
RICE_K_FACTOR_DB = 10.0  # dB (10 dB = fuerte LOS, 0 dB = Rayleigh)
DOPPLER_MAX_HZ = 150.0    # Max Doppler a 437 MHz para LEO

# Residual de frecuencia que queda tras la pre-compensacion Doppler que hace la
# estacion terrena a partir del TLE. Compensar con el valor exacto (que es lo
# que haria un lazo perfectamente enclavado) deja el canal intacto y no mide
# nada; lo que degrada el enlace es este error residual.
DOPPLER_RESIDUAL_HZ_VALUES = [0.0, 0.05, 0.1, 0.2]

# Orbita
# Altura real de STRaND-1 segun su TLE (ver calcular_link_budget.py).
ORBIT_HEIGHT_KM = 775.0
EARTH_RADIUS_KM = 6_371.0

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


# ─── Fading Rice/Rayleigh + Doppler ────────────────────────────────────────

def gen_rice_fading(
    num_samples: int,
    sample_rate: float,
    doppler_hz: float,
    k_factor_db: float,
    rng: np.random.Generator,
) -> np.ndarray:
    K = 10.0 ** (k_factor_db / 10.0)
    sigma = 1.0 / np.sqrt(2.0 * (K + 1.0))

    # Componente difusa (Rayleigh) con perfil Jakes
    n_osc = 32
    gains = np.sqrt(1.0 / n_osc)
    phases = rng.uniform(0.0, 2.0 * np.pi, n_osc)
    freqs = doppler_hz * np.cos(np.pi / (2.0 * n_osc) * (np.arange(n_osc) - 0.5))

    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    ray_i = np.zeros(num_samples, dtype=np.float64)
    ray_q = np.zeros(num_samples, dtype=np.float64)
    for i in range(n_osc):
        arg = 2.0 * np.pi * freqs[i] * t + phases[i]
        ray_i += gains * np.cos(arg)
        ray_q += gains * np.sin(arg)

    ray_i *= sigma
    ray_q *= sigma
    rayleigh = ray_i + 1j * ray_q

    LOS = np.sqrt(K / (K + 1.0)) * np.ones(num_samples, dtype=np.complex128)
    return (LOS + rayleigh).astype(np.complex128)


def apply_doppler(
    samples: np.ndarray,
    doppler_hz: float,
    sample_rate: float,
) -> np.ndarray:
    t = np.arange(len(samples), dtype=np.float64) / sample_rate
    phase = 2.0 * np.pi * doppler_hz * t
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
    t = np.arange(len(samples), dtype=np.float64) / sample_rate
    phase = 2.0 * np.pi * doppler_hz * t
    return (samples * np.exp(-1j * phase)).astype(np.complex128)


# ─── Codificacion convolutional (r=1/2, K=7) ───────────────────────────────

def _poly_to_mask(poly: int, length: int) -> np.ndarray:
    mask = np.zeros(length, dtype=np.uint8)
    for i in range(length):
        mask[length - 1 - i] = (poly >> i) & 1
    return mask


CC_MASK0 = _poly_to_mask(CC_GENERATORS[0], CC_K)
CC_MASK1 = _poly_to_mask(CC_GENERATORS[1], CC_K)


def convolutional_encode(bits: np.ndarray) -> np.ndarray:
    reg = np.zeros(CC_K, dtype=np.uint8)
    out = np.zeros(len(bits) * CC_RATE, dtype=np.uint8)
    for i, bit in enumerate(bits):
        reg = np.roll(reg, 1)
        reg[0] = bit
        out[2 * i] = int((reg & CC_MASK0).sum() % 2)
        out[2 * i + 1] = int((reg & CC_MASK1).sum() % 2)
    # Terminar: 6 colas de 0
    for _ in range(CC_K - 1):
        reg = np.roll(reg, 1)
        reg[0] = 0
        out = np.append(out, [
            int((reg & CC_MASK0).sum() % 2),
            int((reg & CC_MASK1).sum() % 2),
        ])
    return out


def viterbi_decode(soft_bits: np.ndarray) -> np.ndarray:
    n_states = 1 << (CC_K - 1)
    n_bits = len(soft_bits) // CC_RATE
    inf = 1e30

    # Tabla de siguiente estado y salida
    next_state = np.zeros((n_states, 2), dtype=np.int32)
    out_mask = np.zeros((n_states, 2), dtype=np.uint8)
    for s in range(n_states):
        for inp in (0, 1):
            reg = np.zeros(CC_K, dtype=np.uint8)
            reg[0] = inp
            for j in range(1, CC_K):
                reg[j] = (s >> (CC_K - 1 - j)) & 1
            out0 = int((reg & CC_MASK0).sum() % 2)
            out1 = int((reg & CC_MASK1).sum() % 2)
            next_s = int((s >> 1) | (inp << (CC_K - 2)))
            next_state[s, inp] = next_s
            out_mask[s, inp] = (out0 << 1) | out1

    path_metric = np.full(n_states, inf, dtype=np.float64)
    path_metric[0] = 0.0
    traceback = np.zeros((n_bits, n_states), dtype=np.int32)

    for step in range(n_bits):
        if 2 * step + 1 < len(soft_bits):
            r0 = soft_bits[2 * step]
            r1 = soft_bits[2 * step + 1]
        else:
            r0 = 0
            r1 = 0
        new_metric = np.full(n_states, inf, dtype=np.float64)
        for s in range(n_states):
            if path_metric[s] >= inf / 2:
                continue
            for inp in (0, 1):
                ns = next_state[s, inp]
                om = out_mask[s, inp]
                expected = np.array([(om >> 1) & 1, om & 1], dtype=np.float64)
                received = np.array([float(r0), float(r1)], dtype=np.float64)
                branch = float(np.sum(np.abs(expected - received)))
                met = path_metric[s] + branch
                if met < new_metric[ns]:
                    new_metric[ns] = met
                    traceback[step, ns] = s
        path_metric = new_metric

    # Traceback
    best_state = int(np.argmin(path_metric))
    decoded = np.zeros(n_bits, dtype=np.uint8)
    for step in range(n_bits - 1, -1, -1):
        prev_state = traceback[step, best_state]
        if best_state != next_state[prev_state, 0] and best_state != next_state[prev_state, 1]:
            inp = 1
        elif best_state == next_state[prev_state, 0]:
            inp = 0
        else:
            inp = 1
        decoded[step] = inp
        best_state = prev_state
    return decoded


# ─── Canal AWGN ─────────────────────────────────────────────────────────────

def add_awgn(samples: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    signal_power = float(np.mean(np.abs(samples) ** 2))
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    sigma = np.sqrt(noise_power / 2.0)
    noise = sigma * (
        rng.standard_normal(samples.shape) + 1j * rng.standard_normal(samples.shape)
    )
    return (samples + noise).astype(np.complex128)


# ─── Metricas ──────────────────────────────────────────────────────────────

def bit_error_rate(reference: np.ndarray, recovered: np.ndarray) -> tuple[int, float]:
    n = min(len(reference), len(recovered))
    errors = int(np.count_nonzero(reference[:n] != recovered[:n]))
    return errors, errors / max(n, 1)


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


# ─── Simulacion principal ──────────────────────────────────────────────────

@dataclass
class SimResult:
    modulation: str
    rrc: bool
    fading: bool
    fec: bool
    doppler_residual_hz: float
    snr_db: float
    bits_evaluados: int
    errores_bit: int
    ber: float
    ancho_banda_hz: float
    ax25_frames_validos: int


def run_advanced_simulation(
    bits: np.ndarray,
    telemetry_bytes: bytes,
    rng: np.random.Generator,
) -> list[SimResult]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    results: list[SimResult] = []
    pulse = rrc_pulse(RRC_ROLLOFF, RRC_TAPS, SAMPLES_PER_SYMBOL)
    k_factor = RICE_K_FACTOR_DB

    # Construir tramas AX.25
    ax25_frames = build_ax25_frames(telemetry_bytes)
    ax25_bits = frames_to_bits(ax25_frames)

    def canal(clean: np.ndarray, snr_db: float, fading_enabled: bool,
              residual_hz: float) -> np.ndarray:
        """Cadena de canal en el orden fisico correcto.

        El desvanecimiento y el Doppler afectan a la señal antes de que el
        receptor le sume su propio ruido termico; aplicar el AWGN primero haria
        que el fading multiplicara tambien al ruido.
        """
        rx = clean
        if fading_enabled:
            rx = rx * gen_rice_fading(len(rx), SAMPLE_RATE, DOPPLER_MAX_HZ, k_factor, rng)
        rx = apply_doppler(rx, DOPPLER_MAX_HZ, SAMPLE_RATE)
        rx = add_awgn(rx, snr_db, rng)
        # La estacion terrena pre-compensa el Doppler con su prediccion TLE;
        # lo que llega al demodulador es el error residual de esa prediccion.
        return compensate_doppler(rx, DOPPLER_MAX_HZ - residual_hz, SAMPLE_RATE)

    # Sin FEC
    for residual_hz in DOPPLER_RESIDUAL_HZ_VALUES:
        for fading_enabled in (False, True):
            for use_rrc in (False, True):
                if use_rrc:
                    clean = modulate_bpsk_rrc(bits, pulse)
                else:
                    clean = modulate_bpsk_rect(bits)

                bw = estimate_bandwidth(clean)

                for snr_db in SNR_DB_VALUES:
                    rx = canal(clean, snr_db, fading_enabled, residual_hz)
                    if use_rrc:
                        recovered = demodulate_bpsk_rrc(rx, pulse)
                    else:
                        recovered = demodulate_bpsk_rect(rx)

                    errors, ber = bit_error_rate(bits, recovered)
                    results.append(SimResult(
                        modulation="BPSK",
                        rrc=use_rrc,
                        fading=fading_enabled,
                        fec=False,
                        doppler_residual_hz=residual_hz,
                        snr_db=snr_db,
                        bits_evaluados=min(len(bits), len(recovered)),
                        errores_bit=errors,
                        ber=ber,
                        ancho_banda_hz=round(bw, 2),
                        ax25_frames_validos=0,
                    ))

    # Con FEC (sin fading ni residual Doppler, para aislar la ganancia de codificacion)
    encoded = convolutional_encode(bits)
    clean_fec = modulate_bpsk_rect(encoded)
    bw_fec = estimate_bandwidth(clean_fec)

    for snr_db in SNR_DB_VALUES:
        rx = canal(clean_fec, snr_db, False, 0.0)
        hard_bits = demodulate_bpsk_rect(rx).astype(np.float64)
        decoded = viterbi_decode(hard_bits)
        n_check = min(len(bits), len(decoded))
        errors = int(np.count_nonzero(bits[:n_check] != decoded[:n_check]))
        results.append(SimResult(
            modulation="BPSK+FEC",
            rrc=False,
            fading=False,
            fec=True,
            doppler_residual_hz=0.0,
            snr_db=snr_db,
            bits_evaluados=n_check,
            errores_bit=errors,
            ber=errors / max(n_check, 1),
            ancho_banda_hz=round(bw_fec, 2),
            ax25_frames_validos=0,
        ))

    # AX.25 con demodulacion BPSK (RRC on, sin fading ni residual Doppler)
    clean_ax = modulate_bpsk_rrc(ax25_bits, pulse)
    bw_ax = estimate_bandwidth(clean_ax)
    # Offsets de cada trama dentro del flujo de bytes transmitido: el modelo
    # asume sincronizacion de trama ideal (no hay busqueda de banderas), pero
    # la comprobacion del FCS sobre los bytes recibidos si es real.
    longitudes = [len(f.build()) for f in ax25_frames]
    offsets = np.cumsum([0] + longitudes[:-1])

    for snr_db in SNR_DB_VALUES:
        rx = canal(clean_ax, snr_db, False, 0.0)
        recv_bits = demodulate_bpsk_rrc(rx, pulse)
        errors, ber = bit_error_rate(ax25_bits, recv_bits)

        recv_bytes = np.packbits(recv_bits).tobytes()
        valid_frames = sum(
            1
            for offset, n in zip(offsets, longitudes)
            if check_ax25_crc(recv_bytes[offset : offset + n])
        )

        results.append(SimResult(
            modulation="AX.25",
            rrc=True,
            fading=False,
            fec=False,
            doppler_residual_hz=0.0,
            snr_db=snr_db,
            bits_evaluados=min(len(ax25_bits), len(recv_bits)),
            errores_bit=errors,
            ber=ber,
            ancho_banda_hz=round(bw_ax, 2),
            ax25_frames_validos=valid_frames,
        ))

    return results


# ─── Graficas ───────────────────────────────────────────────────────────────

def plot_results(results: list[SimResult]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Simulacion avanzada del enlace RF CubeSat", fontsize=14, fontweight="bold")

    # Grafico 1: Efecto de RRC en BER
    ax = axes[0, 0]
    for label, mask in [("BPSK rectangular (NRZ)", lambda r: not r.rrc and not r.fading and not r.fec and r.doppler_residual_hz == 0),
                         ("BPSK + RRC (α=0.35)", lambda r: r.rrc and not r.fading and not r.fec and r.doppler_residual_hz == 0)]:
        pts = [r for r in results if mask(r)]
        if pts:
            pts.sort(key=lambda x: x.snr_db)
            ax.semilogy([p.snr_db for p in pts], [max(p.ber, 1e-8) for p in pts], marker="o", label=label)
    ax.set_title("Efecto del filtrado RRC")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("BER")
    ax.grid(True, which="both", linestyle=":")
    ax.legend(fontsize=8)

    # Grafico 2: fading Rice y residual de Doppler tras la pre-compensacion
    ax = axes[0, 1]
    residuales = sorted({r.doppler_residual_hz for r in results if not r.fec})
    for label, mask in (
        [("Sin fading, residual 0 Hz", lambda r: not r.fading and not r.rrc and not r.fec and r.doppler_residual_hz == 0),
         ("Fading Rice, residual 0 Hz", lambda r: r.fading and not r.rrc and not r.fec and r.doppler_residual_hz == 0)]
        + [(f"Residual Doppler {d:g} Hz",
            (lambda d: lambda r: not r.fading and not r.rrc and not r.fec and r.doppler_residual_hz == d)(d))
           for d in residuales if d > 0]
    ):
        pts = [r for r in results if mask(r)]
        if pts:
            pts.sort(key=lambda x: x.snr_db)
            ax.semilogy([p.snr_db for p in pts], [max(p.ber, 1e-8) for p in pts], marker="o", label=label)
    ax.set_title("Desvanecimiento Rice y Doppler residual")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("BER")
    ax.grid(True, which="both", linestyle=":")
    ax.legend(fontsize=8)

    # Grafico 3: FEC
    ax = axes[1, 0]
    for label, mask in [("BPSK (sin FEC)", lambda r: not r.fec and not r.rrc and not r.fading and r.doppler_residual_hz == 0),
                         ("BPSK + FEC conv.", lambda r: r.fec)]:
        pts = [r for r in results if mask(r)]
        if pts:
            pts.sort(key=lambda x: x.snr_db)
            ax.semilogy([p.snr_db for p in pts], [max(p.ber, 1e-8) for p in pts], marker="o", label=label)
    ax.set_title("Codificacion convolutional (r=1/2, K=7)")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("BER")
    ax.grid(True, which="both", linestyle=":")
    ax.legend(fontsize=8)

    # Grafico 4: Tramas AX.25
    ax = axes[1, 1]
    pts = [r for r in results if r.modulation == "AX.25"]
    if pts:
        pts.sort(key=lambda x: x.snr_db)
        ax.plot([p.snr_db for p in pts], [p.ax25_frames_validos for p in pts], marker="s", color="green", linewidth=1.5)
        ax.set_title("Tramas AX.25 validas (CRC)")
        ax.set_xlabel("SNR (dB)")
        ax.set_ylabel("Tramas validas")
        ax.grid(True, linestyle=":")
        ax.set_ylim(bottom=-0.5)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "simulacion_avanzada_resultados.png", dpi=180)
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

def export_results(results: list[SimResult]) -> None:
    with (OUTPUT_DIR / "resultados_simulacion_avanzada.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(asdict(results[0]).keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(r) for r in results)

    with (OUTPUT_DIR / "resultados_simulacion_avanzada.json").open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)


def print_summary(results: list[SimResult]) -> None:
    print("=" * 80)
    print("SIMULACION AVANZADA DEL ENLACE RF CUBESAT")
    print("=" * 80)
    print(f"Configuracion: RRC(α={RRC_ROLLOFF}), Rice(K={RICE_K_FACTOR_DB} dB), "
          f"Doppler fisico={DOPPLER_MAX_HZ} Hz")
    print(f"Residuales de Doppler evaluados: {DOPPLER_RESIDUAL_HZ_VALUES} Hz")
    print(f"FEC: Convolucional r=1/2 K=7 | AX.25: FCS CRC-16/X-25")
    n_config = len({(r.modulation, r.rrc, r.fading, r.fec, r.doppler_residual_hz) for r in results})
    print(f"Configuraciones: {n_config} x {len(SNR_DB_VALUES)} puntos de SNR = {len(results)} corridas")
    print()

    groups = {}
    for r in results:
        key = r.modulation
        if r.rrc and not r.modulation.startswith("AX"):
            key += " (RRC)"
        if r.fading:
            key += " + fading"
        if r.doppler_residual_hz > 0:
            key += f" + residual {r.doppler_residual_hz:g} Hz"
        if r.fec:
            key += " + FEC"
        groups.setdefault(key, []).append(r)

    for group_name, pts in sorted(groups.items()):
        pts.sort(key=lambda x: x.snr_db)
        print(f"\n--- {group_name} ---")
        print(f"{'SNR':>5} {'BER':>12} {'Errores':>8} {'AnchoB':>10}")
        for p in pts:
            print(f"{p.snr_db:>5} {p.ber:>12.2e} {p.errores_bit:>8} {p.ancho_banda_hz:>10.1f}")
    print("=" * 80)


# ─── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    # Cargar datos
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"No existe {INPUT_PATH}. Ejecuta decodificar_frames_STRAND1.py primero.")

    raw = INPUT_PATH.read_bytes()
    telemetry_bytes = raw
    bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8)).astype(np.uint8)
    print(f"Datos cargados: {len(telemetry_bytes)} bytes, {len(bits)} bits")

    # Ejecutar simulacion
    rng = np.random.default_rng(RNG_SEED)
    results = run_advanced_simulation(bits, telemetry_bytes, rng)

    # Exportar
    export_results(results)

    # Graficar
    plot_results(results)
    plot_spectrum_comparison()

    # Mostrar resumen
    print_summary(results)

    print(f"\nArchivos generados en {OUTPUT_DIR.resolve()}/")
    print("  - resultados_simulacion_avanzada.csv")
    print("  - resultados_simulacion_avanzada.json")
    print("  - simulacion_avanzada_resultados.png")
    print("  - espectro_rrc_comparacion.png")


if __name__ == "__main__":
    main()
