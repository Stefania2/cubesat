"""Lista blanca de acciones de interfaz que LIRA puede pedir.

Una accion es un nombre y unos parametros. `validar` la acepta o la rechaza
con un motivo; nunca la «corrige» en silencio (un SNR de 15 dB no se convierte
en 12: se rechaza y se dice el limite). Lo que no esta aqui no existe para
LIRA, venga del interprete o de Claude.

Ninguna accion toca el satelite: STRaND-1 esta inactivo y la plataforma no
tiene canal de subida. Todas actuan sobre la interfaz o sobre la simulacion del
enlace RF, que es un modelo en banda base.

Criticas (piden confirmacion explicita): lanzar o reiniciar la simulacion del
enlace —sustituye el resultado que se esta viendo— y restablecer la vista del
gemelo —pierde la posicion de reproduccion—.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

PAGINAS = {
    "inicio": "/", "observaciones": "/observations", "telemetria": "/telemetry",
    "enlace": "/enlace", "simulacion": "/simulacion", "analisis": "/analytics",
    "avanzado": "/advanced", "validacion": "/validacion", "documentacion": "/docs",
}
SECCIONES = {
    "inicio": ("gemelo", "salud", "mensajes"),
    "validacion": ("resumen", "procedencia", "orbital", "telemetria", "temporal",
                   "diagnosticos", "reproducibilidad", "informes"),
}
VISTAS = ("exterior", "interior", "explotada")
CAMARAS = ("isometrica", "frontal", "lateral", "superior")
PESTANAS_GEMELO = ("monitor", "subsistemas", "estructura", "procedencia")
ACCIONES_ENLACE = ("iniciar", "detener", "reiniciar")
NOMBRE_CAMARA = {"isometrica": "isométrica (modelo centrado)", "frontal": "frontal", "lateral": "lateral",
                 "superior": "superior"}

# Limites de la simulacion del enlace: los mismos que impone el servicio
# (`services/enlace_monitor.py`, SNR_MIN_DB y SNR_MAX_DB). Se leen de alli si
# esta disponible para no mantener dos copias.
SNR_MIN_DB, SNR_MAX_DB = 0.0, 12.0


@dataclass
class Accion:
    nombre: str
    parametros: dict[str, Any] = field(default_factory=dict)
    critica: bool = False
    descripcion: str = ""

    def dict(self) -> dict:
        return asdict(self)


class AccionRechazada(ValueError):
    pass


@lru_cache(maxsize=1)
def _velocidades() -> tuple[float, ...]:
    from gemelo_digital.reproduccion import VELOCIDADES

    return tuple(float(v) for v in VELOCIDADES)


@lru_cache(maxsize=1)
def _limites_archivo() -> tuple[Any, Any, tuple[str, ...]]:
    """Primer y ultimo evento del archivo y magnitudes numericas disponibles."""
    from validacion_cientifica import reconstruccion as R

    m = R._motor()
    ev = m["eventos"]
    magnitudes = tuple(sorted(n for n, s in m["series"].items() if not s.discreta))
    return ev[0], ev[-1], magnitudes


def _enum(valor: Any, opciones: tuple[str, ...], que: str) -> str:
    if not isinstance(valor, str) or valor not in opciones:
        raise AccionRechazada(f"{que} «{valor}» no existe. Opciones: {', '.join(opciones)}.")
    return valor


def validar(nombre: str, parametros: dict[str, Any] | None) -> Accion:
    """Devuelve la accion validada o lanza AccionRechazada con el motivo."""
    p = dict(parametros or {})

    def sobran(*admitidos: str) -> None:
        extra = set(p) - set(admitidos)
        if extra:
            raise AccionRechazada(f"Parámetros no admitidos en «{nombre}»: {', '.join(sorted(extra))}.")

    if nombre == "navegar":
        sobran("pagina", "seccion")
        pagina = _enum(p.get("pagina"), tuple(PAGINAS), "La página")
        out = {"pagina": pagina, "ruta": PAGINAS[pagina]}
        if p.get("seccion") is not None:
            out["seccion"] = _enum(p["seccion"], SECCIONES.get(pagina, ()), f"La sección de {pagina}")
        return Accion(nombre, out, descripcion=f"Ir a {pagina}" + (f" · {out['seccion']}" if "seccion" in out else ""))

    if nombre == "gemelo_vista":
        sobran("modo")
        return Accion(nombre, {"modo": _enum(p.get("modo"), VISTAS, "La vista")},
                      descripcion=f"Vista {p['modo']} del modelo 3D")

    if nombre == "gemelo_camara":
        sobran("camara")
        camara = _enum(p.get("camara"), CAMARAS, "La cámara")
        return Accion(nombre, {"camara": camara}, descripcion=f"Cámara {NOMBRE_CAMARA[camara]}")

    if nombre == "gemelo_pestana":
        sobran("pestana")
        return Accion(nombre, {"pestana": _enum(p.get("pestana"), PESTANAS_GEMELO, "La pestaña")},
                      descripcion=f"Pestaña {p['pestana']} del gemelo")

    if nombre == "gemelo_reproduccion":
        sobran("estado")
        estado = _enum(p.get("estado"), ("reproducir", "pausar"), "El estado")
        return Accion(nombre, {"estado": estado}, descripcion=f"{estado.capitalize()} la reproducción")

    if nombre == "gemelo_velocidad":
        sobran("valor")
        try:
            v = float(p.get("valor"))
        except (TypeError, ValueError) as exc:
            raise AccionRechazada("La velocidad debe ser un número.") from exc
        if v not in _velocidades():
            raise AccionRechazada(f"Velocidad ×{v:g} no disponible. Opciones: "
                                  + ", ".join(f"×{x:g}" for x in _velocidades()) + ".")
        return Accion(nombre, {"valor": v}, descripcion=f"Velocidad ×{v:g}")

    if nombre == "gemelo_ir_a_fecha":
        sobran("fecha")
        from validacion_cientifica.tiempo import FechaInvalida, instante_utc, iso

        try:
            t = instante_utc(p.get("fecha"), exigir_zona=False)
        except FechaInvalida as exc:
            raise AccionRechazada(str(exc)) from exc
        ini, fin, _ = _limites_archivo()
        if not ini <= t <= fin:
            raise AccionRechazada(f"La fecha {iso(t)[:10]} está fuera del archivo de telemetría "
                                  f"({iso(ini)[:10]} a {iso(fin)[:10]}).")
        return Accion(nombre, {"fecha": iso(t)}, descripcion=f"Llevar el gemelo al {iso(t)[:19]} UTC")

    if nombre == "gemelo_magnitud":
        sobran("campo")
        _, _, magnitudes = _limites_archivo()
        campo = p.get("campo")
        if campo not in magnitudes:
            raise AccionRechazada(f"«{campo}» no es una magnitud del archivo.")
        return Accion(nombre, {"campo": campo}, descripcion=f"Magnitud gobernante: {campo}")

    if nombre == "enlace_simulacion":
        sobran("accion", "snr_db")
        accion = _enum(p.get("accion"), ACCIONES_ENLACE, "La acción del enlace")
        out: dict[str, Any] = {"accion": accion}
        if accion == "iniciar":
            if p.get("snr_db") is None:
                raise AccionRechazada(f"Para iniciar la simulación hace falta el SNR "
                                      f"({SNR_MIN_DB:g} a {SNR_MAX_DB:g} dB).")
            try:
                snr = float(p["snr_db"])
            except (TypeError, ValueError) as exc:
                raise AccionRechazada("El SNR debe ser un número en dB.") from exc
            if not SNR_MIN_DB <= snr <= SNR_MAX_DB:
                raise AccionRechazada(f"SNR {snr:g} dB fuera del rango permitido "
                                      f"({SNR_MIN_DB:g} a {SNR_MAX_DB:g} dB). No se ejecuta.")
            out["snr_db"] = snr
        elif p.get("snr_db") is not None:
            raise AccionRechazada("El SNR solo se indica al iniciar la simulación.")
        critica = accion in ("iniciar", "reiniciar")
        desc = {"iniciar": f"Lanzar la simulación del enlace RF con SNR {out.get('snr_db', 0):g} dB "
                           "(sustituye el resultado actual; datos SIMULADOS)",
                "detener": "Detener la simulación del enlace RF",
                "reiniciar": "Reiniciar la simulación del enlace RF (borra el resultado actual)"}[accion]
        return Accion(nombre, out, critica=critica, descripcion=desc)

    if nombre == "restablecer_vista":
        sobran()
        return Accion(nombre, {}, critica=True,
                      descripcion="Restablecer el gemelo: vista exterior, cámara isométrica, "
                                  "reproducción en pausa al inicio del archivo")

    raise AccionRechazada(f"La acción «{nombre}» no está permitida.")


def esquemas_para_claude() -> list[dict]:
    """Una herramienta `proponer_accion` con la lista blanca como enumeracion.

    Claude no ejecuta nada: propone; el backend valida con `validar`.
    """
    return [{
        "name": "proponer_accion",
        "description": (
            "Propone UNA acción sobre la interfaz de la plataforma STRaND-1 (no sobre el satélite). "
            "El backend la valida; las críticas esperan confirmación del usuario. Acciones y parámetros: "
            "navegar{pagina: " + "|".join(PAGINAS) + ", seccion?}; "
            "gemelo_vista{modo: " + "|".join(VISTAS) + "}; "
            "gemelo_camara{camara: " + "|".join(CAMARAS) + "} (centrar = isometrica); "
            "gemelo_pestana{pestana: " + "|".join(PESTANAS_GEMELO) + "}; "
            "gemelo_reproduccion{estado: reproducir|pausar}; "
            "gemelo_velocidad{valor: 0.25|0.5|1|2|5|10|60|300}; "
            "gemelo_ir_a_fecha{fecha: ISO 8601 UTC}; gemelo_magnitud{campo}; "
            f"enlace_simulacion{{accion: iniciar|detener|reiniciar, snr_db: {SNR_MIN_DB:g}-{SNR_MAX_DB:g} solo al iniciar}}; "
            "restablecer_vista{}."),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "enum": [
                    "navegar", "gemelo_vista", "gemelo_camara", "gemelo_pestana", "gemelo_reproduccion",
                    "gemelo_velocidad", "gemelo_ir_a_fecha", "gemelo_magnitud", "enlace_simulacion",
                    "restablecer_vista"]},
                "parametros": {"type": "object", "description": "Parámetros de la acción, según la lista."},
            },
            "required": ["nombre", "parametros"],
            "additionalProperties": False,
        },
    }]
