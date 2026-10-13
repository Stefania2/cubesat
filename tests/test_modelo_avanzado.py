"""Modelo avanzado: canal, codigo, tramas, metricas y reproducibilidad."""

from __future__ import annotations

import math

import numpy as np
import pytest

import estimar_snr_iq as snr
import simular_enlace_rf_bpsk_avanzado as rf

RNG = np.random.default_rng(20261013)
BYTES = bytes(RNG.integers(0, 256, 256, dtype=np.uint8))
BITS = np.unpackbits(np.frombuffer(BYTES, dtype=np.uint8))


def _esquema(clave: str) -> rf.Esquema:
    return next(e for e in rf.ESQUEMAS if e.clave == clave)


def _tarea(esquema: str, canal: str = "awgn", ebn0: float = 6.0, ensayo: int = 0, i: int = 0):
    return (_esquema(esquema), rf.CANALES[canal], ebn0, ensayo, i, BITS, BYTES)


# ── Definicion de energia ───────────────────────────────────────────────────

def test_snr_por_muestra_frente_a_ebn0():
    assert rf.snr_muestra_desde_ebn0(0.0) == pytest.approx(-9.031, abs=1e-3)
    # El codigo r=1/2 reparte cada bit en dos simbolos: 3.01 dB menos por muestra.
    assert rf.snr_muestra_desde_ebn0(0.0, 0.5) == pytest.approx(-12.041, abs=1e-3)


def test_el_canal_impone_la_ebn0_pedida():
    pulse = rf.rrc_pulse(rf.RRC_ROLLOFF, rf.RRC_TAPS, rf.SAMPLES_PER_SYMBOL)
    bits = RNG.integers(0, 2, 20_000, dtype=np.uint8)
    clean = rf.modulate_bpsk_rrc(bits, pulse)
    rx = rf.canal_enlace(clean, 7.0, 1.0, False, 0.0, 0.0, (1, 2), (3, 4), desfase_muestras=0.0)
    ruido = rx - clean
    # Es = suma de |pulso|^2 = 1; N0 = varianza compleja del ruido por muestra.
    ebn0 = 10 * math.log10(1.0 / float(np.mean(np.abs(ruido) ** 2)))
    assert ebn0 == pytest.approx(7.0, abs=0.1)


# ── Canal Rice ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("k_db", [0.0, 6.0, 10.0])
def test_rice_potencia_unitaria_y_factor_k(k_db):
    g = np.concatenate([
        rf.gen_rice_fading(60_000, rf.SAMPLE_RATE, 150.0, k_db, np.random.default_rng(i))
        for i in range(60)])
    potencia = float(np.mean(np.abs(g) ** 2))
    p_los = abs(g.mean()) ** 2
    assert potencia == pytest.approx(1.0, abs=0.03)
    assert 10 * math.log10(p_los / (potencia - p_los)) == pytest.approx(k_db, abs=0.5)


def test_rice_depende_del_tiempo_segun_la_dispersion_doppler():
    lento = rf.gen_rice_fading(20_000, rf.SAMPLE_RATE, 5.0, 0.0, np.random.default_rng(1))
    rapido = rf.gen_rice_fading(20_000, rf.SAMPLE_RATE, 500.0, 0.0, np.random.default_rng(1))
    variacion = lambda g: float(np.mean(np.abs(np.diff(g))))  # noqa: E731
    assert variacion(rapido) > 20 * variacion(lento)


# ── Doppler ─────────────────────────────────────────────────────────────────

def test_doppler_constante_y_con_deriva():
    n = 7680
    tono = rf.apply_doppler(np.ones(n, dtype=complex), 100.0, rf.SAMPLE_RATE, 50.0)
    fase = np.unwrap(np.angle(tono))
    f_inst = np.diff(fase) * rf.SAMPLE_RATE / (2 * np.pi)
    t = (np.arange(n - 1) + 0.5) / rf.SAMPLE_RATE
    assert np.allclose(f_inst, 100.0 + 50.0 * t, atol=1e-6)


def test_compensar_el_doppler_exacto_deja_la_senal_intacta():
    x = RNG.standard_normal(1000) + 1j * RNG.standard_normal(1000)
    y = rf.compensate_doppler(rf.apply_doppler(x, 9800.0, rf.SAMPLE_RATE), 9800.0, rf.SAMPLE_RATE)
    assert np.allclose(x, y)


