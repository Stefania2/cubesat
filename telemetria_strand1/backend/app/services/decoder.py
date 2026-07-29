"""Analisis y clasificacion de frames de telemetria.

Regla fundamental del modulo: **nunca se asigna significado fisico a un byte sin
una definicion de protocolo validada**. Todo lo que este modulo produce es una de
estas dos cosas:

  1. Metricas objetivas sobre los bytes (longitud, entropia, bytes imprimibles).
     Son ciertas con independencia del protocolo.
  2. Evidencia estructural: se busca una estructura conocida (banderas AX.25, un
     campo de direcciones con indicativos plausibles, un FCS que cuadre) y se
     informa de si aparece o no.

Si no hay definicion de protocolo validada para el satelite, el frame se queda en
`unclassified` y la telemetria se reporta como no decodificada. Para STRaND-1 no
existe hoy una especificacion publica verificada del formato de telemetria; el
propio SatNOGS DB entrega los 100 frames de este conjunto con el campo `decoded`
vacio, lo que es consistente con esa situacion.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field, asdict

AX25_FLAG = 0x7E
CRC16_X25_POLY_REFLECTED = 0x8408


# ─── Metricas objetivas ─────────────────────────────────────────────────────

def parse_hex(raw: str) -> bytes:
    """Convierte una cadena hexadecimal a bytes, tolerando espacios y saltos."""
    limpio = "".join(c for c in raw if not c.isspace()).replace("0x", "")
    if len(limpio) % 2:
        raise ValueError("La cadena hexadecimal tiene un numero impar de digitos.")
    try:
        return bytes.fromhex(limpio)
    except ValueError as exc:
        raise ValueError(f"Cadena hexadecimal invalida: {exc}") from exc


def shannon_entropy(data: bytes) -> float:
    """Entropia de Shannon en bits por byte (0 a 8)."""
    if not data:
        return 0.0
    total = len(data)
    return -sum(
        (n / total) * math.log2(n / total) for n in Counter(data).values()
    )


def printable_ratio(data: bytes) -> float:
    """Proporcion de bytes ASCII imprimibles."""
    if not data:
        return 0.0
    return sum(1 for b in data if 0x20 <= b <= 0x7E) / len(data)


def ax25_fcs(data: bytes) -> int:
    """FCS de AX.25 (CRC-16/X-25)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ CRC16_X25_POLY_REFLECTED if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


# ─── Busqueda de estructura conocida ────────────────────────────────────────

def _decode_ax25_callsign(chunk: bytes) -> str | None:
    """Intenta leer 7 bytes como un campo de direccion AX.25.

    Devuelve el indicativo si todos los caracteres resultan alfanumericos tras
    deshacer el desplazamiento de un bit; None si el campo no encaja.
    """
    if len(chunk) != 7:
        return None
    chars = []
    for b in chunk[:6]:
        if b & 0x01:  # el bit 0 debe estar libre en los seis primeros bytes
            return None
        c = chr(b >> 1)
        if not (c.isalnum() or c == " "):
            return None
        chars.append(c)
    ssid = (chunk[6] >> 1) & 0x0F
    base = "".join(chars).strip()
    if not base:
        return None
    return f"{base}-{ssid}" if ssid else base


def buscar_estructura_ax25(data: bytes) -> dict:
    """Busca indicios de encapsulado AX.25 y verifica el FCS si los hay."""
    resultado: dict = {
        "flags_encontradas": data.count(AX25_FLAG),
        "campo_direcciones_plausible": False,
        "destino": None,
        "origen": None,
        "fcs_valido": None,
    }

    # Variante con banderas de delimitacion.
    if len(data) >= 20 and data[0] == AX25_FLAG and data[-1] == AX25_FLAG:
        campos, fcs = data[1:-3], data[-3:-1]
        resultado["fcs_valido"] = ax25_fcs(campos).to_bytes(2, "little") == fcs
        cuerpo = campos
    elif len(data) >= 16:
        # Variante sin banderas (KISS): direcciones al principio, FCS al final.
        cuerpo = data
        resultado["fcs_valido"] = (
            ax25_fcs(data[:-2]).to_bytes(2, "little") == data[-2:]
        )
    else:
        return resultado

    destino = _decode_ax25_callsign(cuerpo[0:7])
    origen = _decode_ax25_callsign(cuerpo[7:14])
    if destino and origen:
        resultado.update(
            campo_direcciones_plausible=True, destino=destino, origen=origen
        )
    return resultado


def detectar_patrones(data: bytes) -> dict:
    """Patrones simples y verificables en la secuencia de bytes."""
    conteo = Counter(data)
    byte_dominante, repeticiones = conteo.most_common(1)[0] if data else (None, 0)
    return {
        "todos_iguales": len(conteo) == 1 and len(data) > 1,
        "byte_dominante": f"0x{byte_dominante:02X}" if byte_dominante is not None else None,
        "fraccion_byte_dominante": round(repeticiones / len(data), 4) if data else 0.0,
        "bytes_distintos": len(conteo),
        "empieza_por_flag_ax25": bool(data) and data[0] == AX25_FLAG,
    }


