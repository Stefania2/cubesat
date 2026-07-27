"""Modelo de estacion terrena con seguimiento automatico para CubeSat.

Simula:
  - Paso orbital completo (AOS -> culminacion -> LOS) sobre una traza de circulo
    maximo, con elevacion, azimut y distancia oblicua exactas para orbita circular
  - Seguimiento automatico de antena con velocidad de giro limitada
  - Perdida por apuntamiento a partir del error real fuera de boresight
  - Temperatura de ruido del sistema variable con la elevacion

La geometria se toma de `geometria_orbital.py`, el mismo modulo que usan los dos
scripts de link budget, para que los tres modelos sean consistentes entre si.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from geometria_orbital import (
    angulo_central_deg,
    angulo_central_maximo_deg,
    densidad_ruido_dbm_hz,
    diferencia_azimut_deg,
    distancia_desde_angulo_central,
    elevacion_desde_angulo_central,
    fspl_db,
    periodo_orbital_s,
    separacion_angular_deg,
    temperatura_sistema,
)


# ─── Constantes ────────────────────────────────────────────────────────────

FREQ_HZ = 437.568e6
ORBIT_HEIGHT_KM = 600.0
ORBIT_PERIOD_S = periodo_orbital_s(ORBIT_HEIGHT_KM)

# Parametros de estacion terrena
GS_LAT_DEG = 4.7110   # Latitud (Bogota, Colombia)
GS_LON_DEG = -74.0721 # Longitud
GS_ALT_M = 2_600.0    # Altitud (msnm)

# Antena Yagi UHF
G_ANT_DBI = 15.0
HPBW_DEG = 30.0       # Ancho de haz a -3 dB (tipico Yagi 11 el)
AZ_RATE_DEG_S = 5.0   # Velocidad de rotacion azimut (deg/s)
EL_RATE_DEG_S = 3.0   # Velocidad de rotacion elevacion (deg/s)

# Suelo de ganancia fuera del lobulo principal. El modelo parabolico
# 12*(theta/HPBW)^2 solo es valido cerca del boresight; sin acotarlo produce
# perdidas de cientos de dB en cuanto la antena queda descolgada del satelite.
L_POINT_MAX_DB = 25.0

# Enlace descendente (mismos valores que calcular_link_budget.py)
P_TX_DBM = 30.0
G_TX_DBI = 0.0
L_TX_DB = 0.5
L_RX_DB = 2.0
L_ATM_DB = 0.5
NF_RX_DB = 2.0
T_ANT_MIN_K = 50.0    # Temperatura de ruido de antena en cenit
T_ANT_MAX_K = 200.0   # Temperatura de ruido de antena en horizonte

# Geometria del paso simulado
ELEV_MAX_DEG = 85.0        # Culminacion del paso
TRACK_THRESHOLD_DEG = 5.0  # Elevacion minima para operar el enlace
DT_S = 1.0


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
    elev_max_deg: float


@dataclass(frozen=True)
class TrackingResult:
    tiempo_s: float
    elevacion_deg: float
    azimut_deg: float
    distancia_km: float
    antena_elevacion_deg: float
    antena_azimut_deg: float
    error_apuntamiento_deg: float
    pointing_loss_db: float
    t_sys_k: float
    c_n0_db_hz: float


def calcular_trayectoria(
    elev_max_deg: float,
    dt_s: float = DT_S,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Paso orbital sobre una traza de circulo maximo.

    El punto subsatelite recorre un circulo maximo cuya minima distancia angular
    a la estacion es `gamma_min` (la que corresponde a la elevacion de
    culminacion). Para un desplazamiento a lo largo de la traza `u = omega * t`
    medido desde la culminacion, la trigonometria esferica da:

        cos(gamma) = cos(gamma_min) * cos(u)

    El paso empieza y termina cuando gamma alcanza el limite de visibilidad.
    Devuelve tiempo (s), elevacion (deg), azimut (deg) y distancia (km).
    """
    gamma_min = angulo_central_deg(elev_max_deg, ORBIT_HEIGHT_KM)
    gamma_max = angulo_central_maximo_deg(ORBIT_HEIGHT_KM)

    cos_u_max = math.cos(math.radians(gamma_max)) / math.cos(math.radians(gamma_min))
    u_max = math.acos(min(max(cos_u_max, -1.0), 1.0))

    omega = 2.0 * math.pi / ORBIT_PERIOD_S
    t_max = u_max / omega
    t = np.arange(-t_max, t_max + dt_s, dt_s, dtype=np.float64)
    u = omega * t

    cos_gamma = math.cos(math.radians(gamma_min)) * np.cos(u)
    gamma_deg = np.degrees(np.arccos(np.clip(cos_gamma, -1.0, 1.0)))

    elev = np.array([elevacion_desde_angulo_central(g, ORBIT_HEIGHT_KM) for g in gamma_deg])
    dist = np.array([distancia_desde_angulo_central(g, ORBIT_HEIGHT_KM) for g in gamma_deg])

    # Azimut: la culminacion ocurre al norte de la estacion, de modo que el
    # satelite sale por el WNW y se pone por el ENE.
    az = np.degrees(np.arctan2(np.sin(u), np.cos(u) * math.sin(math.radians(gamma_min))))
    az = az % 360.0

    return t - t[0], elev, az, dist