# ── Referencia AWGN ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("ebn0", [2.0, 4.0, 6.0])
def test_ber_awgn_con_sincronizacion_ideal_coincide_con_la_teoria(ebn0):
    bits = np.random.default_rng(7).integers(0, 2, 60_000, dtype=np.uint8)
    pulse = rf.rrc_pulse(rf.RRC_ROLLOFF, rf.RRC_TAPS, rf.SAMPLES_PER_SYMBOL)
    rx = rf.canal_enlace(rf.modulate_bpsk_rrc(bits, pulse), ebn0, 1.0, False, 0.0, 0.0,
                         (11, int(ebn0)), (0,), desfase_muestras=0.0)
    errores, _ = rf.bit_error_rate(bits, rf.demodulate_bpsk_rrc(rx, pulse))
    inf, sup = rf.intervalo_wilson(errores, len(bits), z=3.3)   # ~99.9 %
    teoria = 0.5 * math.erfc(math.sqrt(10 ** (ebn0 / 10)))
    assert inf <= teoria <= sup


# ── Reproducibilidad y comparacion pareada ──────────────────────────────────

def test_misma_semilla_mismo_resultado():
    assert rf.simular_corrida(_tarea("rrc")) == rf.simular_corrida(_tarea("rrc"))


def test_otro_ensayo_otra_realizacion_de_ruido():
    a = rf.simular_corrida(_tarea("rrc", ebn0=3.0, ensayo=0))
    b = rf.simular_corrida(_tarea("rrc", ebn0=3.0, ensayo=1))
    assert a["errores_bit"] != b["errores_bit"]


def test_dos_senales_ven_el_mismo_ruido_y_el_mismo_desvanecimiento():
    pulse = rf.rrc_pulse(rf.RRC_ROLLOFF, rf.RRC_TAPS, rf.SAMPLES_PER_SYMBOL)
    a = rf.modulate_bpsk_rrc(RNG.integers(0, 2, 500, dtype=np.uint8), pulse)
    b = rf.modulate_bpsk_rrc(RNG.integers(0, 2, 500, dtype=np.uint8), pulse)
    kw = dict(semilla_ruido=(5, 5), semilla_fading=(6, 6), desfase_muestras=0.0)
    pa, pb = (float(np.mean(np.abs(x) ** 2)) for x in (a, b))
    # AWGN: la misma realizacion de ruido, escalada al nivel que pide la Eb/N0
    # sobre la potencia transmitida de cada señal.
    ra = rf.canal_enlace(a, 5.0, 1.0, False, 0.0, 0.0, **kw)
    rb = rf.canal_enlace(b, 5.0, 1.0, False, 0.0, 0.0, **kw)
    assert np.allclose((ra - a) / math.sqrt(pa), (rb - b) / math.sqrt(pb))
    # Rice: ambas se multiplican por la misma ganancia de canal.
    g = rf.gen_rice_fading(len(a), rf.SAMPLE_RATE, rf.FADING_DOPPLER_SPREAD_HZ,
                           rf.RICE_K_FACTOR_DB, np.random.default_rng((6, 6)))
    fa = rf.canal_enlace(a, 5.0, 1.0, True, 0.0, 0.0, **kw)
    fb = rf.canal_enlace(b, 5.0, 1.0, True, 0.0, 0.0, **kw)
    assert np.allclose((fa - g * a) / math.sqrt(pa), (fb - g * b) / math.sqrt(pb))
    assert np.allclose(fa - g * a, ra - a)          # y el ruido no se desvanece


def test_todas_las_configuraciones_comparten_bits_y_criterio():
    claves = {(e.clave, c.clave) for e, c in rf.lista_configuraciones()}
    # Cada esquema con lazos se evalua en los dos canales: nada de comparar
    # una corrida con desvanecimiento contra otra sin el.
    for e in rf.ESQUEMAS:
        if e.sincronizacion != "ideal":
            assert (e.clave, "awgn") in claves and (e.clave, "rice") in claves


# ── Codigo convolucional ────────────────────────────────────────────────────

