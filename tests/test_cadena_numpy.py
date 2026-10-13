"""La replica en NumPy de la cadena GNU Radio, contrastada con la original."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from telemetria_strand1.backend.app.services import cadena_numpy as cn

RAIZ = Path(__file__).resolve().parents[1]
TX = np.fromfile(RAIZ / "frames_STRAND1_bits.bin", dtype=np.uint8)


def test_sin_ruido_recupera_los_18776_bits():
    rx, iq = cn.simular(TX, 60.0, 11)
    assert len(rx) == len(TX) == 18_776
    assert np.array_equal(rx, TX)
    assert len(iq) == (len(TX) + cn.COLA) * cn.SP


def test_los_coeficientes_suman_la_ganancia_y_son_simetricos():
    assert len(cn.TAPS) == 89
    assert cn.TAPS.sum() == pytest.approx(cn.SP)
    assert np.allclose(cn.TAPS, cn.TAPS[::-1])


def test_misma_semilla_mismo_resultado():
    a, _ = cn.simular(TX, 5.0, 11)
    b, _ = cn.simular(TX, 5.0, 11)
    c, _ = cn.simular(TX, 5.0, 12)
    assert np.array_equal(a, b) and not np.array_equal(a, c)


@pytest.mark.parametrize("ebn0", [2.0, 4.0, 6.0])
def test_la_ber_sigue_la_teoria_de_bpsk(ebn0):
    errores = sum(int(np.count_nonzero(cn.simular(TX, ebn0, s)[0] != TX)) for s in range(4))
    n = 4 * len(TX)
    teoria = 0.5 * math.erfc(math.sqrt(10 ** (ebn0 / 10)))
    sigma = math.sqrt(teoria * (1 - teoria) / n)
    assert abs(errores / n - teoria) < 4 * sigma


def test_nivel_de_ruido_igual_al_de_gnuradio():
    limpia = cn.transmitir(TX)
    ruido = cn.canal(limpia, 6.0, 3) - limpia
    # noise_source_c reparte la amplitud v entre las dos cuadraturas.
    assert ruido.real.std() == pytest.approx(cn.amplitud_ruido(6.0) / math.sqrt(2), rel=0.02)
    assert ruido.imag.std() == pytest.approx(ruido.real.std(), rel=0.03)


def test_equivalencia_con_la_cadena_gnuradio(tmp_path):
    pytest.importorskip("gnuradio", reason="GNU Radio no esta instalado en este entorno")
    from gnuradio.filter import firdes

    ref = np.array(firdes.root_raised_cosine(cn.SP, cn.SP * cn.SYM, cn.SYM, cn.ALPHA, cn.NTAPS))
    assert np.abs(cn.TAPS - ref).max() < 1e-6

    rx_gr, iq_gr = tmp_path / "rx.bin", tmp_path / "iq.c64"
    subprocess.run([sys.executable, str(RAIZ / "cadena_strand1_awgn.py"), "--snr-db", "6",
                    "--seed", "11", "--output", str(rx_gr), "--iq-output", str(iq_gr)],
                   check=True, capture_output=True, cwd=RAIZ)
    iq = np.fromfile(iq_gr, dtype=np.complex64)
    bits_gr = np.fromfile(rx_gr, dtype=np.uint8)

    # Misma señal transmitida: lo que GNU Radio saca menos la señal limpia de
    # NumPy es solo ruido, con el nivel previsto.
    ruido = iq - cn.transmitir(TX)[: len(iq)]
    assert ruido.real.std() == pytest.approx(cn.amplitud_ruido(6.0) / math.sqrt(2), rel=0.02)
    # Mismo demodulador: sobre las muestras de GNU Radio, los mismos bits.
    assert np.array_equal(cn.demodular(iq, len(TX)), bits_gr)
