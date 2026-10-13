"""Fuente unica de los parametros del enlace descendente de STRaND-1.

Antes cada script repetia sus constantes y dos de ellos discrepaban (el modelo
de estacion terrena no restaba la perdida de polarizacion que si restaba el
link budget). Este modulo las centraliza y, sobre todo, declara **de donde sale
cada valor**: documentado por una fuente de la mision, deducido de datos, o
supuesto de diseño sin respaldo propio de STRaND-1.

Modulacion real frente a modulacion del modelo
----------------------------------------------
La modulacion documentada del enlace descendente es **FSK a 9600 bit/s con
tramas AX.25 (HDLC) y codificacion NRZI** (AMSAT-UK; registro de transmisores
de SatNOGS DB; recepcion de PY4ZBZ con modem G3RUH). Ninguna fuente consultada
describe BPSK en STRaND-1. La BPSK coherente que usan el modelo avanzado y la
cadena GNU Radio es, por tanto, un **modelo comparativo de banda base**, no la
forma de onda del satelite.

Lo que NO esta documentado y se trata como incertidumbre: desviacion de
frecuencia, filtrado del modulador, uso de aleatorizador G3RUH en el satelite,
ganancia de antena y umbral de Eb/N0 del receptor real.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ─── Procedencia ────────────────────────────────────────────────────────────

DOCUMENTADO = "documentado"      # lo afirma una fuente de la mision o registro
DEDUCIDO = "deducido"            # calculado a partir de datos versionados
SUPUESTO = "supuesto"            # valor de diseño tipico, sin fuente de STRaND-1


@dataclass(frozen=True)
class Parametro:
    valor: float
    unidad: str
    procedencia: str
    fuente: str
    # Semiancho de la incertidumbre usada en el analisis de sensibilidad, en la
    # misma unidad que `valor`. None = no se varia.
    incertidumbre: float | None = None


FUENTE_AMSAT = "AMSAT-UK, «STRaND-1 Telemetry» (amsat-uk.org/satellites/telemetry/strand-1)"
FUENTE_SATNOGS = "SatNOGS DB, transmisor «UHF 9k6 FSK TLM» de NORAD 39090 (estado: inactive)"
FUENTE_EOPORTAL = "eoPortal, «STRaND-1» (eoportal.org/satellite-missions/strand-1)"
FUENTE_TLE = "TLE versionado tle/strand1_2026-08-09.tle"
FUENTE_DISENO = "valor tipico de diseño (Larson & Wertz, SMAD); no es un dato de STRaND-1"

PARAMETROS: dict[str, Parametro] = {
    "frecuencia_hz": Parametro(437.568e6, "Hz", DOCUMENTADO,
        FUENTE_AMSAT + "; " + FUENTE_SATNOGS
        + ". eoPortal cita 437.575 MHz como asignacion previa al lanzamiento."),
    "tasa_bit_bps": Parametro(9600.0, "bit/s", DOCUMENTADO, FUENTE_AMSAT + "; " + FUENTE_SATNOGS),
    "altura_orbital_km": Parametro(775.0, "km", DEDUCIDO,
        FUENTE_TLE + " (movimiento medio -> semieje mayor 7146 km). eoPortal: ~786 km en 2013."),
    # eoPortal: «nominal RF output power of 1 W, which can be increased to 1.5 W
    # [...] in beacon / CW mode the RF output power will be reduced to 0.25 W».
    # El modo en que emite la baliza de telemetria no esta confirmado, asi que
    # el caso de 0.25 W (-6 dB) entra en la sensibilidad.
    "p_tx_dbm": Parametro(30.0, "dBm", DOCUMENTADO,
        FUENTE_EOPORTAL + ": 1 W nominal; 0.25 W en modo baliza/CW", incertidumbre=6.0),
    "g_tx_dbi": Parametro(0.0, "dBi", SUPUESTO,
        "monopolo UHF (eoPortal confirma el tipo de antena, no su ganancia)", incertidumbre=2.0),
    "l_tx_db": Parametro(0.5, "dB", SUPUESTO, FUENTE_DISENO, incertidumbre=0.5),
    "g_rx_dbi": Parametro(15.0, "dBi", SUPUESTO,
        "Yagi UHF de 11-13 elementos: estacion hipotetica del proyecto", incertidumbre=2.0),
    "l_rx_db": Parametro(2.0, "dB", SUPUESTO, FUENTE_DISENO, incertidumbre=1.0),
    "nf_rx_db": Parametro(2.0, "dB", SUPUESTO, FUENTE_DISENO, incertidumbre=1.0),
    "t_ant_k": Parametro(150.0, "K", SUPUESTO,
        FUENTE_DISENO + "; el ruido urbano en UHF puede superarlo ampliamente", incertidumbre=100.0),
    "l_atm_db": Parametro(0.5, "dB", SUPUESTO, FUENTE_DISENO, incertidumbre=0.5),
    # Monopolo lineal en el satelite, sin control de actitud garantizado, contra
    # una Yagi lineal: el desajuste real varia entre 0 dB y nulos profundos con
    # la rotacion de Faraday y la actitud. 1 dB es una reserva, no una medida.
    "l_pol_db": Parametro(1.0, "dB", SUPUESTO,
        FUENTE_DISENO + "; con polarizacion lineal-lineal el valor real es variable (ver informe)",
        incertidumbre=2.0),
    "l_point_db": Parametro(1.0, "dB", SUPUESTO,
        FUENTE_DISENO + "; en el paso SGP4 se sustituye por la perdida calculada del rotor",
        incertidumbre=1.0),
    # Reserva de diseño para la degradacion del modem real respecto de la curva
    # teorica (sincronizacion, filtrado, cuantizacion). No es una perdida fisica
    # del trayecto y NO debe sumarse cuando el umbral ya procede del receptor
    # simulado, que incluye esas degradaciones: seria contarlas dos veces.
    "l_impl_db": Parametro(2.0, "dB", SUPUESTO,
        FUENTE_DISENO + " (reserva de implementacion del demodulador)", incertidumbre=2.0),
}

BER_OBJETIVO = 1e-5


def valor(nombre: str) -> float:
    return PARAMETROS[nombre].valor


# ─── Curvas de BER teoricas en AWGN ─────────────────────────────────────────

def q_func(x: float) -> float:
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def ber_bpsk_coherente(ebn0_lineal: float) -> float:
    """BPSK/antipodal con deteccion coherente: Q(sqrt(2 Eb/N0))."""
    return q_func(math.sqrt(2.0 * ebn0_lineal))


def ber_fsk_coherente(ebn0_lineal: float) -> float:
    """FSK binaria ortogonal con deteccion coherente: Q(sqrt(Eb/N0))."""
    return q_func(math.sqrt(ebn0_lineal))


def ber_fsk_no_coherente(ebn0_lineal: float) -> float:
    """FSK binaria ortogonal con deteccion de envolvente: 0.5 exp(-Eb/2N0)."""
    return 0.5 * math.exp(-ebn0_lineal / 2.0)


@dataclass(frozen=True)
class Esquema:
    clave: str
    nombre: str
    ber: object            # funcion Eb/N0 lineal -> BER
    papel: str             # relacion con el satelite real
    nota: str


ESQUEMAS: dict[str, Esquema] = {
    "fsk_no_coherente": Esquema(
        "fsk_no_coherente", "FSK binaria ortogonal, deteccion no coherente",
        ber_fsk_no_coherente,
        "referencia del enlace documentado (FSK 9600)",
        "Cota teorica de la familia FSK. Un receptor G3RUH real demodula con "
        "discriminador de FM y su umbral no esta documentado para STRaND-1: se "
        "trata como incertidumbre, no como valor confirmado.",
    ),
    "fsk_coherente": Esquema(
        "fsk_coherente", "FSK binaria ortogonal, deteccion coherente",
        ber_fsk_coherente,
        "cota optimista de FSK",
        "Requiere recuperar la fase de ambos tonos; no es lo habitual en UHF amateur.",
    ),
    "bpsk_coherente": Esquema(
        "bpsk_coherente", "BPSK, deteccion coherente",
        ber_bpsk_coherente,
        "modelo comparativo (no es la modulacion documentada de STRaND-1)",
        "Es el esquema del modelo avanzado y de la cadena GNU Radio del proyecto.",
    ),
}

ESQUEMA_DOCUMENTADO = "fsk_no_coherente"
ESQUEMA_MODELO = "bpsk_coherente"


def ebn0_requerida_db(esquema: str, ber_objetivo: float = BER_OBJETIVO) -> float:
    """Eb/N0 teorica (dB) que da `ber_objetivo`, por biseccion sobre la curva.

    Sustituye al valor escrito a mano (10.0 dB «para BPSK ~1e-5»): el umbral se
    calcula de la curva, de modo que cambiar el objetivo o el esquema no deja
    un numero huerfano.
    """
    f = ESQUEMAS[esquema].ber
    lo, hi = -10.0, 40.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if f(10.0 ** (mid / 10.0)) > ber_objetivo:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
