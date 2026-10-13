"""Replica en NumPy de la cadena GNU Radio `cadena_strand1_awgn.py`.

Existe para que la pagina «Enlace RF» pueda simular donde no hay GNU Radio
instalado (un despliegue sin servidor, por ejemplo). No sustituye a la cadena
GNU Radio: la reproduce bloque a bloque, y `tests/test_cadena_numpy.py`
comprueba la equivalencia contra GNU Radio cuando esta disponible:

    bits -> +11 simbolos de cola -> {0,1} a {-1,+1}
         -> interpolacion x8 con RRC (firdes.root_raised_cosine, 89 coeficientes)
         -> + ruido gaussiano complejo
         -> parte real -> filtro adaptado RRC -> muestreo en 88 + 8n -> decisor

Lo que coincide exactamente con GNU Radio: los coeficientes del filtro, la
señal transmitida y el demodulador (los mismos bits sobre las mismas muestras).
Lo que no puede coincidir muestra a muestra: la realizacion del ruido, porque
el generador aleatorio es otro. Su nivel si es el mismo, de modo que la BER
coincide estadisticamente, no bit a bit.
"""

from __future__ import annotations

import math

import numpy as np

SP = 8                  # muestras por simbolo
SYM = 9600              # simbolos por segundo
ALPHA = 0.35
NTAPS = 8 * 11 + 1      # 89 coeficientes
COLA = (NTAPS - 1) // SP
# Constantes de calibracion de la cadena GNU Radio, sin cambios: fijan la
# amplitud del ruido para que `snr_db` sea Eb/N0.
A = 8.00011
KAPPA = 1.98733
RETARDO = NTAPS - 1     # retardo conjunto de los dos filtros, en muestras


def rrc_firdes(ganancia: float, muestras_por_simbolo: float, alpha: float, ntaps: int) -> np.ndarray:
    """Coeficientes de `gnuradio.filter.firdes.root_raised_cosine`.

    Transcripcion de la formula de GNU Radio, normalizada para que la suma de
    los coeficientes valga `ganancia`.
    """
    ntaps |= 1
    spb = muestras_por_simbolo
    taps = np.zeros(ntaps)
    centro = ntaps // 2
    for i in range(ntaps):
        x = i - centro
        x1 = math.pi * x / spb
        x2 = 4.0 * alpha * x / spb
        x3 = x2 * x2 - 1.0
        if abs(x3) >= 1e-6:
            if i != centro:
                num = math.cos((1 + alpha) * x1) + math.sin((1 - alpha) * x1) / (4 * alpha * x / spb)
            else:
                num = math.cos((1 + alpha) * x1) + (1 - alpha) * math.pi / (4 * alpha)
            den = x3 * math.pi
        else:
            x3 = (1 - alpha) * x1
            x2 = (1 + alpha) * x1
            num = (math.sin(x2) * (1 + alpha) * math.pi
                   - math.cos(x3) * ((1 - alpha) * math.pi * spb) / (4 * alpha * x)
                   + math.sin(x3) * spb * spb / (4 * alpha * x * x))
            den = -32 * math.pi * alpha * alpha * x / spb
        taps[i] = 4 * alpha * num / den
    return taps * ganancia / taps.sum()


TAPS = rrc_firdes(SP, SP, ALPHA, NTAPS)


def transmitir(bits: np.ndarray) -> np.ndarray:
    """Señal en banda base a la salida del filtro de transmision (real)."""
    simbolos = np.concatenate([bits.astype(np.float64) * 2.0 - 1.0, -np.ones(COLA)])
    sobremuestreada = np.zeros(len(simbolos) * SP)
    sobremuestreada[::SP] = simbolos
    return np.convolve(sobremuestreada, TAPS)[: len(sobremuestreada)]


def amplitud_ruido(ebn0_db: float) -> float:
    """Amplitud `v` que la cadena GNU Radio pasa a `noise_source_c`."""
    return A / (KAPPA * math.sqrt(2.0 * 10.0 ** (ebn0_db / 10.0)))


def canal(limpia: np.ndarray, ebn0_db: float, semilla: int) -> np.ndarray:
    """Suma ruido gaussiano complejo con el mismo nivel que GNU Radio.

    `noise_source_c` reparte la amplitud entre las dos cuadraturas: cada una
    tiene desviacion tipica v/sqrt(2). Medido sobre el tap IQ de la cadena real.
    """
    rng = np.random.default_rng(semilla)
    sigma = amplitud_ruido(ebn0_db) / math.sqrt(2.0)
    ruido = sigma * (rng.standard_normal(len(limpia)) + 1j * rng.standard_normal(len(limpia)))
    return (limpia + ruido).astype(np.complex64)


def demodular(iq: np.ndarray, n_bits: int) -> np.ndarray:
    """Filtro adaptado, muestreo en el instante de simbolo y decisor."""
    filtrada = np.convolve(iq.real.astype(np.float64), TAPS)[: len(iq)]
    return (filtrada[RETARDO::SP][:n_bits] >= 0.0).astype(np.uint8)


def simular(bits: np.ndarray, ebn0_db: float, semilla: int) -> tuple[np.ndarray, np.ndarray]:
    """Cadena completa. Devuelve (bits recuperados, tap IQ del canal)."""
    iq = canal(transmitir(bits), ebn0_db, semilla)
    return demodular(iq, len(bits)), iq
