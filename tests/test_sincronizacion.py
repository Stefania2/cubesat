import numpy as np

import simular_enlace_rf_bpsk_avanzado as rf


def test_costas_y_gardner_recuperan_bpsk_rrc_con_desfase_y_doppler():
    bits = np.random.default_rng(20260809).integers(0, 2, 4_000, dtype=np.uint8)
    pulse = rf.rrc_pulse(rf.RRC_ROLLOFF, rf.RRC_TAPS, rf.SAMPLES_PER_SYMBOL)
    samples = rf.modulate_bpsk_rrc(bits, pulse)
    samples = rf.apply_doppler(samples, 100.0, rf.SAMPLE_RATE)
    samples = rf.fractional_delay(samples, rf.TIMING_OFFSET_SAMPLES)

    recovered = rf.demodulate_bpsk_rrc_synced(samples, pulse)
    errors, ber = rf.bit_error_rate(bits, recovered)

    assert errors == 0
    assert ber == 0.0


def test_gardner_rejects_un_factor_de_sobremuestreo_invalido():
    with np.testing.assert_raises(ValueError):
        rf.gardner_timing_recovery(np.ones(20, dtype=np.complex128), samples_per_symbol=1)
