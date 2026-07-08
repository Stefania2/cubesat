"""
Modelo de estacion terrena con seguimiento automatico para CubeSat.

Simula:
  - Orbita LEO con calculo de posicion satelite-angulo de elevacion
  - Seguimiento automatico de antena (azimut, elevacion)
  - Perdidas por apuntamiento dinamico
  - Temperatura de ruido del sistema variable con elevacion
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# ─── Constantes ────────────────────────────────────────────────────────────

EARTH_RADIUS_KM = 6_371.0
C_LIGHT = 299_792_458
K_BOLTZ = 1.380649e-23

FREQ_HZ = 437.568e6
ORBIT_HEIGHT_KM = 600.0
ORBIT_PERIOD_S = 2.0 * math.pi * math.sqrt(
    ((EARTH_RADIUS_KM + ORBIT_HEIGHT_KM) * 1e3) ** 3 / 3.986004418e14
)

# Parametros de estacion terrena
GS_LAT_DEG = 4.7110   # Latitud (Bogota, Colombia)
GS_LON_DEG = -74.0721 # Longitud
GS_ALT_M = 2_600.0    # Altitud (msnm)

# Antena Yagi UHF
G_ANT_DBI = 15.0
HPBW_DEG = 30.0       # Ancho de haz a -3 dB (tipico Yagi 11 el)
AZ_RATE_DEG_S = 5.0   # Velocidad de rotacion azimut (deg/s)
EL_RATE_DEG_S = 3.0   # Velocidad de rotacion elevacion (deg/s)

# Parametros RX
NF_RX_DB = 2.0
T_ANT_MIN_K = 50.0    # Temperatura de ruido de antena en cenit
T_ANT_MAX_K = 200.0   # Temperatura de ruido de antena en horizonte
T_GROUND_K = 290.0

# Umbral de seguimiento
TRACK_THRESHOLD_DEG = 5.0  # Elevacion minima para iniciar seguimiento


@dataclass(frozen=True)
class GroundStationParams:
    lat_deg: float
    lon_deg: float
    alt_m: float
    g_ant_dbi: float
    hp_bw_deg: float
    az_rate_deg_s: float
    el_rate_deg_s: float
    nf_rx_db: float
    track_threshold_deg: float


@dataclass(frozen=True)
class TrackingResult:
    tiempo_s: float
    elevacion_deg: float
    azimut_deg: float
    distancia_km: float
    pointing_loss_db: float
    t_sys_k: float
    c_n0_db_hz: float


def calcular_trayectoria(
    duration_s: float,
    dt_s: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calcula elevacion, azimut y distancia de un paso orbital simplificado."""
    n = int(duration_s / dt_s)
    t = np.arange(n, dtype=np.float64) * dt_s

    # Orbita circular simplificada: el satelite pasa sobre la estacion
    omega = 2.0 * math.pi / ORBIT_PERIOD_S
    elev_max = 85.0
    # Tiempo relativo al punto mas cercano (cenit)
    t_rel = t - duration_s / 2.0
    # Distancia angular desde el cenit
    angular_dist = omega * np.abs(t_rel)
    # Elevacion aproximada
    elev = elev_max * np.cos(angular_dist / (math.pi / 6.0))
    elev = np.clip(elev, 0.0, 90.0)

    # Distancia oblicua
    dist = np.where(
        elev > 1.0,
        np.sqrt(
            (EARTH_RADIUS_KM + ORBIT_HEIGHT_KM) ** 2
            + EARTH_RADIUS_KM ** 2
            - 2.0 * (EARTH_RADIUS_KM + ORBIT_HEIGHT_KM) * EARTH_RADIUS_KM
            * np.cos(np.radians(90.0 - elev))
        ),
        ORBIT_HEIGHT_KM * 3.0,
    )

    # Azimut (barrido lineal durante el paso)
    az = 180.0 + 90.0 * np.sin(2.0 * math.pi * t / duration_s)
    az = az % 360.0

    return t, elev, az, dist


def pointing_loss(angular_error_deg: float, hp_bw_deg: float) -> float:
    """Perdida por apuntamiento (modelo gaussiano)."""
    if hp_bw_deg < 0.1:
        return 0.0
    return 12.0 * (angular_error_deg / hp_bw_deg) ** 2


def antenna_tracking(
    elev_deg: float,
    az_deg: float,
    prev_el: float,
    prev_az: float,
    params: GroundStationParams,
    dt_s: float,
) -> tuple[float, float, float]:
    """Simula el seguimiento automatico con velocidad limitada."""
    if elev_deg < params.track_threshold_deg:
        return 0.0, prev_el, prev_az

    # Error antes de correccion
    err_el = elev_deg - prev_el
    err_az = az_deg - prev_az

    # Correccion limitada por velocidad
    max_correction_el = params.el_rate_deg_s * dt_s
    max_correction_az = params.az_rate_deg_s * dt_s

    corr_el = np.clip(err_el, -max_correction_el, max_correction_el)
    corr_az = np.clip(err_az, -max_correction_az, max_correction_az)

    new_el = prev_el + corr_el
    new_az = prev_az + corr_az

    # Error residual
    residual = math.sqrt((elev_deg - new_el) ** 2 + (az_deg - new_az) ** 2)
    return residual, new_el, new_az


def system_noise_temperature(elev_deg: float, nf_rx_db: float) -> float:
    """Temperatura de ruido del sistema en funcion de la elevacion."""
    t_ant = T_ANT_MIN_K + (T_ANT_MAX_K - T_ANT_MIN_K) * math.exp(-elev_deg / 15.0)
    t_rx = (10.0 ** (nf_rx_db / 10.0) - 1.0) * T_GROUND_K
    return t_ant + t_rx


