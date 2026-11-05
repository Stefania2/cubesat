"""Pruebas del modulo HMTA (health_monitor/ y la ruta /api/salud).

Cubren los ocho escenarios de la seccion 9 del encargo con datos simulados y,
para cada uno, que los datos se reciben, que se identifica la variable
afectada, que la alerta corresponde al escenario, que el historial se conserva
y que lo simulado no se confunde con lo real. Los modelos PID se contrastan
con scipy.signal y, si existe, con la salida del script de MATLAB.

No necesitan la base de datos: los casos «reales» se construyen con la misma
forma que devuelve `gemelo_digital.datos`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from health_monitor import (alerts, communication_monitor, health_assessment as ha,
                            obc_monitor, pid_reference as pid, telemetry_acquisition as ta,
                            telemetry_validation as val)

RAIZ = Path(__file__).resolve().parents[1]


# ─── Modelos PID ────────────────────────────────────────────────────────────

def test_ganancia_ultima_coincide_con_routh():
    g1, g2 = pid.ganancia_ultima("G1"), pid.ganancia_ultima("G2")
    assert g1["Ku"] == pytest.approx(8.0, rel=1e-6)
    assert g1["wu_rad_s"] == pytest.approx(np.sqrt(12), rel=1e-6)
    assert g2["Ku"] == pytest.approx(13.5 * 38.048 / 4, rel=1e-6)
    assert g2["wu_rad_s"] == pytest.approx(np.sqrt(38.048), rel=1e-6)


def test_tabla_ziegler_nichols():
    u = pid.ganancia_ultima("G1")
    p, pi, pidc = (pid.sintonia("G1", c) for c in ("P", "PI", "PID"))
    assert p.Kp == pytest.approx(0.5 * u["Ku"]) and p.Ti is None
    assert pi.Kp == pytest.approx(0.45 * u["Ku"]) and pi.Ti == pytest.approx(u["Pu_s"] / 1.2)
    assert pidc.Kp == pytest.approx(0.6 * u["Ku"])
    assert pidc.Ti == pytest.approx(u["Pu_s"] / 2) and pidc.Td == pytest.approx(u["Pu_s"] / 8)


def test_derivativo_lleva_filtro():
    num, den = pid.controlador_continuo(pid.sintonia("G2", "PID"))
    # Sin filtro el PID es impropio (grado del numerador > denominador).
    assert len(num) == len(den) and den[0] > 0


@pytest.mark.parametrize("planta", list(pid.PLANTAS))
def test_discretizacion_igual_que_scipy(planta):
    signal = pytest.importorskip("scipy.signal")
    p = pid.PLANTAS[planta]
    nz, dz, _ = signal.cont2discrete((p["num"], p["den"]), 0.01, "zoh")
    mz, md = pid._zoh(p["num"], p["den"], 0.01)
    assert np.allclose(np.trim_zeros(nz.ravel(), "f"), np.trim_zeros(mz, "f"), atol=1e-12)
    assert np.allclose(dz, md, atol=1e-12)
    for c in pid.CONTROLADORES:
        nc, dc = pid.controlador_continuo(pid.sintonia(planta, c))
        bn, bd = signal.bilinear(nc, dc, 100)
        tn, td = pid._tustin(nc, dc, 0.01)
        assert np.allclose(bn, tn[-len(bn):], rtol=1e-9, atol=1e-9)
        assert np.allclose(bd, td, rtol=1e-9, atol=1e-12)


@pytest.mark.parametrize("controlador", pid.CONTROLADORES)
def test_lazo_muestreado_sigue_al_continuo(controlador):
    signal = pytest.importorskip("scipy.signal")
    r = pid.respuesta("G1", controlador)
    l = pid.lazo("G1", controlador)
    _, yc = signal.step((l["num_s"], l["den_s"]), T=r.t)
    assert np.max(np.abs(yc - r.y)) < 0.03


def test_metricas_y_estabilidad_de_los_seis_lazos():
    inf = pid.informe()
    for m in inf["modelos"]:
        for c in m["controladores"]:
            met = c["metricas"]
            assert met["estable_discreto"] and met["estable_continuo"]
            assert met["max_modulo_polo_z"] < 1
            assert met["sobrepaso_pct"] > 0
    g1 = {c["controlador"]: c["metricas"] for c in inf["modelos"][0]["controladores"]}
    # G1 es tipo 0: con P queda error 1/(1 + Kp·G(0)) = 1/(1 + 4) = 0,2.
    assert g1["P"]["error_estacionario"] == pytest.approx(0.2, abs=1e-6)
    assert g1["PI"]["error_estacionario"] == pytest.approx(0.0, abs=1e-6)
    g2 = {c["controlador"]: c["metricas"] for c in inf["modelos"][1]["controladores"]}
    # G2 tiene integrador: error nulo incluso con P.
    assert g2["P"]["error_estacionario"] == pytest.approx(0.0, abs=1e-6)


def test_muestreo_lento_desestabiliza_y_se_informa():
    r = pid.respuesta("G2", "PID", ts=0.25)
    m = pid.metricas(r)
    assert m["max_modulo_polo_z"] > 1 and m["estable_discreto"] is False
    assert m["sobrepaso_pct"] is None          # sin valor final no hay métricas


def test_coincide_con_matlab():
    ruta = RAIZ / "resultados_simulacion" / "hmta_pid_matlab.json"
    if not ruta.exists():
        pytest.skip("Falta hmta_pid_matlab.json (validacion_matlab/validar_pid_zn.m)")
    ml = json.loads(ruta.read_text(encoding="utf-8"))
    for m in ml["modelos"]:
        u = pid.ganancia_ultima(m["planta"])
        assert u["Ku"] == pytest.approx(m["Ku"], rel=1e-5)
        for c in m["controladores"]:
            r = pid.respuesta(m["planta"], c["controlador"])
            met = pid.metricas(r)
            assert met["max_modulo_polo_z"] == pytest.approx(c["max_modulo_polo_z"], abs=1e-6)
            # MATLAB arrastra un error de redondeo de ~1e-6 en G1 (polo triple).
            assert met["valor_final"] == pytest.approx(c["valor_final"], abs=1e-5)
            assert np.allclose(r.y[::100], c["y_muestras"], atol=1e-4)
            assert met["tiempo_subida_s"] == pytest.approx(c["tiempo_subida_s"], abs=0.011)
            assert met["sobrepaso_pct"] == pytest.approx(c["sobrepaso_pct"], abs=0.1)


# ─── Escenarios simulados (seccion 9) ──────────────────────────────────────

# escenario -> (subsistema afectado, variable, mecanismo, nivel)
ESPERADO = {
    "caida_voltaje": ("eps", "battery_0_voltage", "desviacion", "ADVERTENCIA"),
    "aumento_temperatura": ("termico", "battery_temperature", "limite", "CRITICO"),
    "perdida_paquetes": ("comunicaciones", "perdida_paquetes", "tendencia", "ADVERTENCIA"),
    "errores_comunicacion": ("comunicaciones", "tramas_con_error", "tendencia", "ADVERTENCIA"),
    "reinicios_obc": ("obc", "obc_unix_time", "obc", "ADVERTENCIA"),
    "datos_inconsistentes": ("eps", "battery_0_voltage", "validacion", "ADVERTENCIA"),
    "respuesta_dinamica_anormal": ("anomalias", "respuesta_G1_PID", "modelo", "ADVERTENCIA"),
}


@pytest.fixture(scope="module")
def informes():
    return {e: ha.evaluar(ta.simular_escenario(e)) for e in ta.ESCENARIOS}


def test_nominal_sin_alertas(informes):
    r = informes["nominal"]
    assert r["_alertas"] == []
    assert r["estado_general"] == "NORMAL"
    assert r["anomalias"]["comparacion_modelo"]["fuera_de_tolerancia"] is False


@pytest.mark.parametrize("escenario", list(ESPERADO))
def test_escenario_dispara_su_alerta(informes, escenario):
    subsistema, variable, mecanismo, nivel = ESPERADO[escenario]
    r = informes[escenario]
    assert r["simulado"] and r["procedencia"] == "SIMULADO"
    coincidentes = [a for a in r["_alertas"] if a.subsistema == subsistema
                    and a.variable == variable and a.mecanismo == mecanismo]
    assert coincidentes, [(a.subsistema, a.variable, a.mecanismo) for a in r["_alertas"]]
    assert coincidentes[0].nivel == nivel
    # Las alertas responden a las siete preguntas.
    preguntas = coincidentes[0].dict()["preguntas"]
    assert len(preguntas) == 7
    assert all(v is not None and v != "" for v in preguntas.values()), preguntas


@pytest.mark.parametrize("escenario", list(ESPERADO))
def test_alertas_no_salen_de_su_escenario(informes, escenario):
    """Un escenario no produce alertas en subsistemas que no perturba."""
    subsistema = ESPERADO[escenario][0]
    otros = {a.subsistema for a in informes[escenario]["_alertas"]} - {subsistema, "anomalias"}
    assert otros == set()


def test_critico_solo_con_limite_documentado(informes):
    for e, r in informes.items():
        for a in r["_alertas"]:
            if a.nivel == "CRITICO":
                assert a.mecanismo == "limite" and "prueba" in a.referencia


def test_reinicios_detectados_son_los_inyectados(informes):
    assert len(informes["reinicios_obc"]["subsistemas"]["obc"]["extra"]["reinicios"]) == 3


def test_datos_inconsistentes_se_identifican(informes):
    eps = informes["datos_inconsistentes"]["subsistemas"]["eps"]
    tipos = {(h["variable"], h["tipo"]) for i in eps["indicadores"] for h in i["hallazgos"]}
    assert ("battery_0_voltage", "canal_sin_medida") in tipos
    assert ("battery_1_voltage", "duplicado") in tipos
    assert ("battery_1_voltage", "no_finito") in tipos
    assert ("adc13_px_array_current", "escala_completa") in tipos


def test_sin_telemetria_es_desconocido_no_fallo(informes):
    r = informes["sin_telemetria"]
    assert r["estado_general"] == "DESCONOCIDO"
    assert r["_alertas"] == []
    assert r["subsistemas"]["comunicaciones"]["extra"]["estado_enlace"] == "Sin información suficiente"


def test_nada_simulado_se_marca_real(informes):
    for r in informes.values():
        texto = json.dumps(ha.sin_objetos(r), ensure_ascii=False)
        for s in r["subsistemas"].values():
            for i in s["indicadores"]:
                assert i["procedencia"] != "REAL", (s["clave"], i["clave"])
        assert '"procedencia": "REAL"' not in texto
        assert "2030" in (r["periodo"]["hasta"] or "2030")    # fechas del escenario, no del archivo


def test_historial_se_conserva_y_no_duplica(tmp_path, informes):
    reg = alerts.RegistroEventos(tmp_path / "eventos.sqlite")
    alertas = informes["caida_voltaje"]["_alertas"]
    assert reg.guardar(alertas) == len(alertas)
    assert reg.guardar(alertas) == 0                  # reevaluar no duplica
    reg2 = alerts.RegistroEventos(tmp_path / "eventos.sqlite")
    assert reg2.persistente and reg2.total() == len(alertas)
    guardada = reg2.listar(subsistema="eps")[0]
    assert guardada["procedencia"] == "SIMULADO" and "preguntas" in guardada


def test_registro_cae_a_memoria_si_no_puede_escribir(tmp_path):
    bloqueado = tmp_path / "solo_lectura"
    bloqueado.write_text("no soy un directorio")
    reg = alerts.RegistroEventos(bloqueado / "x" / "eventos.sqlite")
    assert reg.persistente is False and reg.total() == 0


def test_informe_es_serializable(informes):
    for r in informes.values():
        json.dumps(ha.sin_objetos(r))


# ─── Validacion y fuente «real» ────────────────────────────────────────────

def _campos(registros):
    """DataFrame con la forma de gemelo_digital.datos.cargar_campos()."""
    filas = [{"frame_id": i, "timestamp": t, "field_name": f, "value_numeric": v, "unit": u,
              "observation_id": None, "station_id": 1}
             for i, (t, f, v, u) in enumerate(registros)]
    return pd.DataFrame(filas)


def _real_canal_muerto():
    t0 = pd.Timestamp("2021-03-01T10:00:00Z")
    reg = []
    for k in range(120):
        t = t0 + pd.Timedelta(seconds=10 * k)
        reg.append((t, "battery_0_voltage", 9.7488, "V"))      # cuenta ADC = 0
        reg.append((t, "obc_unix_time", 2.0, "s"))              # no avanza: no es reloj
    return ta.desde_campos(_campos(reg))


def test_canal_muerto_no_parece_bateria_sana():
    r = ha.evaluar(_real_canal_muerto(), ventana_dias=30)
    bat = next(i for i in r["subsistemas"]["eps"]["indicadores"] if i["clave"] == "battery_0_voltage")
    assert bat["procedencia"] == "REAL"
    assert bat["estado"] == "DESCONOCIDO" and bat["valor"] is None
    assert any(a.mecanismo == "validacion" for a in r["_alertas"])
    assert all(a.nivel != "CRITICO" for a in r["_alertas"])


def test_reloj_que_no_avanza_no_cuenta_reinicios():
    r = ha.evaluar(_real_canal_muerto(), ventana_dias=30)
    obc = r["subsistemas"]["obc"]
    assert obc["extra"]["comprobacion_reloj"]["es_reloj"] is False
    assert "reinicios" not in obc["extra"]
    assert {d["clave"] for d in obc["no_disponibles"]} >= {"cpu_load", "memory_use", "reboots"}


def test_real_sin_temperatura_ni_actitud():
    r = ha.evaluar(_real_canal_muerto(), ventana_dias=30)
    term, adcs = r["subsistemas"]["termico"], r["subsistemas"]["adcs"]
    assert term["indicadores"] == [] and term["estado"] == "DESCONOCIDO"
    assert "nunca los transmite" in term["notas"][0]
    assert any("Información ADCS no disponible" in n for n in adcs["notas"])
    assert {d["disponibilidad"] for d in term["no_disponibles"]} <= {"definida_no_emitida", "no_existe"}


def test_vigencia_dice_que_el_estado_actual_es_desconocido():
    r = ha.evaluar(_real_canal_muerto(), ventana_dias=30)
    assert "DESCONOCIDO" in r["vigencia"] and r["antiguedad_dias"] > 1


def test_validacion_reglas_basicas():
    idx = pd.DatetimeIndex(pd.date_range("2020-01-01", periods=6, freq="10s", tz="UTC"))
    s = pd.DataFrame({"valor": [7.5, 7.5, np.nan, -1.0, 9.7488, 7.4],
                      "unidad": "V", "estacion": ["A", "A", "A", "A", "A", "B"]}, index=idx)
    s.index = pd.DatetimeIndex([idx[0], idx[0], idx[2], idx[3], idx[4], idx[5]])
    v = val.validar(s, "battery_0_voltage")
    assert list(v["motivo"].fillna("ok")) == ["ok", "duplicado", "no_finito", "fuera_rango_fisico",
                                              "canal_sin_medida", "ok"]


def test_limite_y_alerta_exigen_fuente():
    with pytest.raises(ValueError):
        ta.Limite("x", 0, 1, "CRITICO", "  ")
    with pytest.raises(ValueError):
        alerts.Alerta("eps", "x", "ADVERTENCIA", "limite", "a", "b", "q", "c", 1, "V", 1,
                      referencia="", por_que_importa="p", informacion_adicional="i",
                      procedencia="REAL")


def test_perdida_por_secuencia_cuenta_huecos():
    t0 = pd.Timestamp("2021-01-01T00:00:00Z")
    seq = [10, 11, 13, 14, 18]                      # faltan 12, 15, 16, 17
    df = pd.DataFrame({"timestamp": [t0 + pd.Timedelta(seconds=i) for i in range(5)],
                       "estacion": "A", "seq": seq})
    p = communication_monitor.perdida_por_secuencia(df)
    assert p["paquetes_emitidos_estimados"] == 9 and p["paquetes_recibidos"] == 5
    assert p["perdida"] == pytest.approx(4 / 9, abs=1e-4)


def test_contador_con_vueltas_es_reloj_con_reinicios():
    t = pd.date_range("2030-01-01", periods=100, freq="10s", tz="UTC")
    v = np.arange(100) * 10.0
    v[60:] = v[60:] - v[60] + 1
    s = pd.Series(v, index=t)
    assert obc_monitor.comportamiento_reloj(s)["es_reloj"]
    assert len(obc_monitor.reinicios(s)) == 1


# ─── Ruta /api/salud ───────────────────────────────────────────────────────

@pytest.fixture()
def cliente(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HMTA_DB_PATH", str(tmp_path / "ev.sqlite"))
    from telemetria_strand1.backend.app.routers import salud

    for f in (salud._real, salud._registro, salud._evaluacion_real,
              salud._evaluacion_escenario, salud._historial):
        f.cache_clear()
    monkeypatch.setattr(salud, "PROVEEDOR_REAL", _real_canal_muerto)
    app = FastAPI()
    app.include_router(salud.router)
    yield TestClient(app), salud
    for f in (salud._real, salud._registro, salud._evaluacion_real,
              salud._evaluacion_escenario, salud._historial):
        f.cache_clear()


def test_api_resumen_real(cliente):
    c, _ = cliente
    r = c.get("/api/salud/resumen").json()
    assert r["procedencia"] == "REAL" and r["solo_supervision"] is True
    assert set(r["subsistemas"]) == {"eps", "termico", "comunicaciones", "obc", "adcs"}
    assert c.get("/api/salud/subsistema/eps").json()["clave"] == "eps"
    assert c.get("/api/salud/subsistema/nada").status_code == 404
    assert c.get("/api/salud/resumen", params={"hasta": "no-es-fecha"}).status_code == 422


def test_api_escenario_y_eventos(cliente):
    c, _ = cliente
    assert len(c.get("/api/salud/escenarios").json()["escenarios"]) == len(ta.ESCENARIOS)
    r = c.get("/api/salud/escenario/caida_voltaje").json()
    assert r["procedencia"] == "SIMULADO" and r["simulado"] is True
    assert c.get("/api/salud/escenario/inventado").status_code == 404
    ev = c.get("/api/salud/eventos", params={"procedencia": "SIMULADO"}).json()
    assert ev["persistente"] and ev["total"] >= 1
    assert all(e["procedencia"] == "SIMULADO" for e in ev["eventos"])


def test_api_pid_variables_historial(cliente):
    c, _ = cliente
    p = c.get("/api/salud/pid").json()
    assert p["procedencia"] == "ESTIMADO" and len(p["modelos"]) == 2
    assert c.get("/api/salud/pid", params={"ts": 1}).status_code == 422
    v = c.get("/api/salud/variables").json()
    assert any(x["clave"] == "battery_temperature" and x["disponibilidad"] == "definida_no_emitida"
               for x in v["variables"])
    h = c.get("/api/salud/historial").json()
    assert h["meses"][0]["motivo_dominante"] == "canal_sin_medida"


def test_api_base_caida_es_503_no_satelite_sin_datos(cliente, monkeypatch):
    c, salud = cliente

    def roto():
        raise ConnectionError("sin red")

    monkeypatch.setattr(salud, "PROVEEDOR_REAL", roto)
    salud._real.cache_clear()
    salud._evaluacion_real.cache_clear()
    r = c.get("/api/salud/resumen")
    assert r.status_code == 503 and "no un estado del satélite" in r.json()["detail"]
