"""Decodificacion de la baliza de STRaND-1 con el decodificador oficial.

A diferencia del resto del proyecto, aqui si se traducen bytes a magnitudes
fisicas. Puede hacerse porque existe una especificacion publicada y una
implementacion de referencia mantenida por la comunidad:

  - Especificacion: AMSAT-UK, «STRaND-1 Telemetry»
    https://amsat-uk.org/satellites/telemetry/strand-1/strand-1-telemetry/
    (hoja de calculo original: ukamsat.files.wordpress.com/2013/03/amsat-strand-1-20130327.xlsx)
  - Implementacion: `satnogsdecoders.decoder.Strand`, el decodificador que
    SatNOGS DB declara para este satelite (`telemetries: [{'decoder': 'strand'}]`).

No se reimplementa el formato: se delega en esa libreria. Si un frame no encaja
en la estructura que describe la especificacion, no se decodifica y punto — no
se rellena ningun valor por aproximacion.

Estructura que exige el formato: flag HDLC `C0 80`, numero de secuencia,
longitud, tipo de paquete (1 = baliza de modem, 2 = baliza de OBC), cuerpo y
CRC-16/CCITT.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

NOMBRE_PROTOCOLO = "STRaND-1 beacon (AMSAT-UK)"
REFERENCIA = (
    "AMSAT-UK, STRaND-1 Telemetry "
    "(https://amsat-uk.org/satellites/telemetry/strand-1/strand-1-telemetry/); "
    "implementacion: satnogsdecoders.decoder.Strand, el decodificador que "
    "SatNOGS DB declara para NORAD 39090"
)

# Flag HDLC con el que empieza toda baliza valida de STRaND-1.
FLAG_HDLC = b"\xc0\x80"

# Correspondencia entre los parametros que muestra la interfaz y los campos que
# produce el decodificador oficial. Solo estan los que la especificacion define:
# un parametro sin campo equivalente se queda sin valor antes que aproximarlo.
#
# Varias magnitudes existen por duplicado en el satelite (dos baterias, varios
# paneles). Se toma la primera disponible de la lista y se anota cual fue.
# Solo se mapea lo que la especificacion nombra de forma inequivoca. Los
# parametros que la interfaz pide pero el formato no define se quedan vacios:
#
#   - Magnetometer X/Y/Z: la baliza expone `magnetometer_set_1` y
#     `magnetometer_set_2`, que son dos conjuntos de sensores, no tres ejes.
#     Asignarlos a X e Y seria inventarse la correspondencia.
#   - OBC Uptime: el campo mas parecido es `time_since_last_obc_i2c_message`,
#     que mide otra cosa (silencio en el bus I2C, no tiempo encendido).
#   - System Status: no existe. Lo que hay son diez interruptores concretos.
MAPEO: dict[str, list[str]] = {
    "battery_voltage": ["battery_0_voltage", "battery_1_voltage"],
    "battery_current": ["battery_0_current", "battery_1_current"],
    "temperature": ["battery_0_temperature", "battery_1_temperature",
                    "adc2_py_array_temperature", "adc5_my_array_temperature"],
    "obc_uptime": ["obc_unix_time"],
    "magnetometer_x": ["magnetometer_x"],
    "magnetometer_y": ["magnetometer_y"],
    "magnetometer_z": ["magnetometer_z"],
    "system_status": ["switch_0_ppt_power_supply_estado"],
}

# Unidades fisicas, ya calibradas segun las ecuaciones de AMSAT-UK.
UNIDADES = {
    "battery_voltage": "V",
    "battery_current": "mA",
    "temperature": "°C",
    "obc_uptime": "s",
    "magnetometer_x": "cuenta",
    "magnetometer_y": "cuenta",
    "magnetometer_z": "cuenta",
    "system_status": None,
}


class DecodificadorNoDisponible(RuntimeError):
    """`satnogsdecoders` no esta instalado o no expone el decodificador."""


def _cargar():
    """Importa el decodificador oficial solo cuando hace falta.

    Se aisla el import porque `satnogsdecoders` arrastra `pkg_resources`, que
    Python 3.14 ya no trae de serie: si falta, la aplicacion tiene que seguir
    arrancando y limitarse a no decodificar.
    """
    try:
        from satnogsdecoders.decoder import Strand, get_fields
    except Exception as exc:  # ImportError y fallos de dependencias transitivas
        raise DecodificadorNoDisponible(str(exc)) from exc
    return Strand, get_fields


def disponible() -> bool:
    try:
        _cargar()
        return True
    except DecodificadorNoDisponible:
        return False


def tiene_estructura(data: bytes) -> bool:
    """Comprueba el flag HDLC antes de intentar decodificar.

    Sirve para distinguir dos situaciones que no son lo mismo: un frame que no
    es una baliza de STRaND-1, y una baliza que si lo es pero llega corrupta.
    """
    return data[:2] == FLAG_HDLC


def decodificar(data: bytes) -> dict[str, Any] | None:
    """Devuelve los campos de la baliza, o None si el frame no es una.

    Nunca lanza: un frame que no encaja simplemente no se decodifica.
    """
    if not tiene_estructura(data):
        return None
    try:
        Strand, get_fields = _cargar()
    except DecodificadorNoDisponible as exc:
        logger.warning("Decodificador de STRaND-1 no disponible: %s", exc)
        return None

    try:
        campos = get_fields(Strand.from_bytes(data))
    except Exception as exc:
        logger.debug("Frame con flag HDLC pero no decodificable: %s", exc)
        return None

    return campos or None


def a_parametros(campos: dict[str, Any]) -> dict[str, tuple[Any, str]]:
    """Traduce los campos del decodificador a los parametros de la interfaz.

    Devuelve `{clave_parametro: (valor, campo_de_origen)}`. El campo de origen se
    guarda para que en la interfaz pueda verse de donde sale cada numero.
    """
    salida: dict[str, tuple[Any, str]] = {}
    for parametro, candidatos in MAPEO.items():
        for campo in candidatos:
            if campo in campos and campos[campo] is not None:
                salida[parametro] = (campos[campo], campo)
                break
    return salida


def field_spec() -> list[dict[str, Any]]:
    """Descripcion de los campos para guardar en `protocol_definitions`."""
    return [
        {
            "parametro": parametro,
            "campos_origen": candidatos,
            "unidad": UNIDADES.get(parametro),
        }
        for parametro, candidatos in MAPEO.items()
    ]
