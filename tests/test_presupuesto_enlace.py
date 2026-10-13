"""Presupuesto de enlace: ecuaciones, unidades y coherencia interna.

Los valores de referencia de este archivo estan calculados a mano, de forma
independiente del codigo que se prueba.
"""

from __future__ import annotations

import math

import pytest

import calcular_link_budget as lb
import modelo_estacion_terrena as est
import parametros_enlace as pe
from geometria_orbital import (
    densidad_ruido_dbm_hz,
    distancia_satelite,
    fspl_db,
    temperatura_desde_figura_ruido,
    temperatura_sistema,
)


def _params() -> lb.LinkBudgetParams:
    return lb.LinkBudgetParams(
        frecuencia_hz=lb.FREQ_HZ, modulation=lb.MODULATION, symbol_rate_bps=lb.SYM_RATE,
        p_tx_dbm=lb.P_TX_DBM, g_tx_dbi=lb.G_TX_DBI, l_tx_db=lb.L_TX_DB, g_rx_dbi=lb.G_RX_DBI,
        l_rx_db=lb.L_RX_DB, nf_rx_db=lb.NF_RX_DB, t_ant_k=lb.T_ANT_K, l_atm_db=lb.L_ATM_DB,
        l_pol_db=lb.L_POL_DB, l_point_db=lb.L_POINT_DB, l_impl_db=lb.L_IMPL_DB,
        eb_n0_req_db=lb.EBN0_REQ_DB, eb_n0_req_bpsk_db=lb.EBN0_REQ_BPSK_DB,
        ber_target=lb.BER_TARGET, orbit_height_km=lb.ORBIT_HEIGHT_KM,
    )


# ── Casos de referencia independientes ──────────────────────────────────────

def test_fspl_caso_de_referencia():
    # 32.45 + 20 log10(f_MHz) + 20 log10(d_km) con f = 437.568 MHz y d = 1000 km.
    esperado = 32.45 + 20 * math.log10(437.568) + 20 * math.log10(1000.0)
    assert fspl_db(1_000e3, 437.568e6) == pytest.approx(esperado, abs=0.01)
    assert fspl_db(1_000e3, 437.568e6) == pytest.approx(145.27, abs=0.01)


def test_fspl_crece_6_db_al_doblar_la_distancia():
    assert fspl_db(2e6, 437.568e6) - fspl_db(1e6, 437.568e6) == pytest.approx(6.0206, abs=1e-3)


def test_densidad_de_ruido_a_290_k_es_menos_174_dbm_hz():
    assert densidad_ruido_dbm_hz(290.0) == pytest.approx(-173.98, abs=0.01)


def test_figura_de_ruido_de_3_db_equivale_a_unos_289_k():
    assert temperatura_desde_figura_ruido(3.0) == pytest.approx(288.6, abs=0.5)


def test_temperatura_de_sistema_sin_cable_es_antena_mas_receptor():
    assert temperatura_sistema(150.0, 0.0, 2.0) == pytest.approx(
        150.0 + temperatura_desde_figura_ruido(2.0))


def test_temperatura_de_sistema_con_cable_infinito_tiende_a_t0_mas_receptor():
    assert temperatura_sistema(150.0, 60.0, 2.0) == pytest.approx(
        290.0 + temperatura_desde_figura_ruido(2.0), abs=0.01)


def test_conversion_dbm_vatios():
    assert lb.dbm_to_watt(30.0) == pytest.approx(1.0)
    assert lb.dbm_to_watt(0.0) == pytest.approx(1e-3)
    assert lb.watt_to_dbm(0.25) == pytest.approx(23.98, abs=0.01)


def test_distancia_oblicua_limites_y_monotonia():
    h = lb.ORBIT_HEIGHT_KM
    assert distancia_satelite(90.0, h) == pytest.approx(h)
    # Horizonte: sqrt((R+h)^2 - R^2)
    assert distancia_satelite(0.0, h) == pytest.approx(math.sqrt((6371 + h) ** 2 - 6371 ** 2), rel=1e-6)
    d = [distancia_satelite(e, h) for e in range(0, 91, 5)]
    assert d == sorted(d, reverse=True)


# ── Umbrales por esquema ────────────────────────────────────────────────────

def test_umbrales_teoricos_a_ber_1e5():
    # Valores de tablas: BPSK 9.59 dB; FSK ortogonal no coherente 2 ln(1/(2 Pb)).
    assert pe.ebn0_requerida_db("bpsk_coherente", 1e-5) == pytest.approx(9.59, abs=0.01)
    fsk_nc = 10 * math.log10(2 * math.log(1 / (2 * 1e-5)))
    assert pe.ebn0_requerida_db("fsk_no_coherente", 1e-5) == pytest.approx(fsk_nc, abs=0.01)
    assert fsk_nc == pytest.approx(13.35, abs=0.01)
    # FSK coherente necesita exactamente 3.01 dB mas que BPSK.
    assert (pe.ebn0_requerida_db("fsk_coherente", 1e-5)
            - pe.ebn0_requerida_db("bpsk_coherente", 1e-5)) == pytest.approx(3.01, abs=0.01)


