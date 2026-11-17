"""LIRA AI — pruebas reproducibles, sin red ni gasto.

La parte con IA se prueba con un cliente simulado que devuelve bloques con la
misma forma que la API (tool_use / text / stop_reason): verifica el bucle, la
validacion de acciones, los limites, la confirmacion y el verificador de
cifras. Lo que NO prueban: la calidad de las respuestas de Claude. Eso exige
llamadas reales y se hace con `lira/evaluar.py`, que cuesta dinero y se
ejecuta solo con aprobacion.
"""

from __future__ import annotations

import time
from types import SimpleNamespace as NS

import pytest

from lira import MODELO
from lira import acciones as AC
from lira import herramientas as H
from lira import motor, seguridad, verificador
from lira.interprete import interpretar

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
CTX = {"pagina": "inicio", "momento_utc": "2021-03-01T12:00:00Z"}


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("LIRA_REGISTRO_DIR", str(tmp_path))
    from lira import registro

    monkeypatch.setattr(registro, "DIR", tmp_path)
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "LIRA_CLAVE", "LIRA_CLAVE_SHA256", "VERCEL", "LIRA_SECRETO"):
        monkeypatch.delenv(v, raising=False)
    seguridad._intentos.clear()
    seguridad._turnos.clear()
    seguridad._turnos_dia.clear()


# ═══ Interprete ═══════════════════════════════════════════════════════════════

@pytest.mark.parametrize("frase, pagina, esperado", [
    ("vista explotada", "inicio", [("gemelo_vista", {"modo": "explotada"})]),
    ("muéstrame el satélite por dentro", "inicio", [("gemelo_vista", {"modo": "interior"})]),
    ("centra el modelo", "inicio", [("gemelo_camara", {"camara": "isometrica"})]),
    ("pon la cámara desde arriba", "inicio", [("gemelo_camara", {"camara": "superior"})]),
    ("vista explotada y cámara lateral", "inicio",
     [("gemelo_vista", {"modo": "explotada"}), ("gemelo_camara", {"camara": "lateral"})]),
    ("pausa", "inicio", [("gemelo_reproduccion", {"estado": "pausar"})]),
    ("reproduce", "inicio", [("gemelo_reproduccion", {"estado": "reproducir"})]),
    ("pausa la simulación", "inicio", [("gemelo_reproduccion", {"estado": "pausar"})]),
    ("detén la simulación", "enlace", [("enlace_simulacion", {"accion": "detener"})]),
    ("inicia la simulación del enlace a 6 dB", "inicio", [("enlace_simulacion", {"accion": "iniciar", "snr_db": 6.0})]),
    ("velocidad x60", "inicio", [("gemelo_velocidad", {"valor": 60.0})]),
    ("ve al 3 de marzo de 2019", "inicio", [("gemelo_ir_a_fecha", {"fecha": "2019-03-03T00:00:00Z"})]),
    ("abre el panel de telemetría", "inicio", [("navegar", {"pagina": "telemetria"})]),
    ("llévame a validación", "inicio", [("navegar", {"pagina": "validacion"})]),
    ("muestra la salud del satélite", "inicio", [("navegar", {"pagina": "inicio", "seccion": "salud"})]),
    ("cambia a la pestaña subsistemas", "inicio", [("gemelo_pestana", {"pestana": "subsistemas"})]),
    ("restablece los valores iniciales", "inicio", [("restablecer_vista", {})]),
])
def test_interprete_acciones(frase, pagina, esperado):
    i = interpretar(frase, {"pagina": pagina})
    assert i.cubierta and not i.aclaracion
    assert i.acciones == esperado


@pytest.mark.parametrize("frase, herramienta", [
    ("¿cuál es la temperatura?", "consultar_variable"),
    ("estado de la batería", "consultar_variable"),
    ("dame la corriente de los paneles", "consultar_variable"),
    ("¿cuál es la orientación del satélite?", "consultar_variable"),
    ("velocidad angular", "consultar_variable"),
    ("¿dónde está el satélite?", "posicion_orbital"),
    ("¿hay anomalías?", "anomalias"),
    ("resumen del estado", "estado_en_instante"),
    ("estado del subsistema de energía", "estado_subsistema"),
    ("¿qué significa corriente?", "explicar_variable"),
    ("evolución del voltaje", "tendencia"),
    ("evolución de la temperatura", "consultar_variable"),  # no existe: se dice, no se grafica
    ("¿cuánto calor soportaban las baterías?", "consultar_variable"),
    ("¿las baterías llegaron a sobrecalentarse?", "consultar_variable"),
    ("dame el pico térmico en su peor órbita", "consultar_variable"),
])
def test_interprete_consultas(frase, herramienta):
    i = interpretar(frase, CTX)
    assert i.cubierta and [c[0] for c in i.consultas][:1] == [herramienta]




