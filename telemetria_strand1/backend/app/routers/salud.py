"""API del modulo HMTA (Health Monitoring & Telemetry Analysis).

Capa delgada sobre `health_monitor/`, que vive en la raiz del repositorio junto
a `gemelo_digital/`. Aqui no hay analisis: carga, cache y serializacion.

Todas las rutas son de lectura. El modulo es de supervision: no existe ninguna
ruta que envie ordenes al satelite, y no podria existir --- STRaND-1 esta
inactivo y lo que se supervisa es su archivo historico.

Datos reales
------------
Las lecturas numericas se toman de la misma cache que el gemelo digital
(`gemelo._campos`), asi que abrir el HMTA despues del gemelo no vuelve a pagar
la descarga. Las tablas de recepcion (tramas, secuencias, observaciones) y los
estados de los interruptores se cargan una vez por proceso. Si la base no
responde, la ruta devuelve 503 con el motivo: un panel vacio por una caida de
la base no debe parecer un satelite sin datos.

Escenarios simulados
--------------------
`/escenario/{nombre}` evalua un escenario de prueba. Todo lo que devuelve va
marcado SIMULADO, y las fechas del escenario estan en 2030 para que no puedan
confundirse con el archivo real.
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

# parents[0] routers  [1] app  [2] backend  [3] telemetria_strand1  [4] cubesat
RAIZ_REPO = Path(__file__).resolve().parents[4]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from health_monitor import (catalogo, health_assessment, pid_reference,  # noqa: E402
                            telemetry_acquisition as ta)
from health_monitor.alerts import RegistroEventos  # noqa: E402

router = APIRouter(prefix="/api/salud", tags=["salud (HMTA)"])
log = logging.getLogger(__name__)


def _cargar_real() -> ta.ConjuntoTelemetria:
    """Las cinco consultas en paralelo: en serie, contra Neon, pasan del limite de
    60 s de la funcion de Vercel en la primera peticion."""
    from concurrent.futures import ThreadPoolExecutor

    from gemelo_digital import datos

    from .gemelo import _campos

    with ThreadPoolExecutor(max_workers=5) as pool:
        f = {nombre: pool.submit(fn) for nombre, fn in (
            ("campos", _campos), ("estados", datos.cargar_estados),
            ("tramas", datos.cargar_frames), ("secuencias", datos.cargar_secuencias),
            ("observaciones", datos.cargar_observaciones))}
        r = {k: v.result() for k, v in f.items()}
    return ta.desde_campos(r["campos"], estados=r["estados"], tramas=r["tramas"],
                           secuencias=r["secuencias"], observaciones=r["observaciones"])


# Los tests sustituyen este proveedor para no depender de la base.
PROVEEDOR_REAL = _cargar_real


@lru_cache(maxsize=1)
def _real() -> ta.ConjuntoTelemetria:
    return PROVEEDOR_REAL()


def _conjunto_real() -> ta.ConjuntoTelemetria:
    try:
        return _real()
    except Exception as exc:  # noqa: BLE001 - se informa, no se disimula
        log.warning("HMTA: no se pudo cargar la telemetria real: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=("No se pudo leer la base de telemetría. Esto es un problema de acceso a los "
                    f"datos, no un estado del satélite. Detalle: {type(exc).__name__}")) from exc


@lru_cache(maxsize=1)
def _registro() -> RegistroEventos:
    return RegistroEventos()


@lru_cache(maxsize=32)
def _evaluacion_real(hasta: str | None, ventana_dias: float) -> dict:
    inf = health_assessment.evaluar(_conjunto_real(), hasta=hasta, ventana_dias=ventana_dias)
    _registro().guardar(inf["_alertas"])
    return health_assessment.sin_objetos(inf)


@lru_cache(maxsize=16)
def _evaluacion_escenario(nombre: str) -> dict:
    inf = health_assessment.evaluar(ta.simular_escenario(nombre))
    _registro().guardar(inf["_alertas"])
    return health_assessment.sin_objetos(inf)


@router.get("/resumen")
def resumen(hasta: str | None = Query(None, description="Fin del periodo (ISO 8601). Por "
                                       "defecto, la última telemetría decodificada."),
            ventana_dias: float = Query(health_assessment.VENTANA_DIAS, gt=0, le=4000)) -> dict:
    """Informe de salud completo sobre el archivo real."""
    if hasta is not None:
        try:
            import pandas as pd
            pd.Timestamp(hasta)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"Fecha no válida: {hasta}") from exc
    return _evaluacion_real(hasta, float(ventana_dias))


@router.get("/subsistema/{clave}")
def subsistema(clave: str, hasta: str | None = None,
               ventana_dias: float = Query(health_assessment.VENTANA_DIAS, gt=0, le=4000)) -> dict:
    inf = resumen(hasta, ventana_dias)
    if clave == "anomalias":
        return inf["anomalias"]
    if clave not in inf["subsistemas"]:
        raise HTTPException(status_code=404, detail=f"Subsistema desconocido: {clave}")
    return inf["subsistemas"][clave]


@router.get("/escenarios")
def escenarios() -> dict:
    return {"procedencia": ta.SIMULADO,
            "nota": "Escenarios de prueba del detector. No describen a STRaND-1.",
            "escenarios": [{"nombre": k, "descripcion": v} for k, v in ta.ESCENARIOS.items()]}


@router.get("/escenario/{nombre}")
def escenario(nombre: str) -> dict:
    if nombre not in ta.ESCENARIOS:
        raise HTTPException(status_code=404, detail=f"Escenario desconocido: {nombre}")
    return _evaluacion_escenario(nombre)


@router.get("/pid")
def pid(ts: float = Query(pid_reference.TS_POR_DEFECTO, ge=0.001, le=0.25,
                          description="Periodo de muestreo en segundos")) -> dict:
    """Modelos G1/G2 con P, PI y PID de Ziegler-Nichols (resultado matemático)."""
    return health_assessment.serializable(pid_reference.informe(round(ts, 4)))


@router.get("/variables")
def variables() -> dict:
    return {"subsistemas": catalogo.SUBSISTEMAS, "variables": catalogo.inventario(),
            "procedencias": list(ta.PROCEDENCIAS)}


@lru_cache(maxsize=1)
def _historial() -> list[dict]:
    return health_assessment.serializable(health_assessment.historial_mensual(_conjunto_real()))


@router.get("/historial")
def historial() -> dict:
    """Cobertura mensual de los canales de energia sobre todo el archivo."""
    return {"procedencia": ta.REAL, "fuente": ta.FUENTE_REAL, "meses": _historial()}


@router.get("/eventos")
def eventos(subsistema: str | None = None, procedencia: str | None = None,
            nivel: str | None = None, limite: int = Query(200, ge=1, le=2000)) -> dict:
    """Alertas registradas por las evaluaciones hechas en esta instalación."""
    reg = _registro()
    return {"persistente": reg.persistente, "ruta": reg.ruta, "total": reg.total(),
            "nota": None if reg.persistente else
            "Registro en memoria: esta instancia no puede escribir en disco (p. ej. Vercel). "
            "Se vacía al reiniciarse.",
            "eventos": reg.listar(subsistema, procedencia, nivel, limite)}
