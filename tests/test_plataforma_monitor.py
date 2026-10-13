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


def test_bateria_en_cuenta_cero_se_marca_sin_medida():
    # La ultima baliza trae cuenta ADC = 0, que la recta convierte en 9.7488 V:
    # es la ordenada de la calibracion, no una tension. Antes este test daba
    # ese valor por «tension real» y el panel lo pintaba como NORMAL.
    t = enl.telemetria_enlace()
    bat = next(p for p in t["parametros"] if p["key"] == "battery_0_voltage")
    assert bat["unit"] == "V"
    assert abs(float(bat["value"]) - 9.7488) < 1e-9
    assert bat["status"] == "SIN_MEDIDA"
    assert "ordenada" in bat["nota"]


def test_ningun_parametro_se_marca_normal_sin_limites_documentados():
    t = enl.telemetria_enlace()
    assert {p["status"] for p in t["parametros"]} <= {"DECODIFICADO", "SIN_MEDIDA"}


def test_salida_sin_registro_no_se_presenta_como_resultado(tmp_path, monkeypatch):
    # Reproduce el fallo de la web: un bits_rx_sim.bin heredado, con un bit
    # distinto, aparecia como «discrepancia» sin haber simulado nada.
    tx = enl.cargar_bits(enl.BITS_TX)
    rx = tx.copy()
    rx[0] ^= 1
    monkeypatch.setattr(enl, "BITS_RX_SIM", tmp_path / "bits_rx_sim.bin")
    monkeypatch.setattr(enl, "CORRIDA_META", tmp_path / "corrida.json")
    enl.BITS_RX_SIM.write_bytes(rx.tobytes())
    check = enl.integridad_enlace()
    assert check["valido"] is None and check["diferencia"] is None
    assert check["procedencia"] == "archivo_sin_registro"


def test_corrida_registrada_informa_snr_y_errores(tmp_path, monkeypatch):
    import json

    tx = enl.cargar_bits(enl.BITS_TX)
    rx = tx.copy()
    rx[0] ^= 1
    monkeypatch.setattr(enl, "BITS_RX_SIM", tmp_path / "bits_rx_sim.bin")
    monkeypatch.setattr(enl, "CORRIDA_META", tmp_path / "corrida.json")
    enl.BITS_RX_SIM.write_bytes(rx.tobytes())
    enl.CORRIDA_META.write_text(json.dumps({
        "timestamp_utc": "2026-10-13T00:00:00+00:00", "snr_db": 8.0, "semilla": 11,
        "sha256_rx": enl.sha256_bits(rx)}))
    check = enl.integridad_enlace()
    assert check["diferencia"] == 1 and check["snr_db"] == 8.0
    assert check["procedencia"] == "corrida_anterior"
    assert "errores de canal" in check["mensaje"]


def test_en_un_despliegue_sin_gnuradio_se_simula_con_la_replica_numpy(tmp_path, monkeypatch):
    # Antes la pagina quedaba sin simulacion en el despliegue. Ahora corre la
    # replica en NumPy, y lo dice.
    monkeypatch.setenv("VERCEL", "1")
    for nombre, archivo in (("ESTADO_DIR", ""), ("BITS_RX_SIM", "bits_rx_sim.bin"),
                            ("IQ_SIM", "iq_sim.c64"), ("CORRIDA_META", "corrida.json")):
        monkeypatch.setattr(enl, nombre, tmp_path / archivo if archivo else tmp_path)
    c = enl.config_enlace()
    assert c["simulacion_disponible"] is True
    assert c["motor"] == "numpy" and "NumPy" in c["motor_nota"]
    assert c["tiempo_real"] is False

    corredor = enl.EnlaceRunner()
    monkeypatch.setattr(enl, "enlace", corredor)
    with pytest.raises(RuntimeError):
        corredor.iniciar(8.0)                 # el subproceso GNU Radio no aplica aqui
    paquete = corredor.simular_numpy(6.0)
    m = paquete["metrics"]
    assert m["motor"] == "numpy" and m["snr_db"] == 6.0 and m["bits_comparados"] == 18_776
    assert m["ber"] == m["errores_bit"] / 18_776
    assert 0.3 * m["ber_teorica"] < m["ber"] < 3 * m["ber_teorica"]
    assert m["fer"] is None and m["rssi_dbm"] is None
    assert paquete["integrity"]["procedencia"] == "sesion_actual"
    assert paquete["integrity"]["diferencia"] == m["errores_bit"]
    assert paquete["spectrum"]["disponible"] and paquete["constellation"]["disponible"]
    assert paquete["status"]["sim_status"] == "STOPPED"


def test_constelacion_y_espectro_tienen_la_forma_de_una_bpsk(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    for nombre, archivo in (("ESTADO_DIR", ""), ("BITS_RX_SIM", "bits_rx_sim.bin"),
                            ("IQ_SIM", "iq_sim.c64"), ("CORRIDA_META", "corrida.json")):
        monkeypatch.setattr(enl, nombre, tmp_path / archivo if archivo else tmp_path)
    corredor = enl.EnlaceRunner()
    monkeypatch.setattr(enl, "enlace", corredor)
    paquete = corredor.simular_numpy(12.0)

    # Tras el filtro adaptado los simbolos caen en +-1 sobre el eje I.
    i = np.array([p["i"] for p in paquete["constellation"]["puntos"]])
    q = np.array([p["q"] for p in paquete["constellation"]["puntos"]])
    assert np.abs(i).mean() == pytest.approx(1.0, abs=0.05)
    assert np.abs(np.abs(i) - 1.0).mean() < 0.3 and abs(q.mean()) < 0.1

    # La densidad espectral es mayor dentro de la banda de la señal que fuera.
    datos = paquete["spectrum"]["datos"]
    f = np.array([d["freq_hz"] for d in datos])
    p = np.array([d["power_db"] for d in datos])
    assert p[np.abs(f) < 4000].mean() > p[np.abs(f) > 15000].mean() + 6.0


def test_telemetria_excluye_conteos_adc():
    t = enl.telemetria_enlace()
    assert all(not p["key"].endswith("_adc") for p in t["parametros"])


def test_estado_y_metricas_sin_datos():
    estado = enl.estado_enlace()
    assert {"link_status", "sim_status", "frames_received"}.issubset(estado)
    m = enl.EnlaceRunner()._metricas_sin_datos()
    assert m["rssi_dbm"] is None and m["fer"] is None
    assert "N/A" in m["nota_fer"]