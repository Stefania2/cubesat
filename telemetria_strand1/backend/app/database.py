"""Conexion a base de datos con caida a SQLite si PostgreSQL no responde."""

from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _build_engine():
    """Intenta PostgreSQL; si no hay servidor utilizable, usa SQLite."""
    try:
        engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            future=True,
            # Toda la aplicacion trabaja en UTC, que es la convencion de SatNOGS.
            # Sin esto PostgreSQL devuelve las marcas de tiempo en la zona del
            # servidor y la API acabaria emitiendo desfases locales.
            connect_args={"options": "-c timezone=utc"},
        )
        with engine.connect():
            pass
        logger.info("Base de datos: PostgreSQL (%s)", engine.url.render_as_string(hide_password=True))
        return engine, "postgresql"
    except (OperationalError, ImportError, ModuleNotFoundError) as exc:
        if settings.require_postgres:
            raise RuntimeError(
                f"No se pudo conectar a PostgreSQL ({type(exc).__name__}: {exc}).\n"
                "REQUIRE_POSTGRES=true impide caer a SQLite. Crea el rol y la base:\n"
                "  sudo -u postgres psql -c \"CREATE ROLE strand LOGIN PASSWORD 'strand';\" \\\n"
                "                    -c 'CREATE DATABASE strand1 OWNER strand;'\n"
                "O pon REQUIRE_POSTGRES=false en backend/.env para usar SQLite."
            ) from exc
        logger.warning(
            "PostgreSQL no disponible (%s). Usando SQLite en %s. "
            "Para produccion, crea la base con los comandos del README.",
            type(exc).__name__,
            settings.sqlite_fallback_url,
        )
        engine = create_engine(
            settings.sqlite_fallback_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        return engine, "sqlite"


engine, DB_BACKEND = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registra los modelos en la metadata)

    Base.metadata.create_all(bind=engine)
