"""Base de datos de solo lectura construida desde el archivo sellado.

Con FUENTE_DATOS=archivo (por omision en Vercel) la plataforma no lee
PostgreSQL: al arrancar, cada instancia construye una base SQLite en el
directorio temporal a partir de `validacion_cientifica/archivo/` y toda la API
la lee con el mismo codigo que usa contra PostgreSQL.

Garantias:
  * Antes de construir se verifican las huellas SHA-256 del archivo y del
    complemento de plataforma. Si algo no coincide, se lanza `ArchivoInvalido`
    y la API no arranca: nunca se sirve una base construida con datos alterados.
  * Se escribe en un fichero temporal y se renombra al terminar (operacion
    atomica): una base a medio construir nunca se abre.
  * El nombre lleva la huella del archivo: si el archivo cambia (nuevo sello),
    se construye otra base; nunca se reutiliza una vieja.
  * Un cerrojo de fichero evita que dos procesos la construyan a la vez.

La base se abre despues en modo solo lectura (`mode=ro`).
"""

from __future__ import annotations

import fcntl
import hashlib
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# parents[0] app [1] backend [2] telemetria_strand1 [3] cubesat
RAIZ_REPO = Path(__file__).resolve().parents[3]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

FECHAS = ("timestamp", "ingested_at", "start", "end", "fetched_at", "created_at")
LOTE = 20_000


class ArchivoInvalido(RuntimeError):
    pass


def _fecha(v):
    return None if v is None else datetime.fromisoformat(v.replace("Z", "+00:00"))


def _con_fechas(fila: dict) -> dict:
    return {k: (_fecha(v) if k in FECHAS else v) for k, v in fila.items()}


def huella() -> str:
    from validacion_cientifica import procedencia as P

    sello = P.leer_sello() or {}
    plataforma = "".join(f"{n}:{m['sha256_contenido']}" for n, m in sorted((sello.get("plataforma") or {}).items()))
    return hashlib.sha256(f"{P.huella_conjunto()}|{plataforma}".encode()).hexdigest()


def verificar() -> dict:
    """Comprueba el archivo antes de usarlo. Devuelve la descripcion de la fuente."""
    from validacion_cientifica import estados as E
    from validacion_cientifica import procedencia as P

    if not P.archivo_disponible():
        raise ArchivoInvalido("Falta el archivo sellado (validacion_cientifica/archivo).")
    malos = [r.id for r in [*P.verificar_archivo(), *P.verificar_plataforma()] if r.estado != E.VALIDATED]
    if malos:
        raise ArchivoInvalido(f"El archivo sellado no supera la verificación SHA-256: {', '.join(malos)}.")
    sello = P.leer_sello()
    return {"tipo": "archivo sellado", "sellado_utc": sello["sellado_utc"],
            "plataforma_sellado_utc": sello.get("plataforma_sellado_utc"),
            "huella_conjunto": P.huella_conjunto(), "origen": sello.get("origen")}


def _insertar(conn, tabla, filas) -> int:
    n = 0
    for i in range(0, len(filas), LOTE):
        lote = filas[i:i + LOTE]
        conn.execute(tabla.insert(), lote)
        n += len(lote)
    return n


def _poblar(ruta: Path) -> dict[str, int]:
    from sqlalchemy import create_engine

    from validacion_cientifica import procedencia as P

    from . import models  # noqa: F401  registra las tablas en Base.metadata
    from .database import Base

    motor = create_engine(f"sqlite:///{ruta}", future=True)
    Base.metadata.create_all(motor)
    t = Base.metadata.tables
    ids_obs = {f["observation_id"]: f["id"] for f in P.cargar("observaciones_id")}
    analisis = {f["id"]: f["analysis"] for f in P.cargar("tramas_analisis")}
    clasif = {f["id"]: f for f in P.cargar("tramas_clasificacion")}

    observaciones = [{**_con_fechas(f), "id": ids_obs[f["observation_id"]]} for f in P.cargar("observaciones")]
    tramas = []
    for f in P.cargar("tramas_originales"):
        c = clasif[f["id"]]
        tramas.append({**_con_fechas(f), **{k: v for k, v in c.items() if k != "id"},
                       "analysis": analisis.get(f["id"])})
    campos = [_con_fechas(f) for f in P.cargar("campos_decodificados")]
    reglas = P.cargar("reglas_anomalias")
    protocolos = [_con_fechas(f) for f in P.cargar("protocolos")]

    cuentas = {}
    with motor.begin() as conn:
        cuentas["observations"] = _insertar(conn, t["observations"], observaciones)
        cuentas["frames"] = _insertar(conn, t["frames"], tramas)
        cuentas["decoded_fields"] = _insertar(conn, t["decoded_fields"], campos)
        cuentas["anomaly_rules"] = _insertar(conn, t["anomaly_rules"], reglas)
        cuentas["protocol_definitions"] = _insertar(conn, t["protocol_definitions"], protocolos)
    motor.dispose()
    return cuentas


def construir(directorio: Path | None = None) -> Path:
    """Ruta de la base SQLite del archivo; la construye si no existe."""
    verificar()
    directorio = Path(directorio or os.environ.get("ARCHIVO_SQLITE_DIR") or tempfile.gettempdir())
    directorio.mkdir(parents=True, exist_ok=True)
    destino = directorio / f"strand1_archivo_{huella()[:16]}.db"
    if destino.exists():
        return destino
    with open(destino.with_suffix(".lock"), "w") as cerrojo:
        fcntl.flock(cerrojo, fcntl.LOCK_EX)
        try:
            if destino.exists():           # otro proceso la termino mientras esperabamos
                return destino
            tmp = destino.with_suffix(f".{os.getpid()}.tmp")
            tmp.unlink(missing_ok=True)
            t0 = time.monotonic()
            cuentas = _poblar(tmp)
            os.replace(tmp, destino)
            logger.info("Base del archivo sellado construida en %.1f s: %s", time.monotonic() - t0, cuentas)
        finally:
            fcntl.flock(cerrojo, fcntl.LOCK_UN)
    return destino
