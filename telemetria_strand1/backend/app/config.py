"""Configuracion de la aplicacion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
# El CSV de telemetria real vive en la raiz del repositorio, dos niveles arriba.
DEFAULT_SEED_CSV = BASE_DIR.parent.parent / "frames_STRAND1.csv"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL es el destino de produccion. Si no hay servidor accesible la
    # aplicacion cae a SQLite para poder arrancar sin configuracion previa;
    # el cambio se registra en el log de arranque.
    database_url: str = "postgresql+psycopg://strand:strand@localhost:5432/strand1"
    sqlite_fallback_url: str = f"sqlite:///{BASE_DIR / 'strand1.db'}"
    # Con REQUIRE_POSTGRES=true la aplicacion no cae a SQLite: si PostgreSQL no
    # responde, aborta el arranque con el motivo. Evita seguir trabajando sobre
    # una base local sin darse cuenta.
    require_postgres: bool = False
    # Con READ_ONLY=true las rutas que escriben en la base responden 403 (ver
    # `permisos.py`). Por omision se activa sola en Vercel, que define la
    # variable VERCEL en todas sus funciones: alli la API queda publica y sin
    # autenticacion. En local sigue desactivada.
    read_only: bool = bool(os.environ.get("VERCEL"))

    @field_validator("database_url", mode="before")
    @classmethod
    def _dialecto(cls, v: object) -> object:
        """Fuerza el dialecto psycopg3 en las cadenas que no lo traen.

        Los proveedores gestionados (Neon, Supabase, Render) entregan la cadena
        como `postgresql://...` o `postgres://...`. Sin `+psycopg`, SQLAlchemy
        asume psycopg2, que no esta en requirements, y el arranque falla con un
        ModuleNotFoundError que no menciona la cadena. Asi se puede pegar tal
        cual la da el panel del proveedor.
        """
        if isinstance(v, str):
            v = v.strip()
            for prefijo in ("postgresql://", "postgres://"):
                if v.startswith(prefijo):
                    return "postgresql+psycopg://" + v[len(prefijo):]
        return v

    satnogs_db_url: str = "https://db.satnogs.org/api"
    satnogs_network_url: str = "https://network.satnogs.org/api"

    # SatNOGS DB y SatNOGS Network son instalaciones separadas, con cuentas y
    # tokens distintos: el de una no vale en la otra. Ademas, DB responde 401 a
    # cualquier peticion que lleve un token invalido, incluso a los endpoints
    # publicos que sin token funcionan. Por eso es preferible dejar vacio el
    # token de DB a poner uno que no sea suyo.
    satnogs_network_token: str = ""
    satnogs_db_token: str = ""
    # Compatibilidad con la configuracion anterior, que tenia un unico token.
    # Se usa como respaldo del de Network, que es donde ese token era valido.
    satnogs_api_token: str = ""

    @property
    def token_network(self) -> str:
        return self.satnogs_network_token or self.satnogs_api_token

    @property
    def token_db(self) -> str:
        return self.satnogs_db_token

    norad_id: int = 39090
    satellite_name: str = "STRAND-1"

    seed_csv_path: Path = DEFAULT_SEED_CSV
    # Directorio donde se dejan los archivos de demoddata descargados de
    # SatNOGS Network (data_<obs>_<fecha>_g<n>).
    demoddata_dir: Path = BASE_DIR.parent.parent
    # CSV que produce tools/extraer_telemetria_satnogs.py al recorrer las
    # observaciones de SatNOGS Network.
    extraccion_csv_path: Path = BASE_DIR.parent / "telemetria_satnogs.csv"

    # `NoDecode` impide que la fuente de entorno intente leer esto como JSON.
    # Sin el, `CORS_ORIGINS=https://algo.vercel.app` aborta el arranque durante
    # la lectura de la variable --- antes de que ningun validador se ejecute ---
    # con un error que no menciona el formato esperado. Pegar JSON con corchetes
    # y comillas en el panel de un proveedor es facil de equivocar, asi que se
    # admiten las dos formas.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://cubesatstrand-1.vercel.app",
        "https://cubesatstrand-1-25h8wjfcv-stefania2s-projects.vercel.app",
    ]


    @field_validator("cors_origins", mode="before")
    @classmethod
    def _origenes(cls, v: object) -> object:
        """Admite JSON, lista separada por comas o un solo origen."""
        if isinstance(v, str):
            texto = v.strip()
            if texto.startswith("["):
                import json

                return json.loads(texto)
            return [o.strip() for o in texto.split(",") if o.strip()]
        return v


settings = Settings()
