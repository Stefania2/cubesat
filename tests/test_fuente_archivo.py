"""La web servida desde el archivo sellado responde igual que desde PostgreSQL.

Levanta dos copias reales del backend (uvicorn, entorno `strand_api`): una con
FUENTE_DATOS=postgres contra la base LOCAL y otra con FUENTE_DATOS=archivo, y
compara la respuesta JSON de cada ruta de lectura que usa la base. Cualquier
diferencia de SQL entre PostgreSQL y SQLite (fechas, percentiles, funciones)
aparece aqui, no en produccion.

Se ejecuta con el entorno de la plataforma, que es el que tiene SQLAlchemy:

    ../strand_api/bin/python -m pytest tests/test_fuente_archivo.py

Se omite si no hay PostgreSQL local o si falta SQLAlchemy.
"""

from __future__ import annotations

import csv
import io
import math
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
httpx = pytest.importorskip("httpx")

RAIZ = Path(__file__).resolve().parents[1]
BACKEND = RAIZ / "telemetria_strand1" / "backend"
PG_LOCAL = "postgresql://strand:strand@localhost:5432/strand1"
PUERTOS = {"postgres": 8091, "archivo": 8092}

RUTAS = [
    "/api/frames/kpis", "/api/frames?limit=50&offset=0", "/api/frames?limit=20&offset=30000&status=decoded",
    "/api/frames/series?rango=todo", "/api/frames/series?rango=7d", "/api/frames/estaciones",
    "/api/frames/distribucion", "/api/frames/17348", "/api/frames/1",
    "/api/observations?limit=100", "/api/observations/pasos?limit=3000", "/api/observations/7600707",
    "/api/observations/7600707/paso",
    "/api/telemetry", "/api/telemetry/campos", "/api/telemetry/protocolos",
    "/api/decoder/frame/17348", "/api/anomalies", "/api/anomalies/rules",
    "/api/gemelo/resumen", "/api/gemelo/indice?t=2021-03-01T12:00:00Z", "/api/gemelo/estado?indice=0",
    "/api/gemelo/estado?indice=10482", "/api/gemelo/estado?indice=21832&campo=adc13_px_array_current",
    "/api/gemelo/serie/battery_voltage", "/api/gemelo/serie/battery_voltage?desde=2020-01-01&hasta=2021-06-01",
    "/api/gemelo/eventos/battery_voltage",
    "/api/salud/resumen", "/api/salud/resumen?hasta=2020-10-31&ventana_dias=365", "/api/salud/subsistema/eps",
    "/api/salud/variables", "/api/salud/historial",
    "/api/export/observations.json", "/api/export/frames-processed.json", "/api/export/telemetry-decoded.json",
    "/api/export/frames-raw.csv",
]

# Campos que dicen de donde salen los datos o cuando se calculo la respuesta, no que contienen.
IGNORAR = {"database", "fuente_datos", "generado_utc", "generado", "ejecutado_utc", "evaluado_utc", "exported_at"}


def _pg_local_disponible() -> bool:
    try:
        with socket.create_connection(("localhost", 5432), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def servidores(tmp_path_factory):
    if not _pg_local_disponible():
        pytest.skip("no hay PostgreSQL local en el puerto 5432")
    procesos = {}
    base = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "VERCEL", "DATOS_DSN", "REDIS_URL")}
    for fuente, puerto in PUERTOS.items():
        env = {**base, "FUENTE_DATOS": fuente, "DATABASE_URL": PG_LOCAL, "REQUIRE_POSTGRES": "true",
               "ARCHIVO_SQLITE_DIR": str(tmp_path_factory.mktemp("archivo")), "HMTA_DB_PATH": ":memory:",
               "LIRA_REGISTRO_DIR": str(tmp_path_factory.mktemp("lira"))}
        procesos[fuente] = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(puerto), "--log-level", "warning"],
            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for fuente, puerto in PUERTOS.items():
            for _ in range(240):
                try:
                    if httpx.get(f"http://127.0.0.1:{puerto}/api/status", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if procesos[fuente].poll() is not None:
                    pytest.fail(f"el backend {fuente} no arrancó: {procesos[fuente].stderr.read().decode()[-2000:]}")
                time.sleep(0.5)
        yield {f: f"http://127.0.0.1:{p}" for f, p in PUERTOS.items()}
    finally:
        for p in procesos.values():
            p.terminate()
            p.wait(timeout=20)


def _diferencias(a, b, ruta="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k in IGNORAR:
                continue
            if k not in a or k not in b:
                out.append(f"{ruta}.{k}: solo en {'postgres' if k in a else 'archivo'}")
            else:
                out += _diferencias(a[k], b[k], f"{ruta}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{ruta}: {len(a)} elementos frente a {len(b)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += _diferencias(x, y, f"{ruta}[{i}]")
            if len(out) > 10:
                break
        return out
    if isinstance(a, float) and isinstance(b, (int, float)) or isinstance(b, float) and isinstance(a, (int, float)):
        if math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12):
            return []
    return [] if a == b else [f"{ruta}: {a!r} frente a {b!r}"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_misma_respuesta_desde_postgres_y_desde_el_archivo(servidores, ruta):
    with httpx.Client(timeout=180) as c:
        rp = c.get(servidores["postgres"] + ruta)
        ra = c.get(servidores["archivo"] + ruta)
    assert rp.status_code == ra.status_code, (rp.status_code, ra.status_code, ra.text[:300])
    if ruta.endswith(".csv"):
        fp = list(csv.reader(io.StringIO(rp.text)))
        fa = list(csv.reader(io.StringIO(ra.text)))
        assert fp == fa
        return
    dif = _diferencias(rp.json(), ra.json())
    assert not dif, "\n".join(dif[:10])


def test_status_dice_de_donde_salen_los_datos(servidores):
    s = httpx.get(servidores["archivo"] + "/api/status", timeout=30).json()
    assert s["database"] == "archivo" and s["fuente_datos"]["tipo"] == "archivo sellado"
    assert s["frames"] == 36641 and s["observaciones"] == 3049
    p = httpx.get(servidores["postgres"] + "/api/status", timeout=30).json()
    assert p["database"] == "postgresql" and p["fuente_datos"] is None


def test_fechas_en_utc_explicito(servidores):
    f = httpx.get(servidores["archivo"] + "/api/frames/17348", timeout=30).json()
    assert f["timestamp"].endswith(("Z", "+00:00"))


def test_escrituras_bloqueadas_en_modo_archivo(servidores):
    r = httpx.patch(servidores["archivo"] + "/api/anomalies/rules/zscore", json={"enabled": False}, timeout=30)
    assert r.status_code >= 400