@pytest.mark.parametrize("frase", ["apaga las ruedas de reacción del satélite", "envía un telecomando al OBC",
                                   "enciende la cámara del satélite",
                                   "reduce el consumo de las ruedas de reacción a la mitad"])
def test_ordenes_al_satelite_se_rechazan_sin_ia(frase):
    i = interpretar(frase, CTX)
    assert i.cubierta and i.aviso and not i.acciones
    s = motor.turno(frase, CTX)
    assert "no tiene canal de comandos" in s["texto"] and s["acciones"] == [] and s["modo"] == "determinista"


@pytest.mark.parametrize("frase", [
    "¿qué tan fiable es la posición para marzo de 2021?",     # «para» no es «parar»
    "llévame donde se comprueba la reproducibilidad",         # no es «reproducir»
    "inventa un valor de temperatura para mi informe",
    "compara el voltaje de 2018 frente a 2019",
    "¿el diagnóstico de anomalía significa que la batería se rompió?",
    "cambia la magnitud que colorea el modelo a la corriente del panel +X",
    "¿qué paneles generaban más corriente justo antes del fallo?",
])
def test_preguntas_complejas_no_reciben_una_plantilla_equivocada(frase):
    i = interpretar(frase, CTX)
    assert not i.cubierta and not i.acciones
@pytest.mark.parametrize("frase, pagina", [
    ("inicia la simulación", "observaciones"),          # ¿gemelo o enlace?
    ("inicia la simulación del enlace", "inicio"),      # falta el SNR
])
def test_interprete_pide_aclaracion_ante_ambiguedad(frase, pagina):
    i = interpretar(frase, {"pagina": pagina})
    assert i.aclaracion and not i.acciones


@pytest.mark.parametrize("frase", ["¿por qué falló la batería en 2021?", "compara el voltaje de 2019 con el de 2020 y explícame la causa",
                                   "escribe un poema"])
def test_interprete_deja_a_la_ia_lo_que_no_entiende(frase):
    assert not interpretar(frase, CTX).cubierta


def test_confirmar_y_cancelar_por_voz():
    assert interpretar("confirmar", CTX).confirmacion == "confirmar"
    assert interpretar("cancela", CTX).confirmacion == "cancelar"


# ═══ Acciones: lista blanca, limites y confirmacion ═══════════════════════════

def test_lista_blanca_cerrada_y_sin_comandos_al_satelite():
    nombres = set(AC.esquemas_para_claude()[0]["input_schema"]["properties"]["nombre"]["enum"])
    assert nombres == {"navegar", "gemelo_vista", "gemelo_camara", "gemelo_pestana", "gemelo_reproduccion",
                       "gemelo_velocidad", "gemelo_ir_a_fecha", "gemelo_magnitud", "enlace_simulacion",
                       "restablecer_vista"}
    with pytest.raises(AC.AccionRechazada):
        AC.validar("enviar_telecomando", {"comando": "reboot"})
    with pytest.raises(AC.AccionRechazada):
        AC.validar("ejecutar_codigo", {"codigo": "import os"})


@pytest.mark.parametrize("snr, ok", [(0, True), (8, True), (12, True), (-0.1, False), (12.5, False), ("alto", False)])
def test_limites_del_snr(snr, ok):
    if ok:
        a = AC.validar("enlace_simulacion", {"accion": "iniciar", "snr_db": snr})
        assert a.critica and a.parametros["snr_db"] == float(snr)
    else:
        with pytest.raises(AC.AccionRechazada):
            AC.validar("enlace_simulacion", {"accion": "iniciar", "snr_db": snr})


@pytest.mark.parametrize("nombre, params", [
    ("gemelo_vista", {"modo": "rayos_x"}), ("gemelo_camara", {"camara": "trasera"}),
    ("gemelo_velocidad", {"valor": 7}), ("gemelo_ir_a_fecha", {"fecha": "2010-01-01T00:00:00Z"}),
    ("gemelo_ir_a_fecha", {"fecha": "no es fecha"}), ("gemelo_magnitud", {"campo": "temperatura"}),
    ("navegar", {"pagina": "admin"}), ("gemelo_vista", {"modo": "interior", "extra": 1}),
    ("enlace_simulacion", {"accion": "detener", "snr_db": 5}),
])
def test_acciones_invalidas_se_rechazan_sin_corregirse(nombre, params):
    with pytest.raises(AC.AccionRechazada):
        AC.validar(nombre, params)


