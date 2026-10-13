"""
Calculo de link budget (margen de enlace) para el enlace RF del CubeSat STRaND-1.

Modela el balance de potencias del enlace descendente UHF considerando:
  - Potencia transmitida, ganancia de antenas, perdidas en cables
  - Perdida de trayectoria en espacio libre (FSPL)
  - Perdidas atmosfericas, de polarizacion y apuntamiento
  - Figura de ruido del receptor, temperatura de ruido del sistema
  - Eb/N0 requerida, calculada de la curva de BER de cada esquema
  - Margen de enlace resultante, por esquema de modulacion

La modulacion documentada de STRaND-1 es FSK a 9600 bit/s (ver
`parametros_enlace.py`). El margen principal (`margen_db`) se refiere a ese
esquema; el de BPSK coherente se informa aparte como modelo comparativo.
Los valores y su procedencia viven en `parametros_enlace.py`.

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

import parametros_enlace as pe
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

FREQ_HZ = pe.valor("frecuencia_hz")        # Frecuencia UHF del STRaND-1 (Hz)
SYM_RATE = int(pe.valor("tasa_bit_bps"))    # Tasa de bits (bit/s); binaria: 1 bit/simbolo
# Esquema al que se refiere `margen_db`: el documentado para el satelite.
MODULATION = "FSK"
# Altura real de STRaND-1, no un valor tipico de LEO: se deduce del TLE
# (movimiento medio 14.37185087 rev/dia -> semieje mayor 7146 km). La orbita es
# heliosincrona, i = 98.394°, con excentricidad 0.00098: la aproximacion
# circular que usan estos modelos es valida, la altura de 600 km no lo era.
ORBIT_HEIGHT_KM = pe.valor("altura_orbital_km")

P_TX_DBM = pe.valor("p_tx_dbm")
G_TX_DBI = pe.valor("g_tx_dbi")
L_TX_DB = pe.valor("l_tx_db")
G_RX_DBI = pe.valor("g_rx_dbi")
L_RX_DB = pe.valor("l_rx_db")
NF_RX_DB = pe.valor("nf_rx_db")
T_ANT_K = pe.valor("t_ant_k")
L_ATM_DB = pe.valor("l_atm_db")
L_POL_DB = pe.valor("l_pol_db")
L_POINT_DB = pe.valor("l_point_db")
L_IMPL_DB = pe.valor("l_impl_db")

# Requerimientos del enlace. La Eb/N0 requerida ya no se escribe a mano: se
# obtiene de la curva teorica de cada esquema para la BER objetivo.
BER_TARGET = pe.BER_OBJETIVO
EBN0_REQ_DB = pe.ebn0_requerida_db(pe.ESQUEMA_DOCUMENTADO, BER_TARGET)
EBN0_REQ_BPSK_DB = pe.ebn0_requerida_db(pe.ESQUEMA_MODELO, BER_TARGET)


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
    eb_n0_req_bpsk_db: float
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
    # Margen respecto del esquema documentado (FSK no coherente) y, aparte, del
    # modelo comparativo BPSK. Ambos incluyen la reserva de implementacion.
    margen_db: float
    margen_bpsk_db: float
    eb_n0_requerida_db: float
    eb_n0_requerida_bpsk_db: float
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

    # Eb/N0 (dB) = C/N0 (dB-Hz) - 10 log10(Rb [bit/s])
    eb_n0_db = c_n0_db_hz - 10.0 * math.log10(params.symbol_rate_bps)

    # Eb/N0 requerida (dB): umbral teorico del esquema mas la reserva de
    # implementacion. Es una Eb/N0, no una SNR: la SNR depende ademas del ancho
    # de banda en que se mida el ruido.
    req_db = params.eb_n0_req_db + params.l_impl_db
    req_bpsk_db = params.eb_n0_req_bpsk_db + params.l_impl_db

    # Margen de enlace
    margen_db = eb_n0_db - req_db
    margen_bpsk_db = eb_n0_db - req_bpsk_db

    return LinkBudgetResult(
        elevacion_deg=round(elev_deg, 1),
        distancia_km=round(dist_km, 1),
        fspl_db=round(fspl, 2),
        p_rx_dbm=round(p_rx_dbm, 2),
        c_n0_db_hz=round(c_n0_db_hz, 2),
        eb_n0_db=round(eb_n0_db, 2),
        margen_db=round(margen_db, 2),
        margen_bpsk_db=round(margen_bpsk_db, 2),
        eb_n0_requerida_db=round(req_db, 2),
        eb_n0_requerida_bpsk_db=round(req_bpsk_db, 2),
        perdida_total_db=round(perdida_total, 2),
        t_sys_k=round(t_sys, 1),
    )


def resumen_link_budget(resultados: list[LinkBudgetResult]) -> dict:
    """Genera un resumen con estadisticas del analisis."""
    margenes = [r.margen_db for r in resultados]
    margenes_bpsk = [r.margen_bpsk_db for r in resultados]
    return {
        "esquema_margen_principal": pe.ESQUEMAS[pe.ESQUEMA_DOCUMENTADO].nombre,
        "margen_bpsk_maximo_db": round(max(margenes_bpsk), 2),
        "margen_bpsk_minimo_db": round(min(margenes_bpsk), 2),
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
        "Link budget - enlace descendente STRaND-1 (437.568 MHz, 9600 bit/s)",
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

    snr_req = resultados[0].eb_n0_requerida_db
    req_bpsk = resultados[0].eb_n0_requerida_bpsk_db
    ax = axes[1, 0]
    ax.plot(elevs, [r.eb_n0_db for r in resultados], "m-", linewidth=1.5, label="Eb/N0 obtenida")
    ax.axhline(
        y=snr_req,
        color="r",
        linestyle="--",
        alpha=0.5,
        label=f"Requerida FSK no coherente ({snr_req} dB)",
    )
    ax.axhline(y=req_bpsk, color="b", linestyle=":", alpha=0.6,
               label=f"Requerida BPSK, modelo comparativo ({req_bpsk} dB)")
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
    ax.set_title("Margen de enlace (FSK no coherente, documentada)")
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
        "procedencia": {
            k: {"valor": v.valor, "unidad": v.unidad, "procedencia": v.procedencia,
                "fuente": v.fuente, "incertidumbre": v.incertidumbre}
            for k, v in pe.PARAMETROS.items()
        },
        "esquemas": {
            k: {"nombre": e.nombre, "papel": e.papel, "nota": e.nota,
                "eb_n0_teorica_db": round(pe.ebn0_requerida_db(k, params.ber_target), 2)}
            for k, e in pe.ESQUEMAS.items()
        },
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
        eb_n0_req_db=round(EBN0_REQ_DB, 2),
        eb_n0_req_bpsk_db=round(EBN0_REQ_BPSK_DB, 2),
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
    print(f"Modulacion      : {MODULATION} (documentada); BPSK como modelo comparativo")
    print(f"Tasa de bits    : {SYM_RATE} bit/s")
    print(f"Eb/N0 requerida : FSK no coh. {EBN0_REQ_DB:.2f} dB, BPSK {EBN0_REQ_BPSK_DB:.2f} dB "
          f"(BER {BER_TARGET:g}) + {L_IMPL_DB} dB de reserva")
    print(f"Altura orbital  : {ORBIT_HEIGHT_KM} km")
    print()
    print(f"{'Elev':>5} {'Dist':>7} {'FSPL':>7} {'P_rx':>8} {'C/N0':>8} {'Eb/N0':>7} {'M.FSK':>7} {'M.BPSK':>7}")
    print(f"{'(deg)':>5} {'(km)':>7} {'(dB)':>7} {'(dBm)':>8} {'(dB-Hz)':>8} {'(dB)':>7} {'(dB)':>7} {'(dB)':>7}")
    print("-" * 63)
    for r in resultados:
        print(
            f"{r.elevacion_deg:>5.1f} {r.distancia_km:>7.1f} {r.fspl_db:>7.2f} "
            f"{r.p_rx_dbm:>8.2f} {r.c_n0_db_hz:>8.2f} {r.eb_n0_db:>7.2f} {r.margen_db:>7.2f} {r.margen_bpsk_db:>7.2f}"
        )
    print("-" * 63)
    print(f"\nResumen (margen FSK no coherente):")
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