def test_viterbi_recupera_los_bits_sin_ruido():
    bits = RNG.integers(0, 2, 2000, dtype=np.uint8)
    cod = rf.convolutional_encode(bits)
    assert len(cod) == 2 * (len(bits) + rf.CC_K - 1)
    assert np.array_equal(rf.viterbi_decode(cod)[: len(bits)], bits)


def test_viterbi_corrige_errores_aislados():
    bits = RNG.integers(0, 2, 2000, dtype=np.uint8)
    cod = rf.convolutional_encode(bits)
    cod[::40] ^= 1                      # 2.5 % de errores, bien separados
    assert np.array_equal(rf.viterbi_decode(cod)[: len(bits)], bits)


def test_el_codigo_es_transparente_a_la_inversion():
    bits = RNG.integers(0, 2, 500, dtype=np.uint8)
    invertido = rf.viterbi_decode(rf.convolutional_encode(bits) ^ 1)[: len(bits)]
    # Salvo el transitorio inicial (el decodificador parte del estado cero).
    assert np.array_equal(invertido[rf.CC_K:], (bits ^ 1)[rf.CC_K:])


# ── AX.25 / FCS ─────────────────────────────────────────────────────────────

def test_fcs_es_crc16_x25():
    # Valor de comprobacion normalizado de CRC-16/X-25 para «123456789»: 0x906E.
    assert rf._ax25_fcs(b"123456789") == (0x906E).to_bytes(2, "little")


def _tx_ax25() -> dict:
    pulse = rf.rrc_pulse(rf.RRC_ROLLOFF, rf.RRC_TAPS, rf.SAMPLES_PER_SYMBOL)
    return rf._transmitir(_esquema("ax25"), BITS, BYTES, pulse)


def test_contadores_ax25_sin_errores():
    tx = _tx_ax25()
    r = rf._evaluar_ax25(tx, tx["usuario"])
    assert r["tramas_tx"] == math.ceil(len(BYTES) / rf.PACKET_BYTES)
    assert r["tramas_validas"] == r["tramas_tx"]
    assert r["tramas_invalidas"] == r["tramas_descartadas"] == r["tramas_error_no_detectado"] == 0


def test_un_bit_erroneo_invalida_exactamente_una_trama():
    tx = _tx_ax25()
    rx = tx["usuario"].copy()
    rx[8 * (tx["longitudes"][0] + 30)] ^= 1          # dentro de la segunda trama
    r = rf._evaluar_ax25(tx, rx)
    assert r["tramas_invalidas"] == 1
    assert r["tramas_validas"] == r["tramas_tx"] - 1


def test_trama_no_recuperada_se_cuenta_como_descartada():
    tx = _tx_ax25()
    r = rf._evaluar_ax25(tx, tx["usuario"][: 8 * tx["longitudes"][0]])
    assert r["tramas_validas"] == 1
    assert r["tramas_descartadas"] == r["tramas_tx"] - 1
    assert r["tramas_validas"] + r["tramas_invalidas"] + r["tramas_descartadas"] == r["tramas_tx"]


def test_trama_con_polaridad_invertida_es_valida():
    tx = _tx_ax25()
    assert rf._evaluar_ax25(tx, tx["usuario"] ^ 1)["tramas_validas"] == len(tx["longitudes"])


# ── Metricas y denominadores ────────────────────────────────────────────────

def test_tasa_con_denominador_cero_es_none_no_cero():
    assert rf.tasa(0, 0) is None
    assert rf.intervalo_wilson(0, 0) == (None, None)


def test_cero_errores_tiene_cota_superior_no_nula():
    inf, sup = rf.intervalo_wilson(0, 100_000)
    assert inf == 0.0
    assert sup == pytest.approx(3.84 / 100_000, rel=0.01)


def test_wilson_contiene_la_proporcion_observada():
    inf, sup = rf.intervalo_wilson(30, 1000)
    assert inf < 0.03 < sup


