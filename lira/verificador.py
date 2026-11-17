"""Verificador de cifras: ningun numero de una respuesta sin una herramienta que lo respalde.

El modelo de lenguaje no debe inventar telemetria. El prompt se lo pide, pero
un prompt no es una garantia; esto si es comprobable. Se extraen los numeros
de la respuesta y se buscan en lo que devolvieron las herramientas en ese
turno (y en la propia pregunta del usuario). Un numero coincide si alguno de
la reserva, redondeado con los decimales que escribio la respuesta, da el
mismo valor; tambien se admite la forma en porcentaje de una fraccion.

Exentos: enteros de 0 a 12 (enumeraciones, «los 6 paneles», horas) y años
entre 2010 y 2030 cuando aparecen como tales. Lo que no coincide se devuelve
en `no_verificadas` y la interfaz lo marca; no se borra de la respuesta.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

_NUM = re.compile(r"(?<![\w.,])-?(?:\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,]\d+)?(?![\w])")


def numeros_en_texto(texto: str) -> list[tuple[str, float, int]]:
    """(literal, valor, decimales) de cada numero escrito en el texto."""
    out = []
    for m in _NUM.finditer(texto):
        lit = m.group(0)
        limpio = re.sub(r"[   ]", "", lit)
        if "," in limpio and "." in limpio:
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", ".")
        try:
            valor = float(limpio)
        except ValueError:
            continue
        dec = len(limpio.split(".")[1]) if "." in limpio else 0
        out.append((lit, valor, dec))
    return out


def _reserva(fuentes: Iterable[Any]) -> list[float]:
    pool: list[float] = []

    def recorrer(x: Any) -> None:
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            pool.append(float(x))
        elif isinstance(x, str):
            pool.extend(v for _, v, _ in numeros_en_texto(x))
            pool.extend(float(n) for n in re.findall(r"\d+", x))  # piezas de fechas: 2021, 03, 01
        elif isinstance(x, dict):
            for v in x.values():
                recorrer(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                recorrer(v)

    for f in fuentes:
        if isinstance(f, str) and f[:1] in ("[", "{"):
            try:
                f = json.loads(f)
            except json.JSONDecodeError:
                pass
        recorrer(f)
    return pool


def verificar(texto: str, fuentes: Iterable[Any]) -> dict:
    pool = _reserva(fuentes)
    no_verificadas = []
    n = 0
    for lit, v, dec in numeros_en_texto(texto):
        if v == int(v) and (0 <= v <= 12 or 2010 <= v <= 2030):
            continue
        n += 1
        tol = 0.5 * 10 ** (-dec) + 1e-9
        ok = any(abs(p - v) <= tol or abs(p * 100 - v) <= tol for p in pool)
        if not ok:
            no_verificadas.append(lit)
    return {"cifras_comprobadas": n, "no_verificadas": no_verificadas, "ok": not no_verificadas}