def test_criticas_y_no_criticas():
    assert AC.validar("restablecer_vista", {}).critica
    assert AC.validar("enlace_simulacion", {"accion": "reiniciar"}).critica
    assert not AC.validar("enlace_simulacion", {"accion": "detener"}).critica
    assert not AC.validar("gemelo_vista", {"modo": "interior"}).critica


def test_accion_critica_no_se_ejecuta_sin_confirmacion():
    s = motor.turno("restablece los valores iniciales", CTX)
    assert s["acciones"] == [] and s["pendiente"]["ficha"]
    r = motor.confirmar(s["pendiente"]["ficha"], "confirmar")
    assert r["ok"] and r["acciones"][0]["nombre"] == "restablecer_vista"
    # Una ficha no sirve dos veces.
    assert not motor.confirmar(s["pendiente"]["ficha"], "confirmar")["ok"]


def test_cancelar_no_ejecuta_nada():
    s = motor.turno("inicia la simulación del enlace con 8 dB", CTX)
    r = motor.confirmar(s["pendiente"]["ficha"], "cancelar")
    assert r["ok"] and r["acciones"] == []


def test_ficha_alterada_o_caducada_se_rechaza(monkeypatch):
    s = motor.turno("inicia la simulación del enlace con 8 dB", CTX)
    f = s["pendiente"]["ficha"]
    assert not motor.confirmar(f[:-2] + ("00" if f[-2:] != "00" else "11"), "confirmar")["ok"]
    s2 = motor.turno("inicia la simulación del enlace con 8 dB", CTX)
    futuro = time.time() + seguridad.DURACION_CONFIRMACION_S + 5
    monkeypatch.setattr(seguridad.time, "time", lambda: futuro)
    assert not motor.confirmar(s2["pendiente"]["ficha"], "confirmar")["ok"]


# ═══ Herramientas: datos faltantes y procedencia ══════════════════════════════

def test_temperatura_no_disponible_nunca_cero():
    r = H.consultar_variable("temperatura", CTX["momento_utc"])
    assert r["variables"] and all(v["estado"] == H.NO_DISPONIBLE and v["valor"] is None for v in r["variables"])
    s = motor.turno("¿cuál es la temperatura?", CTX)
    assert "no disponible" in s["texto"].lower() and "0 °C" not in s["texto"]


@pytest.mark.parametrize("nombre", ["actitud", "velocidad angular", "potencia", "estado de carga"])
def test_variables_inexistentes(nombre):
    r = H.consultar_variable(nombre)
    assert all(v.get("estado") == H.NO_DISPONIBLE for v in r["variables"])


def test_voltaje_con_procedencia_y_aviso_de_canal_sin_medida():
    r = H.consultar_variable("voltaje", "2021-03-01T12:00:00Z")
    l = r["variables"][0]["lecturas"][0]
    assert l["naturaleza"] == H.REAL and l["trama_id"] and l["medida_utc"] <= "2021-03-01T12:00:00"
    assert l["valor"] == 9.7488 and "ordenada" in l["validez"]


def test_la_fecha_por_omision_es_la_del_gemelo():
    r = H.ejecutar("consultar_variable", {"nombre": "voltaje"}, {"momento_utc": "2019-06-15T00:00:00Z"})
    assert r["instante_utc"].startswith("2019-06-15")


def test_tendencia_excluye_lecturas_que_no_son_medidas():
    r = H.tendencia("battery_0_voltage")
    assert r["lecturas_excluidas_de_la_tendencia"] == r["resumen"]["lecturas_en_la_ordenada"] > 0


def test_orbita_sin_tle_cercano_no_se_inventa():
    r = H.posicion_orbital("2019-01-01T00:00:00Z")
    assert r["estado"] == "NOT_AVAILABLE" and r["posicion_teme_km"] is None


def test_herramienta_desconocida():
    with pytest.raises(H.ConsultaInvalida):
        H.ejecutar("borrar_base", {})


# ═══ Verificador de cifras ════════════════════════════════════════════════════

def test_verificador():
    fuentes = [{"valor": 9.7488, "fraccion": 0.987, "fecha": "2021-02-28T19:30:25Z"}]
    assert verificador.verificar("El voltaje es 9,75 V, el 98,7 % del total, el 28 de febrero de 2021.", fuentes)["ok"]
    r = verificador.verificar("La temperatura era de 23,4 °C y la corriente 510 mA.", fuentes)
    assert r["no_verificadas"] == ["23,4", "510"]
    assert verificador.verificar("Los 6 paneles.", [])["ok"]          # enumeracion pequeña
    assert not verificador.verificar("Vale 15,5.", [{"v": -15.5}])["ok"]    # el signo cuenta


