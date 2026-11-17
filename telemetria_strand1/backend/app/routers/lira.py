"""API de LIRA AI, la copiloto de la plataforma.

Capa delgada sobre el paquete `lira/` de la raiz del repositorio: validacion
de entradas y serializacion. Ninguna ruta escribe en la base ni envia nada al
satelite. La parte con IA exige una ficha de sesion, que se obtiene con la
contraseña (ver `lira/seguridad.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

# parents[0] routers [1] app [2] backend [3] telemetria_strand1 [4] cubesat
RAIZ_REPO = Path(__file__).resolve().parents[4]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from lira import MODELO, VERSION, motor, registro, seguridad  # noqa: E402

router = APIRouter(prefix="/api/lira", tags=["LIRA AI"])


class Acceso(BaseModel):
    clave: str = Field(max_length=200)


class Mensaje(BaseModel):
    rol: Literal["usuario", "lira"]
    texto: str = Field(max_length=2000)


class Contexto(BaseModel):
    pagina: str | None = Field(default=None, max_length=40)
    momento_utc: str | None = Field(default=None, max_length=40)
    campo: str | None = Field(default=None, max_length=64)
    vista: str | None = Field(default=None, max_length=20)
    camara: str | None = Field(default=None, max_length=20)
    reproduciendo: bool | None = None
    pendiente: bool | None = None


class Turno(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)
    contexto: Contexto = Contexto()
    historial: list[Mensaje] = Field(default_factory=list, max_length=12)


class Confirmacion(BaseModel):
    ficha: str = Field(max_length=4000)
    decision: Literal["confirmar", "cancelar"]


def _ip(request: Request) -> str:
    reenviada = request.headers.get("x-forwarded-for", "")
    return reenviada.split(",")[0].strip() or (request.client.host if request.client else "?")


@router.get("/estado")
def estado() -> dict:
    return {
        "version": VERSION,
        "ia_configurada": seguridad.ia_configurada(),
        "requiere_clave": seguridad.requiere_clave(),
        "modelo": MODELO if seguridad.ia_configurada() else None,
        "registro_activo": registro.activo(),
        "comandos_al_satelite": False,
        "nota": "LIRA actúa sobre la interfaz de la plataforma y la simulación del enlace. STRaND-1 está "
                "inactivo y la plataforma no tiene canal de comandos hacia él.",
    }


@router.post("/acceso")
def acceso(datos: Acceso, request: Request) -> dict:
    if not seguridad.ia_configurada():
        raise HTTPException(status_code=503, detail="La IA no está configurada en este servidor.")
    try:
        ficha = seguridad.comprobar_clave(datos.clave, _ip(request))
    except seguridad.Bloqueado as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if ficha is None:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")
    return {"ficha": ficha, "caduca_s": seguridad.DURACION_SESION_S}


@router.post("/turno")
def turno(datos: Turno, x_lira_ficha: str | None = Header(default=None)) -> dict[str, Any]:
    sesion = seguridad.sesion_valida(x_lira_ficha)
    try:
        return motor.turno(datos.texto, datos.contexto.model_dump(exclude_none=True),
                           [m.model_dump() for m in datos.historial], sesion)
    except seguridad.Bloqueado as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - un fallo de la IA no debe tumbar la interfaz
        import anthropic

        if isinstance(exc, anthropic.APIError):
            raise HTTPException(status_code=502, detail="El servicio de IA no respondió. Prueba de nuevo "
                                                        "o usa órdenes directas.") from exc
        raise


@router.post("/confirmar")
def confirmar(datos: Confirmacion, x_lira_ficha: str | None = Header(default=None)) -> dict:
    return motor.confirmar(datos.ficha, datos.decision, seguridad.sesion_valida(x_lira_ficha))


@router.get("/registro")
def ver_registro(n: int = 50) -> dict:
    if not registro.activo():
        raise HTTPException(status_code=404, detail="El registro de LIRA solo existe en la instalación local.")
    return {"eventos": registro.recientes(min(max(n, 1), 200))}