def fspl_db(dist_m: float, freq_hz: float) -> float:
    return 20.0 * math.log10(dist_m) + 20.0 * math.log10(freq_hz) + 20.0 * math.log10(4.0 * math.pi / C_LIGHT)


def simulate_pass(
    params: GroundStationParams,
    duration_s: float = 900.0,
    dt_s: float = 1.0,
) -> list[TrackingResult]:
    """Simula un paso completo del satelite con seguimiento."""
    t, elev, az, dist = calcular_trayectoria(duration_s, dt_s)
    results: list[TrackingResult] = []
    prev_el = 0.0
    prev_az = 0.0

    for i in range(len(t)):
        residual, prev_el, prev_az = antenna_tracking(
            float(elev[i]), float(az[i]), prev_el, prev_az, params, dt_s
        )
        p_loss = pointing_loss(residual, params.hp_bw_deg)
        t_sys = system_noise_temperature(float(elev[i]), params.nf_rx_db)
        n0 = 10.0 * math.log10(K_BOLTZ * t_sys) + 30.0

        dist_m = float(dist[i]) * 1e3
        fspl = fspl_db(dist_m, FREQ_HZ)
        p_rx_dbm = 30.0 + 0.0 - 0.5 + params.g_ant_dbi - 2.0 - fspl - p_loss - 0.5
        c_n0 = p_rx_dbm - n0

        results.append(TrackingResult(
            tiempo_s=round(float(t[i]), 1),
            elevacion_deg=round(float(elev[i]), 1),
            azimut_deg=round(float(az[i]), 1),
            distancia_km=round(float(dist[i]), 1),
            pointing_loss_db=round(p_loss, 3),
            t_sys_k=round(t_sys, 1),
            c_n0_db_hz=round(c_n0, 2),
        ))
    return results


def plot_tracking(results: list[TrackingResult], output_dir: Path) -> None:
    t = [r.tiempo_s for r in results]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Simulacion de estacion terrena con seguimiento automatico", fontsize=13, fontweight="bold")

    ax = axes[0, 0]
    ax.plot(t, [r.elevacion_deg for r in results], "b-", linewidth=1.2)
    ax.axhline(y=5, color="r", linestyle="--", alpha=0.5, label="Umbral tracking (5°)")
    ax.set_title("Elevacion del satelite")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Elevacion (grados)")
    ax.grid(True, linestyle=":"); ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.plot(t, [r.azimut_deg for r in results], "g-", linewidth=1.2)
    ax.set_title("Azimut del satelite")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Azimut (grados)")
    ax.grid(True, linestyle=":")

    ax = axes[1, 0]
    ax.plot(t, [r.pointing_loss_db for r in results], "m-", linewidth=1.2)
    ax.set_title("Perdida por apuntamiento")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Perdida (dB)")
    ax.grid(True, linestyle=":")

    ax = axes[1, 1]
    ax.plot(t, [r.c_n0_db_hz for r in results], "orange", linewidth=1.2)
    ax.axhline(y=55, color="r", linestyle="--", alpha=0.5, label="Limite inferior tipico")
    ax.set_title("C/N0 durante el paso")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("C/N0 (dB-Hz)")
    ax.grid(True, linestyle=":"); ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(output_dir / "estacion_terrena_seguimiento.png", dpi=180)
    plt.close()


def main() -> None:
    output_dir = Path("resultados_simulacion")
    output_dir.mkdir(exist_ok=True)

    params = GroundStationParams(
        lat_deg=GS_LAT_DEG,
        lon_deg=GS_LON_DEG,
        alt_m=GS_ALT_M,
        g_ant_dbi=G_ANT_DBI,
        hp_bw_deg=HPBW_DEG,
        az_rate_deg_s=AZ_RATE_DEG_S,
        el_rate_deg_s=EL_RATE_DEG_S,
        nf_rx_db=NF_RX_DB,
        track_threshold_deg=TRACK_THRESHOLD_DEG,
    )

    print("=" * 80)
    print("MODELO DE ESTACION TERRENA CON SEGUIMIENTO AUTOMATICO")
    print("=" * 80)
    print(f"Ubicacion: {GS_LAT_DEG}°N, {GS_LON_DEG}°W, {GS_ALT_M} msnm")
    print(f"Antena: Yagi UHF {G_ANT_DBI} dBi, HPBW={HPBW_DEG}°")
    print(f"Seguimiento: {AZ_RATE_DEG_S}°/s az, {EL_RATE_DEG_S}°/s el")
    print(f"Umbral de tracking: {TRACK_THRESHOLD_DEG}°")
    print(f"Duracion del paso: ~{ORBIT_PERIOD_S / 60:.1f} min")

    results = simulate_pass(params)

    # Exportar
    with (output_dir / "estacion_terrena_seguimiento.json").open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)

    plot_tracking(results, output_dir)

    # Resumen
    c_n0_vals = [r.c_n0_db_hz for r in results if r.elevacion_deg > 5]
    pl_vals = [r.pointing_loss_db for r in results if r.elevacion_deg > 5]

    print(f"\nResumen del paso (elevacion > 5°):")
    print(f"  C/N0 promedio: {sum(c_n0_vals) / len(c_n0_vals):.1f} dB-Hz")
    print(f"  C/N0 maximo:   {max(c_n0_vals):.1f} dB-Hz")
    print(f"  Perdida por apuntamiento promedio: {sum(pl_vals) / len(pl_vals):.3f} dB")
    print(f"  Perdida por apuntamiento max:       {max(pl_vals):.3f} dB")
    print(f"\nArchivos generados:")
    print(f"  - estacion_terrena_seguimiento.json")
    print(f"  - estacion_terrena_seguimiento.png")


if __name__ == "__main__":
    main()
