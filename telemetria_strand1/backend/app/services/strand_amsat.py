"""Decodificacion de la baliza de STRaND-1 segun la especificacion de AMSAT-UK.

Fuente: AMSAT-UK, «STRAND-1 Packet Format», hoja `amsat-strand-1-20130327.xlsx`
(https://ukamsat.files.wordpress.com/2013/03/amsat-strand-1-20130327.xlsx),
enlazada desde https://amsat-uk.org/satellites/telemetry/strand-1/strand-1-telemetry/

Por que no se usa el decodificador oficial de `satnogs-decoders`
---------------------------------------------------------------
Ese decodificador reconoce correctamente la estructura del paquete, pero su
especificacion Kaitai lee **un solo byte** por canal (`read_u1`) alli donde el
formato define un contador ADC de 2, 4 u 8 bytes precedido de su tamaño. El
resultado es que devuelve el byte de `DATA_SIZE` como si fuera la medida:

    C0 80 02 06 02 2C 03 02 00 00
                        ^^ ^^ ^^^^^
                        |  |  dato: ADC = 0x0000
                        |  DATA_SIZE = 2
                        canal 0x03 = BATTERY 0 VOLTAGE

    decodificador oficial -> battery_0_voltage_v = 2   (es el DATA_SIZE)
    especificacion AMSAT  -> -0.00945 x 0 + 9.7488 = 9.75 V

Por eso todos los campos parecian constantes: lo que se estaba leyendo era el
tamaño del campo, que efectivamente no cambia. Este modulo lee el dato completo
y le aplica la ecuacion de calibracion publicada.

Estructura del paquete
----------------------
    C0 80 | SEQ (1B) | LENGTH (1B) | ID (1B) | I2C NODE (1B) | CHANNEL (1B) |
    DATA_SIZE (1B) | DATA (DATA_SIZE bytes)

`ID` vale 0x01 para baliza de modem y 0x02 para baliza de OBC. En el enlace real
el paquete va ademas entre flags de TNC (0xC0 0x00 ... 0xC0) y con el escape
KISS que sustituye 0xC0 por 0xDB 0xDC; los archivos de demoddata de SatNOGS
llegan ya sin esa envoltura.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

FLAG_HDLC = b"\xc0\x80"

# Escape KISS: un 0xC0 dentro de los datos viaja como 0xDB 0xDC.
ESCAPE_KISS = (b"\xdb\xdc", b"\xc0")

# Los canales de los nodos 0x2C y 0x2D son convertidores de 10 bits: las rectas
# de calibracion de la hoja solo estan definidas para cuentas de 0 a 1023.
NODOS_ADC = (0x2C, 0x2D)
ADC_MAX = 1023


@dataclass(frozen=True)
class Canal:
    """Un canal de telemetria: como leerlo y como convertirlo a magnitud fisica."""

    nombre: str
    unidad: str | None = None
    # valor_fisico = m * cuenta_adc + c. Sin ecuacion, el valor se deja crudo.
    m: float | None = None
    c: float | None = None
    little_endian: bool = True
    con_signo: bool = False
    # Algunos canales empaquetan varias magnitudes en el mismo dato.
    componentes: tuple[str, ...] = ()

    def convertir(self, cuenta: int) -> float | int:
        if self.m is None:
            return cuenta
        return self.m * cuenta + (self.c or 0.0)


# ── Nodo 0x2C · C/S EPS ─────────────────────────────────────────────────────
EPS = {
    0x00: Canal("battery_0_current_direction"),
    0x01: Canal("battery_0_current", "mA", -3.4969, 3185.1551),
    0x03: Canal("battery_0_voltage", "V", -0.00945, 9.7488),
    0x04: Canal("battery_0_temperature", "°C", -0.163, 111.187),
    0x05: Canal("battery_1_current_direction"),
    0x06: Canal("battery_1_current", "mA", -3.4768, 3173.1106),
    0x08: Canal("battery_1_voltage", "V", -0.00946, 9.7526),
    0x09: Canal("battery_1_temperature", "°C", -0.163, 111.187),
}

# ── Nodo 0x2D · C/S BATTERY (paneles solares) ───────────────────────────────
BATERIA = {
    0x01: Canal("adc1_py_array_current", "mA", -0.542490348, 528.0441026),
    0x02: Canal("adc2_py_array_temperature", "°C", -0.163, 110.338),
    0x03: Canal("adc3_array_pair_y_voltage", "V", -0.035254639, 34.6505381),
    0x04: Canal("adc4_my_array_current", "mA", -0.537846059, 523.1519466),
    0x05: Canal("adc5_my_array_temperature", "°C", -0.163, 110.338),
    0x06: Canal("adc6_array_pair_x_voltage", "V", -0.035579727, 34.76510021),
    0x07: Canal("adc7_mx_array_current", "mA", -0.541228423, 526.8412823),
    0x08: Canal("adc8_mx_array_temperature", "°C", -0.163, 110.338),
    0x09: Canal("adc9_array_pair_z_voltage", "V", -0.00914561, 8.782534345),
    0x0A: Canal("adc10_pz_array_current", "mA", -0.52264946, 508.5204547),
    0x0B: Canal("adc11_pz_array_temperature", "°C", -0.163, 110.338),
    0x0D: Canal("adc13_px_array_current", "mA", -0.518702129, 512.807352),
    0x0E: Canal("adc14_px_array_temperature", "°C", -0.163, 110.338),
    0x11: Canal("adc17_battery_bus_current", "mA", -4.926127936, 4414.027999),
    0x1A: Canal("adc26_5v_bus_current", "mA", -5.431052862, 4636.008505),
    0x1B: Canal("adc27_33v_bus_current", "mA", -3.626006798, 3080.538997),
    0x1E: Canal("adc30_mz_array_temperature", "°C", -0.163, 110.338),
    0x1F: Canal("adc31_mz_array_current", "mA", -0.52947555, 515.5141451),
}

# ── Nodo 0x66 · SWITCH BOARD (big endian) ───────────────────────────────────
# Byte 1 = estado, bytes 2-3 = corriente, bytes 4-5 = tension (mV), cada uno con
# su propia recta de calibracion.
INTERRUPTORES = {
    0x81: ("switch_0_ppt_power_supply", 0.259549, -1.516825, 2.300107, -1113.424579),
    0x86: ("switch_1_ppt_1_2", 0.258359, -1.554162, 2.315349, -1136.056829),
    0x8B: ("switch_2_phone_5v_webcam", 0.259325, -1.595903, 2.3315, -1187.043977),
    0x90: ("switch_3_warp_valve", 0.518526, -8.756971, 3.667785, -7266.803691),
    0x95: ("switch_4_warp_heater", 0.534516, -3.25046, 2.603641, -0.504061),
    0x9A: ("switch_5_digi_wi9c", 0.528245, -2.974109, 2.233264, -930.303516),
    0x9F: ("switch_6_sgr05", 0.260476, -0.91132, 2.254974, -993.915009),
    0xA4: ("switch_7_reaction_wheels", 0.532941, -3.152331, 2.592693, 3.656067),
    # La hoja no publica rectas para los interruptores 8 y 9.
    0xA9: ("switch_8_solar_panel_deploy_arm", None, None, None, None),
    0xAC: ("switch_9_solar_panel_deploy_fire", None, None, None, None),
}

ESTADO_INTERRUPTOR = {
    0x00: "OFF",
    0x01: "ON",
    0x02: "OFF (sobrecorriente)",
    0x05: "ON en sobrecorriente",
    0x08: "OFF por tiempo maximo",
    0x10: "OFF por causa desconocida",
}

# ── Nodo 0x80 · OBC ─────────────────────────────────────────────────────────
# El canal 0x0C llega con DATA_SIZE = 8 pero la hoja solo define los primeros
# 4 bytes («4B UNIX TIME, LITTLE ENDIAN»). Los otros 4 se conservan sin
# interpretar en vez de inventarles un significado.
OBC = {
    0x0C: Canal("obc_unix_time", "s", componentes=("obc_unix_time", "obc_campo_2")),
}

# ── Nodo 0x89 · Magnetometros ───────────────────────────────────────────────
MAGNETOMETROS = {
    0x03: Canal("magnetometer", componentes=("magnetometer_x", "magnetometer_y"), con_signo=True),
    0x05: Canal("magnetometer", componentes=("magnetometer_z",), con_signo=True),
}

NODOS = {
    0x2C: ("eps", EPS),
    0x2D: ("bateria", BATERIA),
    0x66: ("switch_board", None),
    0x80: ("obc", OBC),
    0x89: ("magnetometros", MAGNETOMETROS),
}


@dataclass
class Baliza:
    seq_no: int
    length: int
    packet_type: int
    nodo: int
    nodo_nombre: str
    canal: int
    data_size: int
    datos: bytes
    valores: dict[str, Any] = field(default_factory=dict)
    unidades: dict[str, str | None] = field(default_factory=dict)
    # Cierto cuando la cuenta ADC sale del dominio de la recta de calibracion y
    # por eso el canal se queda sin valor fisico (ver `decodificar`).
    fuera_de_rango: bool = False


def desescapar_kiss(data: bytes) -> bytes:
    return data.replace(*ESCAPE_KISS)


def _entero(data: bytes, little_endian: bool = True, con_signo: bool = False) -> int:
    return int.from_bytes(data, "little" if little_endian else "big", signed=con_signo)


def _decodificar_interruptor(canal: int, datos: bytes) -> tuple[dict, dict]:
    """Estado, corriente y tension de un interruptor (big endian)."""
    nombre, m_i, c_i, m_v, c_v = INTERRUPTORES[canal]
    valores: dict[str, Any] = {}
    unidades: dict[str, str | None] = {}

    if len(datos) >= 1:
        estado = datos[0]
        valores[f"{nombre}_estado"] = ESTADO_INTERRUPTOR.get(estado, f"0x{estado:02X}")
        unidades[f"{nombre}_estado"] = None
    if len(datos) >= 3 and m_i is not None:
        cuenta = _entero(datos[1:3], little_endian=False)
        valores[f"{nombre}_corriente"] = m_i * cuenta + c_i
        unidades[f"{nombre}_corriente"] = "mA"
    if len(datos) >= 5 and m_v is not None:
        cuenta = _entero(datos[3:5], little_endian=False)
        valores[f"{nombre}_tension"] = m_v * cuenta + c_v
        unidades[f"{nombre}_tension"] = "mV"
    return valores, unidades


def decodificar(trama: bytes) -> Baliza | None:
    """Decodifica una baliza. Devuelve None si la trama no lo es."""
    data = desescapar_kiss(trama)
    if not data.startswith(FLAG_HDLC) or len(data) < 8:
        return None

    seq_no, length, packet_type, nodo, canal, data_size = data[2:8]
    if packet_type not in (0x01, 0x02):
        return None

    datos = data[8:8 + data_size]
    if not datos:
        return None

    nodo_nombre, tabla = NODOS.get(nodo, (f"desconocido_0x{nodo:02X}", None))
    baliza = Baliza(seq_no, length, packet_type, nodo, nodo_nombre, canal, data_size, datos)

    if nodo == 0x66:
        if canal in INTERRUPTORES:
            baliza.valores, baliza.unidades = _decodificar_interruptor(canal, datos)
        return baliza

    if tabla is None or canal not in tabla:
        return baliza

    spec = tabla[canal]

    if spec.componentes:
        # Varias magnitudes de 4 bytes en el mismo dato: los ejes del
        # magnetometro, o el tiempo UNIX seguido de un campo no documentado.
        for i, componente in enumerate(spec.componentes):
            trozo = datos[i * 4:(i + 1) * 4]
            if len(trozo) == 4:
                baliza.valores[componente] = _entero(trozo, spec.little_endian, spec.con_signo)
                baliza.unidades[componente] = spec.unidad if i == 0 else None
        return baliza

    cuenta = _entero(datos, spec.little_endian, spec.con_signo)

    # La cuenta cruda se guarda siempre: es el dato tal como llego.
    baliza.valores[f"{spec.nombre}_adc"] = cuenta
    baliza.unidades[f"{spec.nombre}_adc"] = "cuenta"

    # El valor calibrado, solo si la cuenta cae dentro del dominio de la recta.
    # Una cuenta por encima de 1023 no puede venir de un convertidor de 10 bits
    # y, extrapolada, produce imposibles: -19 V de bateria en tramas de
    # 2019-11-30. En esas tramas los 10 bits bajos si caen en rango y los altos
    # parecen llevar estado, pero la hoja de AMSAT-UK no documenta tal
    # empaquetado; enmascararlos seria inventar la interpretacion. Se deja el
    # canal sin valor fisico antes que publicar uno falso.
    if baliza.nodo in NODOS_ADC and not 0 <= cuenta <= ADC_MAX:
        baliza.fuera_de_rango = True
        return baliza

    baliza.valores[spec.nombre] = spec.convertir(cuenta)
    baliza.unidades[spec.nombre] = spec.unidad
    return baliza
