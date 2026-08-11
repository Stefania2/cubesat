#!/usr/bin/env python3
"""Valida la integridad y trazabilidad de una captura IQ de STRaND-1.

No inventa una decodificación: verifica que la captura declare su formato y
contexto de recepción, calcula duración, potencia, componente DC y pico espectral,
y conserva esos resultados junto a los metadatos. Si la captura incluye un archivo
de bits de referencia, informa su disponibilidad para la comparación posterior de
BER, pero no sustituye la sincronización ni la demodulación real.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

REQUIRED_FIELDS = {
    "iq_path", "sample_format", "sample_rate_hz", "center_frequency_hz",
    "timestamp_utc", "satellite_norad_id", "receiver", "antenna",
}
SUPPORTED_FORMATS = {"complex64_le", "ci16_le"}


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_FIELDS - set(manifest))
    if missing:
        raise ValueError("faltan campos obligatorios: " + ", ".join(missing))
    if manifest["sample_format"] not in SUPPORTED_FORMATS:
        raise ValueError("sample_format debe ser uno de: " + ", ".join(sorted(SUPPORTED_FORMATS)))
    if float(manifest["sample_rate_hz"]) <= 0 or float(manifest["center_frequency_hz"]) <= 0:
        raise ValueError("sample_rate_hz y center_frequency_hz deben ser positivos")
    datetime.fromisoformat(str(manifest["timestamp_utc"]).replace("Z", "+00:00"))
    return manifest


def read_iq(path: Path, sample_format: str) -> np.ndarray:
    if sample_format == "complex64_le":
        return np.fromfile(path, dtype="<c8").astype(np.complex128)
    raw = np.fromfile(path, dtype="<i2")
    if len(raw) % 2:
        raise ValueError("ci16_le debe contener pares I/Q completos")
    return (raw[0::2].astype(np.float64) + 1j * raw[1::2].astype(np.float64)) / 32768.0


def analyze_iq(samples: np.ndarray, sample_rate_hz: float) -> dict:
    if len(samples) == 0:
        raise ValueError("la captura IQ está vacía")
    nfft = min(262_144, 1 << int(np.floor(np.log2(len(samples)))))
    block = samples[:nfft]
    spectrum = np.fft.fftshift(np.fft.fft(block * np.hanning(nfft)))
    frequencies = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / sample_rate_hz))
    peak_index = int(np.argmax(np.abs(spectrum)))
    power = float(np.mean(np.abs(samples) ** 2))
    dc = complex(np.mean(samples))
    return {
        "samples": int(len(samples)),
        "duration_s": len(samples) / sample_rate_hz,
        "mean_power": power,
        "rms": float(np.sqrt(power)),
        "dc_i": dc.real,
        "dc_q": dc.imag,
        "spectral_peak_offset_hz": float(frequencies[peak_index]),
        "spectral_peak_relative_db": float(20.0 * np.log10(abs(spectrum[peak_index]) / max(nfft, 1) + 1e-15)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON de metadatos de la captura")
    parser.add_argument("--salida", type=Path, help="JSON de informe; por defecto, junto al manifiesto")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    iq_path = (args.manifest.parent / manifest["iq_path"]).resolve()
    if not iq_path.is_file():
        raise FileNotFoundError(f"no existe la captura IQ: {iq_path}")
    samples = read_iq(iq_path, manifest["sample_format"])
    analysis = analyze_iq(samples, float(manifest["sample_rate_hz"]))
    report = {
        "manifest": manifest,
        "iq_file": str(iq_path),
        "analysis": analysis,
        "reference_bits_declared": bool(manifest.get("reference_bits_path")),
        "validation_scope": (
            "integridad de archivo, metadatos y caracterización espectral; "
            "la validación BER requiere una secuencia de referencia y demodulación sincronizada"
        ),
    }
    output = args.salida or args.manifest.with_name(args.manifest.stem + "_validacion.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Captura: {analysis['samples']} muestras · {analysis['duration_s']:.3f} s")
    print(f"Pico espectral: {analysis['spectral_peak_offset_hz']:.1f} Hz respecto a la frecuencia central")
    print(f"Informe: {output}")


if __name__ == "__main__":
    main()
