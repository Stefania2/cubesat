import json

import numpy as np

from validar_captura_iq import analyze_iq, load_manifest, read_iq


def test_valida_manifiesto_y_captura_complex64(tmp_path):
    iq = np.exp(1j * 2.0 * np.pi * 1_200.0 * np.arange(4096) / 76_800.0).astype("<c8")
    iq_path = tmp_path / "strand1.c64"
    iq.tofile(iq_path)
    manifest_path = tmp_path / "strand1.json"
    manifest_path.write_text(json.dumps({
        "iq_path": iq_path.name,
        "sample_format": "complex64_le",
        "sample_rate_hz": 76800,
        "center_frequency_hz": 437568000,
        "timestamp_utc": "2026-08-09T10:55:44Z",
        "satellite_norad_id": 39090,
        "receiver": "prueba",
        "antenna": "prueba",
    }), encoding="utf-8")

    manifest = load_manifest(manifest_path)
    metrics = analyze_iq(read_iq(iq_path, manifest["sample_format"]), manifest["sample_rate_hz"])

    assert metrics["samples"] == 4096
    assert abs(metrics["spectral_peak_offset_hz"] - 1200.0) < 25.0
