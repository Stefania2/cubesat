"""Un turno de conversacion con LIRA.

    1. El interprete determinista intenta entender la frase entera.
    2. Si la entiende: ejecuta consultas, valida acciones y redacta con plantillas
       cuyos numeros salen de las herramientas. Sin IA, sin coste.
    3. Si no, y hay acceso a la IA: Claude (claude-sonnet-5-5) con las mismas
       herramientas de consulta y una herramienta `proponer_accion`. El bucle lo
       llevamos nosotros: cada propuesta se valida con `acciones.validar`.
    4. Sin acceso: se hace lo entendido y se dice que lo demas requiere la IA.

En todos los casos la respuesta pasa por el verificador de cifras y se anota
en el registro (solo en local). Las acciones criticas no se devuelven como
ejecutables: se devuelve una ficha firmada que el usuario confirma o cancela.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from . import MODELO
from . import acciones as AC
from . import herramientas as H
from . import registro, seguridad, verificador
from .interprete import interpretar

MAX_ITERACIONES = 6
PRESUPUESTO_S = 40.0            # la funcion de Vercel corta a los 60 s
MAX_HISTORIAL = 6
ESFUERZO = "medium"

SISTEMA = """Eres LIRA (Language Intelligence for Real-time Aerospace Operations), la copiloto de \
misión de la plataforma STRaND-1: el archivo histórico de telemetría del CubeSat STRaND-1 \
(NORAD 39090, inactivo), su gemelo digital 3D y una simulación del enlace RF.

