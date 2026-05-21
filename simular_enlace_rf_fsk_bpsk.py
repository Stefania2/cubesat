"""
Modelo de simulacion del enlace RF CubeSat para BPSK y FSK.

El script toma los frames reales ya exportados del proyecto, genera una cadena
baseband equivalente, agrega ruido AWGN y mide BER para varios valores de SNR.
Tambien exporta muestras IQ limpias para inspeccion en GNU Radio.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


INPUT_PATH = Path("frames_STRAND1_gnuradio.bin")
OUTPUT_DIR = Path("resultados_simulacion")

SYMBOL_RATE = 9_600
SAMPLES_PER_SYMBOL = 8
SAMPLE_RATE = SYMBOL_RATE * SAMPLES_PER_SYMBOL
FSK_DEVIATION_HZ = 2_400
SNR_DB_VALUES = [-2, 0, 2, 4, 6, 8, 10, 12]
RNG_SEED = 20260521


@dataclass(frozen=True)
class SimulationConfig:
    input_file: str
    symbol_rate_bps: int
    sample_rate_sps: int
    samples_per_symbol: int
    fsk_deviation_hz: int
    snr_db_values: list[int]
    random_seed: int


def load_bits(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path.resolve()}. Ejecuta primero decodificar_frames_STRAND1.py"
        )

    raw = path.read_bytes()
    if not raw:
        raise ValueError(f"El archivo {path.resolve()} esta vacio.")

    return np.unpackbits(np.frombuffer(raw, dtype=np.uint8)).astype(np.uint8)


def modulate_bpsk(bits: np.ndarray) -> np.ndarray:
    symbols = (bits.astype(np.float32) * 2.0) - 1.0
    i_samples = np.repeat(symbols, SAMPLES_PER_SYMBOL)
    q_samples = np.zeros_like(i_samples)
    return (i_samples + 1j * q_samples).astype(np.complex64)


def demodulate_bpsk(samples: np.ndarray) -> np.ndarray:
    symbols = samples[: len(samples) // SAMPLES_PER_SYMBOL * SAMPLES_PER_SYMBOL]
    symbols = symbols.reshape(-1, SAMPLES_PER_SYMBOL)
    decisions = np.mean(symbols.real, axis=1) >= 0.0
    return decisions.astype(np.uint8)


def modulate_fsk(bits: np.ndarray) -> np.ndarray:
    freq = np.where(bits == 1, FSK_DEVIATION_HZ, -FSK_DEVIATION_HZ)
    freq_samples = np.repeat(freq, SAMPLES_PER_SYMBOL)
    phase = np.cumsum(2.0 * np.pi * freq_samples / SAMPLE_RATE)
    return np.exp(1j * phase).astype(np.complex64)


def demodulate_fsk(samples: np.ndarray) -> np.ndarray:
    usable = samples[: len(samples) // SAMPLES_PER_SYMBOL * SAMPLES_PER_SYMBOL]
    symbols = usable.reshape(-1, SAMPLES_PER_SYMBOL)
    n = np.arange(SAMPLES_PER_SYMBOL, dtype=np.float32)
    tone_one = np.exp(-1j * 2.0 * np.pi * FSK_DEVIATION_HZ * n / SAMPLE_RATE)
    tone_zero = np.exp(1j * 2.0 * np.pi * FSK_DEVIATION_HZ * n / SAMPLE_RATE)
    energy_one = np.abs(np.sum(symbols * tone_one, axis=1)) ** 2
    energy_zero = np.abs(np.sum(symbols * tone_zero, axis=1)) ** 2
    return (energy_one >= energy_zero).astype(np.uint8)


def add_awgn(samples: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    signal_power = float(np.mean(np.abs(samples) ** 2))
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    sigma = np.sqrt(noise_power / 2.0)
    noise = sigma * (
        rng.standard_normal(samples.shape) + 1j * rng.standard_normal(samples.shape)
    )
    return (samples + noise).astype(np.complex64)


def bit_error_rate(reference: np.ndarray, recovered: np.ndarray) -> tuple[int, float]:
    n = min(len(reference), len(recovered))
    errors = int(np.count_nonzero(reference[:n] != recovered[:n]))
    return errors, errors / n


def estimate_bandwidth(samples: np.ndarray, threshold_db: float = -20.0) -> float:
    spectrum = np.fft.fftshift(np.fft.fft(samples))
    power_db = 20.0 * np.log10(np.abs(spectrum) / np.max(np.abs(spectrum)) + 1e-12)
    freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), d=1.0 / SAMPLE_RATE))
    active = freqs[power_db >= threshold_db]
    if len(active) == 0:
        return 0.0
    return float(active.max() - active.min())


def run_simulation(bits: np.ndarray) -> list[dict[str, float | int | str]]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    rng = np.random.default_rng(RNG_SEED)
    modulators = {
        "BPSK": (modulate_bpsk, demodulate_bpsk),
        "FSK": (modulate_fsk, demodulate_fsk),
    }
    rows: list[dict[str, float | int | str]] = []

    for name, (modulate, demodulate) in modulators.items():
        clean = modulate(bits)
        clean.tofile(OUTPUT_DIR / f"strand1_{name.lower()}_iq_clean_complex64.bin")
        bandwidth_hz = estimate_bandwidth(clean)

        for snr_db in SNR_DB_VALUES:
            noisy = add_awgn(clean, snr_db, rng)
            recovered = demodulate(noisy)
            errors, ber = bit_error_rate(bits, recovered)
            rows.append(
                {
                    "modulacion": name,
                    "snr_db": snr_db,
                    "bits_evaluados": int(min(len(bits), len(recovered))),
                    "errores_bit": errors,
                    "ber": ber,
                    "ancho_banda_estimado_hz": round(bandwidth_hz, 2),
                }
            )

    return rows


def write_outputs(bits: np.ndarray, rows: list[dict[str, float | int | str]]) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    config = SimulationConfig(
        input_file=str(INPUT_PATH.resolve()),
        symbol_rate_bps=SYMBOL_RATE,
        sample_rate_sps=SAMPLE_RATE,
        samples_per_symbol=SAMPLES_PER_SYMBOL,
        fsk_deviation_hz=FSK_DEVIATION_HZ,
        snr_db_values=SNR_DB_VALUES,
        random_seed=RNG_SEED,
    )

    with (OUTPUT_DIR / "configuracion_modelo_rf.json").open("w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2, ensure_ascii=False)

    with (OUTPUT_DIR / "resultados_ber_fsk_bpsk.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    plt.figure(figsize=(8, 5))
    for modulation in ("BPSK", "FSK"):
        subset = [row for row in rows if row["modulacion"] == modulation]
        snr = [float(row["snr_db"]) for row in subset]
        ber = [max(float(row["ber"]), 1.0 / len(bits)) for row in subset]
        plt.semilogy(snr, ber, marker="o", label=modulation)

    plt.title("BER del enlace RF simulado con telemetria STRaND-1")
    plt.xlabel("SNR (dB)")
    plt.ylabel("BER")
    plt.grid(True, which="both", linestyle=":")
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "curva_ber_fsk_bpsk.png", dpi=180)
    plt.close()


def main() -> None:
    bits = load_bits(INPUT_PATH)
    rows = run_simulation(bits)
    write_outputs(bits, rows)

    print("=" * 72)
    print("MODELO DE SIMULACION RF FSK/BPSK COMPLETADO")
    print("=" * 72)
    print(f"Bits de telemetria evaluados : {len(bits)}")
    print(f"Symbol rate                  : {SYMBOL_RATE} bps")
    print(f"Sample rate                  : {SAMPLE_RATE} sps")
    print(f"Muestras por simbolo         : {SAMPLES_PER_SYMBOL}")
    print(f"Resultados                   : {OUTPUT_DIR.resolve()}")
    print()
    for row in rows:
        print(
            f"{row['modulacion']:4s} | SNR={row['snr_db']:>3} dB | "
            f"BER={row['ber']:.6f} | errores={row['errores_bit']}"
        )
    print("=" * 72)


if __name__ == "__main__":
    main()
