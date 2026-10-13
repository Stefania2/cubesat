#!/usr/bin/env python3
"""Estimacion de SNR a partir de las muestras IQ, contrastada con la SNR conocida.

Fijar la SNR de una simulacion no es estimarla. Este script estima Es/N0 desde
la señal recibida, sin conocer los bits, y la compara con el valor impuesto
para medir sesgo y dispersion del estimador.

Metodo: M2M4 (momentos de segundo y cuarto orden; Pauluzzi y Beaulieu, 2000)
sobre la salida del filtro adaptado muestreada a tasa de simbolo.

    M2 = E{|y|²} = S + N            M4 = E{|y|⁴}
    S  = sqrt(2·M2² − M4)           N  = M2 − S         (BPSK, ruido complejo)

Supuestos, y que ocurre cuando no se cumplen:
  - Simbolos BPSK de amplitud constante: con desvanecimiento la amplitud varia
    dentro de la ventana y el estimador se sesga a la baja (lo interpreta como
    ruido). Por eso se evalua tambien en el canal Rice.
  - Ruido gaussiano complejo circular y blanco a la salida del filtro adaptado.
  - Muestreo en el instante de simbolo: un error de reloj mete interferencia
    entre simbolos, que el estimador cuenta como ruido. Se evalua con reloj
    ideal y con el recuperado por Gardner.
  - No necesita fase de portadora (usa |y|), asi que tolera Doppler residual
    pequeño frente a la tasa de simbolo.

Alcance: el IQ es **sintetico**. El resultado caracteriza al estimador, no al
canal real de STRaND-1. Aplicarlo a una captura de SDR exigira ademas conocer
la respuesta del receptor.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import simular_enlace_rf_bpsk_avanzado as rf

OUTPUT_DIR = Path("resultados_simulacion")
SEMILLA = 20261014
ESN0_DB_VALUES = [0.0, 3.0, 6.0, 9.0, 12.0, 15.0]
VENTANAS = [64, 256, 1024, 4096]
N_SIMBOLOS = 65_536


def estimar_m2m4(simbolos: np.ndarray) -> float | None:
    """Es/N0 (dB) por M2M4, o None si la estimacion no es valida.

    Con pocos simbolos o SNR muy baja, 2·M2² − M4 puede salir negativo (o N
    no positivo): el metodo no tiene solucion real y se informa como tal en
    lugar de devolver un numero.
    """
    p = np.abs(simbolos) ** 2
    m2, m4 = float(p.mean()), float((p ** 2).mean())
    disc = 2.0 * m2 * m2 - m4
    if disc <= 0.0:
        return None
    s = math.sqrt(disc)
    n = m2 - s
    if n <= 0.0:
        return None
    return 10.0 * math.log10(s / n)


def simbolos_recibidos(esn0_db: float, fading: bool, reloj: str,
                       rng: np.random.Generator) -> np.ndarray:
    """Salida del filtro adaptado a tasa de simbolo, sin usar los bits."""
    bits = rng.integers(0, 2, N_SIMBOLOS, dtype=np.uint8)
    pulse = rf.rrc_pulse(rf.RRC_ROLLOFF, rf.RRC_TAPS, rf.SAMPLES_PER_SYMBOL)
    clean = rf.modulate_bpsk_rrc(bits, pulse)
    semilla = tuple(int(x) for x in rng.integers(0, 2 ** 31, 3))
    rx = rf.canal_enlace(clean, esn0_db, 1.0, fading, 0.0, 0.0,
                         semilla_ruido=semilla, semilla_fading=semilla[::-1],
                         desfase_muestras=rf.TIMING_OFFSET_SAMPLES if reloj == "gardner" else 0.0)
    matched = np.convolve(rx, pulse[::-1], mode="same")
    if reloj == "gardner":
        return rf.gardner_timing_recovery(matched)
    return matched[:: rf.SAMPLES_PER_SYMBOL]


def evaluar() -> list[dict]:
    rng = np.random.default_rng(SEMILLA)
    filas = []
    for canal, fading in (("awgn", False), ("rice", True)):
        for reloj in ("ideal", "gardner"):
            for esn0 in ESN0_DB_VALUES:
                y = simbolos_recibidos(esn0, fading, reloj, rng)
                for ventana in VENTANAS:
                    bloques = [y[i:i + ventana] for i in range(0, len(y) - ventana + 1, ventana)]
                    est = [estimar_m2m4(b) for b in bloques]
                    validas = np.array([e for e in est if e is not None])
                    fila = {
                        "canal": canal, "reloj": reloj, "esn0_real_db": esn0,
                        "ventana_simbolos": ventana, "ventanas": len(bloques),
                        "ventanas_validas": int(len(validas)),
                    }
                    if len(validas):
                        err = validas - esn0
                        fila.update(
                            esn0_estimada_media_db=round(float(validas.mean()), 3),
                            sesgo_db=round(float(err.mean()), 3),
                            desviacion_db=round(float(validas.std(ddof=1)), 3) if len(validas) > 1 else None,
                            rmse_db=round(float(np.sqrt(np.mean(err ** 2))), 3),
                        )
                    else:
                        fila.update(esn0_estimada_media_db=None, sesgo_db=None,
                                    desviacion_db=None, rmse_db=None)
                    filas.append(fila)
    return filas


def graficar(filas: list[dict]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    fig.suptitle("Estimador M2M4 de Es/N0 sobre IQ sintetico: sesgo y dispersion",
                 fontsize=12, fontweight="bold")
    for ax, metrica, titulo in ((axes[0], "sesgo_db", "Sesgo (estimada − real)"),
                                (axes[1], "desviacion_db", "Desviacion tipica entre ventanas")):
        for canal, reloj, estilo in (("awgn", "ideal", "-"), ("awgn", "gardner", "--"),
                                     ("rice", "ideal", ":")):
            for ventana in (64, 1024):
                pts = [f for f in filas if f["canal"] == canal and f["reloj"] == reloj
                       and f["ventana_simbolos"] == ventana and f[metrica] is not None]
                ax.plot([p["esn0_real_db"] for p in pts], [p[metrica] for p in pts],
                        estilo, marker="o", ms=3,
                        label=f"{canal}, reloj {reloj}, {ventana} simb.")
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xlabel("Es/N0 real (dB)")
        ax.set_ylabel("dB")
        ax.set_title(titulo)
        ax.grid(True, linestyle=":")
        ax.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "estimacion_snr_iq.png", dpi=160)
    plt.close()


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    filas = evaluar()
    salida = {
        "tipo_de_dato": "simulado: caracteriza al estimador sobre IQ sintetico, no al canal real",
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": rf._commit(),
        "metodo": "M2M4 sobre la salida del filtro adaptado RRC a tasa de simbolo",
        "magnitud": "Es/N0 (= Eb/N0 en BPSK sin codificar)",
        "semilla": SEMILLA,
        "simbolos_por_punto": N_SIMBOLOS,
        "ventanas_simbolos": VENTANAS,
        "canal_rice": {"k_db": rf.RICE_K_FACTOR_DB,
                       "dispersion_doppler_hz": rf.FADING_DOPPLER_SPREAD_HZ},
        "resultados": filas,
    }
    (OUTPUT_DIR / "estimacion_snr_iq.json").write_text(
        json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    graficar(filas)

    print("Estimador M2M4 de Es/N0 (IQ sintetico)")
    print(f"{'canal':>5} {'reloj':>8} {'real':>5} {'vent':>5} {'validas':>9} {'media':>7} {'sesgo':>7} {'desv':>6}")
    for f in filas:
        if f["ventana_simbolos"] not in (64, 1024):
            continue
        def n(v): return "N/A" if v is None else f"{v:.2f}"
        print(f"{f['canal']:>5} {f['reloj']:>8} {f['esn0_real_db']:>5.1f} {f['ventana_simbolos']:>5} "
              f"{f['ventanas_validas']:>4}/{f['ventanas']:<4} {n(f['esn0_estimada_media_db']):>7} "
              f"{n(f['sesgo_db']):>7} {n(f['desviacion_db']):>6}")
    print("Salidas: resultados_simulacion/estimacion_snr_iq.json, estimacion_snr_iq.png")


if __name__ == "__main__":
    main()
