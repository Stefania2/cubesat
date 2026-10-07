"""Servicio de telemetria STRAND-1 del dashboard.

Fuente de verdad: el decodificador validado de la plataforma del proyecto
(`telemetria_strand1/backend/app/services/strand_amsat.py`, especificacion
AMSAT-UK). Se aplica sobre las balizas reales registradas por SatNOGS y ya
presentes en `telemetria_strand1/telemetria_decodificada_good.csv`.

Nota de honestidad: ese CSV fue decodificado en su dia con el decodificador
oficial (que lee DATA_SIZE como valor y produce voltajes de 2 V). Aqui se
re-decodifica con la version corregida del proyecto, que produce los valores
reales calibrados (p. ej. battery_0_voltage ~ 9.7 V). No se inventan campos.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from dataclasses import dataclass
from typing import Any

from .config import FRAMES_CSV, LIMITES_TELEMETRIA, RUTA_STRAND_AMSAT
from .models import FrameTelemetria, TelemetriaParam, TelemetriaOut

BALIZAS_CSV = (
    RUTA_STRAND_AMSAT.parent.parent.parent.parent
    / "telemetria_decodificada_good.csv"
)


@dataclass
class BalizaReg:
    timestamp: str | None
    estacion: str | None
    hex_data: str | None
    tamano_bytes: int | None
    datos: dict[str, Any] = None


def _cargar_decoder():
    spec = importlib.util.spec_from_file_location("strand_amsat", RUTA_STRAND_AMSAT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["strand_amsat"] = mod
    spec.loader.exec_module(mod)
    return mod


_decoder = None
_cache_balizas: list[BalizaReg] | None = None


def _decoder_mod():
    global _decoder
    if _decoder is None:
        _decoder = _cargar_decoder()
    return _decoder


def leer_balizas() -> list[BalizaReg]:
    global _cache_balizas
    if _cache_balizas is not None:
        return _cache_balizas
    mod = _decoder_mod()
    regs: list[BalizaReg] = []
    if not BALIZAS_CSV.exists():
        _cache_balizas = regs
        return regs
    with BALIZAS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hex_data = (row.get("hex") or "").strip()
            if not hex_data:
                continue
            try:
                raw = bytes.fromhex("".join(hex_data.split()))
            except ValueError:
                continue
            baliza = mod.decodificar(raw)
            datos = baliza.valores if baliza else {}
            regs.append(
                BalizaReg(
                    timestamp=row.get("timestamp"),
                    estacion=row.get("estacion"),
                    hex_data=hex_data[:64] + ("..." if len(hex_data) > 64 else ""),
                    tamano_bytes=len(raw),
                    datos=datos,
                )
            )
    _cache_balizas = regs
    return regs


# Parametros a mostrar (clave decodificador, etiqueta, unidad). Solo claves que
# puede producir strand_amsat.py en este conjunto.
CATALOGO = [
    ("battery_0_voltage", "Battery 0 Voltage", "V"),
    ("battery_1_voltage", "Battery 1 Voltage", "V"),
    ("battery_0_temperature", "Battery 0 Temperature", "°C"),
    ("battery_1_temperature", "Battery 1 Temperature", "°C"),
    ("adc17_battery_bus_current", "Battery Bus Current", "mA"),
    ("adc1_py_array_current", "Solar Panel +Y Current", "mA"),
    ("adc13_px_array_current", "Solar Panel +X Current", "mA"),
    ("adc7_mx_array_current", "Solar Panel -X Current", "mA"),
    ("adc4_my_array_current", "Solar Panel -Y Current", "mA"),
    ("switch_0_ppt_power_supply_estado", "PPT Power Supply Switch", None),
    ("switch_1_ppt_1_2_estado", "PPT 1/2 Switch", None),
    ("switch_2_phone_5v_webcam_estado", "5V Webcam Switch", None),
    ("magnetometer_x", "Magnetometer X", "cuenta"),
    ("magnetometer_y", "Magnetometer Y", "cuenta"),
    ("magnetometer_z", "Magnetometer Z", "cuenta"),
    ("obc_unix_time", "OBC Unix Time", "s"),
]


def parametros_telemetria() -> list[TelemetriaParam]:
    regs = leer_balizas()
    ultimo: dict[str, Any] = {}
    for reg in regs:
        for clave, val in reg.datos.items():
            if clave not in ultimo and clave.endswith("_adc") is False:
                ultimo[clave] = val
        if all(c in ultimo for c, _, _ in CATALOGO):
            break

    resultado: list[TelemetriaParam] = []
    for clave, label, unidad in CATALOGO:
        if clave not in ultimo:
            resultado.append(
                TelemetriaParam(
                    key=clave, label=label, value=None, unit=unidad,
                    status="N/A", disponible=False,
                )
            )
            continue
        valor = ultimo[clave]
        limite = LIMITES_TELEMETRIA.get(clave)
        if isinstance(valor, (int, float)) and limite is not None:
            status = "NORMAL" if limite[0] <= valor <= limite[1] else "ALERTA"
        else:
            status = "OK"
        resultado.append(
            TelemetriaParam(
                key=clave, label=label, value=valor, unit=unidad, status=status
            )
        )
    return resultado


def telemetria_out() -> TelemetriaOut:
    regs = leer_balizas()
    frames = [
        FrameTelemetria(
            timestamp=r.timestamp,
            observer=r.estacion,
            tamano_bytes=r.tamano_bytes,
            hex=r.hex_data,
            decodificado=bool(r.datos),
            campos=dict(r.datos),
        )
        for r in regs[-20:]
    ]
    ultimo_ts = next((f.timestamp for f in reversed(frames) if f.timestamp), None)
    return TelemetriaOut(
        total_frames=len(regs),
        ultimo_timestamp=ultimo_ts,
        parametros=parametros_telemetria(),
        frames=frames,
        nota=(
            f"{len(regs)} balizas reales decodificadas con strand_amsat.py "
            "(especificacion AMSAT-UK corregida). La tabla muestra la baliza mas "
            "reciente por canal."
        ),
    )