def test_paquetes_erroneos_y_no_recuperados():
    ref = np.zeros(64 * 8 * 4, dtype=np.uint8)
    rx = ref.copy()
    rx[5] = 1
    assert rf.errores_por_bloque(ref, rx, 64 * 8) == (4, 1, 0)
    assert rf.errores_por_bloque(ref, rx[: 64 * 8 * 3], 64 * 8) == (4, 1, 1)
    # Un paquete integro pero invertido se da por bueno (receptor diferencial).
    rx2 = ref.copy()
    rx2[64 * 8: 64 * 8 * 2] = 1
    assert rf.errores_por_bloque(ref, rx2, 64 * 8) == (4, 0, 0)


def test_ber_diferencial_es_insensible_a_un_salto_de_polaridad():
    ref = RNG.integers(0, 2, 1000, dtype=np.uint8)
    rx = ref.copy()
    rx[400:] ^= 1                                   # salto de ciclo a mitad
    assert rf.bit_error_rate(ref, rx)[0] == 600
    assert rf.errores_diferenciales(ref, rx) == (1, 999)


def test_resolver_polaridad():
    ref = RNG.integers(0, 2, 500, dtype=np.uint8)
    rx, invertido = rf.resolver_polaridad(ref, ref ^ 1)
    assert invertido and np.array_equal(rx, ref)
    rx, invertido = rf.resolver_polaridad(ref, ref.copy())
    assert not invertido


def test_el_cruce_de_umbral_no_interpola_sobre_un_cero():
    assert rf.cruce_umbral([(0, 1e-1), (3, 1e-2), (6, 1e-4)], 1e-3) == pytest.approx(4.5)
    assert rf.cruce_umbral([(0, 1e-1), (3, 0.0)], 1e-3) is None
    assert rf.cruce_umbral([(0, 1e-4), (3, 1e-5)], 1e-3) is None


def test_agregado_fer_solo_donde_hay_trama():
    configs = [(_esquema("rrc"), rf.CANALES["awgn"]), (_esquema("ax25"), rf.CANALES["awgn"])]
    resultados, _ = rf.ejecutar(BITS, BYTES, n_ensayos=2, ebn0_values=[4.0, 30.0],
                                configs=configs, procesos=1)
    por = {(r.esquema, r.ebn0_db): r for r in resultados}
    assert por[("rrc", 4.0)].fer is None and por[("rrc", 4.0)].ax25_frames_validos is None
    ax = por[("ax25", 30.0)]
    assert ax.ax25_frames_tx == 2 * math.ceil(len(BYTES) / rf.PACKET_BYTES)
    assert ax.ax25_frames_validos == ax.ax25_frames_tx and ax.fer == 0.0
    assert ax.fer_ic95_sup > 0.0
    for r in resultados:
        assert r.ber == r.errores_bit / r.bits_evaluados
        assert r.per == r.paquetes_erroneos / r.paquetes
        if r.ax25:
            assert (r.ax25_frames_validos + r.ax25_frames_invalidos
                    + r.ax25_frames_descartados) == r.ax25_frames_tx
            assert r.fer == (r.ax25_frames_invalidos + r.ax25_frames_descartados) / r.ax25_frames_tx


# ── Estimador de SNR ────────────────────────────────────────────────────────

@pytest.mark.parametrize("esn0", [3.0, 9.0, 15.0])
def test_m2m4_en_awgn(esn0):
    n = 20_000
    rng = np.random.default_rng(int(esn0))
    s = rng.choice([-1.0, 1.0], n)
    sigma = math.sqrt(10 ** (-esn0 / 10) / 2)
    y = s + sigma * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    assert snr.estimar_m2m4(y) == pytest.approx(esn0, abs=0.4)


def test_m2m4_devuelve_none_cuando_no_tiene_solucion():
    rng = np.random.default_rng(0)
    solo_ruido = rng.standard_normal(64) + 1j * rng.standard_normal(64)
    # Ruido gaussiano: M4 = 2 M2^2 en media; con pocas muestras el
    # discriminante puede ser negativo y entonces no hay estimacion.
    resultados = [snr.estimar_m2m4(np.roll(solo_ruido, k) * (1 + 0.5 * (k % 2))) for k in range(4)]
    assert all(r is None or isinstance(r, float) for r in resultados)
    assert snr.estimar_m2m4(np.array([1.0, 3.0, 0.1, 5.0, 0.2, 4.0], dtype=complex)) is None
