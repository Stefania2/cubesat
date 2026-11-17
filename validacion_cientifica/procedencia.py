"""MODULO 1 — Data Provenance: archivo sellado, huellas SHA-256 y procedencia.

Archivo sellado
---------------
`archivar.py` copia de PostgreSQL a `validacion_cientifica/archivo/` cuatro
ficheros JSON Lines comprimidos, uno por capa, para que la ORIGINAL y la
PROCESADA vivan separadas tambien fuera de la base:

    tramas_originales.jsonl.gz     ORIGINAL   frames.raw_hex y metadatos de recepcion
    observaciones.jsonl.gz         ORIGINAL   tabla observations (SatNOGS Network)
    tramas_clasificacion.jsonl.gz  PROCESADA  metricas y clasificacion de cada trama
    campos_decodificados.jsonl.gz  PROCESADA  decoded_fields: valores ya convertidos

Cada fila se serializa de forma canonica (`fila_canonica`): claves ordenadas,
sin espacios, UTF-8, fechas UTC ISO 8601 con microsegundos, `null` para lo
ausente. Con eso el mismo contenido da siempre los mismos bytes y la misma
huella, y la huella sirve para dos cosas:

  * comprobar que el archivo no ha cambiado desde que se sello (`verificar_archivo`);
  * comprobar que la base de datos sigue conteniendo lo mismo (`archivar.comparar_con_base`).

Se guardan dos huellas por fichero: la del contenido sin comprimir (la que
importa, independiente de la version de zlib) y la del fichero .gz tal cual.

Lo que el archivo NO puede probar: que `raw_hex` sea identico a la respuesta
original de la API de SatNOGS. La plataforma no guardo esas respuestas al
ingerir; el archivo sella la capa ORIGINAL tal como esta en la base. Es una
limitacion documentada, no una garantia que se aparente.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from . import estados as E

RAIZ_REPO = Path(__file__).resolve().parents[1]
DIR_ARCHIVO = Path(__file__).resolve().parent / "archivo"
SELLO = DIR_ARCHIVO / "sello.json"
COMPARACION_BASE = Path(__file__).resolve().parent / "resultados" / "comparacion_base.json"

FICHEROS = {
    "tramas_originales": "ORIGINAL",
    "observaciones": "ORIGINAL",
    "tramas_clasificacion": "PROCESADA",
    "campos_decodificados": "PROCESADA",
    # No sale de la base: es la copia sellada del catalogo de TLE historicos
    # (geometria_observaciones.json + tle/), que la descarga de SatNOGS amplia.
    "catalogo_tle": "ORIGINAL",
}

# Complemento para servir la plataforma web sin PostgreSQL (`app/archivo_sqlite.py`).
# Se sella aparte: no son entradas de ninguna reconstruccion, asi que no entran en
# `huella_conjunto` y los manifests ya emitidos siguen siendo reproducibles.
FICHEROS_PLATAFORMA = {
    "tramas_analisis": "PROCESADA",       # frames.analysis (evidencia estructural AX.25)
    "observaciones_id": "ORIGINAL",       # clave primaria de observations
    "reglas_anomalias": "CONFIGURACION",  # anomaly_rules
    "protocolos": "CONFIGURACION",        # protocol_definitions
}


# ── Serializacion canonica y huellas ────────────────────────────────────────

def fila_canonica(fila: dict) -> bytes:
    return json.dumps(fila, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8") + b"\n"


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def sha256_fichero(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def huella_filas(filas: Iterable[dict]) -> tuple[str, int, bytes]:
    """Huella SHA-256 del contenido canonico, numero de filas y los bytes."""
    buf = io.BytesIO()
    n = 0
    for fila in filas:
        buf.write(fila_canonica(fila))
        n += 1
    contenido = buf.getvalue()
    return sha256(contenido), n, contenido


def comprimir_determinista(contenido: bytes) -> bytes:
    """gzip sin fecha ni nombre: el mismo contenido da el mismo fichero."""
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as gz:
        gz.write(contenido)
    return buf.getvalue()


# ── Lectura y verificacion del archivo ──────────────────────────────────────

def leer_sello() -> dict | None:
    if not SELLO.exists():
        return None
    return json.loads(SELLO.read_text(encoding="utf-8"))


def _ruta(nombre: str) -> Path:
    return DIR_ARCHIVO / f"{nombre}.jsonl.gz"


@lru_cache(maxsize=8)
def _contenido(nombre: str) -> bytes:
    with gzip.open(_ruta(nombre), "rb") as f:
        return f.read()


def cargar(nombre: str) -> list[dict]:
    """Filas de un fichero del archivo, tal como se sellaron."""
    if nombre not in FICHEROS and nombre not in FICHEROS_PLATAFORMA:
        raise KeyError(nombre)
    return [json.loads(linea) for linea in _contenido(nombre).splitlines() if linea]


@lru_cache(maxsize=4)
def _indice(nombre: str) -> dict:
    return {fila["id"]: fila for fila in cargar(nombre)}


def cargar_fila(nombre: str, id_: int) -> dict:
    """Una fila tal como se sello (sin pasar por pandas: los tipos quedan intactos)."""
    return _indice(nombre)[id_]


def archivo_disponible() -> bool:
    return SELLO.exists() and all(_ruta(n).exists() for n in FICHEROS)


@lru_cache(maxsize=1)
def verificar_archivo() -> list[E.Resultado]:
    """Recalcula las huellas del archivo y las compara con el sello."""
    sello = leer_sello()
    if sello is None:
        return [E.no_disponible("PROV-ARCH", "procedencia", "Archivo sellado",
                                "No existe validacion_cientifica/archivo/sello.json. "
                                "Ejecute archivar.py contra la base para crearlo.")]
    fuera = []
    for nombre, capa in FICHEROS.items():
        meta = sello["ficheros"].get(nombre)
        rid = f"PROV-SHA-{nombre}"
        titulo = f"Integridad SHA-256 · {nombre} ({capa})"
        if meta is None or not _ruta(nombre).exists():
            fuera.append(E.no_disponible(rid, "procedencia", titulo, "Fichero ausente del archivo."))
            continue
        obtenido = sha256(_contenido(nombre))
        filas = _contenido(nombre).count(b"\n")
        ok = obtenido == meta["sha256_contenido"] and filas == meta["filas"]
        fuera.append(E.ejecutado(
            rid, "procedencia", titulo, ok,
            esperado={"sha256": meta["sha256_contenido"], "filas": meta["filas"]},
            obtenido={"sha256": obtenido, "filas": filas},
            tolerancia="igualdad exacta",
            detalle=("El contenido coincide con el sellado el " + sello["sellado_utc"]) if ok else
                    "El contenido NO coincide con el sello: el archivo se modifico despues de sellarse.",
            referencia="FIPS 180-4 (SHA-256)",
            datos={"capa": capa, "sha256_gz": sha256_fichero(_ruta(nombre)),
                   "sha256_gz_sellado": meta["sha256_gz"]},
        ))
    return fuera


def ultima_comparacion_base() -> dict | None:
    """Resultado registrado de `archivar.py --comparar` (no se repite en la API)."""
    if not COMPARACION_BASE.exists():
        return None
    return json.loads(COMPARACION_BASE.read_text(encoding="utf-8"))


def verificar_plataforma() -> list[E.Resultado]:
    """Huellas del complemento de plataforma frente a su sello."""
    sello = (leer_sello() or {}).get("plataforma")
    if not sello:
        return [E.no_disponible("PROV-PLAT", "procedencia", "Complemento de plataforma",
                                "El sello no incluye el complemento de plataforma.")]
    fuera = []
    for nombre, capa in FICHEROS_PLATAFORMA.items():
        meta = sello.get(nombre)
        rid = f"PROV-PLAT-{nombre}"
        if meta is None or not _ruta(nombre).exists():
            fuera.append(E.no_disponible(rid, "procedencia", f"Plataforma · {nombre}", "Fichero ausente."))
            continue
        obtenido = sha256(_contenido(nombre))
        fuera.append(E.ejecutado(rid, "procedencia", f"Integridad SHA-256 · {nombre} ({capa})",
                                 obtenido == meta["sha256_contenido"],
                                 esperado=meta["sha256_contenido"], obtenido=obtenido,
                                 tolerancia="igualdad exacta", referencia="FIPS 180-4 (SHA-256)"))
    return fuera


def huella_conjunto() -> str | None:
    """Una sola huella que identifica todas las entradas del archivo."""
    sello = leer_sello()
    if sello is None:
        return None
    partes = "".join(f"{n}:{sello['ficheros'][n]['sha256_contenido']}\n" for n in sorted(FICHEROS))
    return sha256(partes.encode())


# ── Versiones del procesamiento ─────────────────────────────────────────────

CODIGO_PROCESAMIENTO = {
    "decodificador_amsat": "telemetria_strand1/backend/app/services/strand_amsat.py",
    "mapeo_parametros": "telemetria_strand1/backend/app/services/strand_telemetry.py",
    "propagador_sgp4_plataforma": "orbita_sgp4.py",
    "reconstruccion_estado": "gemelo_digital/estado.py",
    "diagnostico_estadistico": "gemelo_digital/anomalias.py",
    "validacion_cientifica": "validacion_cientifica/reconstruccion.py",
}


def commit_aplicacion() -> str | None:
    """Commit desplegado (Vercel) o el de la copia local; None si no se sabe."""
    sha = os.environ.get("VERCEL_GIT_COMMIT_SHA")
    if sha:
        return sha
    head = RAIZ_REPO / ".git" / "HEAD"
    try:
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            ruta = RAIZ_REPO / ".git" / ref[5:]
            if ruta.exists():
                return ruta.read_text().strip()
            empaquetadas = RAIZ_REPO / ".git" / "packed-refs"
            for linea in empaquetadas.read_text().splitlines():
                if linea.endswith(ref[5:]):
                    return linea.split()[0]
            return None
        return ref
    except OSError:
        return None


def arbol_modificado() -> bool | None:
    """True si la copia local tiene cambios sin confirmar respecto al commit; None si no se sabe.

    En Vercel no hay .git: el commit (si existe) es el del despliegue y no se
    puede comprobar. Las huellas del codigo son, en todo caso, la identidad exacta.
    """
    if os.environ.get("VERCEL") or not (RAIZ_REPO / ".git").exists():
        return None
    import subprocess

    try:
        r = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=RAIZ_REPO,
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(r.stdout.strip()) if r.returncode == 0 else None


@lru_cache(maxsize=1)
def versiones() -> dict:
    """Version de cada pieza que interviene, identificada por la huella de su codigo.

    El codigo de procesamiento no lleva numero de version propio; la huella
    SHA-256 del fichero fuente lo identifica sin ambiguedad: si cambia una
    sola recta de calibracion, cambia la huella.
    """
    import numpy
    import pandas
    import sgp4

    from . import VERSION

    codigo = {}
    for clave, rel in CODIGO_PROCESAMIENTO.items():
        ruta = RAIZ_REPO / rel
        codigo[clave] = {"fichero": rel,
                         "sha256": sha256_fichero(ruta) if ruta.exists() else None}
    try:
        from sgp4.api import accelerated
    except ImportError:
        accelerated = None
    return {
        "aplicacion": {"modulo_validacion": VERSION, "commit": commit_aplicacion(),
                       "cambios_sin_confirmar": arbol_modificado(),
                       "nota": "El commit identifica la base del código; si hay cambios sin confirmar, "
                               "la identidad exacta son las huellas de «codigo»."},
        "python": sys.version.split()[0],
        "bibliotecas": {"sgp4": sgp4.__version__, "sgp4_acelerado_cpp": accelerated,
                        "numpy": numpy.__version__, "pandas": pandas.__version__},
        "codigo": codigo,
    }


# ── Decodificador de la plataforma (no se duplica: se importa) ──────────────

def _modulo(nombre: str):
    """Importa un servicio del backend reutilizando la copia ya cargada si existe."""
    for clave in (f"app.services.{nombre}", f"telemetria_strand1.backend.app.services.{nombre}"):
        if clave in sys.modules:
            return sys.modules[clave]
    if str(RAIZ_REPO) not in sys.path:
        sys.path.insert(0, str(RAIZ_REPO))
    import importlib

    return importlib.import_module(f"telemetria_strand1.backend.app.services.{nombre}")


def amsat():
    return _modulo("strand_amsat")


def mapeo():
    return _modulo("strand_telemetry")


def redecodificar(raw_hex: str) -> dict | None:
    """Repite exactamente lo que hizo la ingesta (`ingest.decodificar_frames_almacenados`).

    Devuelve `{campo: (valor, unidad)}` o None si la trama no es una baliza.
    Sirve para contrastar la capa PROCESADA almacenada con el codigo vigente.
    """
    a, m = amsat(), mapeo()
    limpio = "".join(c for c in raw_hex if not c.isspace()).replace("0x", "")
    try:
        datos = bytes.fromhex(limpio)
    except ValueError:
        return None
    baliza = a.decodificar(datos)
    if baliza is None:
        return None
    campos = dict(baliza.valores)
    campos.setdefault("seq_no", baliza.seq_no)
    campos.setdefault("i2c_node_address", baliza.nodo)
    campos.setdefault("node_channel", baliza.canal)
    registros = dict(campos)
    registros.update({clave: valor for clave, (valor, _) in m.a_parametros(campos).items()})
    return {k: (v, m.UNIDADES.get(k) or baliza.unidades.get(k)) for k, v in registros.items()}


def baliza_detalle(raw_hex: str) -> dict | None:
    """Estructura de la baliza: nodo, canal, cuenta original y bytes de datos."""
    a = amsat()
    try:
        datos = bytes.fromhex("".join(c for c in raw_hex if not c.isspace()))
    except ValueError:
        return None
    b = a.decodificar(datos)
    if b is None:
        return None
    return {"seq_no": b.seq_no, "tipo_paquete": b.packet_type, "nodo_i2c": f"0x{b.nodo:02X}",
            "nodo": b.nodo_nombre, "canal": f"0x{b.canal:02X}", "data_size": b.data_size,
            "datos_hex": b.datos.hex().upper(), "fuera_de_dominio_adc": b.fuera_de_rango}


# ── Procedencia de una variable y de una lectura ────────────────────────────

FUENTE_SATNOGS = {
    "demoddata": "SatNOGS Network: fichero demoddata de la observación",
    "network": "SatNOGS Network (API de observaciones)",
    "sids": "SatNOGS DB (SiDS: trama enviada por una estación)",
    None: "SatNOGS (DB o Network); el canal concreto no se registró al ingerir",
}


def procedencia_trama(trama: dict, campos: list[dict] | None = None) -> dict:
    """Ficha de procedencia de una trama del archivo y de cada valor que se extrajo de ella."""
    sello = leer_sello() or {}
    vers = versiones()
    cal = amsat().calibraciones()
    redec = redecodificar(trama["raw_hex"]) or {}
    detalle = baliza_detalle(trama["raw_hex"])
    valores = []
    for c in campos or []:
        nombre = c["field_name"]
        base = nombre[:-4] if nombre.endswith("_adc") else nombre
        conv = cal.get(base)
        original = None
        if conv and f"{base}_adc" in redec:
            original = {"valor": redec[f"{base}_adc"][0], "tipo": conv["tipo_original"]}
        valor_redec = redec.get(nombre, (None, None))[0]
        valores.append({
            "campo": nombre,
            "valor_procesado": c["value_numeric"] if c["value_numeric"] is not None else c["value_text"],
            "unidad": c["unit"],
            "valor_original": original,
            "metodo_conversion": conv["conversion"] if conv and not nombre.endswith("_adc") else
                                 ("ninguna: entero recibido" if nombre.endswith("_adc") or c["unit"] in ("cuenta", None)
                                  else "decodificación según la especificación"),
            "fuente_conversion": amsat().FUENTE_CALIBRACION,
            "revalidado_con_codigo_vigente": None if valor_redec is None else
                (valor_redec == c["value_numeric"] or valor_redec == c["value_text"]),
        })
    return E.limpiar({
        "trama_id": trama["id"],
        "fuente_original": FUENTE_SATNOGS.get(trama.get("app_source"), FUENTE_SATNOGS[None]),
        "app_source_registrado": trama.get("app_source"),
        "observacion_id": trama.get("observation_id"),
        "estacion_id": trama.get("station_id"),
        "observador": trama.get("observer"),
        "fecha_recepcion_utc": trama["timestamp"],
        "fecha_medicion_utc": None,
        "fecha_medicion_nota": ("NO DISPONIBLE: la baliza de STRaND-1 no lleva marca de tiempo de "
                                "medición (obc_unix_time no se comporta como reloj). Se asocia a la "
                                "fecha de recepción en tierra."),
        "fecha_ingesta_utc": trama.get("ingested_at"),
        "fecha_ingesta_nota": ("Fecha en que la trama entró en la base de la plataforma. La fecha de "
                               "descarga original desde SatNOGS no se registró."),
        "valor_original_hex": trama["raw_hex"],
        "sha256_trama": sha256(bytes.fromhex(trama["raw_hex"])) if _hex_valido(trama["raw_hex"]) else None,
        "estructura": detalle,
        "valores": valores,
        "version_procesador": vers["codigo"]["decodificador_amsat"],
        "archivo": {"fichero": "tramas_originales.jsonl.gz",
                    "sha256_contenido": (sello.get("ficheros", {}).get("tramas_originales") or {}).get("sha256_contenido")},
    })


def _hex_valido(h: str) -> bool:
    try:
        bytes.fromhex(h)
        return True
    except (ValueError, TypeError):
        return False
