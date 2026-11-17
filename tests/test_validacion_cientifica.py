"""STRaND-1 SCIENTIFIC VALIDATION — pruebas automatizadas.

Cada caso registra con `record_property` su categoria, el resultado esperado,
el obtenido y la tolerancia; `validacion_cientifica/ejecutar_pruebas.py` los
recoge del informe JUnit. Nada de esto toca la base de datos ni la red: las
entradas son el archivo sellado del repositorio, el catalogo de TLE y los
vectores de Vallado que distribuye python-sgp4. La unica prueba que usa la red
(SatNOGS en vivo) se omite salvo que se pida con SATNOGS_EN_VIVO=1, y omitida
queda NOT_VERIFIED, no aprobada.

Casos de regresion: los valores esperados de `REGRESION` se fijaron el
2026-11-17 sobre el archivo sellado y estan documentados en
docs/VALIDACION_CIENTIFICA.md §8. Detectan cambios; no prueban por si solos
que el valor sea fisicamente correcto (eso lo cubren las pruebas C y D).
"""

from __future__ import annotations

import gzip
import json
import math
import os
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from validacion_cientifica import conjunto as C
from validacion_cientifica import diagnosticos as D
from validacion_cientifica import estados as E
from validacion_cientifica import informe as I
from validacion_cientifica import orbital as O
from validacion_cientifica import procedencia as P
from validacion_cientifica import reconstruccion as R
from validacion_cientifica import sincronizacion as S
from validacion_cientifica import telemetria as T
from validacion_cientifica.tiempo import FechaInvalida, instante_utc

pytestmark = pytest.mark.skipif(not P.archivo_disponible(), reason="falta el archivo sellado")

INSTANTE_REF = "2021-03-01T12:00:00Z"


@pytest.fixture
def registrar(record_property):
    def _r(categoria, esperado, obtenido, tolerancia):
        record_property("categoria", categoria)
        record_property("esperado", json.dumps(esperado, ensure_ascii=False, default=str)[:400])
        record_property("obtenido", json.dumps(obtenido, ensure_ascii=False, default=str)[:400])
        record_property("tolerancia", str(tolerancia))
    return _r


def _validado(r: E.Resultado, registrar, categoria):
    registrar(categoria, r.esperado, r.obtenido, r.tolerancia)
    assert r.estado == E.VALIDATED, f"{r.id}: {r.estado} · {r.detalle} · {r.obtenido}"


# ═══ Unitarias ═══════════════════════════════════════════════════════════════

# -- Validacion de TLE --------------------------------------------------------

def _tle_versionado():
    return next(r for r in O.catalogo_tle() if "versionado" in r.fuente)


def test_tle_versionado_supera_todas_las_comprobaciones(registrar):
    reg = _tle_versionado()
    _validado(O.resultado_tle(reg.linea1, reg.linea2, reg.fuente), registrar, "unitaria · TLE")


def test_checksum_detecta_un_digito_alterado(registrar):
    reg = _tle_versionado()
    i = next(k for k in range(20, 60) if reg.linea2[k].isdigit())   # un digito de los elementos
    malo = reg.linea2[:i] + str((int(reg.linea2[i]) + 1) % 10) + reg.linea2[i + 1:]
    comps = O.comprobar_tle(reg.linea1, malo)
    registrar("unitaria · TLE", "checksum_linea_2 = False", comps["checksum_linea_2"], "exacta")
    assert comps["checksum_linea_2"][0] is False
    assert comps["checksum_linea_1"][0] is True


def test_checksum_cuenta_el_signo_menos_como_uno():
    assert O.checksum("-" + "0" * 67) == 1
    assert O.checksum("+" + "0" * 67) == 0


def test_tle_de_otro_satelite_se_rechaza(registrar):
    l1, l2, _ = O._vectores_vallado()[0]
    comps = O.comprobar_tle(l1[:69], l2[:69])
    registrar("unitaria · TLE", "norad=False", comps["norad"], "exacta")
    assert comps["norad"][0] is False
    assert comps["checksum_linea_1"][0] is True


def test_catalogo_historico_integro(registrar):
    _validado(O.resultados_catalogo(), registrar, "unitaria · TLE")


# -- Propagacion SGP4 ---------------------------------------------------------

@pytest.mark.parametrize("indice", [0, 1])
def test_sgp4_reproduce_los_vectores_de_vallado(indice, registrar):
    _validado(O.prueba_vallado()[indice], registrar, "unitaria · SGP4 (referencia independiente)")