def pointing_loss_db(error_deg: float, hp_bw_deg: float) -> float:
    """Perdida por apuntamiento, acotada al nivel de lobulo lateral."""
    if hp_bw_deg < 0.1:
        return 0.0
    return min(12.0 * (error_deg / hp_bw_deg) ** 2, L_POINT_MAX_DB)


def antenna_tracking(
    elev_deg: float,
    az_deg: float,
    prev_el: float,
    prev_az: float,
    params: GroundStationParams,
    dt_s: float,
) -> tuple[float, float, float]:
    """Un paso del seguimiento con velocidad de giro limitada.

    Devuelve (error fuera de boresight en grados, nueva elevacion, nuevo azimut).
    """
    err_el = elev_deg - prev_el
    err_az = diferencia_azimut_deg(prev_az, az_deg)

    max_el = params.el_rate_deg_s * dt_s
    max_az = params.az_rate_deg_s * dt_s

    new_el = prev_el + float(np.clip(err_el, -max_el, max_el))
    new_az = (prev_az + float(np.clip(err_az, -max_az, max_az))) % 360.0

    error = separacion_angular_deg(new_az, new_el, az_deg, elev_deg)
    return error, new_el, new_az


def antenna_noise_temperature(elev_deg: float) -> float:
    """Temperatura de ruido de la antena: maxima en el horizonte (suelo y ruido
    industrial en el lobulo), minima apuntando al cenit."""
    return T_ANT_MIN_K + (T_ANT_MAX_K - T_ANT_MIN_K) * math.exp(-elev_deg / 15.0)


def simulate_pass(params: GroundStationParams, dt_s: float = DT_S) -> list[TrackingResult]:
    t, elev, az, dist = calcular_trayectoria(params.elev_max_deg, dt_s)
    results: list[TrackingResult] = []

    # La estacion se pre-posiciona en el punto de adquisicion antes del paso,
    # que es lo que hace un rotor comandado por prediccion TLE. Arrancar en
    # (0, 0) generaria un transitorio artificial de decenas de grados de error.
    prev_el = float(elev[0])
    prev_az = float(az[0])

    for i in range(len(t)):
        error, prev_el, prev_az = antenna_tracking(
            float(elev[i]), float(az[i]), prev_el, prev_az, params, dt_s
        )
        p_loss = pointing_loss_db(error, params.hp_bw_deg)
        t_sys = temperatura_sistema(
            antenna_noise_temperature(float(elev[i])), L_RX_DB, params.nf_rx_db
        )
        n0 = densidad_ruido_dbm_hz(t_sys)

        fspl = fspl_db(float(dist[i]) * 1e3, FREQ_HZ)
        p_rx_dbm = (
            P_TX_DBM + G_TX_DBI - L_TX_DB
            + params.g_ant_dbi - L_RX_DB
            - fspl - L_ATM_DB - p_loss
        )

        results.append(TrackingResult(
            tiempo_s=round(float(t[i]), 1),
            elevacion_deg=round(float(elev[i]), 2),
            azimut_deg=round(float(az[i]), 2),
            distancia_km=round(float(dist[i]), 1),
            antena_elevacion_deg=round(prev_el, 2),
            antena_azimut_deg=round(prev_az, 2),
            error_apuntamiento_deg=round(error, 3),
            pointing_loss_db=round(p_loss, 3),
            t_sys_k=round(t_sys, 1),
            c_n0_db_hz=round(p_rx_dbm - n0, 2),
        ))
    return results


