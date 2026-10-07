"""Tests del modulo «Enlace RF» integrado en la plataforma telemetria_strand1.

Cubre el servicio `enlace_monitor` (integridad de los 18.776 bits, configuracion
del enlace y telemetria AMSAT re-decodificada). El router y el WebSocket se
validan con la plataforma (venv strand_api, /api/enlace/* y /ws/enlace).

Nota: estos tests corren con el venv `strand`; no importan `app.main` porque
ese modulo exige las dependencias de la plataforma (sqlalchemy, satnogsdecoders).
"""

from __future__ import annotations

import numpy as np
import pytest

from telemetria_strand1.backend.app.services import enlace_monitor as enl


def test_config_enlace_expone_los_datos_del_proyecto():
    c = enl.config_enlace()
    assert c["modulacion"] == "BPSK"
    assert c["frecuencia_hz"] == 437_568_000
    assert c["tasa_bits_bps"] == 9600
    assert c["bits_esperados"] == 18_776
    assert c["frames_esperados"] == 100
    assert c["muestras_por_simbolo"] == 8


def test_tx_tiene_18776_bits():
    bits = enl.cargar_bits(enl.BITS_TX)
    assert len(bits) == enl.N_BITS == 18_776
    assert set(np.unique(bits)).issubset({0, 1})


def test_validar_integridad_sobre_copia_identica(tmp_path):
    tx = enl.cargar_bits(enl.BITS_TX)
    ruta = tmp_path / "rx.bin"
    ruta.write_bytes(tx.tobytes())
    check = enl.validar_integridad(ruta)
    assert check["valido"] is True
    assert check["bits_entrada"] == check["bits_recuperados"] == 18_776
    assert check["diferencia"] == 0
    assert check["sha256_entrada"] == check["sha256_recuperado"]


def test_validar_integridad_detecta_error(tmp_path):
    tx = enl.cargar_bits(enl.BITS_TX)
    rx = tx.copy()
    rx[0] ^= 1
    ruta = tmp_path / "rx_error.bin"
    ruta.write_bytes(rx.tobytes())
    check = enl.validar_integridad(ruta)
    assert check["valido"] is False
    assert check["diferencia"] == 1


def test_validar_integridad_sin_salida_no_rompe():
    check = enl.validar_integridad(tmp_path := enl.ESTADO_DIR / "no_existe.bin")
    assert check["valido"] is None
    assert "simulacion" in check["mensaje"].lower()


def test_telemetria_decodifica_balizas_reales():
    t = enl.telemetria_enlace()
    assert t["total_frames"] >= 5000
    assert len(t["parametros"]) >= 30
    assert t["nota"] and "strand_amsat" in t["nota"]


def test_telemetria_tiene_tension_real_de_bateria():
    t = enl.telemetria_enlace()
    bat = next(p for p in t["parametros"] if p["key"] == "battery_0_voltage")
    assert bat["disponible"] is True
    assert abs(float(bat["value"]) - 9.7488) < 0.01
    assert bat["unit"] == "V"
    assert bat["status"] in ("NORMAL", "ALERTA")


def test_telemetria_excluye_conteos_adc():
    t = enl.telemetria_enlace()
    assert all(not p["key"].endswith("_adc") for p in t["parametros"])


def test_estado_y_metricas_sin_datos():
    estado = enl.estado_enlace()
    assert {"link_status", "sim_status", "frames_received"}.issubset(estado)
    m = enl.EnlaceRunner()._metricas_sin_datos()
    assert m["rssi_dbm"] is None and m["fer"] is None
    assert "N/A" in m["nota_fer"]