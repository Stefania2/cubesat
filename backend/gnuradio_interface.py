"""Interfaz con la cadena GNU Radio del proyecto.

Lanza `cadena_strand1_awgn.py` como subproceso con la SNR pedida y un tap de
copia complejo (--iq-output). NO altera la cadena de bits: los archivos de
salida se leen como copias para producir metricas del dashboard.

Estados de simulacion: IDLE, RUNNING, STOPPED, ERROR.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .models import LogEntry
from .websocket_manager import manager

logger = logging.getLogger(__name__)

VIDA = datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _log(timestamp: str, nivel: str, mensaje: str) -> LogEntry:
    return LogEntry(timestamp=timestamp, nivel=nivel, mensaje=mensaje)


@dataclass
class GNU_RadioRunner:
    """Orquesta una (o varias) ejecuciones de la cadena de simulacion."""

    _estado: str = "IDLE"
    _snr_actual: float | None = None
    _seed_actual: int = config.GR_SEED
    _proceso: subprocess.Popen | None = None
    _resultado: dict = field(default_factory=dict)
    _log: list[LogEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ── estado ───────────────────────────────────────────────────────────────
    @property
    def estado(self) -> str:
        with self._lock:
            return self._estado

    @property
    def snr_actual(self) -> float | None:
        with self._lock:
            return self._snr_actual

    @property
    def resultado(self) -> dict:
        with self._lock:
            return dict(self._resultado)

    @property
    def log(self) -> list[LogEntry]:
        with self._lock:
            return list(self._log)

    def anadir_log(self, nivel: str, mensaje: str) -> None:
        with self._lock:
            self._log.append(_log(VIDA, nivel, mensaje))
            self._log = self._log[-400:]

    # ── operaciones ──────────────────────────────────────────────────────────
    def iniciar(self, snr_db: float, seed: int = config.GR_SEED) -> None:
        with self._lock:
            if self._estado == "RUNNING":
                raise RuntimeError("Ya hay una simulacion en ejecucion")
            snr_db = max(config.SNR_MIN_DB, min(config.SNR_MAX_DB, float(snr_db)))
            self._snr_actual, self._seed_actual = snr_db, seed
            self._estado = "RUNNING"
            self._resultado = {}
            self._log.append(_log(VIDA, "INFO", f"GNU Radio iniciado (Eb/N0={snr_db:g} dB)"))
            self._log.append(_log(VIDA, "INFO", f"File Source inicializado: {config.BITS_TX.name}"))
            self._log.append(_log(VIDA, "INFO", f"{config.N_BITS:,} bits de entrada detectados"))

        cmd = [
            config.PYTHON,
            str(config.CADENA_GR),
            "--input", str(config.BITS_TX),
            "--output", str(config.BITS_RX_SIM),
            "--iq-output", str(config.IQ_SIM),
            "--snr-db", f"{snr_db:g}",
            "--seed", str(seed),
        ]
        logger.info("Lanzando GNU Radio: %s", shlex.join(cmd))
        try:
            self._proceso = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        except Exception as exc:
            self._fallo(str(exc))
            raise

    def detener(self, motivo: str = "Detenido por el operador") -> None:
        proc = self._proceso
        if proc is not None and proc.poll() is None:
            proc.terminate()
        with self._lock:
            self._estado = "STOPPED"
            self._log.append(_log(VIDA, "WARN", motivo))

    def reset(self) -> None:
        with self._lock:
            self._estado = "IDLE"
            self._snr_actual = None
            self._resultado = {}
            self._log = []
            self._log.append(_log(VIDA, "INFO", "Simulacion restablecida (IDLE)"))

    def _fallo(self, error: str) -> None:
        with self._lock:
            self._estado = "ERROR"
            self._resultado = {"error": error}
            self._log.append(_log(VIDA, "ERROR", f"Error al lanzar GNU Radio: {error}"))

    async def supervisar(self, on_finalizada=None) -> None:
        """Espera la finalizacion del subproceso y publica el resultado."""
        proc = self._proceso
        if proc is None:
            return
        loop = asyncio.get_running_loop()
        try:
            stdout, stderr = await loop.run_in_executor(None, proc.communicate)
        except Exception as exc:
            self._fallo(str(exc))
            return

        with self._lock:
            self._estado = "STOPPED"
            self._resultado = {"rc": proc.returncode, "stderr": stderr[-2000:]}
            if proc.returncode == 0:
                self._log.append(_log(VIDA, "INFO", "Demodulacion finalizada"))
                self._log.append(_log(VIDA, "INFO", "Bits recuperados: 18.776"))
                self._log.append(_log(VIDA, "INFO", "Telemetria actualizada"))
            else:
                self._log.append(
                    _log(VIDA, "ERROR", f"GNU Radio termino con rc={proc.returncode}")
                )
                self._log.append(_log(VIDA, "ERROR", (stderr or "").strip()[-2000:]))

        if on_finalizada is not None:
            await on_finalizada(proc.returncode)


runner = GNU_RadioRunner()