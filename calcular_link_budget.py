"""
Calculo de link budget (margen de enlace) para el enlace RF del CubeSat STRaND-1.

Modela el balance de potencias del enlace descendente UHF considerando:
  - Potencia transmitida, ganancia de antenas, perdidas en cables
  - Perdida de trayectoria en espacio libre (FSPL)
  - Perdidas atmosfericas, de polarizacion y apuntamiento
  - Figura de ruido del receptor, temperatura de ruido del sistema
  - Relacion Eb/N0 requerida para BPSK con BER objetivo
  - Margen de enlace resultante

Referencias:
  - Larson & Wertz, Space Mission Analysis and Design (SMAD)
  - Maral & Bousquet, Satellite Communications Systems
  - CubeSat Design Specification (CDS) Rev. 14
  - Datos reales de telemetria STRaND-1 (NORAD 39090)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import json
import math

import matplotlib.pyplot as plt
import numpy as np

from geometria_orbital import (
    C_LIGHT,
    EARTH_RADIUS_KM,
    K_BOLTZ,
    densidad_ruido_dbm_hz,
    distancia_satelite,
    fspl_db,
    temperatura_sistema,
)


# ─── Parametros del satelite ────────────────────────────────────────────

FREQ_HZ = 437.568e6        # Frecuencia UHF del STRaND-1 (Hz)
SYM_RATE = 9_600            # Tasa de simbolos (baudios)
MODULATION = "BPSK"         # Esquema de modulacion
ORBIT_HEIGHT_KM = 600.0     # Altura orbital tipica (km)

# Parametros del transmisor (CubeSat)
P_TX_DBM = 30.0             # Potencia transmitida: 1 W = 30 dBm
G_TX_DBI = 0.0              # Ganancia antena transmisora (monopolo UHF)
L_TX_DB = 0.5               # Perdida en cableado del satelite (dB)

# Parametros del receptor (estacion terrestre)
G_RX_DBI = 15.0             # Ganancia antena receptora (Yagi UHF de 11-13 el)
L_RX_DB = 2.0               # Perdida en cableado estacion terrena (dB)
NF_RX_DB = 2.0              # Figura de ruido del receptor (dB)
T_ANT_K = 150.0             # Temperatura de ruido de antena (K)

# Perdidas adicionales
L_ATM_DB = 0.5              # Perdida atmosferica (dB)
L_POL_DB = 1.0              # Perdida por desajuste de polarizacion (dB)
L_POINT_DB = 1.0            # Perdida por apuntamiento (dB)
L_IMPL_DB = 2.0             # Perdida de implementacion del modem (dB)

# Requerimientos del enlace
BER_TARGET = 1e-5           # Tasa de error de bit objetivo
EBN0_REQ_DB = 10.0          # Eb/N0 requerida para BPSK con BER ~1e-5


@dataclass(frozen=True)
class LinkBudgetParams:
    """Parametros fijos del enlace."""
    frecuencia_hz: float
    modulation: str
    symbol_rate_bps: int
    p_tx_dbm: float
    g_tx_dbi: float
    l_tx_db: float
    g_rx_dbi: float
    l_rx_db: float
    nf_rx_db: float
    t_ant_k: float
    l_atm_db: float
    l_pol_db: float
    l_point_db: float
    l_impl_db: float
    eb_n0_req_db: float
    ber_target: float
    orbit_height_km: float


@dataclass(frozen=True)
class LinkBudgetResult:
    """Resultado del calculo para una elevacion dada."""
    elevacion_deg: float
    distancia_km: float
    fspl_db: float
    p_rx_dbm: float
    c_n0_db_hz: float
    eb_n0_db: float
    margen_db: float
    snr_requerida_db: float
    perdida_total_db: float
    t_sys_k: float


# ─── Funciones auxiliares ───────────────────────────────────────────────

def dbm_to_watt(dbm: float) -> float:
    return 10.0 ** (dbm / 10.0) * 1e-3


def watt_to_dbm(watt: float) -> float:
    return 10.0 * math.log10(watt * 1e3)


def calcular_link_budget(
    elev_deg: float,
    params: LinkBudgetParams,
) -> LinkBudgetResult:
    """Calcula el link budget para una elevacion dada."""
    # Distancia oblicua
    dist_km = distancia_satelite(elev_deg, params.orbit_height_km)
    dist_m = dist_km * 1e3

    # Free Space Path Loss
    fspl = fspl_db(dist_m, params.frecuencia_hz)

    # Perdidas totales (suma de todas las perdidas)
    perdida_total = fspl + params.l_atm_db + params.l_pol_db + params.l_point_db

    # Potencia recibida (dBm)
    p_rx_dbm = (
        params.p_tx_dbm
        + params.g_tx_dbi
        - params.l_tx_db
        + params.g_rx_dbi
        - params.l_rx_db
        - perdida_total
    )

    # Temperatura de ruido del sistema referida a la entrada del receptor,
    # incluyendo el ruido que aportan los cables entre la antena y el LNA.
    t_sys = temperatura_sistema(params.t_ant_k, params.l_rx_db, params.nf_rx_db)

    # Densidad espectral de ruido (dBm/Hz)
    n0_dbm_hz = densidad_ruido_dbm_hz(t_sys)

    # C/N0 (dB-Hz)
    c_n0_db_hz = p_rx_dbm - n0_dbm_hz

    # Eb/N0 (dB)
    eb_n0_db = c_n0_db_hz - 10.0 * math.log10(params.symbol_rate_bps)

    # SNR requerida (dB) teniendo en cuenta perdidas de implementacion
    snr_req_db = params.eb_n0_req_db + params.l_impl_db

    # Margen de enlace
    margen_db = eb_n0_db - snr_req_db

    return LinkBudgetResult(
        elevacion_deg=round(elev_deg, 1),
        distancia_km=round(dist_km, 1),
        fspl_db=round(fspl, 2),
        p_rx_dbm=round(p_rx_dbm, 2),
        c_n0_db_hz=round(c_n0_db_hz, 2),
        eb_n0_db=round(eb_n0_db, 2),
        margen_db=round(margen_db, 2),
        snr_requerida_db=round(snr_req_db, 2),
        perdida_total_db=round(perdida_total, 2),
        t_sys_k=round(t_sys, 1),
    )


def resumen_link_budget(resultados: list[LinkBudgetResult]) -> dict:
    """Genera un resumen con estadisticas del analisis."""
    margenes = [r.margen_db for r in resultados]
    return {
        "margen_maximo_db": round(max(margenes), 2),
        "margen_minimo_db": round(min(margenes), 2),
        "margen_promedio_db": round(sum(margenes) / len(margenes), 2),
        "elevacion_margen_minimo_deg": resultados[margenes.index(min(margenes))].elevacion_deg,
        "elevacion_margen_maximo_deg": resultados[margenes.index(max(margenes))].elevacion_deg,
        "peor_caso_p_rx_dbm": min(r.p_rx_dbm for r in resultados),
        "peor_caso_fspl_db": max(r.fspl_db for r in resultados),
    }


def graficar_resultados(
    resultados: list[LinkBudgetResult],
    output_dir: Path,
) -> None:
    """Genera graficas del link budget."""
    elevs = [r.elevacion_deg for r in resultados]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(
        "Link Budget - Enlace descendente STRaND-1 (437.568 MHz, 9600 bps BPSK)",
        fontsize=13,
        fontweight="bold",
    )

    ax = axes[0, 0]
    ax.plot(elevs, [r.perdida_total_db for r in resultados], "b-", linewidth=1.5)
    ax.set_title("Perdida total del enlace")
    ax.set_xlabel("Elevacion (grados)")
    ax.set_ylabel("Perdida (dB)")
    ax.grid(True, linestyle=":")
    ax.invert_xaxis()

    ax = axes[0, 1]
    ax.plot(elevs, [r.p_rx_dbm for r in resultados], "g-", linewidth=1.5)
    ax.axhline(y=-120, color="r", linestyle="--", alpha=0.5, label="Sensibilidad tipica RX")
    ax.set_title("Potencia recibida")
    ax.set_xlabel("Elevacion (grados)")
    ax.set_ylabel("P_rx (dBm)")
    ax.grid(True, linestyle=":")
    ax.legend(fontsize=8)
    ax.invert_xaxis()

    snr_req = resultados[0].snr_requerida_db
    ax = axes[1, 0]
    ax.plot(elevs, [r.eb_n0_db for r in resultados], "m-", linewidth=1.5, label="Eb/N0 obtenida")
    ax.axhline(
        y=snr_req,
        color="r",
        linestyle="--",
        alpha=0.5,
        label=f"Requerida ({snr_req} dB)",
    )
    ax.set_title("Relacion Eb/N0")
    ax.set_xlabel("Elevacion (grados)")
    ax.set_ylabel("Eb/N0 (dB)")
    ax.grid(True, linestyle=":")
    ax.legend(fontsize=8)
    ax.invert_xaxis()

    ax = axes[1, 1]
    colores = ["g" if r.margen_db >= 3 else ("orange" if r.margen_db >= 0 else "r") for r in resultados]
    ax.bar(elevs, [r.margen_db for r in resultados], color=colores, width=1.8)
    ax.axhline(y=3, color="g", linestyle="--", alpha=0.5, label="Margen minimo recomendado (3 dB)")
    ax.axhline(y=0, color="r", linestyle="-", alpha=0.3)
    ax.set_title("Margen de enlace")
    ax.set_xlabel("Elevacion (grados)")
    ax.set_ylabel("Margen (dB)")
    ax.grid(True, linestyle=":")
    ax.legend(fontsize=8)
    ax.invert_xaxis()

    plt.tight_layout()
    plt.savefig(output_dir / "link_budget_margen_enlace.png", dpi=180)
    plt.close()


def exportar_csv(resultados: list[LinkBudgetResult], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(resultados[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(r) for r in resultados)


def exportar_json(params: LinkBudgetParams, resultados: list[LinkBudgetResult], resumen: dict, path: Path) -> None:
    data = {
        "parametros": asdict(params),
        "resultados": [asdict(r) for r in resultados],
        "resumen": resumen,
        "constantes": {
            "K_boltz": K_BOLTZ,
            "c_luz": C_LIGHT,
            "radio_terrestre_km": EARTH_RADIUS_KM,
        },
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main() -> None:
    output_dir = Path("resultados_simulacion")
    output_dir.mkdir(exist_ok=True)

    # Parametros fijos
    params = LinkBudgetParams(
        frecuencia_hz=FREQ_HZ,
        modulation=MODULATION,
        symbol_rate_bps=SYM_RATE,
        p_tx_dbm=P_TX_DBM,
        g_tx_dbi=G_TX_DBI,
        l_tx_db=L_TX_DB,
        g_rx_dbi=G_RX_DBI,
        l_rx_db=L_RX_DB,
        nf_rx_db=NF_RX_DB,
        t_ant_k=T_ANT_K,
        l_atm_db=L_ATM_DB,
        l_pol_db=L_POL_DB,
        l_point_db=L_POINT_DB,
        l_impl_db=L_IMPL_DB,
        eb_n0_req_db=EBN0_REQ_DB,
        ber_target=BER_TARGET,
        orbit_height_km=ORBIT_HEIGHT_KM,
    )

    # Barrido de elevacion (5 a 90 grados)
    elevaciones = list(range(5, 91, 5))

    resultados = [calcular_link_budget(el, params) for el in elevaciones]

    resumen = resumen_link_budget(resultados)

    # Exportar
    graficar_resultados(resultados, output_dir)
    exportar_csv(resultados, output_dir / "link_budget_resultados.csv")
    exportar_json(params, resultados, resumen, output_dir / "link_budget_completo.json")

    # Mostrar en pantalla
    print("=" * 90)
    print("CALCULO DE LINK BUDGET - Enlace descendente STRaND-1")
    print("=" * 90)
    print(f"Frecuencia      : {FREQ_HZ/1e6:.3f} MHz (banda UHF)")
    print(f"Modulacion      : {MODULATION}")
    print(f"Tasa de simbolos: {SYM_RATE} bps")
    print(f"Altura orbital  : {ORBIT_HEIGHT_KM} km")
    print()
    print(f"{'Elev':>5} {'Dist':>7} {'FSPL':>7} {'P_rx':>8} {'C/N0':>8} {'Eb/N0':>7} {'Margen':>7}")
    print(f"{'(deg)':>5} {'(km)':>7} {'(dB)':>7} {'(dBm)':>8} {'(dB-Hz)':>8} {'(dB)':>7} {'(dB)':>7}")
    print("-" * 55)
    for r in resultados:
        print(
            f"{r.elevacion_deg:>5.1f} {r.distancia_km:>7.1f} {r.fspl_db:>7.2f} "
            f"{r.p_rx_dbm:>8.2f} {r.c_n0_db_hz:>8.2f} {r.eb_n0_db:>7.2f} {r.margen_db:>7.2f}"
        )
    print("-" * 55)
    print(f"\nResumen:")
    print(f"  Margen maximo  : {resumen['margen_maximo_db']:.2f} dB (elev={resumen['elevacion_margen_maximo_deg']} deg)")
    print(f"  Margen minimo  : {resumen['margen_minimo_db']:.2f} dB (elev={resumen['elevacion_margen_minimo_deg']} deg)")
    print(f"  Margen promedio: {resumen['margen_promedio_db']:.2f} dB")
    print(f"  Peor caso P_rx : {resumen['peor_caso_p_rx_dbm']:.2f} dBm")
    print()
    print(f"Archivos generados en: {output_dir.resolve()}")
    print(f"  - link_budget_resultados.csv")
    print(f"  - link_budget_margen_enlace.png")
    print(f"  - link_budget_completo.json")
    print("=" * 90)


if __name__ == "__main__":
    main()
