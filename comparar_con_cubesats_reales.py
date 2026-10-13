"""
Comparacion de resultados de simulacion con parametros reales de CubeSats
documentados en la literatura tecnica internacional.

Referencias:
  - Bouwmeester, J., & Guo, J. (2010). Survey of worldwide pico- and
    nanosatellite missions. Acta Astronautica, 67(7-8), 854-862.
  - CubeSat Design Specification (CDS) Rev. 14, Cal Poly SLO, 2022.
  - Larson & Wertz, Space Mission Analysis and Design (3rd ed.).
  - Datos de misiones especificas: STRaND-1, Libertad 1, FACSAT-1,
    Delfi-C3, ESTCube-1, AAUSAT-II, ITUPSAT 1.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.special import erfc


# ─── Parametros de la simulacion ────────────────────────────────────────

SYM_RATE = 9_600
SAMPLE_RATE = 76_800
SAMPLES_PER_SYMBOL = 8
FREQ_MHZ = 437.568

# Conversion de SNR (simulacion) a Eb/N0 teorica
# En la simulacion, SNR es la relacion senal-ruido en el ancho de banda de
# muestreo (76800 Hz). Eb/N0 = SNR * (B / R) = SNR * 8.
# En dB: Eb/N0_dB = SNR_dB + 10*log10(8) = SNR_dB + 9.03 dB
SNR_TO_EBN0_DB = 10.0 * math.log10(SAMPLE_RATE / SYM_RATE)  # ~9.03 dB


@dataclass(frozen=True)
class RealCubeSat:
    nombre: str
    pais: str
    ano_lanzamiento: int
    formato: str
    frecuencia_mhz: float
    banda: str
    modulacion: str
    tasa_bps: int
    potencia_tx_dbm: float
    tipo_antena: str
    ganancia_antena_dbi: float
    referencia: str
    # Solo la fila de STRaND-1 se ha contrastado con fuentes en la auditoria de
    # 2026-10. Las demas proceden de la recopilacion inicial del proyecto y
    # quedan pendientes de verificar una a una contra su fuente primaria.
    verificado: bool = False


@dataclass(frozen=True)
class ComparisonMetric:
    parametro: str
    simulado: str
    real_referencia: str
    concordancia: str


# ─── Base de datos de CubeSats reales ────────────────────────────────────

CUBESATS_REALES = [
    RealCubeSat(
        nombre="STRaND-1",
        pais="Reino Unido",
        ano_lanzamiento=2013,
        formato="3U",
        frecuencia_mhz=437.568,
        banda="UHF",
        # FSK 9600 con AX.25/HDLC y NRZI: AMSAT-UK y SatNOGS DB. Aqui figuraba
        # «BPSK», que ninguna fuente respalda.
        modulacion="FSK",
        tasa_bps=9600,
        potencia_tx_dbm=30.0,       # eoPortal: 1 W nominal (0.25 W en modo baliza/CW)
        tipo_antena="Monopolo",
        ganancia_antena_dbi=0.0,    # supuesto: la ganancia no esta publicada
        referencia="AMSAT-UK; SatNOGS DB; eoPortal",
        verificado=True,
    ),
    RealCubeSat(
        nombre="Libertad 1",
        pais="Colombia",
        ano_lanzamiento=2007,
        formato="1U",
        frecuencia_mhz=437.405,
        banda="UHF",
        modulacion="AFSK",
        tasa_bps=1200,
        potencia_tx_dbm=27.0,
        tipo_antena="Dipolo",
        ganancia_antena_dbi=2.0,
        referencia="Universidad Sergio Arboleda / ESA",
    ),
    RealCubeSat(
        nombre="FACSAT-1",
        pais="Colombia",
        ano_lanzamiento=2018,
        formato="3U",
        frecuencia_mhz=437.375,
        banda="UHF",
        modulacion="BPSK",
        tasa_bps=9600,
        potencia_tx_dbm=30.0,
        tipo_antena="Monopolo",
        ganancia_antena_dbi=0.0,
        referencia="FAC / GomSpace",
    ),
    RealCubeSat(
        nombre="Delfi-C3",
        pais="Paises Bajos",
        ano_lanzamiento=2008,
        formato="3U",
        frecuencia_mhz=145.870,
        banda="VHF",
        modulacion="BPSK",
        tasa_bps=1200,
        potencia_tx_dbm=28.0,
        tipo_antena="Dipolo desplegable",
        ganancia_antena_dbi=2.0,
        referencia="TU Delft",
    ),
    RealCubeSat(
        nombre="ESTCube-1",
        pais="Estonia",
        ano_lanzamiento=2013,
        formato="1U",
        frecuencia_mhz=437.250,
        banda="UHF",
        modulacion="BPSK",
        tasa_bps=9600,
        potencia_tx_dbm=30.0,
        tipo_antena="Monopolo",
        ganancia_antena_dbi=0.0,
        referencia="Universidad de Tartu",
    ),
    RealCubeSat(
        nombre="AAUSAT-II",
        pais="Dinamarca",
        ano_lanzamiento=2008,
        formato="1U",
        frecuencia_mhz=437.425,
        banda="UHF",
        modulacion="AFSK",
        tasa_bps=1200,
        potencia_tx_dbm=28.0,
        tipo_antena="Monopolo",
        ganancia_antena_dbi=0.0,
        referencia="Universidad de Aalborg",
    ),
    RealCubeSat(
        nombre="ITUPSAT 1",
        pais="Turquia",
        ano_lanzamiento=2009,
        formato="1U",
        frecuencia_mhz=437.325,
        banda="UHF",
        modulacion="BPSK",
        tasa_bps=9600,
        potencia_tx_dbm=30.0,
        tipo_antena="Monopolo",
        ganancia_antena_dbi=0.0,
        referencia="Universidad de Estambul",
    ),
]


# ─── Curvas teoricas de BER ─────────────────────────────────────────────

def ber_bpsk_teorica(eb_n0_lin: np.ndarray) -> np.ndarray:
    """BER teorica para BPSK coherente en AWGN: 0.5 * erfc(sqrt(Eb/N0))."""
    return 0.5 * erfc(np.sqrt(eb_n0_lin))


def ber_fsk_nocoherente_teorica(eb_n0_lin: np.ndarray) -> np.ndarray:
    """BER teorica para FSK no coherente: 0.5 * exp(-Eb/(2*N0))."""
    return 0.5 * np.exp(-eb_n0_lin / 2.0)


def ber_bpsk_diferencial_teorica(eb_n0_lin: np.ndarray) -> np.ndarray:
    """BER teorica para DPSK: 0.5 * exp(-Eb/N0)."""
    return 0.5 * np.exp(-eb_n0_lin)


# ─── Carga de resultados simulados ─────────────────────────────────────

def cargar_resultados_ber(path: Path) -> dict[str, list[dict]]:
    resultados: dict[str, list[dict]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mod = row["modulacion"]
            if mod not in resultados:
                resultados[mod] = []
            resultados[mod].append({
                "snr_db": float(row["snr_db"]),
                "ber": float(row["ber"]),
                "errores": int(row["errores_bit"]),
                "bits": int(row["bits_evaluados"]),
            })
    return resultados


# ─── Grafica de comparacion BER ────────────────────────────────────────

def graficar_comparacion_ber(
    resultados: dict[str, list[dict]],
    output_dir: Path,
) -> None:
    snr_range = np.linspace(-4, 14, 200)
    eb_n0_range_lin = 10.0 ** ((snr_range + SNR_TO_EBN0_DB) / 10.0)

    fig, ax = plt.subplots(figsize=(10, 7))

    # Curvas teoricas
    ax.semilogy(
        snr_range,
        ber_bpsk_teorica(eb_n0_range_lin),
        "b-",
        linewidth=1.2,
        label="BPSK teorica (coherente)",
    )
    ax.semilogy(
        snr_range,
        ber_fsk_nocoherente_teorica(eb_n0_range_lin),
        "r-",
        linewidth=1.2,
        label="FSK teorica (no coherente)",
    )
    ax.semilogy(
        snr_range,
        ber_bpsk_diferencial_teorica(eb_n0_range_lin),
        "c--",
        linewidth=1.0,
        alpha=0.6,
        label="DPSK teorica",
    )

    # Puntos simulados
    for mod, datos in resultados.items():
        snr = [d["snr_db"] for d in datos]
        ber = [max(d["ber"], 1e-7) for d in datos]
        marker = "o" if mod == "BPSK" else "s"
        color = "blue" if mod == "BPSK" else "red"
        ax.semilogy(
            snr,
            ber,
            marker=marker,
            linestyle="",
            markersize=7,
            markerfacecolor=color,
            markeredgecolor="black",
            markeredgewidth=0.5,
            label=f"{mod} simulada (STRaND-1)",
        )

    # Marca BER objetivo tipico
    ax.axhline(y=1e-5, color="gray", linestyle=":", alpha=0.6)
    ax.text(
        -3.5,
        1.5e-5,
        "BER objetivo tipico (1e-5)",
        fontsize=8,
        color="gray",
    )

    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("BER")
    ax.set_title(
        "Comparacion BER simulada vs. teorica\n"
        f"STRaND-1 | {SYM_RATE} bps BPSK/FSK | {SAMPLE_RATE/1e3:.1f} kHz sample rate"
    )
    ax.set_ylim(1e-7, 1)
    ax.set_xlim(-4, 14)
    ax.grid(True, which="both", linestyle=":", alpha=0.5)
    ax.legend(fontsize=9, loc="upper right")

    # Anotacion de SNR_EBN0
    ax.text(
        0.98,
        0.02,
        f"Eb/N0 = SNR + {SNR_TO_EBN0_DB:.1f} dB\n"
        f"({SAMPLE_RATE/1e3:.0f} kHz BW, {SYM_RATE} bps)",
        transform=ax.transAxes,
        fontsize=8,
        verticalalignment="bottom",
        horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    plt.tight_layout()
    plt.savefig(output_dir / "comparacion_ber_teorica_vs_simulada.png", dpi=180)
    plt.close()


# ─── Lectura de los resultados ya generados ────────────────────────────

@dataclass(frozen=True)
class ResumenSimulado:
    """Cifras leidas de los archivos de resultados.

    La tabla comparativa se construye a partir de estos valores en lugar de
    llevarlos escritos a mano: transcribirlos hacia que la tabla se
    desincronizara de las simulaciones en cuanto se reejecutaba el pipeline.
    """
    ber_bpsk_0db: float
    snr_bpsk_ber_cero: float | None
    ber_fsk_0db: float
    snr_fsk_ber_cero: float | None
    bw_bpsk_hz: float
    bw_fsk_hz: float
    bw_rrc_hz: float | None
    margen_min_db: float
    margen_min_elev: float
    margen_max_db: float
    margen_max_elev: float


def _primer_snr_sin_errores(datos: list[dict]) -> float | None:
    con_cero = [d["snr_db"] for d in datos if d["errores"] == 0]
    return min(con_cero) if con_cero else None


def _ber_en(datos: list[dict], snr_db: float) -> float:
    return next(d["ber"] for d in datos if d["snr_db"] == snr_db)


def cargar_resumen_simulado(
    resultados: dict[str, list[dict]],
    output_dir: Path,
) -> ResumenSimulado:
    bpsk, fsk = resultados["BPSK"], resultados["FSK"]

    with (output_dir / "resultados_ber_fsk_bpsk.csv").open(newline="", encoding="utf-8") as f:
        anchos = {r["modulacion"]: float(r["ancho_banda_estimado_hz"]) for r in csv.DictReader(f)}

    # El ancho de banda con conformado RRC viene del modelo avanzado, si se ha
    # ejecutado; es opcional para que este script siga corriendo sin el.
    bw_rrc = None
    avanzado = output_dir / "resultados_simulacion_avanzada.csv"
    if avanzado.exists():
        with avanzado.open(newline="", encoding="utf-8") as f:
            rrc = [float(r["ancho_banda_hz"]) for r in csv.DictReader(f) if r["rrc"] == "True"]
        if rrc:
            bw_rrc = min(rrc)

    with (output_dir / "link_budget_resultados.csv").open(newline="", encoding="utf-8") as f:
        lb = [(float(r["margen_db"]), float(r["elevacion_deg"])) for r in csv.DictReader(f)]

    return ResumenSimulado(
        ber_bpsk_0db=_ber_en(bpsk, 0.0),
        snr_bpsk_ber_cero=_primer_snr_sin_errores(bpsk),
        ber_fsk_0db=_ber_en(fsk, 0.0),
        snr_fsk_ber_cero=_primer_snr_sin_errores(fsk),
        bw_bpsk_hz=anchos["BPSK"],
        bw_fsk_hz=anchos["FSK"],
        bw_rrc_hz=bw_rrc,
        margen_min_db=min(lb)[0],
        margen_min_elev=min(lb)[1],
        margen_max_db=max(lb)[0],
        margen_max_elev=max(lb)[1],
    )


# ─── Tabla comparativa de parametros ────────────────────────────────────

def generar_tabla_comparativa(
    output_dir: Path,
    sim: ResumenSimulado,
) -> list[ComparisonMetric]:
    bits = "18776"
    bw_rrc_txt = (
        f"\nBPSK + RRC (α=0.35): ~{sim.bw_rrc_hz / 1000:.1f} kHz (99 % ocupado)"
        if sim.bw_rrc_hz
        else ""
    )
    pendiente = "Valores de los demas satelites: recopilacion inicial, pendientes de verificar."
    metricas = [
        ComparisonMetric(
            parametro="Frecuencia de operacion",
            simulado=f"{FREQ_MHZ:.3f} MHz (UHF)",
            real_referencia="STRaND-1: 437.568 MHz (AMSAT-UK, SatNOGS DB)",
            concordancia="Coincide por construccion: el modelo usa la frecuencia\n"
                         "documentada del satelite.",
        ),
        ComparisonMetric(
            parametro="Modulacion",
            simulado="BPSK coherente (modelo comparativo) y FSK de banda base",
            real_referencia="STRaND-1: FSK 9600, AX.25/HDLC, NRZI (AMSAT-UK, SatNOGS DB)",
            concordancia="Parcial. La familia FSK coincide; la BPSK del modelo avanzado\n"
                         "NO es la modulacion del satelite. La desviacion y el filtrado\n"
                         "del modulador real no estan documentados.",
        ),
        ComparisonMetric(
            parametro="Tasa de bits",
            simulado=f"{SYM_RATE} bit/s",
            real_referencia="STRaND-1: 9600 bit/s (AMSAT-UK, SatNOGS DB)",
            concordancia="Coincide por construccion.",
        ),
        ComparisonMetric(
            parametro="Potencia de transmision",
            simulado="1 W (30 dBm)",
            real_referencia="STRaND-1: 1 W nominal; 0.25 W en modo baliza/CW (eoPortal)",
            concordancia="Coincide con el valor nominal. El modo en que se emite la\n"
                         "telemetria no esta confirmado: -6 dB entra en la sensibilidad.",
        ),
        ComparisonMetric(
            parametro="BER vs SNR - BPSK",
            simulado=f"BER {sim.ber_bpsk_0db:.1e} a SNR por muestra de 0 dB (Eb/N0 9.03 dB)\n"
                     f"0 errores en {bits} bits desde {sim.snr_bpsk_ber_cero:.0f} dB",
            real_referencia="Teoria BPSK coherente: BER 3.4e-5 a Eb/N0 = 9 dB",
            concordancia="Compatible con la teoria dentro del intervalo de confianza de\n"
                         f"una muestra de {bits} bits. No es una comparacion con el\n"
                         "satelite: no existe BER medida del enlace real.",
        ),
        ComparisonMetric(
            parametro="Margen de enlace (link budget)",
            simulado=f"{sim.margen_min_db:.1f} dB a elev={sim.margen_min_elev:.0f} deg\n"
                     f"{sim.margen_max_db:.1f} dB a elev={sim.margen_max_elev:.0f} deg\n"
                     "(FSK no coherente, umbral teorico)",
            real_referencia="Sin dato publicado del margen de STRaND-1.\n"
                            "Criterio de diseño habitual: 3-6 dB (Larson & Wertz)",
            concordancia="No comparable con una medida. El valor es una prediccion con\n"
                         "estacion hipotetica y parametros supuestos (ver sensibilidad).",
        ),
        ComparisonMetric(
            parametro="Ancho de banda estimado",
            simulado=f"BPSK rectangular: ~{sim.bw_bpsk_hz / 1000:.1f} kHz (-20 dB)\n"
                     f"FSK: ~{sim.bw_fsk_hz / 1000:.1f} kHz (-20 dB)"
                     + bw_rrc_txt,
            real_referencia="Canalizacion UHF amateur: 25 kHz\n"
                            "Con RRC: R*(1+α) = 12.96 kHz (teorico)",
            concordancia="El modelo con RRC cabe en el canal. El ancho de banda real\n"
                         "de la emision de STRaND-1 no se ha medido en este trabajo.",
        ),
    ]
    _ = pendiente

    with (output_dir / "comparacion_parametros_cubesats_reales.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.writer(f)
        writer.writerow(["Parametro", "Simulado", "Referencia real", "Concordancia"])
        for m in metricas:
            writer.writerow([m.parametro, m.simulado, m.real_referencia, m.concordancia])

    with (output_dir / "comparacion_parametros_cubesats_reales.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(
            {
                "metrica": "Comparacion de parametros de simulacion vs. CubeSats reales",
                "satelite_referencia": "STRaND-1 (NORAD 39090)",
                "metricas": [asdict(m) for m in metricas],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return metricas


# ─── Tabla de CubeSats reales ──────────────────────────────────────────

def exportar_tabla_cubesats(output_dir: Path) -> None:
    with (output_dir / "cubesats_reales_referencia.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.writer(f)
        writer.writerow([
            "Satelite", "Pais", "Ano", "Formato", "Freq (MHz)",
            "Banda", "Modulacion", "Tasa (bps)", "P_tx (dBm)",
            "Antena", "G_ant (dBi)", "Referencia",
        ])
        for c in CUBESATS_REALES:
            writer.writerow([
                c.nombre, c.pais, c.ano_lanzamiento, c.formato,
                c.frecuencia_mhz, c.banda, c.modulacion, c.tasa_bps,
                c.potencia_tx_dbm, c.tipo_antena, c.ganancia_antena_dbi, c.referencia,
            ])

    with (output_dir / "cubesats_reales_referencia.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(
            {"cubesats_reales": [asdict(c) for c in CUBESATS_REALES]},
            f,
            indent=2,
            ensure_ascii=False,
        )


# ─── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    output_dir = Path("resultados_simulacion")
    output_dir.mkdir(exist_ok=True)

    # Cargar resultados de simulacion BER
    ber_path = output_dir / "resultados_ber_fsk_bpsk.csv"
    if not ber_path.exists():
        print("ERROR: No se encuentra resultados_ber_fsk_bpsk.csv")
        print("Ejecuta primero: python simular_enlace_rf_fsk_bpsk.py")
        return

    resultados = cargar_resultados_ber(ber_path)
    sim = cargar_resumen_simulado(resultados, output_dir)

    # Grafica comparacion BER teorica vs simulada
    print("Generando grafica de comparacion BER...")
    graficar_comparacion_ber(resultados, output_dir)

    # Tabla de parametros comparativos
    print("Generando tabla comparativa con CubeSats reales...")
    metricas = generar_tabla_comparativa(output_dir, sim)

    # Tabla de CubeSats de referencia
    print("Exportando base de datos de CubeSats de referencia...")
    exportar_tabla_cubesats(output_dir)

    # Mostrar resumen en pantalla
    print()
    print("=" * 100)
    print("COMPARACION CON CUBESATS REALES - RESUMEN")
    print("=" * 100)
    print()
    print(f"Satelite de referencia: STRaND-1 (NORAD 39090)")
    print(f"Frecuencia: {FREQ_MHZ} MHz | Modulacion: BPSK/FSK | Tasa: {SYM_RATE} bps")
    print()
    print("CubeSats reales utilizados como referencia:")
    for c in CUBESATS_REALES:
        print(f"  - {c.nombre:12s} ({c.pais:16s}) {c.ano_lanzamiento} | "
              f"{c.frecuencia_mhz:6.3f} MHz | {c.modulacion:5s} | {c.tasa_bps:5d} bps")
    print()
    print("Metricas comparativas generadas:")
    for i, m in enumerate(metricas, 1):
        print(f"  {i}. {m.parametro}")
        print(f"     Simulado : {m.simulado.split(chr(10))[0]}")
        print(f"     Real     : {m.real_referencia.split(chr(10))[0]}")
        print(f"     Concordancia: {m.concordancia.split(chr(10))[0]}")
        print()
    print("=" * 100)
    print(f"Archivos generados en: {output_dir.resolve()}")
    print("  - comparacion_ber_teorica_vs_simulada.png")
    print("  - comparacion_parametros_cubesats_reales.csv")
    print("  - comparacion_parametros_cubesats_reales.json")
    print("  - cubesats_reales_referencia.csv")
    print("  - cubesats_reales_referencia.json")
    print("=" * 100)


if __name__ == "__main__":
    main()
