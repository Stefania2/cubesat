"""Acceso a la IA, fichas firmadas y limites de uso.

La aplicacion es publica; la parte con IA gasta saldo de Anthropic, asi que
pide una contraseña. Variables de entorno (ninguna se imprime ni se registra):

    ANTHROPIC_API_KEY   clave de la API de Anthropic
    LIRA_CLAVE          contraseña de la IA (o LIRA_CLAVE_SHA256 con su huella)
    LIRA_SECRETO        opcional: clave para firmar fichas; por defecto se deriva de la contraseña

Sin LIRA_CLAVE, en Vercel la IA queda desactivada (nunca abierta por omision);
en local, sin LIRA_CLAVE, la IA se permite sin contraseña.

Las fichas (de sesion y de confirmacion) son HMAC-SHA256 sin estado, porque en
Vercel cada peticion puede caer en una instancia distinta. Los limites de uso
se llevan en memoria de la instancia: frenan el abuso, pero no son un tope de
gasto exacto. El tope real es el limite de gasto de la cuenta en la consola
de Anthropic.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque

DURACION_SESION_S = 12 * 3600
DURACION_CONFIRMACION_S = 60
MAX_INTENTOS_CLAVE = 5            # por IP cada 10 minutos
MAX_TURNOS_IA_HORA = 30           # por sesion
MAX_TURNOS_IA_DIA_INSTANCIA = 300


def en_vercel() -> bool:
    return bool(os.environ.get("VERCEL"))


def _huella_clave() -> str | None:
    h = os.environ.get("LIRA_CLAVE_SHA256", "").strip().lower()
    if h:
        return h
    c = os.environ.get("LIRA_CLAVE", "")
    return hashlib.sha256(c.encode()).hexdigest() if c else None


def credencial_anthropic() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def requiere_clave() -> bool:
    return _huella_clave() is not None or en_vercel()


def ia_configurada() -> bool:
    """Hay credencial de Anthropic y la IA no esta abierta sin contraseña en publico."""
    if not credencial_anthropic():
        return False
    return not (en_vercel() and _huella_clave() is None)


def _secreto() -> bytes:
    s = os.environ.get("LIRA_SECRETO")
    if s:
        return s.encode()
    return hashlib.sha256(("lira-fichas:" + (_huella_clave() or "local-sin-clave")).encode()).digest()


def _firmar(datos: dict) -> str:
    cuerpo = base64.urlsafe_b64encode(json.dumps(datos, separators=(",", ":"), sort_keys=True).encode()).decode().rstrip("=")
    firma = hmac.new(_secreto(), cuerpo.encode(), hashlib.sha256).hexdigest()
    return f"{cuerpo}.{firma}"


def _leer(ficha: str | None, tipo: str) -> dict | None:
    if not ficha or "." not in ficha or len(ficha) > 4000:
        return None
    cuerpo, firma = ficha.rsplit(".", 1)
    esperada = hmac.new(_secreto(), cuerpo.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(firma, esperada):
        return None
    try:
        datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    if datos.get("tipo") != tipo or datos.get("exp", 0) < time.time():
        return None
    return datos


# ── Contraseña y sesion ─────────────────────────────────────────────────────

_intentos: dict[str, deque] = defaultdict(deque)


def _ventana(cola: deque, segundos: float) -> None:
    ahora = time.time()
    while cola and cola[0] < ahora - segundos:
        cola.popleft()


class Bloqueado(Exception):
    pass


def comprobar_clave(clave: str, ip: str) -> str | None:
    """Ficha de sesion si la contraseña es correcta; None si no. Bloquea tras varios fallos."""
    cola = _intentos[ip]
    _ventana(cola, 600)
    if len(cola) >= MAX_INTENTOS_CLAVE:
        raise Bloqueado("Demasiados intentos. Espera unos minutos.")
    huella = _huella_clave()
    if huella is None:
        return None if en_vercel() else crear_sesion()
    # Los teclados del móvil añaden espacios al final y cambian mayúsculas: se
    # aceptan la contraseña tal cual, sin espacios y sin espacios en mayúsculas.
    limpia = "".join((clave or "").split())
    candidatas = {clave or "", limpia, limpia.upper()}
    if not any(hmac.compare_digest(hashlib.sha256(c.encode()).hexdigest(), huella) for c in candidatas):
        cola.append(time.time())
        return None
    cola.clear()
    return crear_sesion()


def crear_sesion() -> str:
    return _firmar({"tipo": "sesion", "sid": secrets.token_hex(8), "exp": int(time.time()) + DURACION_SESION_S})


def sesion_valida(ficha: str | None) -> dict | None:
    if not requiere_clave():
        return {"sid": "local"}
    return _leer(ficha, "sesion")


_turnos: dict[str, deque] = defaultdict(deque)
_turnos_dia: deque = deque()


def consumir_turno_ia(sid: str) -> None:
    cola = _turnos[sid]
    _ventana(cola, 3600)
    _ventana(_turnos_dia, 86400)
    if len(cola) >= MAX_TURNOS_IA_HORA:
        raise Bloqueado(f"Límite de {MAX_TURNOS_IA_HORA} preguntas a la IA por hora alcanzado.")
    if len(_turnos_dia) >= MAX_TURNOS_IA_DIA_INSTANCIA:
        raise Bloqueado("Límite diario de uso de la IA alcanzado en este servidor.")
    cola.append(time.time())
    _turnos_dia.append(time.time())


# ── Confirmacion de acciones criticas ───────────────────────────────────────

_usadas: set[str] = set()


def ficha_confirmacion(accion: dict) -> str:
    return _firmar({"tipo": "confirmacion", "accion": accion, "nonce": secrets.token_hex(6),
                    "exp": int(time.time()) + DURACION_CONFIRMACION_S})


def leer_confirmacion(ficha: str) -> dict | None:
    """La accion firmada si la ficha es valida, no ha caducado y no se ha usado en esta instancia."""
    datos = _leer(ficha, "confirmacion")
    if datos is None or datos["nonce"] in _usadas:
        return None
    _usadas.add(datos["nonce"])
    return datos["accion"]
