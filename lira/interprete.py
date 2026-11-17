"""Interprete determinista de ordenes en español.

Resuelve sin IA lo que tiene una forma reconocible: ordenes de interfaz
(«vista explotada», «pausa», «ve al 3 de marzo de 2021») y consultas directas
(«¿cuál es el voltaje?», «temperatura»). Es gratuito, inmediato y
reproducible, y es lo unico que funciona sin la contraseña de la IA.

Reglas de ambigüedad: si una orden admite dos lecturas y el contexto (la
pagina en pantalla) no decide, se pregunta en lugar de elegir. «Pausa la
simulacion» en el inicio es la reproduccion del gemelo; en Enlace RF es la
simulacion del enlace; en otra pagina, se pregunta.

Devuelve una `Interpretacion`; `cubierta` dice si la frase se entendio entera.
Lo que no se entiende entero pasa a Claude (si hay acceso) o se responde
con lo que si se sabe hacer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


SIN_CANAL_DE_COMANDOS = (
    "No puedo enviar órdenes al satélite: STRaND-1 está inactivo y esta plataforma no tiene canal de "
    "comandos hacia él. Solo actúo sobre la interfaz y sobre la simulación del enlace.")


@dataclass
class Interpretacion:
    aviso: str | None = None
    acciones: list[tuple[str, dict]] = field(default_factory=list)
    consultas: list[tuple[str, dict]] = field(default_factory=list)
    aclaracion: str | None = None
    confirmacion: str | None = None      # "confirmar" | "cancelar"
    cubierta: bool = False
    no_entendido: list[str] = field(default_factory=list)


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[¿?¡!.;:]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _fecha(t: str) -> str | None:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[t ](\d{2}):(\d{2}))?", t)
    if m:
        y, mo, d, hh, mm = m.groups()
        return f"{y}-{mo}-{d}T{hh or '00'}:{mm or '00'}:00Z"
    m = re.search(r"(?:(\d{1,2}) de )?(" + "|".join(MESES) + r")(?: de(?:l)?)? (\d{4})", t)
    if m:
        d, mes, y = m.groups()
        return f"{y}-{MESES[mes]:02d}-{int(d or 1):02d}T00:00:00Z"
    return None


PAGINAS = [("telemetria", "telemetria"), ("observacion", "observaciones"), ("enlace", "enlace"),
           ("simulacion", "simulacion"), ("analisis", "analisis"), ("avanzado", "avanzado"),
           ("validacion", "validacion"), ("documentacion", "documentacion"), ("inicio", "inicio")]
VERBOS_IR = r"\b(abre|abrir|ve a|ir a|vamos a|llevame a|lleva(?:me)? al?|muestra(?:me)?|mostrar|cambia(?:r)? a|pasa a|navega a)\b"
CONSULTA_VARIABLE = [("temperatura", "temperatura"), ("calor", "temperatura"), ("caliente", "temperatura"),
                     ("calent", "temperatura"),
                     ("frio", "temperatura"), ("termic", "temperatura"), ("voltaje", "voltaje"), ("tension", "voltaje"),
                     ("bateria", "bateria"), ("corriente", "corriente"), ("actitud", "actitud"),
                     ("orientacion del satelite", "actitud"), ("velocidad angular", "velocidad angular"),
                     ("giro", "velocidad angular"), ("potencia", "potencia"), ("estado de carga", "carga"),
                     ("magnetometro", "magnetometro"), ("ruedas de reaccion", "ruedas")]
NO_EMITIDAS = ("temperatura", "actitud", "velocidad angular", "potencia", "carga")
SUBSISTEMAS = [("energ", "eps"), ("eps", "eps"), ("termic", "termico"), ("comunicacion", "comunicaciones"),
               ("obc", "obc"), ("computador", "obc"), ("adcs", "adcs")]


def _clausula(c: str, contexto: dict, out: Interpretacion) -> bool:
    """Interpreta una clausula. Devuelve False si no la entiende."""
    pagina = (contexto or {}).get("pagina") or ""

    if re.fullmatch(r"(si |vale |ok )?(confirm\w*|adelante|hazlo|ejecuta(lo)?)", c):
        out.confirmacion = "confirmar"
        return True
    if re.fullmatch(r"(no |)(cancel\w*|olvidalo|detente|aborta\w*|no lo hagas)", c):
        out.confirmacion = "cancelar"
        return True

    # Ordenes dirigidas al satelite: no existe canal de comandos. Respuesta fija, sin IA.
    if (re.search(r"\b(apaga\w*|enciende\w*|desactiva\w*|envia\w*|manda\w*|ordena\w*|telecomando\w*|"
                  r"reduc\w*|aument\w*|ajusta\w*|regula\w*|recarga\w*|"
                  r"comando\w*|despliega\w*|reinicia el satelite|resetea el satelite)\b", c)
            and re.search(r"\b(satelite|cubesat|strand|rueda\w*|bateria\w*|interruptor\w*|panel\w*|"
                          r"antena\w*|obc|computador|magnetometro\w*|propulsor\w*|warp|camara del satelite)\b", c)):
        out.aviso = SIN_CANAL_DE_COMANDOS
        return True

    # Preguntas que piden razonar (comparar, explicar causas, valorar, estimar):
    # una plantilla responderia otra cosa. Van a la IA.
    definicion = re.fullmatch(r"(que significa|que es|explicame|explica|para que sirve)( el| la| los| las| un| una)?"
                              r"( \w+){1,4}", c)
    if not definicion and re.search(r"\b(por que|causa\w*|motivo|compar\w*|frente a|versus|vs|diferencia\w*|relacion|significa|"
                 r"fiable|confiable|precis\w*|inventa\w*|estima\w*|calcula\w*|predic\w*|supon\w*|"
                 r"magnitud|colorea\w*|gobierna\w*|mas que|menos que|mayor|menor|antes del|despues del|"
                 r"justo antes|justo despues|cuando empez\w*|cuando comenz\w*)\b", c):
        return False

    explicar = definicion or re.search(r"\b(que es|explica(me)?|para que sirve)\b", c)
    evolucion = re.search(r"\b(evolucion|tendencia|historico|grafica)\b", c)

    # Simulacion del enlace RF / reproduccion del gemelo
    menciona_sim = re.search(r"\bsimulacion\b|\benlace\b", c)
    reproducir = re.search(r"\b(reproduce|reproducir|reproducelo|reproduzca|play|reanuda\w*|continua|continuar|"
                           r"activa|activar|inicia|iniciar|arranca|arrancar|lanza|lanzar)\b", c)
    # «para» es casi siempre preposicion: solo cuenta como orden sola («para»).
    pausar = re.search(r"\b(pausa|pausar|pausalo|deten|detener|detenla|parar|paralo|stop)\b|^para$", c)
    reiniciar = re.search(r"\b(restablec\w*|reinici\w*|resetea\w*|valores iniciales)\b", c)
    es_enlace = bool(re.search(r"\benlace\b|\brf\b|\bsnr\b", c)) or (menciona_sim and pagina == "enlace")
    es_gemelo = bool(re.search(r"reproduccion|gemelo|modelo|vista", c)) or (menciona_sim and pagina == "inicio")
    if (reproducir or pausar or reiniciar) and menciona_sim and not es_enlace and not es_gemelo:
        out.aclaracion = ("¿Te refieres a la reproducción del gemelo digital (Inicio) o a la simulación "
                          "del enlace RF (página Enlace RF)?")
        return True
    if es_enlace and (reproducir or pausar or reiniciar):
        if reiniciar:
            out.acciones.append(("enlace_simulacion", {"accion": "reiniciar"}))
        elif pausar:
            out.acciones.append(("enlace_simulacion", {"accion": "detener"}))
        else:
            m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(?:db|decibel)", c) or re.search(r"snr (?:de )?(-?\d+(?:[.,]\d+)?)", c)
            if not m:
                out.aclaracion = "¿Con qué SNR quieres lanzar la simulación del enlace? Debe estar entre 0 y 12 dB."
                return True
            out.acciones.append(("enlace_simulacion", {"accion": "iniciar", "snr_db": float(m.group(1).replace(",", "."))}))
        return True
    if reiniciar and not menciona_sim:
        out.acciones.append(("restablecer_vista", {}))
        return True

    if re.search(r"\bcentr\w*\b", c):
        out.acciones.append(("gemelo_camara", {"camara": "isometrica"}))
        return True
    if not explicar and re.search(r"\b(explotad\w*|despiez\w*|desarma\w*)\b", c):
        out.acciones.append(("gemelo_vista", {"modo": "explotada"}))
        return True
    if re.search(r"\b(vista interior|por dentro|interior)\b", c) and not explicar:
        out.acciones.append(("gemelo_vista", {"modo": "interior"}))
        return True
    if re.search(r"\b(vista exterior|por fuera|exterior)\b", c):
        out.acciones.append(("gemelo_vista", {"modo": "exterior"}))
        return True
    for patron, camara in ((r"frontal|de frente", "frontal"), (r"lateral|de lado|perfil", "lateral"),
                           (r"superior|desde arriba|cenital|planta", "superior"), (r"isometric\w*", "isometrica")):
        if re.search(patron, c) and re.search(r"camara|vista|mira|muestra|gira|orienta|pon|ver", c):
            out.acciones.append(("gemelo_camara", {"camara": camara}))
            return True
    m = re.search(r"velocidad\s*(?:a|de|x)?\s*x?\s*(\d+(?:[.,]\d+)?)", c) or re.search(r"\bx\s*(\d+(?:[.,]\d+)?)\b", c)
    if m and "angular" not in c:
        out.acciones.append(("gemelo_velocidad", {"valor": float(m.group(1).replace(",", "."))}))
        return True
    if (reproducir or pausar) and (es_gemelo or not menciona_sim):
        if pausar or reproducir:
            out.acciones.append(("gemelo_reproduccion", {"estado": "pausar" if pausar else "reproducir"}))
            return True

    fecha = _fecha(c)
    if fecha and re.search(r"\b(ve|ir|lleva\w*|salta\w*|mueve\w*|situa\w*|posiciona\w*|cursor)\b", c):
        out.acciones.append(("gemelo_ir_a_fecha", {"fecha": fecha}))
        return True

    for clave, pest in (("subsistemas", "subsistemas"), ("estructura", "estructura"), ("procedencia", "procedencia")):
        if re.search(rf"\b(pestana|cambia\w*|entre)\b.*\b{clave}\b|^{clave}$", c):
            out.acciones.append(("gemelo_pestana", {"pestana": pest}))
            return True

    if re.search(VERBOS_IR, c) or re.fullmatch(r"(panel de )?\w+", c):
        if "salud" in c:
            out.acciones.append(("navegar", {"pagina": "inicio", "seccion": "salud"}))
            return True
        for clave, pag in PAGINAS:
            if clave in c and not (clave == "simulacion" and es_enlace):
                if pag == "telemetria" and any(v in c for v, _ in CONSULTA_VARIABLE):
                    break
                out.acciones.append(("navegar", {"pagina": pag}))
                return True

    # Consultas
    if re.search(r"\b(fallo\w*|falla\w*|rompi\w*|averi\w*)\b", c):
        return False   # «¿se rompió?», «el fallo de 2021»: piden interpretar, no listar
    if re.search(r"\banomal\w*\b", c):
        args = {"campo": "battery_voltage"}
        anio = re.search(r"\b(20[12]\d)\b", c)
        if anio:
            args.update(desde=f"{anio.group(1)}-01-01T00:00:00Z", hasta=f"{anio.group(1)}-12-31T23:59:59Z")
        out.consultas.append(("anomalias", args))
        return True
    for clave, sub in SUBSISTEMAS:
        if clave in c and re.search(r"\b(estado|subsistema|como esta|como va)\b", c):
            out.consultas.append(("estado_subsistema", {"subsistema": sub, **({"fecha": fecha} if fecha else {})}))
            return True
    for clave, nombre in CONSULTA_VARIABLE:
        if clave in c:
            if explicar:
                out.consultas.append(("explicar_variable", {"nombre": nombre}))
            elif evolucion and nombre in NO_EMITIDAS:
                out.consultas.append(("consultar_variable", {"nombre": nombre}))
            elif evolucion:
                out.consultas.append(("tendencia", {"campo": nombre}))
                if nombre in ("voltaje", "bateria"):
                    out.acciones.append(("navegar", {"pagina": "inicio", "seccion": "gemelo"}))
                    out.acciones.append(("gemelo_magnitud", {"campo": "battery_voltage"}))
            else:
                out.consultas.append(("consultar_variable", {"nombre": nombre, **({"fecha": fecha} if fecha else {})}))
            return True
    # La orbita despues de las variables: «el pico termico en su peor orbita» es temperatura.
    if re.search(r"\b(donde esta|posicion|orbita\w*|ubicacion|coordenadas)\b", c):
        out.consultas.append(("posicion_orbital", {"fecha": fecha} if fecha else {}))
        return True
    if re.search(r"\b(estado general|resumen|como esta|estado del (satelite|cubesat)|reporte|informe de estado)\b", c):
        out.consultas.append(("estado_en_instante", {"fecha": fecha} if fecha else {}))
        return True
    return False


def interpretar(texto: str, contexto: dict | None = None) -> Interpretacion:
    out = Interpretacion()
    t = normalizar(texto)
    if not t:
        out.aclaracion = "No he oído nada. ¿Puedes repetirlo?"
        out.cubierta = True
        return out
    # Varias ordenes en una frase: «vista explotada y camara superior».
    clausulas = [c.strip() for c in re.split(r",| y luego | y despues | y (?=\w)", t) if c.strip()]
    for c in clausulas:
        if not _clausula(c, contexto or {}, out):
            out.no_entendido.append(c)
        if out.aclaracion:
            break
    out.cubierta = not out.no_entendido
    return out
