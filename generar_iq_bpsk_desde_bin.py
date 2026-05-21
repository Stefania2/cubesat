"""
Convierte un archivo binario de bytes de telemetria en una senal BPSK
baseband sintetica para pruebas en GNU Radio.

Importante:
- El archivo de entrada contiene payloads concatenados, no capturas IQ reales.
- La salida sirve para simulacion de cadena digital, no para reproducir
  condiciones reales de canal RF.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


INPUT_PATH = Path("frames_STRAND1_gnuradio.bin")
OUTPUT_BITS = Path("frames_STRAND1_bits.bin")
OUTPUT_IQ = Path("frames_STRAND1_bpsk_iq_complex64.bin")

SAMPLES_PER_SYMBOL = 8


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"No existe el archivo de entrada: {INPUT_PATH.resolve()}"
        )

    raw = INPUT_PATH.read_bytes()
    if not raw:
        raise ValueError("El archivo de entrada esta vacio.")

    byte_array = np.frombuffer(raw, dtype=np.uint8)
    bits = np.unpackbits(byte_array)

    # Mapeo BPSK NRZ: 0 -> -1, 1 -> +1
    symbols = (bits.astype(np.float32) * 2.0) - 1.0

    # Pulso rectangular simple para que GNU Radio pueda leerlo como IQ complejo.
    i_samples = np.repeat(symbols, SAMPLES_PER_SYMBOL).astype(np.float32)
    q_samples = np.zeros_like(i_samples)
    iq = (i_samples + 1j * q_samples).astype(np.complex64)

    OUTPUT_BITS.write_bytes(bits.astype(np.uint8).tobytes())
    iq.tofile(OUTPUT_IQ)

    print("=" * 60)
    print("ARCHIVOS LISTOS PARA GNU RADIO")
    print("=" * 60)
    print(f"Entrada                 : {INPUT_PATH.resolve()}")
    print(f"Bytes de telemetria     : {len(raw)}")
    print(f"Bits generados          : {len(bits)}")
    print(f"Muestras por simbolo    : {SAMPLES_PER_SYMBOL}")
    print(f"Archivo bits (uint8)    : {OUTPUT_BITS.resolve()}")
    print(f"Archivo IQ (complex64)  : {OUTPUT_IQ.resolve()}")
    print()
    print("Uso recomendado en GNU Radio:")
    print("- Para inspeccionar bytes: File Source -> Byte -> frames_STRAND1_gnuradio.bin")
    print("- Para inspeccionar bits : File Source -> Byte -> frames_STRAND1_bits.bin")
    print("- Para simulacion BPSK   : File Source -> Complex -> frames_STRAND1_bpsk_iq_complex64.bin")
    print("=" * 60)


if __name__ == "__main__":
    main()
