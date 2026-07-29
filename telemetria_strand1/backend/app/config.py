"""Configuracion de la aplicacion."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

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

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


settings = Settings()
