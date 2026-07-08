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
from scipy.special import erfc

# ─── Constantes del sistema ────────────────────────────────────────────────

INPUT_PATH = Path("frames_STRAND1_gnuradio.bin")
OUTPUT_DIR = Path("resultados_simulacion")

SYMBOL_RATE = 9_600
SAMPLES_PER_SYMBOL = 8
SAMPLE_RATE = SYMBOL_RATE * SAMPLES_PER_SYMBOL
SNR_DB_VALUES = [-2, 0, 2, 4, 6, 8, 10, 12]
RNG_SEED = 20260701

# RRC
RRC_ROLLOFF = 0.35
RRC_TAPS = 32  # Taps a cada lado del pulso

# Fading
RICE_K_FACTOR_DB = 10.0  # dB (10 dB = fuerte LOS, 0 dB = Rayleigh)
DOPPLER_MAX_HZ = 150.0    # Max Doppler a 437 MHz para LEO

# Orbita
ORBIT_HEIGHT_KM = 600.0
EARTH_RADIUS_KM = 6_371.0

# Convolutional code (r=1/2, K=7, polinomios 171, 133 octal)
CC_K = 7
CC_GENERATORS = (0o171, 0o133)
CC_RATE = 2  # 1 bit in, 2 bits out

# CRC-16-CCITT
CRC_POLY = 0x1021


@dataclass(frozen=True)
class AX25Frame:
    destination: str
    source: str
    control: int
    pid: int
    info: bytes

    def build(self) -> bytes:
        flag = b"\x7e"
        dest_bytes = _encode_ax25_call(self.destination)
        src_bytes = _encode_ax25_call(self.source)
        control = bytes([self.control])
        pid = bytes([self.pid])
        fcs = _crc16_ccitt(flag + dest_bytes + src_bytes + control + pid + self.info)
        return flag + dest_bytes + src_bytes + control + pid + self.info + fcs + flag


def _encode_ax25_call(call: str) -> bytes:
    if "-" in call:
        base, ssid = call.split("-", 1)
        ssid = int(ssid)
    else:
        base = call
        ssid = 0
    b = base.ljust(6, " ").encode("ascii")
    b = bytes([c << 1 for c in b])
    b += bytes([0x60 | ssid])
    return b


def _crc16_ccitt(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ CRC_POLY
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc.to_bytes(2, "little")


def build_ax25_frames(telemetry_bytes: bytes, frame_size: int = 64) -> list[AX25Frame]:
    frames = []
    for i in range(0, len(telemetry_bytes), frame_size):
        chunk = telemetry_bytes[i : i + frame_size]
        frame = AX25Frame(
            destination="CQ",
            source="STRAND1",
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
    if len(frame_bytes) < 4:
        return False
    fcs = int.from_bytes(frame_bytes[-3:-1], "little")
    data = frame_bytes[:-3] + b"\x00\x00" + frame_bytes[-1:]
    calculated = int.from_bytes(_crc16_ccitt(data), "little")
    return fcs == calculated


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
    return pulse.astype(np.float64)


def apply_rrc(samples: np.ndarray, pulse: np.ndarray) -> np.ndarray:
    return np.convolve(samples, pulse, mode="same")


# ─── Modulacion BPSK (con RRC) ─────────────────────────────────────────────

def modulate_bpsk_rrc(bits: np.ndarray, pulse: np.ndarray) -> np.ndarray:
    symbols = (bits.astype(np.float64) * 2.0) - 1.0
    upsampled = np.zeros(len(symbols) * SAMPLES_PER_SYMBOL, dtype=np.float64)
    upsampled[::SAMPLES_PER_SYMBOL] = symbols
    shaped = np.convolve(upsampled, pulse, mode="same")
    return (shaped + 1j * 0.0).astype(np.complex128)


def demodulate_bpsk_rrc(samples: np.ndarray, pulse: np.ndarray) -> np.ndarray:
    real_part = np.real(samples)
    matched = np.convolve(real_part, pulse[::-1], mode="same")
    usable = matched[: len(matched) // SAMPLES_PER_SYMBOL * SAMPLES_PER_SYMBOL]
    integrated = usable.reshape(-1, SAMPLES_PER_SYMBOL).mean(axis=1)
    return (integrated >= 0.0).astype(np.uint8)


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


def estimate_bandwidth(samples: np.ndarray, threshold_db: float = -20.0) -> float:
    spectrum = np.fft.fftshift(np.fft.fft(samples))
    power_db = 20.0 * np.log10(np.abs(spectrum) / max(np.max(np.abs(spectrum)), 1e-12) + 1e-12)
    freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), d=1.0 / SAMPLE_RATE))
    active = freqs[power_db >= threshold_db]
    if len(active) == 0:
        return 0.0
    return float(active.max() - active.min())


# ─── Simulacion principal ──────────────────────────────────────────────────

