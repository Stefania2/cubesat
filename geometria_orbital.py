"""Geometria orbital y constantes de radio compartidas por los scripts de enlace.

Antes cada script redefinia su propia copia de la constante de Boltzmann, del
radio terrestre y de la formula de distancia oblicua. Eso hizo que
`modelo_estacion_terrena.py` divergiera de `calcular_link_budget.py`: usaba
`90 - elevacion` como angulo central de la Tierra, lo que sobreestimaba la
distancia al satelite en un factor de hasta seis. Este modulo centraliza esas
definiciones para que los tres modelos de enlace partan de la misma geometria.

Convenciones:
  - Orbita circular, Tierra esferica de radio medio.
  - `gamma` es el angulo central geocentrico entre la estacion terrena y el
    punto subsatelite.
  - `eta` es el angulo de nadir visto desde el satelite.
  - gamma + eta + elevacion = 90 grados.
"""

from __future__ import annotations

import math

# ─── Constantes fisicas ────────────────────────────────────────────────────

EARTH_RADIUS_KM = 6_371.0        # Radio terrestre medio (km)
C_LIGHT = 299_792_458            # Velocidad de la luz (m/s)
K_BOLTZ = 1.380649e-23           # Constante de Boltzmann (J/K)
MU_EARTH = 3.986004418e14        # Parametro gravitacional terrestre (m^3/s^2)
T0_K = 290.0                     # Temperatura de referencia para figura de ruido (K)


# ─── Geometria del enlace ──────────────────────────────────────────────────

def angulo_nadir_deg(elev_deg: float, h_km: float,
                     r_km: float = EARTH_RADIUS_KM) -> float:
    """Angulo de nadir (grados) visto desde el satelite para una elevacion dada."""
    seno = r_km / (r_km + h_km) * math.cos(math.radians(elev_deg))
    return math.degrees(math.asin(min(max(seno, -1.0), 1.0)))


def angulo_central_deg(elev_deg: float, h_km: float,
                       r_km: float = EARTH_RADIUS_KM) -> float:
    """Angulo central geocentrico (grados) para una elevacion dada."""
    return 90.0 - elev_deg - angulo_nadir_deg(elev_deg, h_km, r_km)


def angulo_central_maximo_deg(h_km: float,
                              r_km: float = EARTH_RADIUS_KM) -> float:
    """Angulo central en el horizonte (elevacion = 0): limite de visibilidad."""
    return math.degrees(math.acos(r_km / (r_km + h_km)))


def distancia_desde_angulo_central(gamma_deg: float, h_km: float,
                                   r_km: float = EARTH_RADIUS_KM) -> float:
    """Distancia oblicua (km) a partir del angulo central, por ley del coseno."""
    gamma = math.radians(gamma_deg)
    return math.sqrt(
        (r_km + h_km) ** 2 + r_km ** 2
        - 2.0 * (r_km + h_km) * r_km * math.cos(gamma)
    )


def elevacion_desde_angulo_central(gamma_deg: float, h_km: float,
                                   r_km: float = EARTH_RADIUS_KM) -> float:
    """Elevacion (grados) a partir del angulo central geocentrico."""
    gamma = math.radians(gamma_deg)
    k = r_km / (r_km + h_km)
    if abs(math.sin(gamma)) < 1e-12:
        return 90.0
    return math.degrees(math.atan2(math.cos(gamma) - k, math.sin(gamma)))


def distancia_satelite(elev_deg: float, h_km: float,
                       r_km: float = EARTH_RADIUS_KM) -> float:
    """Distancia oblicua (km) desde la estacion terrena al satelite.

    En el cenit se reduce a la altura orbital; en el horizonte alcanza el maximo
    de visibilidad.
    """
    if elev_deg >= 89.999:
        return h_km
    return distancia_desde_angulo_central(
        angulo_central_deg(elev_deg, h_km, r_km), h_km, r_km
    )


def periodo_orbital_s(h_km: float, r_km: float = EARTH_RADIUS_KM) -> float:
    """Periodo de una orbita circular (segundos)."""
    a_m = (r_km + h_km) * 1e3
    return 2.0 * math.pi * math.sqrt(a_m ** 3 / MU_EARTH)


def separacion_angular_deg(az1_deg: float, el1_deg: float,
                           az2_deg: float, el2_deg: float) -> float:
    """Angulo entre dos direcciones dadas en azimut/elevacion (grados).

    Necesario para el error de apuntamiento: restar azimutes por separado
    sobreestima el error a elevaciones altas, donde un grado de azimut abarca
    mucho menos que un grado de arco sobre el cielo.
    """
    el1, el2 = math.radians(el1_deg), math.radians(el2_deg)
    d_az = math.radians(az2_deg - az1_deg)
    coseno = (
        math.sin(el1) * math.sin(el2)
        + math.cos(el1) * math.cos(el2) * math.cos(d_az)
    )
    return math.degrees(math.acos(min(max(coseno, -1.0), 1.0)))


def diferencia_azimut_deg(desde_deg: float, hasta_deg: float) -> float:
    """Diferencia de azimut por el camino corto, en el rango (-180, 180]."""
    return (hasta_deg - desde_deg + 180.0) % 360.0 - 180.0


# ─── Radio ─────────────────────────────────────────────────────────────────

def fspl_db(dist_m: float, freq_hz: float) -> float:
    """Perdida de trayectoria en espacio libre (dB)."""
    return (
        20.0 * math.log10(dist_m)
        + 20.0 * math.log10(freq_hz)
        + 20.0 * math.log10(4.0 * math.pi / C_LIGHT)
    )


def temperatura_desde_figura_ruido(nf_db: float) -> float:
    """Convierte figura de ruido (dB) a temperatura equivalente de ruido (K)."""
    return (10.0 ** (nf_db / 10.0) - 1.0) * T0_K


def temperatura_sistema(t_ant_k: float, perdida_rx_db: float,
                        nf_rx_db: float) -> float:
    """Temperatura de ruido del sistema referida a la entrada del receptor.

    Los cables entre la antena y el LNA no solo atenuan la señal: tambien
    aportan su propio ruido termico y atenuan el de la antena. Sumar sin mas
    T_antena + T_receptor ignora ambos efectos y da un enlace mas optimista de
    lo que es (unos 1.5 dB con 2 dB de cable).
    """
    l = 10.0 ** (perdida_rx_db / 10.0)
    return t_ant_k / l + (l - 1.0) / l * T0_K + temperatura_desde_figura_ruido(nf_rx_db)


def densidad_ruido_dbm_hz(t_sys_k: float) -> float:
    """Densidad espectral de potencia de ruido N0 (dBm/Hz)."""
    return 10.0 * math.log10(K_BOLTZ * t_sys_k) + 30.0
