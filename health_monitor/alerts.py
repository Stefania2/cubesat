"""Alertas del HMTA y su registro persistente.

Una alerta responde siempre a las siete preguntas del encargo: que ocurrio,
en que componente, que variable, que valor se registro, cual es la referencia,
por que puede importar y que haria falta para investigarlo. Si falta alguna de
esas piezas la alerta no se construye: `Alerta.__post_init__` lo comprueba.

Niveles
-------
    NORMAL       dentro de los parametros conocidos
    ADVERTENCIA  desviacion que requiere seguimiento
    CRITICO      supera un limite critico **validado** (con fuente)
    DESCONOCIDO  no hay informacion suficiente

Una desviacion estadistica, por grande que sea, no es CRITICO: sin un limite
documentado no hay base para decir que el componente esta fuera de servicio.
Y ninguna alerta afirma una averia: describe una desviacion.

Registro
--------
`RegistroEventos` guarda las alertas en SQLite (biblioteca estandar, sin
dependencias). Cada alerta tiene un identificador determinista --- un hash de
subsistema, variable, mecanismo, inicio y procedencia ---, asi que volver a
evaluar el mismo periodo no duplica eventos. La ruta sale de `HMTA_DB_PATH`;
sin ella, o si el disco es de solo lectura (Vercel), el registro vive en
memoria y lo dice (`persistente = False`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

NORMAL = "NORMAL"
ADVERTENCIA = "ADVERTENCIA"
CRITICO = "CRITICO"
DESCONOCIDO = "DESCONOCIDO"
NIVELES = (NORMAL, ADVERTENCIA, CRITICO, DESCONOCIDO)

# Gravedad para ordenar y combinar estados. DESCONOCIDO no es «peor» que
# NORMAL: la ausencia de datos no es un fallo del satelite.
GRAVEDAD = {NORMAL: 1, DESCONOCIDO: 0, ADVERTENCIA: 2, CRITICO: 3}

RUTA_POR_DEFECTO = Path(__file__).resolve().parent / "_datos" / "eventos_hmta.sqlite"


@dataclass(frozen=True)
class Alerta:
    subsistema: str
    variable: str
    nivel: str
    mecanismo: str                 # limite | tendencia | desviacion | modelo | validacion | ...
    inicio: str
    fin: str
    que_ocurrio: str
    componente: str
    valor_registrado: float | str | None
    unidad: str | None
    valor_referencia: float | str | None
    referencia: str                # de donde sale el valor de referencia
    por_que_importa: str
    informacion_adicional: str     # que haria falta para investigarlo
    procedencia: str               # REAL, SIMULADO, ESTIMADO...
    lecturas: int = 1
    detalle: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.nivel not in NIVELES:
            raise ValueError(f"Nivel no valido: {self.nivel}")
        for nombre in ("que_ocurrio", "componente", "referencia", "por_que_importa",
                       "informacion_adicional"):
            if not str(getattr(self, nombre)).strip():
                raise ValueError(f"Una alerta necesita «{nombre}».")

    @property
    def id(self) -> str:
        clave = "|".join([self.subsistema, self.variable, self.mecanismo, self.inicio,
                          self.procedencia])
        return hashlib.sha1(clave.encode()).hexdigest()[:16]

    def dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["preguntas"] = {
            "que_ocurrio": self.que_ocurrio,
            "en_que_componente": self.componente,
            "que_variable": self.variable,
            "que_valor_se_registro": self.valor_registrado,
            "cual_es_la_referencia": self.valor_referencia,
            "por_que_importa": self.por_que_importa,
            "que_falta_para_investigar": self.informacion_adicional,
        }
        return d


def peor(niveles) -> str:
    """Nivel combinado: el mas grave; DESCONOCIDO solo si no hay ningun otro."""
    niveles = list(niveles)
    if not niveles:
        return DESCONOCIDO
    return max(niveles, key=lambda n: GRAVEDAD[n])


class RegistroEventos:
    """Historial de alertas en SQLite."""

    ESQUEMA = """
        create table if not exists eventos (
            id text primary key,
            registrado_utc text default (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            inicio text not null,
            fin text not null,
            subsistema text not null,
            variable text not null,
            nivel text not null,
            mecanismo text not null,
            procedencia text not null,
            que_ocurrio text not null,
            json text not null
        )
    """

    def __init__(self, ruta: str | Path | None = None):
        ruta = ruta if ruta is not None else os.environ.get("HMTA_DB_PATH", str(RUTA_POR_DEFECTO))
        self.persistente = str(ruta) != ":memory:"
        try:
            if self.persistente:
                Path(ruta).parent.mkdir(parents=True, exist_ok=True)
            self._con = sqlite3.connect(str(ruta), check_same_thread=False)
            self._con.execute(self.ESQUEMA)
            self._con.commit()
        except (sqlite3.OperationalError, OSError) as exc:
            log.warning("Registro HMTA en memoria: no se pudo abrir %s (%s)", ruta, exc)
            self.persistente = False
            self._con = sqlite3.connect(":memory:", check_same_thread=False)
            self._con.execute(self.ESQUEMA)
        self.ruta = str(ruta) if self.persistente else ":memory:"

    def guardar(self, alertas: list[Alerta]) -> int:
        """Inserta las alertas nuevas. Devuelve cuantas lo eran."""
        antes = self.total()
        self._con.executemany(
            "insert or ignore into eventos (id, inicio, fin, subsistema, variable, nivel, "
            "mecanismo, procedencia, que_ocurrio, json) values (?,?,?,?,?,?,?,?,?,?)",
            [(a.id, a.inicio, a.fin, a.subsistema, a.variable, a.nivel, a.mecanismo,
              a.procedencia, a.que_ocurrio, json.dumps(a.dict(), ensure_ascii=False, default=str))
             for a in alertas])
        self._con.commit()
        return self.total() - antes

    def total(self) -> int:
        return self._con.execute("select count(*) from eventos").fetchone()[0]

    def listar(self, subsistema: str | None = None, procedencia: str | None = None,
               nivel: str | None = None, limite: int = 500) -> list[dict]:
        sql = "select json, registrado_utc from eventos where 1=1"
        args: list = []
        for col, val in (("subsistema", subsistema), ("procedencia", procedencia),
                         ("nivel", nivel)):
            if val:
                sql += f" and {col} = ?"
                args.append(val)
        sql += " order by inicio desc limit ?"
        args.append(limite)
        fuera = []
        for texto, registrado in self._con.execute(sql, args):
            d = json.loads(texto)
            d["registrado_utc"] = registrado
            fuera.append(d)
        return fuera