@dataclass
class SimResult:
    modulation: str
    rrc: bool
    fading: bool
    fec: bool
    doppler_hz: float
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
    dopplers = [0.0, DOPPLER_MAX_HZ * 0.3, DOPPLER_MAX_HZ]
    k_factor = RICE_K_FACTOR_DB

    # Construir tramas AX.25
    ax25_frames = build_ax25_frames(telemetry_bytes)
    ax25_bits = frames_to_bits(ax25_frames)
    n_ax25_frames = len(ax25_frames)

    # Sin FEC
    for doppler_hz in dopplers:
        for fading_enabled in (False, True):
            for use_rrc in (False, True):
                label = "BPSK"
                tx_bits = bits
                mod_bits = bits

                # Modulacion
                if use_rrc:
                    clean = modulate_bpsk_rrc(mod_bits, pulse)
                else:
                    symbols = (mod_bits.astype(np.float64) * 2.0) - 1.0
                    upsampled = np.zeros(len(symbols) * SAMPLES_PER_SYMBOL, dtype=np.float64)
                    upsampled[::SAMPLES_PER_SYMBOL] = symbols
                    clean = upsampled.astype(np.complex128)

                bw = estimate_bandwidth(clean)

                for snr_db in SNR_DB_VALUES:
                    noisy = add_awgn(clean, snr_db, rng)

                    if fading_enabled:
                        fade = gen_rice_fading(len(noisy), SAMPLE_RATE, doppler_hz, k_factor, rng)
                        noisy *= fade

                    if doppler_hz > 0:
                        noisy = apply_doppler(noisy, doppler_hz, SAMPLE_RATE)

                    # Demodulacion
                    if use_rrc:
                        recovered = demodulate_bpsk_rrc(noisy, pulse)
                    else:
                        usable = noisy[: len(noisy) // SAMPLES_PER_SYMBOL * SAMPLES_PER_SYMBOL]
                        integrated = usable.real.reshape(-1, SAMPLES_PER_SYMBOL).mean(axis=1)
                        recovered = (integrated >= 0.0).astype(np.uint8)

                    errors, ber = bit_error_rate(tx_bits, recovered)
                    results.append(SimResult(
                        modulation=label,
                        rrc=use_rrc,
                        fading=fading_enabled,
                        fec=False,
                        doppler_hz=round(doppler_hz, 1),
                        snr_db=snr_db,
                        bits_evaluados=min(len(tx_bits), len(recovered)),
                        errores_bit=errors,
                        ber=ber,
                        ancho_banda_hz=round(bw, 2),
                        ax25_frames_validos=0,
                    ))

    # Con FEC (solo sin fading, sin RRC para comparacion base)
    label = "BPSK+FEC"
    mod_bits = bits[:len(bits) // 2 * 2]
    encoded = convolutional_encode(mod_bits)
    symbols = (encoded.astype(np.float64) * 2.0) - 1.0
    upsampled = np.zeros(len(symbols) * SAMPLES_PER_SYMBOL, dtype=np.float64)
    upsampled[::SAMPLES_PER_SYMBOL] = symbols
    clean = upsampled.astype(np.complex128)
    bw = estimate_bandwidth(clean)

    for snr_db in SNR_DB_VALUES:
        noisy = add_awgn(clean, snr_db, rng)
        usable = noisy[: len(noisy) // SAMPLES_PER_SYMBOL * SAMPLES_PER_SYMBOL]
        integrated = usable.real.reshape(-1, SAMPLES_PER_SYMBOL).mean(axis=1)
        hard_bits = np.where(integrated >= 0.0, 1.0, 0.0)
        decoded = viterbi_decode(hard_bits)
        n_check = min(len(mod_bits), len(decoded))
        errors = int(np.count_nonzero(mod_bits[:n_check] != decoded[:n_check]))
        ber = errors / max(n_check, 1)
        results.append(SimResult(
            modulation=label,
            rrc=False,
            fading=False,
            fec=True,
            doppler_hz=0.0,
            snr_db=snr_db,
            bits_evaluados=n_check,
            errores_bit=errors,
            ber=ber,
            ancho_banda_hz=round(bw, 2),
            ax25_frames_validos=0,
        ))

    # AX.25 con demodulacion BPSK (RRC on, sin fading, sin Doppler)
    ax25_tx_bits = ax25_bits
    clean_ax = modulate_bpsk_rrc(ax25_tx_bits, pulse)
    for snr_db in SNR_DB_VALUES:
        noisy = add_awgn(clean_ax, snr_db, rng)
        recv_bits = demodulate_bpsk_rrc(noisy, pulse)
        _, ber = bit_error_rate(ax25_tx_bits, recv_bits)

        # Reconstruir frames desde bits recibidos
        recv_bytes = np.packbits(recv_bits).tobytes()
        valid_frames = 0
        for frame in ax25_frames:
            if len(recv_bytes) < 20:
                continue
            f = frame.build()
            if f in recv_bytes:
                valid_frames += 1

        results.append(SimResult(
            modulation="AX.25",
            rrc=True,
            fading=False,
            fec=False,
            doppler_hz=0.0,
            snr_db=snr_db,
            bits_evaluados=len(ax25_tx_bits),
            errores_bit=int(ber * len(ax25_tx_bits)),
            ber=ber,
            ancho_banda_hz=round(bw, 2),
            ax25_frames_validos=valid_frames,
        ))

    return results


# ─── Graficas ───────────────────────────────────────────────────────────────

def plot_results(results: list[SimResult]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Simulacion avanzada del enlace RF CubeSat", fontsize=14, fontweight="bold")

    # Grafico 1: Efecto de RRC en BER
    ax = axes[0, 0]
    for label, mask in [("BPSK (sin RRC)", lambda r: not r.rrc and not r.fading and not r.fec and r.doppler_hz == 0),
                         ("BPSK (con RRC)", lambda r: r.rrc and not r.fading and not r.fec and r.doppler_hz == 0)]:
        pts = [r for r in results if mask(r)]
        if pts:
            pts.sort(key=lambda x: x.snr_db)
            ax.semilogy([p.snr_db for p in pts], [max(p.ber, 1e-8) for p in pts], marker="o", label=label)
    ax.set_title("Efecto del filtrado RRC")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("BER")
    ax.grid(True, which="both", linestyle=":")
    ax.legend(fontsize=8)

    # Grafico 2: Efecto de fading + Doppler
    ax = axes[0, 1]
    for label, mask in [("Sin fading", lambda r: not r.fading and not r.rrc and not r.fec and r.doppler_hz == 0),
                         ("Fading Rice", lambda r: r.fading and not r.rrc and not r.fec and r.doppler_hz < 1),
                         ("Fading + Doppler 150 Hz", lambda r: r.fading and not r.rrc and not r.fec and r.doppler_hz > 50)]:
        pts = [r for r in results if mask(r)]
        if pts:
            pts.sort(key=lambda x: x.snr_db)
            ax.semilogy([p.snr_db for p in pts], [max(p.ber, 1e-8) for p in pts], marker="o", label=label)
    ax.set_title("Efecto del canal con desvanecimiento")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("BER")
    ax.grid(True, which="both", linestyle=":")
    ax.legend(fontsize=8)

    # Grafico 3: FEC
    ax = axes[1, 0]
    for label, mask in [("BPSK (sin FEC)", lambda r: not r.fec and not r.rrc and not r.fading and r.doppler_hz == 0),
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


def plot_spectrum_comparison(results: list[SimResult]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle("Comparacion de espectro: BPSK sin y con filtrado RRC", fontsize=13, fontweight="bold")

    pulse = rrc_pulse(RRC_ROLLOFF, RRC_TAPS, SAMPLES_PER_SYMBOL)
    rng = np.random.default_rng(RNG_SEED)
    bits = rng.integers(0, 2, 1000, dtype=np.uint8)

    for idx, (use_rrc, title) in enumerate([(False, "BPSK rectangular"), (True, "BPSK con RRC (α=0.35)")]):
        if use_rrc:
            clean = modulate_bpsk_rrc(bits, pulse)
        else:
            symbols = (bits.astype(np.float64) * 2.0) - 1.0
            upsampled = np.zeros(len(symbols) * SAMPLES_PER_SYMBOL, dtype=np.float64)
            upsampled[::SAMPLES_PER_SYMBOL] = symbols
            clean = upsampled.astype(np.complex128)

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
          f"Doppler max={DOPPLER_MAX_HZ} Hz")
    print(f"FEC: Convolucional r=1/2 K=7 | AX.25: CRC-16-CCITT")
    print(f"Total de configuraciones evaluadas: {len(results)}")
    print()

    groups = {}
    for r in results:
        key = r.modulation
        if r.rrc and not r.modulation.startswith("AX"):
            key += " (RRC)"
        if r.fading:
            key += f" + fading"
        if abs(r.doppler_hz) > 1:
            key += f" + Doppler"
        if r.fec:
            key += " + FEC"
        groups.setdefault(key, []).append(r)

    for group_name, pts in sorted(groups.items()):
        pts.sort(key=lambda x: x.snr_db)
        print(f"\n--- {group_name} ---")
        print(f"{'SNR':>5} {'BER':>12} {'Errores':>8} {'AnchoB':>8}")
        for p in pts:
            print(f"{p.snr_db:>5} {p.ber:>12.2e} {p.errores_bit:>8} {p.ancho_banda_hz:>8.1f}")
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
    plot_spectrum_comparison(results)

    # Mostrar resumen
    print_summary(results)

    print(f"\nArchivos generados en {OUTPUT_DIR.resolve()}/")
    print("  - resultados_simulacion_avanzada.csv")
    print("  - resultados_simulacion_avanzada.json")
    print("  - simulacion_avanzada_resultados.png")
    print("  - espectro_rrc_comparacion.png")


if __name__ == "__main__":
    main()
