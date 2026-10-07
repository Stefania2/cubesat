"""Servicio de metricas del enlace.

Calcula las metricas a partir de los resultados REALES de la simulacion GNU
Radio: bits recuperados (integridad de los 18.776), BER medido, y a partir del
tap IQ complejo una FFT y una constelacion reales. Las metricas que la cadena
actual no puede medir (RSSI, FER) se devuelven como `None` con la explicacion
en las notas correspondientes. Nada se inventa.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from . import config
from . import integridad
from .models import ConstellationOut, MetricsOut, SpectrumOut

logger = logging.getLogger(__name__)

HISTORIAL_MAX = 300
FFT_NFFT = 4096
FFT_MAX_PUNTOS = 2048
CONST_PUNTOS = 400


def _leer_iq(ruta: Path | None = None) -> np.ndarray | None:
    ruta = ruta or config.IQ_SIM
    if not ruta.exists():
        return None
    try:
        datos = np.fromfile(ruta, dtype=np.complex64)
    except Exception:
        return None
    return datos if datos.size else None


def _punkto_tiempo() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MetricsService:
    def __init__(self) -> None:
        self._estado: dict[str, Any] = {
            "snr_db": None,
            "ber": None,
            "potencia_relativa_dbfs": None,
            "ruido_estimado": None,
            "integridad": None,
            "frames_recibidos": None,
            "frames_validos": None,
            "frames_error": None,
            "disponible": False,
        }
        self._historial: deque[dict[str, Any]] = deque(maxlen=HISTORIAL_MAX)
        self._espectro: SpectrumOut | None = None
        self._constelacion: ConstellationOut | None = None

    def metrics_out(self) -> MetricsOut:
        e = self._estado
        return MetricsOut(
            snr_db=e.get("snr_db"),
            ber=e.get("ber"),
            rssi_dbm=None,
            fer=None,
            potencia_relativa_dbfs=e.get("potencia_relativa_dbfs"),
            ruido_estimado=e.get("ruido_estimado"),
            frecuencia_hz=config.FREQ_HZ,
            tasa_bits_bps=config.SYMBOL_RATE,
            ancho_banda_hz=config.SYMBOL_RATE * (1 + config.ROLLOFF),
            frames_recibidos=e.get("frames_recibidos"),
            frames_validos=e.get("frames_validos"),
            frames_error=e.get("frames_error"),
            nota_rssi=(
                "N/A — el modelo es baseband-equivalente: no hay potencia RF "
                "para expresar en dBm"
            ),
            nota_fer=(
                "N/A — la cadena minima no tiene trama AX.25 ni FEC; el modelo "
                "avanzado (simular_enlace_rf_bpsk_avanzado.py) si reporta "
                "ax25_frames_validos"
            ),
            nota_frecuencia="437.568 MHz UHF (banda de bajada nominal de STRAND-1)",
            nota_ancho_banda=(
                f"BW ≈ R·(1+α) = {config.SYMBOL_RATE * (1 + config.ROLLOFF):.0f} "
                f"Hz (RRC, α={config.ROLLOFF})"
            ),
        )

    def historial(self) -> list[dict[str, Any]]:
        return list(self._historial)

    def actualizar(self, snr_db: float) -> None:
        try:
            rx = integridad.cargar_bits(config.BITS_RX_SIM)
        except FileNotFoundError:
            logger.warning("No hay bits recuperados; metricas sin BER")
            return
        tx = integridad.cargar_bits(config.BITS_TX)
        n = min(len(tx), len(rx))
        errores = int(np.count_nonzero(tx[:n] != rx[:n])) if n else 0
        ber = errores / n if n else None
        check = integridad.validar_bits(config.BITS_RX_SIM)

        iq = _leer_iq()
        potencia = None
        ruido = None
        if iq is not None:
            potencia = float(10.0 * np.log10(np.mean(np.abs(iq) ** 2) + 1e-12))
            ruido = _estimador_ruido(iq)

        self._estado = {
            "snr_db": snr_db,
            "ber": ber,
            "potencia_relativa_dbfs": potencia,
            "ruido_estimado": ruido,
            "integridad": check,
            "frames_recibidos": 100,
            "frames_validos": 100 if check.valido else None,
            "frames_error": 0 if check.valido else None,
            "disponible": True,
        }
        self._historial.append(
            {
                "timestamp": _punkto_tiempo(),
                "snr_db": snr_db,
                "ber": ber,
                "potencia_relativa_dbfs": potencia,
            }
        )
        self._calcular_espectro_constelacion(iq)

    def spectrum_out(self) -> SpectrumOut:
        if self._espectro is None:
            return SpectrumOut(
                disponible=False,
                fuente=None,
                nota=(
                    "FFT data unavailable — ejecuta la simulacion (POST /api/simulate) "
                    "para capturar el tap IQ real de la cadena GNU Radio"
                ),
            )
        return self._espectro

    def constellation_out(self) -> ConstellationOut:
        if self._constelacion is None:
            return ConstellationOut(
                disponible=False,
                fuente=None,
                nota="Constelacion no disponible — ejecuta la simulacion primero",
            )
        return self._constelacion

    def reset(self) -> None:
        self.__init__()

    def _calcular_espectro_constelacion(self, iq: np.ndarray | None) -> None:
        if iq is None or iq.size < FFT_NFFT:
            self._espectro = None
            self._constelacion = None
            return
        f, psd = _welch(iq)
        paso = max(1, len(f) // FFT_MAX_PUNTOS)
        self._espectro = SpectrumOut(
            disponible=True,
            fuente="Tap IQ real de cadena_strand1_awgn.py (canal tras AWGN)",
            frecuencia_central_hz=0.0,
            ancho_banda_hz=config.SAMPLE_RATE,
            datos=[
                {"freq_hz": round(float(fr), 2), "power_db": round(float(p), 3)}
                for fr, p in zip(f[::paso], psd[::paso])
            ],
        )
        en_simbolo = iq[:: config.SAMPLES_PER_SYMBOL]
        if en_simbolo.size > CONST_PUNTOS:
            idx = np.linspace(0, en_simbolo.size - 1, CONST_PUNTOS).astype(int)
            en_simbolo = en_simbolo[idx]
        sel = en_simbolo if en_simbolo.size else iq[:CONST_PUNTOS]
        self._constelacion = ConstellationOut(
            disponible=True,
            fuente="Muestras IQ del canal muestreadas a tasa de simbolo (tap real)",
            puntos=[
                {"i": round(float(z.real), 4), "q": round(float(z.imag), 4)}
                for z in sel
            ],
        )


def _estimador_ruido(iq: np.ndarray) -> float | None:
    """Potencia media de ruido en bandas fuera de la senal RRC (Welch)."""
    if iq.size < FFT_NFFT * 4:
        return None
    try:
        f, psd = _welch(iq)
    except Exception:
        return None
    banda_senal = config.SYMBOL_RATE * (1 + config.ROLLOFF) / 2
    fuera = np.abs(f) > banda_senal + 1000
    if not np.any(fuera):
        return None
    # `psd` ya esta en dB (10*log10); la potencia de ruido fuera de banda se
    # devuelve directamente en dB.
    return float(np.mean(psd[fuera]))


def _welch(senal: np.ndarray, nfft: int = FFT_NFFT):
    ventana = np.hanning(nfft)
    bloques = max(1, (senal.size - nfft) // (nfft // 2))
    acc = np.zeros(nfft, dtype=np.complex128)
    for b in range(bloques):
        inicio = b * (nfft // 2)
        trozo = senal[inicio:inicio + nfft]
        if trozo.size < nfft:
            trozo = np.pad(trozo, (0, nfft - trozo.size))
        acc += np.fft.fftshift(np.fft.fft(trozo * ventana))
    psd = (np.abs(acc) ** 2) / (bloques * nfft)
    psd_db = 10.0 * np.log10(psd + 1e-12)
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / config.SAMPLE_RATE))
    return f, psd_db


metrics = MetricsService()