def plot_tracking(results: list[TrackingResult], output_dir: Path) -> None:
    t = [r.tiempo_s for r in results]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Simulacion de estacion terrena con seguimiento automatico",
                 fontsize=13, fontweight="bold")

    ax = axes[0, 0]
    ax.plot(t, [r.elevacion_deg for r in results], "b-", linewidth=1.4, label="Satelite")
    ax.plot(t, [r.antena_elevacion_deg for r in results], "c--", linewidth=1.0, label="Antena")
    ax.axhline(y=TRACK_THRESHOLD_DEG, color="r", linestyle="--", alpha=0.5,
               label=f"Umbral operativo ({TRACK_THRESHOLD_DEG:.0f}°)")
    ax.set_title("Elevacion")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Elevacion (grados)")
    ax.grid(True, linestyle=":"); ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.plot(t, [r.azimut_deg for r in results], "g-", linewidth=1.4, label="Satelite")
    ax.plot(t, [r.antena_azimut_deg for r in results], "y--", linewidth=1.0, label="Antena")
    ax.set_title("Azimut")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Azimut (grados)")
    ax.grid(True, linestyle=":"); ax.legend(fontsize=8)

    ax = axes[1, 0]
    ax.plot(t, [r.pointing_loss_db for r in results], "m-", linewidth=1.4)
    ax.set_title("Perdida por apuntamiento (limite de seguimiento en azimut)")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Perdida (dB)")
    ax.grid(True, linestyle=":")

    ax = axes[1, 1]
    ax.plot(t, [r.c_n0_db_hz for r in results], color="orange", linewidth=1.4)
    ax.axhline(y=51.8, color="r", linestyle="--", alpha=0.5,
               label="Requerido 9600 bps (Eb/N0=12 dB)")
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
        elev_max_deg=ELEV_MAX_DEG,
    )

    results = simulate_pass(params)
    visibles = [r for r in results if r.elevacion_deg >= TRACK_THRESHOLD_DEG]

    print("=" * 80)
    print("MODELO DE ESTACION TERRENA CON SEGUIMIENTO AUTOMATICO")
    print("=" * 80)
    print(f"Ubicacion: {GS_LAT_DEG}°N, {abs(GS_LON_DEG)}°W, {GS_ALT_M:.0f} msnm")
    print(f"Antena: Yagi UHF {G_ANT_DBI} dBi, HPBW={HPBW_DEG}°")
    print(f"Seguimiento: {AZ_RATE_DEG_S}°/s az, {EL_RATE_DEG_S}°/s el")
    print(f"Periodo orbital: {ORBIT_PERIOD_S / 60:.1f} min (altura {ORBIT_HEIGHT_KM:.0f} km)")
    print(f"Paso simulado: culminacion a {ELEV_MAX_DEG:.0f}°, "
          f"duracion {results[-1].tiempo_s / 60:.1f} min de horizonte a horizonte")

    with (output_dir / "estacion_terrena_seguimiento.json").open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)

    plot_tracking(results, output_dir)

    c_n0 = [r.c_n0_db_hz for r in visibles]
    err = [r.error_apuntamiento_deg for r in visibles]
    p_loss = [r.pointing_loss_db for r in visibles]

    print(f"\nResumen con el satelite sobre {TRACK_THRESHOLD_DEG:.0f}° "
          f"({len(visibles) * DT_S / 60:.1f} min utiles):")
    print(f"  Distancia            : {min(r.distancia_km for r in visibles):.0f} - "
          f"{max(r.distancia_km for r in visibles):.0f} km")
    print(f"  C/N0 promedio        : {sum(c_n0) / len(c_n0):.1f} dB-Hz")
    print(f"  C/N0 minimo / maximo : {min(c_n0):.1f} / {max(c_n0):.1f} dB-Hz")
    print(f"  Error apuntamiento   : promedio {sum(err) / len(err):.2f}°, maximo {max(err):.2f}°")
    print(f"  Perdida apuntamiento : promedio {sum(p_loss) / len(p_loss):.2f} dB, "
          f"maxima {max(p_loss):.2f} dB")
    print(f"\nArchivos generados en {output_dir.resolve()}/")
    print(f"  - estacion_terrena_seguimiento.json")
    print(f"  - estacion_terrena_seguimiento.png")


if __name__ == "__main__":
    main()