Reglas que no puedes romper:
1. Ningún número sin herramienta. Toda cifra de telemetría, órbita o estadística que digas debe \
salir del resultado de una herramienta de este turno. Si no la tienes, consúltala o di que no la tienes.
2. Lo que no existe se dice. STRaND-1 nunca emitió temperaturas, actitud, velocidad angular, \
corrientes de batería ni de bus. Si te las piden, di explícitamente que NO ESTÁN DISPONIBLES y \
por qué; nunca las estimes ni las rellenes con cero.
3. Distingue siempre la naturaleza del dato: MEDIDO (baliza real), CALCULADO (SGP4, calibración), \
DERIVADO (estadístico), SIMULADO (enlace RF). Si una lectura es vieja respecto al instante, dilo. \
Si una herramienta marca «validez» (canal sin medida), dilo antes que el valor.
4. Anomalías solo según las reglas documentadas que devuelve la herramienta `anomalias`. Una \
desviación estadística nunca es una falla confirmada.
5. Para cambiar la interfaz usa solo `proponer_accion`. No puedes ejecutar código ni enviar nada \
al satelite: no existe canal de comandos. Si te lo piden, explícalo.
6. Si la orden es ambigua, pregunta antes de proponer acciones.
7. Tus respuestas se leen en voz alta: español claro, frases cortas, como máximo unas 90 palabras \
salvo que pidan detalle. Fechas en UTC. Sin markdown ni listas largas."""


class SinAcceso(Exception):
    pass


# ── Plantillas (modo determinista) ──────────────────────────────────────────

def _n(v: Any) -> str:
    if isinstance(v, float):
        return (f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:.1f}").replace(".", ",")
    return str(v)


def _f(iso: str | None) -> str:
    return f"{iso[:10]} {iso[11:19]} UTC" if iso else "fecha desconocida"


def redactar(nombre: str, r: dict) -> str:
    if nombre == "consultar_variable":
        if not r.get("variables"):
            return r.get("nota", "No reconozco esa variable.")
        partes = []
        for v in r["variables"]:
            if v.get("estado") == H.NO_DISPONIBLE:
                partes.append(f"{v['nombre']}: no disponible. {v['nota']}")
                continue
            for l in v.get("lecturas", []):
                if l.get("valor") is None:
                    partes.append(f"{v['nombre']}: sin medición anterior a ese instante.")
                    continue
                txt = f"{v['nombre']}: {_n(l['valor'])} {l.get('unidad') or ''}, medido el {_f(l['medida_utc'])}."
                if l.get("validez"):
                    txt += " Atención: " + l["validez"]
                elif l.get("nota"):
                    txt += " " + l["nota"]
                partes.append(txt)
        return " ".join(partes)
    if nombre == "explicar_variable":
        if not r.get("variables"):
            return r.get("nota", "")
        v = r["variables"][0]
        disp = {"emitida": "STRaND-1 la emite.", "definida_no_emitida": "STRaND-1 nunca la emitió.",
                "no_existe": "Ningún canal de STRaND-1 la mide.", "derivada": "Se calcularía a partir de otras."}
        return f"{v['nombre']}: {v['que_es']} {v['por_que_importa']} {disp.get(v['disponibilidad'], '')}"
    if nombre == "estado_en_instante":
        bv = next((l for l in r["lecturas"] if l["campo"] == "battery_voltage"), None)
        txt = f"Estado de STRaND-1 al {_f(r['instante_utc'])}. "
        if bv and bv.get("valor") is not None:
            txt += f"Voltaje de batería {_n(bv['valor'])} V, medido el {_f(bv['medida_utc'])}"
            txt += " (canal sin medida: cuenta del ADC en cero). " if bv.get("validez") else ". "
        d = r["diagnostico"]
        txt += f"Diagnóstico estadístico: {(d.get('interpretacion') or 'no evaluable').replace('_', ' ')}. "
        o = r["orbita"]
        if o.get("latitud_deg") is not None:
            txt += (f"Posición calculada: latitud {_n(o['latitud_deg'])} grados, longitud {_n(o['longitud_deg'])}, "
                    f"altura {_n(o['altura_km'])} km. ")
        else:
            txt += "Posición orbital no disponible: no hay un TLE cercano a esa fecha. "
        return txt + "No hay temperaturas ni actitud: el satélite nunca las transmitió."
    if nombre == "estado_subsistema":
        partes = [f"{r['descripcion']}."]
        for v in r["variables"]:
            if v.get("estado") == H.NO_DISPONIBLE:
                partes.append(f"{v['nombre']}: no disponible.")
            else:
                vals = [l for l in v.get("lecturas", []) if l.get("valor") is not None]
                if vals:
                    l = vals[0]
                    partes.append(f"{v['nombre']}: {_n(l['valor'])} {l.get('unidad') or ''}"
                                  + (" (canal sin medida)" if l.get("validez") else "") + ".")
        if r.get("nota"):
            partes.append(r["nota"])
        return " ".join(partes)
    if nombre == "tendencia":
        s = r["resumen"]
        if not s.get("lecturas"):
            return f"No hay lecturas de {r['campo']} en ese intervalo."
        txt = (f"{r['campo']}: {s['lecturas']} lecturas entre {s['desde'][:10]} y {s['hasta'][:10]}; mediana "
               f"{_n(s['mediana'])}, mínimo {_n(s['minimo'])}, máximo {_n(s['maximo'])}.")
        if s.get("lecturas_en_la_ordenada"):
            txt += f" {s['lecturas_en_la_ordenada']} lecturas son la ordenada de la recta: no son medidas."
        t = r.get("tendencia")
        if r.get("lecturas_excluidas_de_la_tendencia"):
            txt += " La tendencia se calcula sin ellas."
        if t is None:
            txt += " No hay medidas suficientes para una tendencia."
        else:
            txt += (f" Tendencia {'significativa' if t['significativa'] else 'no significativa'}: "
                    f"{_n(t['pendiente_por_dia'])} por día.")
        return txt
    if nombre == "anomalias":
        if not r["eventos"]:
            return f"No hay tramos anómalos de {r['campo']} según las reglas documentadas."
        e = r["eventos"][0]
        return (f"{r['eventos_total']} tramos anómalos de {r['campo']}. El más largo: "
                f"{(e['interpretacion'] or e['etiqueta']).replace('_', ' ')}, del {e['inicio'][:10]} al "
                f"{e['fin'][:10]}, {e['n_lecturas']} lecturas. Es un diagnóstico estadístico, no una falla confirmada.")
    if nombre == "posicion_orbital":
        te = r.get("terrestre")
        if not te:
            return f"Posición no disponible al {_f(r['instante_utc'])}. {r['nota']}"
        return (f"Al {_f(r['instante_utc'])}, posición calculada con SGP4: latitud {_n(te['latitud_deg'])} grados, "
                f"longitud {_n(te['longitud_deg'])}, altura {_n(te['altura_km'])} km, rapidez "
                f"{_n(r['rapidez_km_s'])} km por segundo. TLE de {_n(abs(r['antiguedad_tle_dias']))} días de antigüedad.")
    if nombre == "limites":
        return (f"Archivo de {r['archivo_desde'][:10]} a {r['archivo_hasta'][:10]}; SNR de la simulación entre "
                f"{_n(r['snr_db'][0])} y {_n(r['snr_db'][1])} dB.")
    return ""


# ── Acciones ────────────────────────────────────────────────────────────────

def _procesar_accion(nombre: str, params: dict, salida: dict) -> str:
    """Valida; añade a ejecutables o deja pendiente de confirmacion. Devuelve texto para el modelo."""
    try:
        a = AC.validar(nombre, params)
    except AC.AccionRechazada as exc:
        salida["rechazadas"].append({"nombre": nombre, "parametros": params, "motivo": str(exc)})
        return f"RECHAZADA: {exc}"
    if a.critica:
        if salida["pendiente"] is not None:
            salida["rechazadas"].append({"nombre": nombre, "parametros": params,
                                         "motivo": "Ya hay una acción crítica esperando confirmación."})
            return "RECHAZADA: ya hay una acción crítica esperando confirmación."
        salida["pendiente"] = {"ficha": seguridad.ficha_confirmacion(a.dict()), "descripcion": a.descripcion,
                               "caduca_s": seguridad.DURACION_CONFIRMACION_S}
        return "PENDIENTE DE CONFIRMACIÓN: el usuario debe confirmarla; todavía no se ha ejecutado."
    salida["acciones"].append(a.dict())
    return f"ACEPTADA: {a.descripcion}. La interfaz la ejecutará."


def _nueva_salida() -> dict:
    return {"texto": "", "modo": "determinista", "acciones": [], "pendiente": None, "rechazadas": [],
            "consultas": [], "verificacion": None, "uso": None, "aclaracion": False}


def _determinista(interp, contexto: dict, salida: dict) -> list[str]:
    textos = []
    for nombre, args in interp.consultas:
        try:
            r = H.ejecutar(nombre, args, contexto)
            salida["consultas"].append({"herramienta": nombre, "argumentos": args, "resultado": r})
            textos.append(redactar(nombre, r))
        except H.ConsultaInvalida as exc:
            textos.append(str(exc))
    for nombre, params in interp.acciones:
        _procesar_accion(nombre, params, salida)
    hechas = [a["descripcion"] for a in salida["acciones"]]
    if hechas:
        textos.append("Hecho: " + "; ".join(hechas) + ".")
    for r in salida["rechazadas"]:
        textos.append(f"No lo ejecuto: {r['motivo']}")
    if salida["pendiente"]:
        textos.append(f"Esta acción necesita confirmación: {salida['pendiente']['descripcion']}. "
                      "Di «confirmar» o pulsa Confirmar; «cancelar» la descarta.")
    return textos


# ── Claude ──────────────────────────────────────────────────────────────────

def _cliente_por_defecto():
    import anthropic

    return anthropic.Anthropic(max_retries=1, timeout=30.0)


CLIENTE: Callable[[], Any] = _cliente_por_defecto


def _mensajes(texto: str, contexto: dict, historial: list[dict]) -> list[dict]:
    msgs: list[dict] = []
    for h in (historial or [])[-MAX_HISTORIAL:]:
        rol = "user" if h.get("rol") == "usuario" else "assistant"
        t = str(h.get("texto", ""))[:1000]
        if not t or (not msgs and rol != "user"):
            continue
        if msgs and msgs[-1]["role"] == rol:
            msgs[-1]["content"] += "\n" + t
        else:
            msgs.append({"role": rol, "content": t})
    ctx = {k: contexto.get(k) for k in ("pagina", "momento_utc", "campo", "vista", "camara", "reproduciendo")
           if contexto.get(k) is not None}
    actual = f"[Contexto de la interfaz: {json.dumps(ctx, ensure_ascii=False)}]\n{texto[:2000]}"
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"] += "\n" + actual
    else:
        msgs.append({"role": "user", "content": actual})
    return msgs


def _con_ia(texto: str, contexto: dict, historial: list[dict], salida: dict) -> list[Any]:
    """Bucle de herramientas. Devuelve las fuentes (resultados) para el verificador."""
    cliente = CLIENTE()
    tools = H.esquemas_para_claude() + AC.esquemas_para_claude()
    mensajes = _mensajes(texto, contexto, historial)
    fuentes: list[Any] = []
    inicio = time.monotonic()
    uso = {"entrada": 0, "salida": 0, "cache_lectura": 0, "llamadas": 0}
    respuesta = None
    for _ in range(MAX_ITERACIONES):
        if time.monotonic() - inicio > PRESUPUESTO_S:
            salida["texto"] = "Se me acabó el tiempo para responder. Prueba con una pregunta más concreta."
            break
        respuesta = cliente.beta.messages.create(
            model=MODELO, max_tokens=4000, system=SISTEMA, tools=tools, messages=mensajes,
            output_config={"effort": ESFUERZO}, cache_control={"type": "ephemeral"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        u = getattr(respuesta, "usage", None)
        if u is not None:
            uso["entrada"] += getattr(u, "input_tokens", 0) or 0
            uso["salida"] += getattr(u, "output_tokens", 0) or 0
            uso["cache_lectura"] += getattr(u, "cache_read_input_tokens", 0) or 0
        uso["llamadas"] += 1
        if respuesta.stop_reason == "refusal":
            salida["texto"] = "No puedo ayudar con esa petición."
            break
        if respuesta.stop_reason != "tool_use":
            break
        mensajes.append({"role": "assistant", "content": respuesta.content})
        resultados = []
        for b in respuesta.content:
            if getattr(b, "type", None) != "tool_use":
                continue
            entrada = b.input if isinstance(b.input, dict) else {}
            if b.name == "proponer_accion":
                txt = _procesar_accion(str(entrada.get("nombre")), entrada.get("parametros") or {}, salida)
                resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": txt,
                                   **({"is_error": True} if txt.startswith("RECHAZADA") else {})})
                continue
            try:
                r = H.ejecutar(b.name, entrada, contexto)
                fuentes.append(r)
                salida["consultas"].append({"herramienta": b.name, "argumentos": entrada, "resultado": r})
                resultados.append({"type": "tool_result", "tool_use_id": b.id,
                                   "content": json.dumps(r, ensure_ascii=False, default=str)})
            except (H.ConsultaInvalida, KeyError, ValueError) as exc:
                resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": f"Error: {exc}",
                                   "is_error": True})
        mensajes.append({"role": "user", "content": resultados})
    if respuesta is not None and not salida["texto"]:
        salida["texto"] = " ".join(getattr(b, "text", "") for b in respuesta.content
                                   if getattr(b, "type", None) == "text").strip()
        if respuesta.stop_reason == "tool_use":
            salida["texto"] = (salida["texto"] + " (Respuesta incompleta: se alcanzó el límite de pasos.)").strip()
    salida["uso"] = uso
    return fuentes


# ── Turno ───────────────────────────────────────────────────────────────────

def turno(texto: str, contexto: dict | None = None, historial: list[dict] | None = None,
          sesion: dict | None = None) -> dict:
    contexto = contexto or {}
    salida = _nueva_salida()
    interp = interpretar(texto, contexto)
    pendiente_ctx = contexto.get("pendiente")

    if interp.confirmacion:
        if pendiente_ctx:
            salida["confirmacion"] = interp.confirmacion
            salida["texto"] = "Confirmado." if interp.confirmacion == "confirmar" else "Cancelado. No se ejecuta nada."
        else:
            salida["texto"] = "No hay ninguna acción esperando confirmación."
    elif interp.aviso and not (interp.acciones or interp.consultas):
        salida["texto"] = interp.aviso
    elif interp.aclaracion:
        salida["texto"] = interp.aclaracion
        salida["aclaracion"] = True
    elif interp.cubierta:
        textos = _determinista(interp, contexto, salida)
        if interp.aviso:
            textos.insert(0, interp.aviso)
        salida["texto"] = " ".join(t for t in textos if t)
    elif sesion is not None and seguridad.ia_configurada():
        salida["modo"] = "ia"
        seguridad.consumir_turno_ia(sesion["sid"])
        fuentes = _con_ia(texto, contexto, historial or [], salida)
        salida["verificacion"] = verificador.verificar(salida["texto"], [*fuentes, texto, contexto])
    else:
        salida["modo"] = "sin_acceso"
        partes = _determinista(interp, contexto, salida)
        if not seguridad.ia_configurada():
            motivo = "La IA no está configurada en este servidor."
        else:
            motivo = "Para preguntas abiertas necesito la contraseña de la IA."
        partes.append(f"No he entendido «{', '.join(interp.no_entendido)}». {motivo} Sin ella puedo: "
                      "consultar voltaje, corriente, temperatura u órbita; cambiar la vista o la cámara del "
                      "modelo; reproducir, pausar o ir a una fecha; y abrir cualquier página.")
        salida["texto"] = " ".join(p for p in partes if p)

    if salida["verificacion"] is None:
        salida["verificacion"] = verificador.verificar(
            salida["texto"], [c["resultado"] for c in salida["consultas"]] + [
                texto, contexto, [a["parametros"] for a in salida["acciones"]],
                [r["motivo"] for r in salida["rechazadas"]], (salida["pendiente"] or {}).get("descripcion", "")])
    registro.anotar({
        "sesion": (sesion or {}).get("sid"), "entrada": texto, "modo": salida["modo"],
        "consultas": [{"herramienta": c["herramienta"], "argumentos": c["argumentos"]} for c in salida["consultas"]],
        "acciones": salida["acciones"], "pendiente": (salida["pendiente"] or {}).get("descripcion"),
        "rechazadas": salida["rechazadas"], "verificacion": salida["verificacion"], "uso": salida["uso"],
        "modelo": MODELO if salida["modo"] == "ia" else None,
    })
    return salida


def confirmar(ficha: str, decision: str, sesion: dict | None = None) -> dict:
    """Resuelve una accion critica pendiente: la re-valida y la devuelve ejecutable, o la descarta."""
    accion = seguridad.leer_confirmacion(ficha)
    if accion is None:
        registro.anotar({"sesion": (sesion or {}).get("sid"), "confirmacion": decision, "resultado": "ficha_invalida"})
        return {"ok": False, "texto": "La confirmación ha caducado o no es válida. Vuelve a pedirlo.", "acciones": []}
    if decision != "confirmar":
        registro.anotar({"sesion": (sesion or {}).get("sid"), "confirmacion": "cancelar", "accion": accion})
        return {"ok": True, "texto": "Cancelado. No se ejecuta nada.", "acciones": []}
    try:
        a = AC.validar(accion["nombre"], accion["parametros"] if accion["nombre"] != "navegar" else
                       {k: v for k, v in accion["parametros"].items() if k != "ruta"})
    except AC.AccionRechazada as exc:
        return {"ok": False, "texto": f"No lo ejecuto: {exc}", "acciones": []}
    registro.anotar({"sesion": (sesion or {}).get("sid"), "confirmacion": "confirmar", "accion": a.dict()})
    return {"ok": True, "texto": f"Confirmado: {a.descripcion}.", "acciones": [a.dict()]}
