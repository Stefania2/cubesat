"""
Simulacion del enlace ascendente (uplink) para comandos hacia el CubeSat.

Modela:
  - Potencia de transmision desde estacion terrena
  - Link budget ascendente (Tierra → satelite)
  - Modulacion BPSK para comandos a 1200 bps
  - Recepcion a bordo con antena isotropica
  - Capacidad del enlace (bps) vs elevacion
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from geometria_orbital import (
    densidad_ruido_dbm_hz,
    distancia_satelite,
    fspl_db,
    temperatura_sistema,
)


# ─── Constantes ────────────────────────────────────────────────────────────

FREQ_UPLINK_HZ = 435.0e6   # Frecuencia uplink UHF (banda de 435 MHz)
SYM_RATE_UPLINK = 1_200     # Tasa tipica para comandos (bps)

# Altura real de STRaND-1 segun su TLE (ver calcular_link_budget.py).
ORBIT_HEIGHT_KM = 775.0

# Parametros estacion terrena (TX)
P_TX_GS_DBM = 40.0          # 10 W = 40 dBm (potencia legal tipica)
G_TX_GS_DBI = 15.0          # Yagi UHF 15 dBi
L_TX_GS_DB = 2.0            # Perdida en cables TX (dB)

# Parametros satelite (RX)
G_RX_SAT_DBI = 0.0          # Monopolo UHF (isotropico)
L_RX_SAT_DB = 0.5           # Perdida en cables RX satelite (dB)
NF_RX_SAT_DB = 4.0          # Figura de ruido del receptor satelite
T_ANT_SAT_K = 290.0         # Temperatura de antena satelite (ve latierra)

# Perdidas
L_ATM_DB = 0.5
L_POL_DB = 1.0
L_POINT_DB = 1.0
L_IMPL_DB = 2.0

# Requerimiento
BER_TARGET = 1e-5
EBN0_REQ_DB = 10.0          # BPSK con FEC ligero


@dataclass(frozen=True)
class UplinkResult:
    elevacion_deg: float
    distancia_km: float
    fspl_db: float
    p_rx_sat_dbm: float
    c_n0_db_hz: float
    eb_n0_db: float
    margen_db: float
    capacidad_max_bps: float
    t_sys_k: float


def calcular_uplink(elev_deg: float) -> UplinkResult:
    dist_km = distancia_satelite(elev_deg, ORBIT_HEIGHT_KM)
    dist_m = dist_km * 1e3

    fspl = fspl_db(dist_m, FREQ_UPLINK_HZ)
    perdida_total = fspl + L_ATM_DB + L_POL_DB + L_POINT_DB

    # Potencia recibida en el satelite
    p_rx_dbm = (
        P_TX_GS_DBM
        + G_TX_GS_DBI
        - L_TX_GS_DB
        + G_RX_SAT_DBI
        - L_RX_SAT_DB
        - perdida_total
    )

    # Temperatura de ruido del satelite (incluye el ruido del cable de a bordo)
    t_sys = temperatura_sistema(T_ANT_SAT_K, L_RX_SAT_DB, NF_RX_SAT_DB)

    # Densidad espectral de ruido
    n0_dbm_hz = densidad_ruido_dbm_hz(t_sys)

    # C/N0
    c_n0_db_hz = p_rx_dbm - n0_dbm_hz

    # Eb/N0 para la tasa de comandos
    eb_n0_db = c_n0_db_hz - 10.0 * math.log10(SYM_RATE_UPLINK)

    # SNR requerida
    snr_req_db = EBN0_REQ_DB + L_IMPL_DB

    # Margen
    margen_db = eb_n0_db - snr_req_db

    # Tasa maxima sostenible con la misma calidad de enlace: la que agota el
    # margen dejando justo la Eb/N0 requerida.
    #     Rb_max = 10^((C/N0 - Eb/N0_req - L_impl) / 10)
    # La version anterior restaba 10*log10(Eb/N0_req_dB) --- tomaba el logaritmo
    # de un valor que ya estaba en dB --- y devolvia decibelios rotulados como
    # bps, de ahi que reportara ~57 bps para un enlace con 24 dB de margen.
    capacity_bps = 10.0 ** ((c_n0_db_hz - snr_req_db) / 10.0)

    return UplinkResult(
        elevacion_deg=round(elev_deg, 1),
        distancia_km=round(dist_km, 1),
        fspl_db=round(fspl, 2),
        p_rx_sat_dbm=round(p_rx_dbm, 2),
        c_n0_db_hz=round(c_n0_db_hz, 2),
        eb_n0_db=round(eb_n0_db, 2),
        margen_db=round(margen_db, 2),
        capacidad_max_bps=round(capacity_bps, 0),
        t_sys_k=round(t_sys, 1),
    )


def plot_uplink(results: list[UplinkResult], output_dir: Path) -> None:
    elevs = [r.elevacion_deg for r in results]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Enlace ascendente (uplink) — Comandos a 1200 bps", fontsize=13, fontweight="bold")

    ax = axes[0, 0]
    ax.plot(elevs, [r.p_rx_sat_dbm for r in results], "b-", linewidth=1.5)
    ax.axhline(y=-120, color="r", linestyle="--", alpha=0.5, label="Sensibilidad tipica")
    ax.set_title("Potencia recibida a bordo")
    ax.set_xlabel("Elevacion (deg)"); ax.set_ylabel("P_rx (dBm)")
    ax.grid(True, linestyle=":"); ax.legend(fontsize=8)
    ax.invert_xaxis()

    ax = axes[0, 1]
    ax.plot(elevs, [r.eb_n0_db for r in results], "m-", linewidth=1.5, label="Eb/N0 obtenida")
    ax.axhline(y=EBN0_REQ_DB + L_IMPL_DB, color="r", linestyle="--", alpha=0.5, label=f"Requerida ({EBN0_REQ_DB + L_IMPL_DB} dB)")
    ax.set_title("Relacion Eb/N0")
    ax.set_xlabel("Elevacion (deg)"); ax.set_ylabel("Eb/N0 (dB)")
    ax.grid(True, linestyle=":"); ax.legend(fontsize=8)
    ax.invert_xaxis()

    ax = axes[1, 0]
    colors = ["g" if r.margen_db >= 3 else ("orange" if r.margen_db >= 0 else "r") for r in results]
    ax.bar(elevs, [r.margen_db for r in results], color=colors, width=1.8)
    ax.axhline(y=3, color="g", linestyle="--", alpha=0.5, label="Margen minimo (3 dB)")
    ax.set_title("Margen de enlace ascendente")
    ax.set_xlabel("Elevacion (deg)"); ax.set_ylabel("Margen (dB)")
    ax.grid(True, linestyle=":"); ax.legend(fontsize=8)
    ax.invert_xaxis()

    ax = axes[1, 1]
    ax.semilogy(elevs, [r.capacidad_max_bps for r in results], "g-", linewidth=1.5,
                label="Tasa maxima sostenible")
    ax.axhline(y=SYM_RATE_UPLINK, color="b", linestyle="--", alpha=0.5, label=f"Tasa requerida ({SYM_RATE_UPLINK} bps)")
    ax.set_title("Tasa maxima con la Eb/N0 requerida")
    ax.set_xlabel("Elevacion (deg)"); ax.set_ylabel("Tasa (bps)")
    ax.grid(True, which="both", linestyle=":"); ax.legend(fontsize=8)
    ax.invert_xaxis()

    plt.tight_layout()
    plt.savefig(output_dir / "enlace_ascendente_resultados.png", dpi=180)
    plt.close()


def main() -> None:
    output_dir = Path("resultados_simulacion")
    output_dir.mkdir(exist_ok=True)

    print("=" * 80)
    print("SIMULACION DE ENLACE ASCENDENTE (UPLINK)")
    print("=" * 80)
    print(f"Frecuencia uplink: {FREQ_UPLINK_HZ / 1e6:.1f} MHz")
    print(f"Potencia TX (GS):  {P_TX_GS_DBM:.0f} dBm ({10 ** ((P_TX_GS_DBM - 30) / 10):.1f} W)")
    print(f"Antena TX (GS):    Yagi {G_TX_GS_DBI} dBi")
    print(f"Antena RX (SAT):   Monopolo {G_RX_SAT_DBI} dBi")
    print(f"Tasa de comandos:  {SYM_RATE_UPLINK} bps")
    print(f"Requerido Eb/N0:   {EBN0_REQ_DB} dB (BER < {BER_TARGET})")

    elevaciones = list(range(5, 91, 5))
    results = [calcular_uplink(el) for el in elevaciones]

    # Exportar
    with (output_dir / "enlace_ascendente_resultados.json").open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)

    plot_uplink(results, output_dir)

    # Tabla
    print(f"\n{'Elev':>5} {'Dist':>7} {'FSPL':>7} {'P_rx':>8} {'C/N0':>8} {'Eb/N0':>7} {'Margen':>7} {'Capmax':>8}")
    print(f"{'(deg)':>5} {'(km)':>7} {'(dB)':>7} {'(dBm)':>8} {'(dB-Hz)':>8} {'(dB)':>7} {'(dB)':>7} {'(bps)':>8}")
    print("-" * 63)
    for r in results:
        print(f"{r.elevacion_deg:>5.1f} {r.distancia_km:>7.1f} {r.fspl_db:>7.2f} "
              f"{r.p_rx_sat_dbm:>8.2f} {r.c_n0_db_hz:>8.2f} {r.eb_n0_db:>7.2f} "
              f"{r.margen_db:>7.2f} {r.capacidad_max_bps:>8.0f}")

    margenes = [r.margen_db for r in results]
    print(f"\nResumen uplink:")
    print(f"  Margen minimo:   {min(margenes):.2f} dB")
    print(f"  Margen maximo:   {max(margenes):.2f} dB")
    print(f"  Margen promedio: {sum(margenes) / len(margenes):.2f} dB")

    print(f"\nArchivos generados en {output_dir.resolve()}/")
    print(f"  - enlace_ascendente_resultados.json")
    print(f"  - enlace_ascendente_resultados.png")


if __name__ == "__main__":
    main()
