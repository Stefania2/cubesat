"""Bloqueo de las rutas que escriben en la base cuando la API es publica."""

from __future__ import annotations

from fastapi import HTTPException

from .config import settings


def exigir_escritura() -> None:
    """Dependencia de las rutas que modifican la base de datos.

    La API no tiene autenticacion. En local eso no importa, pero publicada
    cualquiera con la URL podria ingerir tramas o cambiar umbrales sobre la
    base canonica. Con `READ_ONLY=true` esas rutas responden 403 y el resto
    --- todas las lecturas --- sigue funcionando.
    """
    if settings.read_only:
        raise HTTPException(
            status_code=403,
            detail="Esta instancia es de solo lectura: la ingesta y los cambios "
                   "de umbrales solo estan disponibles en la instalacion local.",
        )