def test_sgp4_cpp_y_python_puro_coinciden_en_strand1(registrar):
    _validado(O.prueba_cpp_vs_python(), registrar, "unitaria · SGP4")


def test_repetibilidad_bit_a_bit(registrar):
    reg = _tle_versionado()
    _validado(O.prueba_repetibilidad(reg, reg.epoca + timedelta(hours=7)), registrar, "unitaria · SGP4")


def test_registro_de_propagacion_completo(registrar):
    reg = _tle_versionado()
    p = O.registro_propagacion(reg, reg.epoca + timedelta(hours=1))
    claves = {"norad_id", "tle", "fuente_tle", "epoca_tle_utc", "instante_propagacion_utc",
              "implementacion_sgp4", "posicion_km", "velocidad_km_s", "marco_referencia", "unidades"}
    registrar("unitaria · SGP4", sorted(claves), sorted(p), "todas presentes")
    assert claves <= set(p)
    rap = math.sqrt(sum(v * v for v in p["velocidad_km_s"].values()))
    # Velocidad circular a 775 km: sqrt(398600.4418 / 7153.137) = 7,46 km/s.
    assert abs(rap - math.sqrt(398600.4418 / (6378.137 + 775))) < 0.05


# -- Coordenadas ----------------------------------------------------------------

@pytest.mark.parametrize("rid", ["ORB-D1", "ORB-D2", "ORB-D3"])
def test_transformaciones_de_coordenadas(rid, registrar):
    r = next(x for x in O.prueba_transformaciones() if x.id == rid)
    _validado(r, registrar, "unitaria · coordenadas")


def test_geodesica_casos_analiticos():
    lat, lon, h = O.geodetica_heikkinen(6378.137, 0.0, 0.0)
    assert abs(lat) < 1e-9 and abs(lon) < 1e-9 and abs(h) < 1e-9
    lat, lon, h = O.geodetica_heikkinen(0.0, 0.0, 6356.7523142 + 10)
    assert abs(lat - 90) < 1e-9 and abs(h - 10) < 1e-6


# -- Conversion de unidades -----------------------------------------------------

@pytest.mark.parametrize("cuenta, esperado", [(0, 9.7488), (300, -0.00945 * 300 + 9.7488), (1023, -0.00945 * 1023 + 9.7488)])
def test_conversion_bateria_0_segun_amsat(cuenta, esperado, registrar):
    trama = bytes.fromhex("C0800206022C0302") + cuenta.to_bytes(2, "little")
    r = P.redecodificar(trama.hex())
    registrar("unitaria · unidades", esperado, r["battery_0_voltage"], "exacta (misma expresión)")
    assert r["battery_0_voltage"][0] == esperado and r["battery_0_voltage"][1] == "V"
    assert r["battery_0_voltage_adc"][0] == cuenta


def test_cuenta_fuera_del_dominio_de_10_bits_no_produce_valor_fisico(registrar):
    trama = bytes.fromhex("C0800206022C0302") + (1024).to_bytes(2, "little")
    r = P.redecodificar(trama.hex())
    registrar("unitaria · unidades", "sin battery_0_voltage", sorted(r), "exacta")
    assert "battery_0_voltage" not in r and r["battery_0_voltage_adc"][0] == 1024


# -- Estadistica --------------------------------------------------------------

def test_zscore_robusto_contra_calculo_directo(registrar):
    rng = np.random.default_rng(39090)
    idx = pd.date_range("2020-01-01", periods=120, freq="min", tz="UTC")
    s = pd.Series(rng.normal(7.4, 0.05, 120), index=idx)
    z = D.A.zscore_robusto(s)
    i = 100
    w = s.iloc[i - 50:i + 1].to_numpy()          # ventana final de 51, incluye la lectura
    med = np.median(w)
    mad = np.median(np.abs(w - med))
    esperado = (s.iloc[i] - med) / (1.4826 * mad)
    registrar("unitaria · estadística", esperado, z["z"].iloc[i], 1e-12)
    assert abs(z["z"].iloc[i] - esperado) < 1e-12


def test_ventanas_incompletas(registrar):
    _validado(D.prueba_ventanas_incompletas(), registrar, "unitaria · estadística")


def test_canal_enrielado_con_dos_valores_alternos():
    idx = pd.date_range("2021-02-01", periods=40, freq="min", tz="UTC")
    s = pd.Series([9.7488, 9.7526] * 20, index=idx)
    assert D.A.enrielado(s).iloc[-1]


# -- Huellas --------------------------------------------------------------------

