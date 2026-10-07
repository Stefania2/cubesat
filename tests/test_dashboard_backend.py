"""Tests del dashboard STRAND-1 (backend FastAPI).

Cubre, por orden de importancia para el proyecto:
1. Integridad de los 18.776 bits (regla critica: TX == RX).
2. Decodificacion de balizas reales con strand_amsat (source de verdad).
3. Metricas (BER medido, espectro y constelacion del tap IQ real).
4. Endpoints REST y WebSocket del backend.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend import config, integridad
from backend.metrics_service import MetricsService, metrics as metrics_global
from backend.telemetry_service import telemetria_out


# ─────────────────────────────────────────────────────────────────────────────
# 1. Integridad de los 18.776 bits
# ─────────────────────────────────────────────────────────────────────────────
def test_config_exige_los_numeros_del_proyecto():
    assert config.N_BITS == 18_776
    assert config.SYMBOL_RATE == 9600
    assert config.SAMPLE_RATE == 76_800
    assert config.FREQ_HZ == 437_568_000


def test_archivo_transmision_tiene_18776_bits():
    bits = integridad.cargar_bits(config.BITS_TX)
    assert len(bits) == config.N_BITS == 18_776
    assert set(np.unique(bits)).issubset({0, 1})


def test_archivo_recepcion_de_referencia_es_valido():
    if not config.BITS_RX.exists():
        pytest.skip("falta frames_STRAND1_bits_rx.bin")
    check = integridad.validar_bits(config.BITS_RX)
    assert check.valido is True
    assert check.bits_entrada == 18_776
    assert check.bits_recuperados == 18_776
    assert check.diferencia == 0
    assert check.sha256_entrada == check.sha256_recuperado


def test_validar_bits_detecta_un_error(tmp_path):
    tx = integridad.cargar_bits(config.BITS_TX)
    rx = tx.copy()
    rx[0] ^= 1
    ruta = tmp_path / "rx_con_error.bin"
    ruta.write_bytes(rx.tobytes())
    check = integridad.validar_bits(ruta)
    assert check.valido is False
    assert check.diferencia == 1
    assert check.bits_entrada == 18_776


def test_sha256_reproducible():
    bits = integridad.cargar_bits(config.BITS_TX)
    assert integridad.sha256_bits(bits) == integridad.sha256_bits(bits)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Telemetria decodificada (balizas reales, strand_amsat)
# ─────────────────────────────────────────────────────────────────────────────
def test_telemetria_usa_balizas_reales_decodificadas():
    t = telemetria_out()
    assert t.total_frames >= 5000
    assert len(t.parametros) >= 15
    assert all(
        (p.disponible and p.status in ("OK", "NORMAL", "ALERTA")) or not p.disponible
        for p in t.parametros
    )
    assert t.nota and "strand_amsat" in t.nota


def test_telemetria_contiene_tension_real_de_bateria():
    t = telemetria_out()
    bat = next(p for p in t.parametros if p.key == "battery_0_voltage")
    assert bat.disponible is True
    assert isinstance(bat.value, (int, float))
    assert 5.0 < float(bat.value) < 15.0  # valor calibrado ~9.7 V


def test_telemetria_incluye_frames_decodificados():
    t = telemetria_out()
    assert any(f.decodificado for f in t.frames)
    assert any(f.hex for f in t.frames)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Metricas del enlace (BER, espectro, constelacion)
# ─────────────────────────────────────────────────────────────────────────────
def _escribir_rx_identico(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BITS_RX_SIM", tmp_path / "rx.bin")
    tx = integridad.cargar_bits(config.BITS_TX)
    ruta = tmp_path / "rx.bin"
    ruta.write_bytes(tx.tobytes())
    return ruta


def test_metrics_ber_cero_con_bits_identicos(tmp_path, monkeypatch):
    _escribir_rx_identico(tmp_path, monkeypatch)
    ms = MetricsService()
    ms.actualizar(12.0)
    out = ms.metrics_out()
    assert out.ber == 0.0
    assert out.frames_validos == 100
    assert out.frames_error == 0
    assert out.rssi_dbm is None  # honesto: no hay potencia RF para dBm
    assert out.fer is None


def test_metrics_ber_opaco_sin_bits_recuperados():
    ms = MetricsService()
    ms._estado["disponible"] = False  # nunca se ejecuto la simulacion
    out = ms.metrics_out()
    assert out.ber is None
    assert not ms.spectrum_out().disponible
    assert not ms.constellation_out().disponible


def test_espectro_y_constelacion_desde_tap_iq(tmp_path, monkeypatch):
    _escribir_rx_identico(tmp_path, monkeypatch)
    iq = (
        np.random.default_rng(7).standard_normal(24_000)
        + 1j * np.random.default_rng(7).standard_normal(24_000)
    ).astype(np.complex64)
    ruta_iq = tmp_path / "iq.c64"
    ruta_iq.write_bytes(iq.tobytes())
    ms = MetricsService()
    ms.actualizar(9.0)
    spec = ms.spectrum_out()
    con = ms.constellation_out()
    assert spec.disponible is True
    assert len(spec.datos) > 0
    assert spec.datos[0]["freq_hz"] < spec.datos[-1]["freq_hz"]  # FFT ordenada
    assert con.disponible is True
    assert len(con.puntos) == 400


# ─────────────────────────────────────────────────────────────────────────────
# 4. API REST y WebSocket
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from backend import main as appmod

    return TestClient(appmod.app)


def test_endpoints_rest_responden(client):
    for ruta in (
        "/api/health",
        "/api/status",
        "/api/config",
        "/api/telemetry",
        "/api/frames",
        "/api/metrics",
        "/api/spectrum",
        "/api/constellation",
        "/api/integrity",
        "/api/history",
        "/api/log",
    ):
        r = client.get(ruta)
        assert r.status_code == 200, ruta


def test_config_api_expone_los_datos_del_enlace(client):
    cfg = client.get("/api/config").json()
    assert cfg["modulacion"] == config.MODULATION
    assert cfg["frecuencia_hz"] == 437_568_000
    assert cfg["bits_esperados"] == 18_776


def test_integridad_api(client):
    integ = client.get("/api/integrity").json()
    assert integ["bits_entrada"] == 18_776
    assert "sha256_entrada" in integ and "sha256_recuperado" in integ


def test_telemetria_api(client):
    t = client.get("/api/telemetry").json()
    assert t["total_frames"] >= 5000
    assert len(t["parametros"]) >= 15


def test_ws_snapshot_y_ping(client):
    with client.websocket_connect("/ws") as ws:
        recibidos = set()
        for _ in range(4):
            m = ws.receive_json()
            recibidos.add(m["type"])
        assert {"status_update", "metrics_update", "integrity_update",
                "telemetry_update"}.issubset(recibidos)
        ws.send_text("ping")
        pong = None
        for _ in range(6):
            m = ws.receive_json()
            if m["type"] == "pong":
                pong = m
                break
        assert pong is not None and pong["type"] == "pong"