def test_las_curvas_de_ber_devuelven_el_objetivo_en_su_umbral():
    for clave, esquema in pe.ESQUEMAS.items():
        x = 10 ** (pe.ebn0_requerida_db(clave, 1e-4) / 10)
        assert esquema.ber(x) == pytest.approx(1e-4, rel=1e-3)


def test_la_modulacion_documentada_es_fsk_y_el_modelo_es_bpsk():
    assert pe.ESQUEMA_DOCUMENTADO.startswith("fsk")
    assert pe.ESQUEMA_MODELO == "bpsk_coherente"
    assert lb.MODULATION == "FSK"
    assert "no es la modulacion documentada" in pe.ESQUEMAS["bpsk_coherente"].papel


def test_todo_parametro_declara_procedencia_y_fuente():
    for nombre, p in pe.PARAMETROS.items():
        assert p.procedencia in (pe.DOCUMENTADO, pe.DEDUCIDO, pe.SUPUESTO), nombre
        assert p.fuente, nombre


# ── Cadena P_rx -> C/N0 -> Eb/N0 -> margen ──────────────────────────────────

def test_caso_cenital_calculado_a_mano():
    r = lb.calcular_link_budget(90.0, _params())
    fspl = fspl_db(775e3, 437.568e6)
    p_rx = 30.0 + 0.0 - 0.5 + 15.0 - 2.0 - fspl - 0.5 - 1.0 - 1.0
    assert r.fspl_db == pytest.approx(143.05, abs=0.01)
    assert r.p_rx_dbm == pytest.approx(p_rx, abs=0.01)
    assert r.p_rx_dbm == pytest.approx(-103.05, abs=0.01)


@pytest.mark.parametrize("elev", [5, 20, 45, 70, 90])
def test_relaciones_entre_potencia_ruido_cn0_ebn0_y_margen(elev):
    p = _params()
    r = lb.calcular_link_budget(float(elev), p)
    n0 = densidad_ruido_dbm_hz(temperatura_sistema(p.t_ant_k, p.l_rx_db, p.nf_rx_db))
    # Tolerancia de redondeo: cada campo se guarda con dos decimales.
    assert r.c_n0_db_hz == pytest.approx(r.p_rx_dbm - n0, abs=0.011)
    assert r.eb_n0_db == pytest.approx(r.c_n0_db_hz - 10 * math.log10(9600), abs=0.011)
    assert r.margen_db == pytest.approx(r.eb_n0_db - r.eb_n0_requerida_db, abs=0.011)
    assert r.margen_bpsk_db == pytest.approx(r.eb_n0_db - r.eb_n0_requerida_bpsk_db, abs=0.011)
    # Las perdidas se restan una sola vez: P_rx reconstruida desde los terminos.
    assert r.p_rx_dbm == pytest.approx(
        p.p_tx_dbm + p.g_tx_dbi - p.l_tx_db + p.g_rx_dbi - p.l_rx_db - r.perdida_total_db, abs=0.011)
    assert r.perdida_total_db == pytest.approx(
        r.fspl_db + p.l_atm_db + p.l_pol_db + p.l_point_db, abs=0.011)


def test_el_margen_bpsk_supera_al_fsk_en_la_diferencia_de_umbrales():
    r = lb.calcular_link_budget(30.0, _params())
    assert r.margen_bpsk_db - r.margen_db == pytest.approx(
        lb.EBN0_REQ_DB - lb.EBN0_REQ_BPSK_DB, abs=0.02)


def test_el_margen_crece_con_la_elevacion():
    m = [lb.calcular_link_budget(float(e), _params()).margen_db for e in range(5, 91, 5)]
    assert m == sorted(m)


def test_la_estacion_terrena_usa_los_mismos_parametros_que_el_link_budget():
    # El modelo de estacion omitia la perdida de polarizacion y daba 1 dB mas.
    assert est.L_POL_DB == lb.L_POL_DB == pe.valor("l_pol_db")
    for nombre in ("P_TX_DBM", "G_TX_DBI", "L_TX_DB", "L_RX_DB", "L_ATM_DB", "NF_RX_DB",
                   "FREQ_HZ", "ORBIT_HEIGHT_KM"):
        assert getattr(est, nombre) == getattr(lb, nombre), nombre
