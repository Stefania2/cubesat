"""Genera una captura IQ de referencia de STRaND-1 con su manifiesto.

No es una recepcion fisica: sintetiza un paso baseband con los bytes de
telemetria reales de STRaND-1 (frames_STRAND1_gnuradio.bin) usando la misma
cadena del modelo avanzado (BPSK con conformado RRC, 9600 bps) y el
desplazamiento Doppler calculado con SGP4 para la estacion de Bogota en la
epoca del TLE. Se conserva la secuencia de bits de referencia para que una
validacion BER posterior tenga contra que medir.

La captura y su manifiesto se guardan en captura/ y se procesan con
validar_captura_iq.py. Cuando se disponga de una captura real de un SDR, se
sustituye el binario y los metadatos de receiver/antenna sin cambiar el resto.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import simular_enlace_rf_bpsk_avanzado as rf
from orbita_sgp4 import Observer, load_tle, propagate_point, tle_epoch

BYTES_PATH = Path("frames_STRAND1_gnuradio.bin")
TLE_PATH = Path("tle/strand1_2026-08-09.tle")
OUTPUT_DIR = Path("captura")
OUTPUT_IQ = OUTPUT_DIR / "strand1_2026-08-09.c64"
OUTPUT_BITS = OUTPUT_DIR / "strand1_bits_referencia.bin"
OUTPUT_MANIFEST = OUTPUT_DIR / "strand1_2026-08-09.json"

CENTER_FREQUENCY_HZ = 437.568e6
BOGOTA = Observer(lat_deg=4.7110, lon_deg=-74.0721, alt_m=2600)


def main() -> None:
    if not BYTES_PATH.exists():
        raise FileNotFoundError(f"No existe el archivo de entrada: {BYTES_PATH.resolve()}")

    tle = load_tle(TLE_PATH)
    epoch = tle_epoch(tle)
    doppler_hz = propagate_point(tle, BOGOTA, epoch, CENTER_FREQUENCY_HZ).doppler_hz

    raw = BYTES_PATH.read_bytes()
    if not raw:
        raise ValueError("El archivo de entrada esta vacio.")
    bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8))
    pulse = rf.rrc_pulse(rf.RRC_ROLLOFF, rf.RRC_TAPS, rf.SAMPLES_PER_SYMBOL)
    samples = rf.apply_doppler(rf.modulate_bpsk_rrc(bits, pulse), doppler_hz, rf.SAMPLE_RATE)

    OUTPUT_DIR.mkdir(exist_ok=True)
    samples.astype("<c8").tofile(OUTPUT_IQ)
    bits.astype(np.uint8).tofile(OUTPUT_BITS)

    manifest = {
        "iq_path": OUTPUT_IQ.name,
        "sample_format": "complex64_le",
        "sample_rate_hz": rf.SAMPLE_RATE,
        "center_frequency_hz": CENTER_FREQUENCY_HZ,
        "timestamp_utc": epoch.isoformat().replace("+00:00", "Z"),
        "satellite_norad_id": 39090,
        "receiver": "referencia sintetizada sin front-end RF (SDR real pendiente)",
        "antenna": "referencia: misma cadena del modelo, BPSK RRC a=0.35 (antena real pendiente)",
        "reference_bits_path": OUTPUT_BITS.name,
        "doppler_offset_hz": round(doppler_hz, 3),
        "tle": {
            "name": tle.name,
            "source": str(TLE_PATH),
            "epoch_utc": epoch.isoformat().replace("+00:00", "Z"),
        },
    }
    OUTPUT_MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Telemetria : {len(raw)} bytes -> {len(bits)} bits")
    print(f"Modulacion : BPSK RRC (a={rf.RRC_ROLLOFF}) a {rf.SAMPLE_RATE:g} sps, {len(samples)} muestras")
    print(f"Doppler SGP4 ({epoch.isoformat()} UTC, Bogota): {doppler_hz:.3f} Hz")
    print(f"IQ         : {OUTPUT_IQ}")
    print(f"Bits ref   : {OUTPUT_BITS}")
    print(f"Manifiesto : {OUTPUT_MANIFEST}")
    print("Siguiente paso: python validar_captura_iq.py captura/strand1_2026-08-09.json")


if __name__ == "__main__":
    main()