def test_sha256_vector_fips():
    # FIPS 180-2, apendice B.1: SHA-256("abc").
    assert P.sha256(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_serializacion_canonica_y_gzip_deterministas():
    filas = [{"b": 1, "a": None, "t": "2020-01-01T00:00:00.000000Z"}, {"a": 1.5, "b": "ñ"}]
    h1, n, c1 = P.huella_filas(filas)
    h2, _, c2 = P.huella_filas([dict(reversed(list(f.items()))) for f in filas])
    assert h1 == h2 and n == 2
    assert P.comprimir_determinista(c1) == P.comprimir_determinista(c2)
    assert gzip.decompress(P.comprimir_determinista(c1)) == c1


def test_tiempo_sin_zona_se_rechaza():
    with pytest.raises(FechaInvalida):
        instante_utc("2021-03-01T12:00:00")
    assert instante_utc("2021-03-01T07:00:00-05:00") == instante_utc("2021-03-01T12:00:00Z")


# ═══ Integracion ═════════════════════════════════════════════════════════════

def test_archivo_sellado_integro(registrar):
    res = P.verificar_archivo()
    registrar("integración · procedencia", "VALIDATED ×4", [r.estado for r in res], "igualdad SHA-256")
    assert all(r.estado == E.VALIDATED for r in res), [r.dict() for r in res]


def test_archivo_conserva_los_tipos_originales():
    fila = P.cargar("tramas_originales")[0]
    assert isinstance(fila["id"], int) and isinstance(fila["norad_id"], int)
    assert isinstance(fila["raw_hex"], str)


def test_procesamiento_de_telemetria_reproduce_la_capa_procesada(registrar):
    r = next(x for x in T.controles_globales() if x.id == "TEL-CONV")
    _validado(r, registrar, "integración · telemetría")


def test_controles_de_telemetria_sin_fallos(registrar):
    res = T.controles_globales()
    registrar("integración · telemetría", "ningún FAILED", {r.id: r.estado for r in res}, "—")
    assert not [r for r in res if r.estado == E.FAILED]


def test_variables_no_emitidas_son_no_disponibles_y_no_cero():
    fichas = {f["campo"]: f for f in T.variables()}
    temp = next(f for c, f in fichas.items() if "battery_0_temperature" in c)
    assert temp["estado_integridad"] == E.NOT_AVAILABLE and temp["n_lecturas"] == 0
    assert all(f["estado_fisico"] in (E.NOT_VERIFIED, E.NOT_AVAILABLE) for f in fichas.values())


def test_contraste_con_satnogs(registrar):
    r = O.prueba_satnogs(P.cargar("observaciones"))
    if r.estado == E.NOT_AVAILABLE:
        pytest.skip(r.detalle)
    registrar("integración · SatNOGS (implementación independiente)", r.esperado, r.obtenido, r.tolerancia)
    assert r.estado in (E.VALIDATED, E.WARNING), r.obtenido


@pytest.mark.skipif(os.environ.get("SATNOGS_EN_VIVO") != "1", reason="prueba en vivo: SATNOGS_EN_VIVO=1")
def test_api_satnogs_en_vivo_coincide_con_el_archivo(registrar):
    import httpx

    o = next(x for x in P.cargar("observaciones") if x.get("max_elevation_deg") is not None)
    r = httpx.get("https://network.satnogs.org/api/observations/",
                  params={"id": o["observation_id"], "format": "json"}, timeout=60)
    r.raise_for_status()
    remoto = r.json()[0]
    registrar("integración · API SatNOGS", o["max_elevation_deg"], remoto.get("max_altitude"), "exacta")
    assert remoto["norad_cat_id"] == 39090
    assert float(remoto["max_altitude"]) == float(o["max_elevation_deg"])


@pytest.mark.parametrize("instante", ["2016-11-30T16:39:41Z", "2019-06-15T00:00:00Z", INSTANTE_REF,
                                      "2023-01-28T02:58:36Z", "2026-01-01T00:00:00Z", "2010-01-01T00:00:00Z"])
def test_sincronizacion_temporal(instante, registrar):
    res = S.verificar(R.reconstruir(instante))
    registrar("integración · sincronización", "sin FAILED", {r.id: r.estado for r in res}, "exacta")
    assert not [r.dict() for r in res if r.estado == E.FAILED]


def test_sincronizacion_global(registrar):
    _validado(S.prueba_global(), registrar, "integración · sincronización")


def test_estados_discretos_nunca_se_interpolan():
    rec = R.reconstruir("2019-06-15T00:00:00Z")
    discretas = [l for l in rec["telemetria"]["lecturas"] if l["tipo"] == "discreto"]
    assert discretas and all(l["asociacion"] in (R.EXACTA, R.ANTERIOR, R.NO_DISPONIBLE) for l in discretas)
    assert all(isinstance(l["valor"], str) or l["valor"] is None for l in discretas)


def test_instante_anterior_al_archivo_no_inventa_datos():
    rec = R.reconstruir("2010-01-01T00:00:00Z")
    assert rec["gemelo"]["estado"] == E.NOT_AVAILABLE
    assert all(l["valor"] is None and l["estado"] == E.NOT_AVAILABLE for l in rec["telemetria"]["lecturas"])
    assert rec["orbita"]["estado"] == E.NOT_AVAILABLE and rec["orbita"]["propagacion"] is None


@pytest.fixture
def router_gemelo(monkeypatch):
    g = pytest.importorskip("telemetria_strand1.backend.app.routers.gemelo")
    monkeypatch.delenv("REDIS_URL", raising=False)
    for f in (g._redis, g._campos, g._estado, g._unidades, g._clasificacion, g._etiquetas_por_evento):
        f.cache_clear()
    monkeypatch.setattr(g, "_campos", lambda: C.campos_gemelo())
    yield g
    for f in (g._redis, g._estado, g._unidades, g._clasificacion, g._etiquetas_por_evento):
        f.cache_clear()


def test_modelo_3d_del_gemelo_coincide_con_la_reconstruccion(router_gemelo, registrar):
    """El estado que pinta el modelo 3D (router del gemelo) = el de la reconstruccion."""
    ev = R._motor()["eventos"]
    distintos = []
    for i in np.linspace(0, len(ev) - 1, 15).astype(int):
        api = router_gemelo.estado_en(indice=int(i), campo="battery_voltage")
        rec = R.reconstruir(ev[i].isoformat())
        if api["estado_cubesat"] != rec["modelo3d"]["estado_cubesat"]:
            distintos.append((int(i), api["estado_cubesat"], rec["modelo3d"]["estado_cubesat"]))
        valores = {l["campo"]: l["valor"] for l in rec["telemetria"]["lecturas"]}
        for l in api["lecturas"]:
            if valores.get(l["campo"]) != l["valor"]:
                distintos.append((int(i), l["campo"]))
    registrar("integración · modelo 3D", "sin diferencias", distintos, "exacta")
    assert not distintos


def test_indice_del_gemelo_es_el_de_la_reconstruccion(router_gemelo):
    rec = R.reconstruir(INSTANTE_REF)
    assert router_gemelo.indice_en(INSTANTE_REF)["indice"] == rec["gemelo"]["evento"]


def test_manifest_contiene_lo_necesario_y_se_reproduce(registrar):
    man = R.manifest(R.reconstruir(INSTANTE_REF))
    for clave in ("mision", "reconstruccion", "fuente_telemetria", "datos", "orbita", "versiones",
                  "parametros_estadisticos", "sincronizacion", "aplicacion", "resultados", "archivos"):
        assert clave in man
    assert man["mision"]["norad_id"] == 39090
    # Campo desconocido → null, no inventado: en 2021 no hay TLE cercano.
    assert man["orbita"]["sgp4"] is None and man["orbita"]["estado"] == E.NOT_AVAILABLE
    res = R.verificar_manifest(json.loads(json.dumps(man)))
    registrar("integración · expediente", "todo VALIDATED", {r.id: r.estado for r in res}, "exacta")
    assert all(r.estado == E.VALIDATED for r in res)


def test_manifest_alterado_se_detecta():
    man = R.manifest(R.reconstruir(INSTANTE_REF))
    man["resultados"]["sha256"] = "0" * 64
    res = {r.id: r.estado for r in R.verificar_manifest(man)}
    assert res["REP-RESULT"] == E.FAILED


def test_informe_pdf_y_json():
    inf = I.generar(INSTANTE_REF)
    assert set(f"{n}_" for n in range(1, 15)) <= {k.split("_")[0] + "_" for k in inf}
    pdf = I.pdf(inf)
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    xref = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert pdf[xref:xref + 4] == b"xref"


def test_api_validacion():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from telemetria_strand1.backend.app.routers import validacion

    app = fastapi.FastAPI()
    app.include_router(validacion.router)
    c = TestClient(app)
    assert c.get("/api/validacion/reconstruccion", params={"t": "2021-03-01T12:00:00"}).status_code == 422
    assert c.get("/api/validacion/reconstruccion", params={"t": INSTANTE_REF, "campo": "x;drop"}).status_code == 422
    r = c.get("/api/validacion/reconstruccion", params={"t": INSTANTE_REF})
    assert r.status_code == 200
    man = r.json()["manifest"]
    v = c.post("/api/validacion/manifest/verificar", content=json.dumps(man))
    assert v.status_code == 200 and v.json()["recuento"]["FAILED"] == 0
    assert c.post("/api/validacion/manifest/verificar", content=b"no json").status_code == 422
    p = c.get("/api/validacion/informe", params={"t": INSTANTE_REF, "formato": "pdf"})
    assert p.status_code == 200 and p.content.startswith(b"%PDF")
    assert c.get("/api/validacion/procedencia/trama/17348").json()["valores"]


# ═══ Regresion ═══════════════════════════════════════════════════════════════

# Fijados el 2026-11-17 sobre el archivo sellado (ver docstring).
REGRESION = {
    "instante": INSTANTE_REF,
    "evento_utc": "2021-02-28T19:30:25.000000Z",
    "battery_voltage": 9.7488,
    "estado_cubesat": "INSTRUMENTACION_PERDIDA",
    "trama_17348": {"raw_hex": "C0800206022C03020000", "battery_0_voltage": 9.7488, "battery_0_voltage_adc": 0},
    "lecturas_battery_voltage": 5269,
}


def test_regresion_reconstruccion_conocida(registrar):
    rec = R.reconstruir(REGRESION["instante"])
    bv = next(l for l in rec["telemetria"]["lecturas"] if l["campo"] == "battery_voltage")
    obt = {"evento_utc": rec["gemelo"]["momento_evento_utc"], "battery_voltage": bv["valor"],
           "estado_cubesat": rec["modelo3d"]["estado_cubesat"]}
    esp = {k: REGRESION[k] for k in obt}
    registrar("regresión · reconstrucción", esp, obt, "exacta")
    assert obt == esp


def test_regresion_valor_procesado_validado(registrar):
    ref = REGRESION["trama_17348"]
    assert P.cargar_fila("tramas_originales", 17348)["raw_hex"] == ref["raw_hex"]
    r = P.redecodificar(ref["raw_hex"])
    registrar("regresión · valores procesados", ref, {k: r[k][0] for k in ("battery_0_voltage", "battery_0_voltage_adc")}, "exacta")
    assert r["battery_0_voltage"][0] == ref["battery_0_voltage"]
    assert r["battery_0_voltage_adc"][0] == ref["battery_0_voltage_adc"]


def test_regresion_orbital_frente_a_implementacion_independiente(registrar):
    """Resultado orbital de referencia: el TLE versionado a +12 h, contra Python puro."""
    from sgp4.model import Satrec as SatrecPython

    reg = _tle_versionado()
    t = reg.epoca + timedelta(hours=12)
    _, r_app, v_app = O.propagar_teme(reg.linea1, reg.linea2, t)
    _, r_ind, v_ind = O.propagar_teme(reg.linea1, reg.linea2, t, SatrecPython)
    d = max(abs(a - b) for a, b in zip(r_app, r_ind))
    registrar("regresión · órbita", r_ind, r_app, "1e-6 km")
    assert d < 1e-6


def test_regresion_diagnostico_estable(registrar):
    r = D.resultado_campo("battery_voltage")
    registrar("regresión · diagnóstico", REGRESION["lecturas_battery_voltage"], r["n_lecturas"], "exacta")
    assert r["n_lecturas"] == REGRESION["lecturas_battery_voltage"]
    _validado(D.prueba_reproducibilidad(), registrar, "regresión · diagnóstico")


def test_reconstruccion_no_depende_del_catalogo_vivo(monkeypatch, tmp_path, registrar):
    """Regresion: el 2026-11-17 la misma reconstruccion dio huellas distintas en Vercel y en
    local porque el catalogo de TLE se leia del fichero que amplia la descarga de SatNOGS.
    Ahora se lee de la copia sellada: borrar o cambiar el fichero vivo no altera nada."""
    antes = R.huella_resultados(R.reconstruir("2025-06-01T00:00:00Z"))
    monkeypatch.setattr(O, "GEOMETRIA", tmp_path / "no_existe.json")
    monkeypatch.setattr(O, "TLE_VERSIONADO", tmp_path / "no_existe.tle")
    O.catalogo_tle.cache_clear()
    try:
        despues = R.huella_resultados(R.reconstruir("2025-06-01T00:00:00Z"))
    finally:
        O.catalogo_tle.cache_clear()
    registrar("regresión · reproducibilidad", antes, despues, "igualdad exacta")
    assert antes == despues
    assert O.comparar_catalogo_vivo().estado == E.WARNING  # el vivo vacio difiere del sellado: se avisa