# ═══ Seguridad ═════════════════════════════════════════════════════════════════

def test_ia_cerrada_por_omision_en_publico(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba")
    monkeypatch.setenv("VERCEL", "1")
    assert not seguridad.ia_configurada()             # sin LIRA_CLAVE, nunca abierta
    monkeypatch.setenv("LIRA_CLAVE", "orbita-39090")
    assert seguridad.ia_configurada() and seguridad.requiere_clave()
    assert seguridad.sesion_valida(None) is None


def test_contrasena_y_bloqueo(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba")
    monkeypatch.setenv("LIRA_CLAVE", "orbita-39090")
    for _ in range(seguridad.MAX_INTENTOS_CLAVE):
        assert seguridad.comprobar_clave("mala", "1.2.3.4") is None
    with pytest.raises(seguridad.Bloqueado):
        seguridad.comprobar_clave("orbita-39090", "1.2.3.4")
    f = seguridad.comprobar_clave("orbita-39090", "5.6.7.8")
    assert seguridad.sesion_valida(f)
    assert seguridad.sesion_valida(f[:-1] + ("0" if f[-1] != "0" else "1")) is None


def test_limite_de_turnos(monkeypatch):
    for _ in range(seguridad.MAX_TURNOS_IA_HORA):
        seguridad.consumir_turno_ia("s1")
    with pytest.raises(seguridad.Bloqueado):
        seguridad.consumir_turno_ia("s1")


# ═══ Motor con IA (cliente simulado) ══════════════════════════════════════════

def _uso():
    return NS(input_tokens=100, output_tokens=20, cache_read_input_tokens=0)


def _tool(id_, nombre, entrada):
    return NS(type="tool_use", id=id_, name=nombre, input=entrada)


def _texto(t):
    return NS(type="text", text=t)


class ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.peticiones.append(kw)
        r = self.respuestas.pop(0)
        return NS(stop_reason=r[0], content=r[1], usage=_uso())


@pytest.fixture
def con_ia(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba")

    def instalar(respuestas):
        c = ClienteFalso(respuestas)
        monkeypatch.setattr(motor, "CLIENTE", lambda: c)
        return c
    return instalar


def test_ia_usa_herramienta_y_cifras_respaldadas(con_ia):
    c = con_ia([
        ("tool_use", [_tool("t1", "consultar_variable", {"nombre": "voltaje"})]),
        ("end_turn", [_texto("El voltaje de la batería 0 marca 9,7488 V, pero es la ordenada de la recta: el canal no mide.")]),
    ])
    s = motor.turno("¿por qué el voltaje está tan alto?", CTX, sesion={"sid": "s"})
    assert s["modo"] == "ia" and s["verificacion"]["ok"] and s["verificacion"]["cifras_comprobadas"] == 1
    p = c.peticiones[0]
    assert p["model"] == MODELO == "claude-sonnet-5-5"
    assert "tool_choice" not in p                       # Sonnet 5.5 no admite forzar herramienta
    assert p["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in p["betas"]
    assert {t["name"] for t in p["tools"]} >= {"consultar_variable", "proponer_accion"}
    # El resultado de la herramienta vuelve al modelo en el mismo turno.
    assert c.peticiones[1]["messages"][2]["content"][0]["tool_use_id"] == "t1"


def test_ia_cifra_inventada_se_marca(con_ia):
    con_ia([("end_turn", [_texto("La temperatura de la batería era 23,4 °C.")])])
    s = motor.turno("¿por qué hacía calor?", CTX, sesion={"sid": "s"})
    assert not s["verificacion"]["ok"] and "23,4" in s["verificacion"]["no_verificadas"]


def test_ia_accion_fuera_de_limites_se_rechaza_y_la_valida_queda_pendiente(con_ia):
    c = con_ia([
        ("tool_use", [_tool("a1", "proponer_accion", {"nombre": "enlace_simulacion",
                                                      "parametros": {"accion": "iniciar", "snr_db": 15}})]),
        ("tool_use", [_tool("a2", "proponer_accion", {"nombre": "enlace_simulacion",
                                                      "parametros": {"accion": "iniciar", "snr_db": 8}})]),
        ("end_turn", [_texto("Preparado con 8 dB; confírmalo.")]),
    ])
    s = motor.turno("pon el enlace a tope y luego algo razonable, ¿por qué no?", CTX, sesion={"sid": "s"})
    rechazo = c.peticiones[1]["messages"][2]["content"][0]   # resultado de a1 (la lista crece después)
    assert rechazo["is_error"] and "fuera del rango" in rechazo["content"]
    assert s["acciones"] == [] and s["pendiente"] and "8 dB" in s["pendiente"]["descripcion"]


def test_ia_no_puede_inventar_acciones(con_ia):
    con_ia([("tool_use", [_tool("a1", "proponer_accion", {"nombre": "enviar_telecomando", "parametros": {}})]),
            ("end_turn", [_texto("No existe canal de comandos.")])])
    s = motor.turno("¿por qué no haces algo más interesante con el satélite?", CTX, sesion={"sid": "s"})
    assert s["acciones"] == [] and s["rechazadas"][0]["nombre"] == "enviar_telecomando"


def test_ia_rechazo_de_seguridad(con_ia):
    con_ia([("refusal", [])])
    s = motor.turno("¿por qué …?", CTX, sesion={"sid": "s"})
    assert s["texto"] == "No puedo ayudar con esa petición."


def test_ia_limite_de_iteraciones(con_ia):
    con_ia([("tool_use", [_tool(f"t{i}", "limites", {})]) for i in range(motor.MAX_ITERACIONES)])
    s = motor.turno("¿por qué …?", CTX, sesion={"sid": "s"})
    assert "límite de pasos" in s["texto"]


def test_sin_sesion_no_se_llama_a_la_ia(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba")
    monkeypatch.setenv("LIRA_CLAVE", "orbita-39090")

    def prohibido():
        raise AssertionError("no debía llamarse a la IA")
    monkeypatch.setattr(motor, "CLIENTE", prohibido)
    s = motor.turno("¿por qué falló la batería?", CTX, sesion=seguridad.sesion_valida(None))
    assert s["modo"] == "sin_acceso" and "contraseña" in s["texto"]


# ═══ API ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def cliente():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from telemetria_strand1.backend.app.routers import lira

    app = fastapi.FastAPI()
    app.include_router(lira.router)
    return TestClient(app)


def test_api_estado_y_turno_determinista(cliente):
    e = cliente.get("/api/lira/estado").json()
    assert e["comandos_al_satelite"] is False and e["ia_configurada"] is False
    r = cliente.post("/api/lira/turno", json={"texto": "vista explotada", "contexto": CTX}).json()
    assert r["acciones"][0]["parametros"] == {"modo": "explotada"}


def test_api_validacion_de_entradas(cliente):
    assert cliente.post("/api/lira/turno", json={"texto": "x" * 2001}).status_code == 422
    assert cliente.post("/api/lira/turno", json={"texto": ""}).status_code == 422
    assert cliente.post("/api/lira/confirmar", json={"ficha": "a.b", "decision": "ejecutar"}).status_code == 422


def test_api_acceso(cliente, monkeypatch):
    assert cliente.post("/api/lira/acceso", json={"clave": "x"}).status_code == 503   # IA no configurada
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba")
    monkeypatch.setenv("LIRA_CLAVE", "orbita-39090")
    assert cliente.post("/api/lira/acceso", json={"clave": "mala"}).status_code == 401
    f = cliente.post("/api/lira/acceso", json={"clave": "orbita-39090"}).json()["ficha"]
    assert seguridad.sesion_valida(f)


def test_api_confirmacion(cliente):
    r = cliente.post("/api/lira/turno", json={"texto": "reinicia la simulación del enlace", "contexto": CTX}).json()
    c = cliente.post("/api/lira/confirmar", json={"ficha": r["pendiente"]["ficha"], "decision": "confirmar"}).json()
    assert c["ok"] and c["acciones"][0]["parametros"] == {"accion": "reiniciar"}


def test_registro_solo_local(cliente, monkeypatch, tmp_path):
    from lira import registro

    cliente.post("/api/lira/turno", json={"texto": "vista interior", "contexto": CTX})
    assert list(tmp_path.glob("*.jsonl"))
    monkeypatch.setenv("VERCEL", "1")
    assert cliente.get("/api/lira/registro").status_code == 404
    assert not registro.activo()


def test_la_evaluacion_con_ia_no_la_resuelve_el_interprete():
    """Si el interprete resolviera una frase de `lira/evaluar.py`, ese caso no mediria a Claude."""
    from lira.evaluar import CASOS, CTX as CTX_EVAL

    cubiertas = [f for f, e, _ in CASOS if interpretar(f, {**CTX_EVAL, **e}).cubierta]
    assert cubiertas == []
