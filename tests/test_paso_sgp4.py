"""Paso SGP4: Doppler, signo, coherencia geometrica y serie de margen."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

import margen_paso_sgp4 as mp
import parametros_enlace as pe
from geometria_orbital import C_LIGHT
from orbita_sgp4 import Observer, load_tle, propagate_point, tle_epoch

TLE = load_tle(Path("tle/strand1_2026-08-09.tle"))
BOGOTA = Observer(4.7110, -74.0721, 2600.0)
PAR = {k: v.valor for k, v in pe.PARAMETROS.items()}


@pytest.fixture(scope="module")
def paso():
    pasos = mp.buscar_pasos(TLE, BOGOTA, tle_epoch(TLE), 24, PAR["frecuencia_hz"])
    elegido = max(pasos, key=lambda p: p["elev_max_deg"])
    puntos = mp.propagar_paso(TLE, BOGOTA, elegido, PAR["frecuencia_hz"])
    return puntos, mp.serie_paso(puntos, PAR)


def test_hay_pasos_completos_y_no_empiezan_a_medias():
    inicio = tle_epoch(TLE)
    pasos = mp.buscar_pasos(TLE, BOGOTA, inicio, 24, PAR["frecuencia_hz"])
    assert len(pasos) >= 2
    assert all(p["inicio"] > inicio for p in pasos)


def test_doppler_se_calcula_con_la_portadora_y_la_velocidad_radial(paso):
    puntos, _ = paso
    p = puntos[len(puntos) // 4]
    esperado = -p.range_rate_km_s * 1000.0 / C_LIGHT * PAR["frecuencia_hz"]
    assert p.doppler_hz == pytest.approx(esperado, abs=0.01)


def test_signo_del_doppler(paso):
    puntos, _ = paso
    # Al principio el satelite se acerca: v_radial < 0 y la portadora sube.
    assert puntos[0].range_rate_km_s < 0 and puntos[0].doppler_hz > 0
    assert puntos[-1].range_rate_km_s > 0 and puntos[-1].doppler_hz < 0


def test_el_doppler_decrece_monotonamente_y_cruza_cero_en_la_culminacion(paso):
    _, filas = paso
    d = np.array([f["doppler_hz"] for f in filas])
    # Sobre la elevacion operativa. Rasante al horizonte la velocidad radial
    # aun crece unas decimas de Hz por la rotacion terrestre: es fisico.
    operativo = np.array([f["elevacion_deg"] >= mp.ELEV_OPERATIVA_DEG for f in filas])
    assert np.all(np.diff(d[operativo]) < 0)
    i_cero = int(np.argmin(np.abs(d)))
    i_max = int(np.argmax([f["elevacion_deg"] for f in filas]))
    # Maxima elevacion y distancia minima (Doppler nulo) casi coinciden.
    assert abs(i_cero - i_max) <= 3
    assert abs(d).max() < 12_000                      # LEO en UHF: ~±10 kHz


def test_la_velocidad_radial_es_la_derivada_de_la_distancia(paso):
    _, filas = paso
    t = np.array([f["tiempo_s"] for f in filas])
    dist = np.array([f["distancia_km"] for f in filas])
    rr = np.array([f["velocidad_radial_km_s"] for f in filas])
    assert np.allclose(np.gradient(dist, t)[2:-2], rr[2:-2], atol=5e-3)


def test_la_tasa_de_doppler_es_maxima_cerca_de_la_culminacion(paso):
    _, filas = paso
    tasa = np.abs([f["tasa_doppler_hz_s"] for f in filas])
    i_max = int(np.argmax([f["elevacion_deg"] for f in filas]))
    assert abs(int(np.argmax(tasa)) - i_max) <= 5


def test_residual_proporcional_al_error_de_tiempo(paso):
    _, filas = paso
    d = mp.analisis_doppler(TLE, BOGOTA, filas, PAR["frecuencia_hz"])
    res = {r["error_tiempo_s"]: r["residual_max_abs_hz"] for r in d["residual_tras_precompensacion"]}
    # residual ≈ error de tiempo × tasa de Doppler
    for dt, valor in res.items():
        assert valor == pytest.approx(dt * d["tasa_doppler_max_abs_hz_s"], rel=0.05)
    assert d["coherencia_velocidad_radial_max_abs_km_s"] < 5e-3


def test_la_serie_de_ebn0_es_coherente_con_la_trayectoria(paso):
    _, filas = paso
    for f in filas[:: max(1, len(filas) // 20)]:
        p_rx, c_n0, ebn0 = mp.eb_n0_db(f["distancia_km"], f["l_point_db"], PAR)
        assert (f["p_rx_dbm"], f["c_n0_db_hz"], f["eb_n0_db"]) == pytest.approx(
            (p_rx, c_n0, ebn0), abs=0.006)
    # Mas cerca, mas señal: Eb/N0 maxima donde la distancia es minima.
    i = int(np.argmin([f["distancia_km"] for f in filas]))
    assert abs(i - int(np.argmax([f["eb_n0_db"] for f in filas]))) <= 3


def test_estadisticas_del_margen(paso):
    _, filas = paso
    umbral = mp.umbrales(PAR)[pe.ESQUEMA_DOCUMENTADO]["eb_n0_db"]
    e = mp.estadisticas(filas, umbral)
    pc = e["percentiles_db"]
    assert e["margen_min_db"] <= pc["p5"] <= pc["p50"] <= pc["p95"] <= e["margen_max_db"]
    assert 0.0 <= e["porcentaje_tiempo_margen_positivo"] <= 100.0
    assert sum(e["intervalos_margen_positivo_s"]) == pytest.approx(
        e["duracion_total_margen_positivo_s"], abs=0.2)
    operativas = [f for f in filas if f["elevacion_deg"] >= mp.ELEV_OPERATIVA_DEG]
    assert e["duracion_total_margen_positivo_s"] <= operativas[-1]["tiempo_s"] - operativas[0]["tiempo_s"] + 1
    # Un umbral inalcanzable da 0 % y ningun intervalo, no un error.
    alto = mp.estadisticas(filas, 200.0)
    assert alto["porcentaje_tiempo_margen_positivo"] == 0.0
    assert alto["intervalos_margen_positivo_s"] == []


def test_paso_sin_elevacion_operativa_se_declara_no_disponible(paso):
    _, filas = paso
    bajas = [dict(f, elevacion_deg=1.0) for f in filas]
    assert mp.estadisticas(bajas, 10.0)["disponible"] is False


def test_el_umbral_calibrado_no_lleva_reserva_de_implementacion():
    u = mp.umbrales(PAR)
    teorico = pe.ebn0_requerida_db("bpsk_coherente") + PAR["l_impl_db"]
    assert u["bpsk_coherente"]["eb_n0_db"] == pytest.approx(teorico, abs=0.01)
    for clave, dato in u.items():
        if clave.startswith("simulado_"):
            assert dato["tipo"] == "calibrado_receptor_simulado"
            assert "sin reserva" in dato["papel"]


def test_sensibilidad_signos_fisicos(paso):
    puntos, _ = paso
    s = mp.sensibilidad(puntos, PAR)
    por = {r["parametro"]: r for r in s["uno_a_la_vez"]}
    # Mas potencia o mas ganancia: mas margen. Mas perdida o mas ruido: menos.
    assert por["p_tx_dbm"]["delta_margen_db_mas"] == pytest.approx(pe.PARAMETROS["p_tx_dbm"].incertidumbre)
    assert por["g_rx_dbi"]["delta_margen_db_mas"] > 0 > por["g_rx_dbi"]["delta_margen_db_menos"]
    for perdida in ("l_pol_db", "l_atm_db", "l_tx_db", "l_rx_db", "l_impl_db", "nf_rx_db", "t_ant_k"):
        assert por[perdida]["delta_margen_db_mas"] < 0 < por[perdida]["delta_margen_db_menos"], perdida
    mc = s["montecarlo"]["margen_min_db"]
    assert mc["p5"] < mc["p50"] < mc["p95"]


def test_doppler_del_tle_es_reproducible():
    t = tle_epoch(TLE) + timedelta(hours=1)
    a = propagate_point(TLE, BOGOTA, t, PAR["frecuencia_hz"])
    b = propagate_point(TLE, BOGOTA, t, PAR["frecuencia_hz"])
    assert a == b
