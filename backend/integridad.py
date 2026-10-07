"""Integridad de los 18.776 bits STRAND-1.

Regla critica del proyecto: los 18.776 bits de telemetria deben conservarse de
entrada a salida. Este modulo carga los archivos de bits y los valida
(longitud exacta, diferencia por bits y SHA-256). No modifica ningun archivo:
solo lee copias del estado de la simulacion.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .config import BITS_TX, BITS_RX, BITS_RX_SIM, N_BITS
from .models import IntegridadBit


def cargar_bits(ruta: Path) -> np.ndarray:
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo de bits: {ruta}")
    return np.frombuffer(ruta.read_bytes(), dtype=np.uint8)


def sha256_bits(bits: np.ndarray) -> str:
    return hashlib.sha256(bits.tobytes()).hexdigest()


def validar_bits(ruta_rx: Path = BITS_RX) -> IntegridadBit:
    tx = cargar_bits(BITS_TX)
    rx = cargar_bits(ruta_rx)
    m = min(len(tx), len(rx))
    diferencia = int(np.count_nonzero(tx[:m] != rx[:m])) if m else -1
    valido = (
        len(tx) == N_BITS
        and len(rx) == N_BITS
        and diferencia == 0
        and sha256_bits(tx) == sha256_bits(rx)
    )
    return IntegridadBit(
        valido=valido,
        bits_entrada=len(tx),
        bits_recuperados=len(rx),
        diferencia=diferencia,
        sha256_entrada=sha256_bits(tx),
        sha256_recuperado=sha256_bits(rx),
        frames_esperados=100,
        mensaje=(
            "18.776 bits de entrada y salida identicos"
            if valido
            else f"discrepancia detectada ({len(tx)} vs {len(rx)}, diff={diferencia})"
        ),
    )


def assert_bits_completos(bits: np.ndarray, nombre: str) -> None:
    if len(bits) != N_BITS:
        raise AssertionError(
            f"{nombre} debe tener exactamente {N_BITS} bits, tiene {len(bits)}"
        )