# ─── Resultado del analisis ─────────────────────────────────────────────────

@dataclass
class ResultadoAnalisis:
    byte_count: int
    entropy_bits_per_byte: float
    printable_ratio: float
    distinct_bytes: int
    status: str
    frame_type: str
    protocol: str | None
    analysis: dict = field(default_factory=dict)
    mensaje: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def analizar_frame(data: bytes, protocolos_validados: list | None = None) -> ResultadoAnalisis:
    """Analiza un frame y lo clasifica sin interpretar su contenido.

    `protocolos_validados` son definiciones de protocolo marcadas como validadas
    para este satelite. Mientras la lista este vacia ningun frame puede alcanzar
    el estado `decoded`.
    """
    protocolos_validados = protocolos_validados or []

    ax25 = buscar_estructura_ax25(data)
    patrones = detectar_patrones(data)
    analisis = {"ax25": ax25, "patrones": patrones}

    entropia = shannon_entropy(data)
    imprimibles = printable_ratio(data)

    # Clasificacion. El orden va de lo mas objetivo a lo mas especulativo, y en
    # ningun caso se traduce un byte a una magnitud fisica.
    if not data:
        status, tipo, protocolo = "error", "empty", None
        mensaje = "Frame vacio: no hay bytes que analizar."
    elif len(data) < 8:
        status, tipo, protocolo = "unclassified", "fragment", None
        mensaje = (
            f"Frame de {len(data)} byte(s). Demasiado corto para contener una "
            "cabecera de enlace completa; probablemente un fragmento de una "
            "recepcion parcial."
        )
    elif patrones["todos_iguales"]:
        status, tipo, protocolo = "error", "constant", None
        mensaje = (
            f"Todos los bytes son {patrones['byte_dominante']}. Es indicativo de "
            "una recepcion sin señal o de un fallo del demodulador."
        )
    elif ax25["campo_direcciones_plausible"] and ax25["fcs_valido"]:
        status, tipo, protocolo = "partially_decoded", "ax25_ui", "AX.25"
        mensaje = (
            f"Encapsulado AX.25 verificado por FCS: {ax25['origen']} -> "
            f"{ax25['destino']}. La capa de enlace queda decodificada, pero el "
            "significado del campo de informacion sigue sin protocolo validado."
        )
    elif ax25["campo_direcciones_plausible"]:
        status, tipo, protocolo = "unclassified", "ax25_candidate", None
        mensaje = (
            "El campo de direcciones podria ser AX.25, pero el FCS no cuadra. "
            "No se asume el protocolo."
        )
    else:
        status, tipo, protocolo = "unclassified", "unclassified", None
        mensaje = (
            "No se reconoce ninguna estructura de protocolo validada. Los bytes "
            "se conservan en crudo sin interpretar."
        )

    if not protocolos_validados and status == "decoded":
        # Salvaguarda: sin definicion validada no se permite el estado decoded.
        status, mensaje = "partially_decoded", mensaje + " (sin protocolo validado registrado)"

    return ResultadoAnalisis(
        byte_count=len(data),
        entropy_bits_per_byte=round(entropia, 4),
        printable_ratio=round(imprimibles, 4),
        distinct_bytes=patrones["bytes_distintos"],
        status=status,
        frame_type=tipo,
        protocol=protocolo,
        analysis=analisis,
        mensaje=mensaje,
    )


def analizar_hex(raw: str, protocolos_validados: list | None = None) -> dict:
    """Punto de entrada del decodificador manual de la interfaz."""
    data = parse_hex(raw)
    resultado = analizar_frame(data, protocolos_validados)
    salida = resultado.to_dict()
    salida["bytes"] = [f"{b:02X}" for b in data]
    salida["decoded"] = resultado.status in ("decoded", "partially_decoded")
    salida["pipeline"] = [
        {"paso": "RAW HEX", "estado": "ok", "detalle": f"{len(raw.strip())} caracteres"},
        {"paso": "BYTES", "estado": "ok", "detalle": f"{len(data)} bytes"},
        {
            "paso": "FRAME IDENTIFICATION",
            "estado": "ok" if resultado.frame_type != "unclassified" else "pendiente",
            "detalle": resultado.frame_type,
        },
        {
            "paso": "PROTOCOL",
            "estado": "ok" if resultado.protocol else "pendiente",
            "detalle": resultado.protocol or "Unknown",
        },
        {
            "paso": "PAYLOAD",
            "estado": "pendiente" if not resultado.protocol else "ok",
            "detalle": "Sin delimitar" if not resultado.protocol else "Delimitado por la cabecera",
        },
        {
            "paso": "DECODED TELEMETRY",
            "estado": "pendiente",
            "detalle": "Requiere definicion de protocolo validada",
        },
    ]
    return salida
