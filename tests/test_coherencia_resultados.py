"""Coherencia entre resultados, informe, pagina estatica y frontend.

Estas pruebas no comprueban que un numero sea «bueno»: comprueban que el mismo
numero aparezca en todas partes y que nada publicado se haya quedado atras
respecto de `resultados_simulacion/`.

Si fallan tras cambiar un modelo, el arreglo es regenerar, no editar a mano:

    python generar_tablas_informe.py && python generar_resumen_web.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

import generar_resumen_web as web
import generar_tablas_informe as tablas

RAIZ = Path(__file__).resolve().parents[1]
RES = RAIZ / "resultados_simulacion"
FRONT = RAIZ / "telemetria_strand1" / "frontend" / "src"
INFORME = (RAIZ / "docs" / "INFORME_TECNICO_FINAL.md").read_text(encoding="utf-8")


def _json(nombre: str):
    return json.loads((RES / nombre).read_text(encoding="utf-8"))


# ── Informe ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nombre", sorted(tablas.TABLAS))
def test_cada_tabla_del_informe_coincide_con_los_resultados(nombre, monkeypatch):
    monkeypatch.chdir(RAIZ)
    m = re.search(rf"<!-- TABLA:{nombre} -->\n(.*?)\n<!-- /TABLA:{nombre} -->", INFORME, re.DOTALL)
    assert m, f"falta el marcador TABLA:{nombre} en el informe"
    assert m.group(1) == tablas.TABLAS[nombre](), (
        f"la tabla «{nombre}» del informe no coincide con los resultados: "
        "ejecuta generar_tablas_informe.py")


def test_el_informe_no_tiene_marcadores_de_tabla_sin_generador():
    en_informe = set(re.findall(r"<!-- TABLA:([a-z_0-9]+) -->", INFORME))
    assert en_informe == set(tablas.TABLAS)


@pytest.mark.parametrize("frase", [
    "estándar de facto", "concordancia alta", "Concordancia alta", "análsis",
    "±150 Hz", "8,23 °/s", "0,09 dB",
])
def test_el_informe_no_conserva_afirmaciones_retiradas(frase):
    assert frase not in INFORME


def test_el_informe_declara_la_modulacion_documentada():
    assert "FSK a 9600 bit/s con tramas AX.25 (HDLC) y codificación NRZI" in INFORME
    assert "modelo comparativo" in INFORME


# ── Resumen web y pagina estatica ───────────────────────────────────────────

def test_el_resumen_publicado_es_el_que_dan_los_resultados_actuales():
    publicado = json.loads(web.SALIDA.read_text(encoding="utf-8"))
    assert publicado == json.loads(json.dumps(web.construir())), (
        "resumen_simulacion.json esta desfasado: ejecuta generar_resumen_web.py")


def test_index_html_muestra_los_valores_vigentes():
    html = web.INDEX_HTML.read_text(encoding="utf-8")
    datos = web.datos_pagina_estatica(web.construir())
    encontrados = web.PATRON_DATO.findall(html)
    assert encontrados, "index.html no tiene ningun dato enlazado"
    for _, clave, valor, _ in encontrados:
        assert valor == datos[clave], f"index.html: «{clave}» vale {valor}, deberia valer {datos[clave]}"


def test_el_readme_publica_los_resultados_vigentes():
    texto = web.README.read_text(encoding="utf-8")
    assert web.rellenar_readme(texto, web.construir()) == texto, (
        "el bloque de resultados del README esta desfasado: ejecuta generar_resumen_web.py")
    for viejo in ("7.1 dB", "~4 dB", "8.23 °/s", "Concordancia alta", "144 corridas"):
        assert viejo not in texto


@pytest.mark.parametrize("viejo", ["7.1–18.0", "8.23 °/s", "2.62°", "0.09 dB", "~4 dB", "144 corridas"])
def test_index_html_no_conserva_cifras_escritas_a_mano(viejo):
    assert viejo not in web.INDEX_HTML.read_text(encoding="utf-8")


# ── Frontend ────────────────────────────────────────────────────────────────

def test_simulacion_tsx_toma_sus_cifras_del_resumen():
    tsx = (FRONT / "pages" / "Simulacion.tsx").read_text(encoding="utf-8")
    assert "from '../data/resumen_simulacion.json'" in tsx
    codigo = "\n".join(l for l in tsx.splitlines() if not l.lstrip().startswith(("*", "/*", "//")))
    for viejo in ("8,23", "2,62°", "0,09 dB", "7,1 – 18,0", "23,3 – 34,2", "~4 dB",
                  "estándar de facto"):
        assert viejo not in codigo, f"Simulacion.tsx conserva el literal «{viejo}»"
    # Ningun numero de resultado como literal: dB, kHz o porcentajes con decimales.
    assert not re.search(r"'[^'\n]*\d+[,.]\d+ (dB|kHz)[^'\n]*'", codigo)


def test_advanced_tsx_no_afirma_que_no_hay_balizas():
    tsx = (FRONT / "pages" / "Advanced.tsx").read_text(encoding="utf-8")
    assert "ningún frame recibido es una baliza" not in tsx
    assert "api.telemetry()" in tsx


def test_enlace_rf_distingue_modelo_y_dato_historico():
    tsx = (FRONT / "pages" / "EnlaceRF.tsx").read_text(encoding="utf-8")
    assert "simulacion_disponible" in tsx
    assert "histórica real" in tsx
    assert "DISCREPANCIA" not in tsx


def test_el_estado_de_corridas_locales_no_se_despliega():
    assert "/telemetria_strand1/backend/_estado_enlace" in (RAIZ / ".vercelignore").read_text()


# ── Resultados: consistencia interna y valores imposibles ───────────────────

def test_csv_y_json_del_modelo_avanzado_son_el_mismo_resultado():
    datos = _json("resultados_simulacion_avanzada.json")["resultados"]
    with (RES / "resultados_simulacion_avanzada.csv").open(newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    assert len(filas) == len(datos)
    for fila, r in zip(filas, datos):
        assert fila["esquema"] == r["esquema"] and float(fila["ebn0_db"]) == r["ebn0_db"]
        assert int(fila["errores_bit"]) == r["errores_bit"]
        # «No aplica» es celda vacia en el CSV y null en el JSON, nunca cero.
        assert (fila["fer"] == "") == (r["fer"] is None)
        assert (fila["ax25_frames_validos"] == "") == (r["ax25_frames_validos"] is None)


def test_metricas_del_modelo_avanzado_tienen_denominadores_coherentes():
    avz = _json("resultados_simulacion_avanzada.json")
    ensayos = avz["metadatos"]["ensayos_por_punto"]
    for r in avz["resultados"]:
        assert r["ensayos"] == ensayos
        assert r["bits_evaluados"] > 0 and r["ber"] == r["errores_bit"] / r["bits_evaluados"]
        for campo in ("ber", "per", "fer", "ber_diferencial"):
            assert r[campo] is None or 0.0 <= r[campo] <= 1.0
        assert r["ber_ic95_inf"] <= r["ber"] <= r["ber_ic95_sup"]
        if r["errores_bit"] == 0:
            assert r["ber_ic95_sup"] > 0.0          # un cero lleva su cota
        if r["ax25"]:
            assert r["fer"] is not None
            assert (r["ax25_frames_validos"] + r["ax25_frames_invalidos"]
                    + r["ax25_frames_descartados"]) == r["ax25_frames_tx"]
        else:
            assert r["fer"] is None and r["ax25_frames_validos"] is None


def test_la_ganancia_de_codificacion_solo_se_informa_si_es_medible():
    for g in _json("resultados_simulacion_avanzada.json")["analisis"]["ganancia_codificacion"]:
        if g["ganancia_db"] is None:
            assert g["estado"].startswith("no estimable")
        else:
            assert g["ganancia_db"] == pytest.approx(
                g["ebn0_sin_codigo_db"] - g["ebn0_con_codigo_db"], abs=0.011)


def test_metadatos_de_reproducibilidad_presentes():
    m = _json("resultados_simulacion_avanzada.json")["metadatos"]
    for clave in ("commit", "generado_utc", "semilla_base", "ensayos_por_punto", "ebn0_db",
                  "definicion_ebn0", "definiciones", "limitaciones", "tipo_de_dato"):
        assert m.get(clave), clave
    assert "simulado" in m["tipo_de_dato"]
    paso = _json("margen_paso_sgp4.json")
    assert paso["tle"]["linea1"].startswith("1 39090") and paso["sensibilidad"]["montecarlo"]["semilla"]
    assert paso["antiguedad_tle_en_el_paso_h"] >= 0


def test_link_budget_csv_y_json_coinciden_y_son_fisicamente_plausibles():
    datos = _json("link_budget_completo.json")
    with (RES / "link_budget_resultados.csv").open(newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    assert [float(f["margen_db"]) for f in filas] == [r["margen_db"] for r in datos["resultados"]]
    dist = [float(f["distancia_km"]) for f in filas]
    assert dist == sorted(dist, reverse=True)
    assert all(775.0 <= d <= 3300.0 for d in dist)
    assert all(-140.0 < float(f["p_rx_dbm"]) < -80.0 for f in filas)
    assert datos["parametros"]["modulation"] == "FSK"


def test_el_paso_sgp4_y_el_barrido_dan_margenes_compatibles():
    # Misma geometria y mismos parametros: a igual elevacion el margen del paso
    # solo difiere del barrido en la perdida de apuntamiento (reserva de 1 dB
    # en el barrido, calculada del rotor en el paso).
    barrido = {r["elevacion_deg"]: r for r in _json("link_budget_completo.json")["resultados"]}
    paso = _json("margen_paso_sgp4.json")
    umbral = paso["umbrales"]["fsk_no_coherente"]["eb_n0_db"]
    with (RES / "margen_paso_sgp4_serie.csv").open(newline="", encoding="utf-8") as f:
        serie = list(csv.DictReader(f))
    for elev in (10, 30, 60):
        fila = min(serie[: len(serie) // 2], key=lambda s: abs(float(s["elevacion_deg"]) - elev))
        margen_paso = float(fila["eb_n0_db"]) - umbral
        esperado = barrido[elev]["margen_db"] + paso["parametros"]["l_point_db"] - float(fila["l_point_db"])
        assert margen_paso == pytest.approx(esperado, abs=0.6)   # orbita real vs circular


def test_analisis_de_recepcion_es_internamente_coherente():
    rec = _json("analisis_recepcion_telemetria.json")
    d = rec["diversidad"]
    n = d["por_numero_de_estaciones"]
    assert sum(n.values()) == d["emisiones_distintas_recibidas"]
    assert d["emisiones_multiestacion"] == n["2"] + n["3"] + n["4_o_mas"]
    assert d["emisiones_distintas_recibidas"] <= rec["balizas"]["con_observador"] <= rec["balizas"]["total"]
    assert d["ganancia_por_combinacion"] >= 1.0
    par = rec["par_M0KSF"]["en_ventanas_comunes"]
    assert par["union"] == par["solo_M0KSF"] + par["solo_M0KSF-BB"] + par["ambas"]
    ps = rec["perdida_por_secuencia"]
    for v in [ps["global"], *ps["por_año"].values(), *ps["por_elevacion_maxima_de_la_observacion"]]:
        assert v["paquetes_recibidos"] <= v["paquetes_emitidos_estimados"]
        assert v["perdida"] is None or 0.0 <= v["perdida"] <= 1.0
    assert rec["fer_empirica"]["disponible"] is False and rec["fer_empirica"]["motivo"]
    for f in rec["exito_por_observacion"]["filas"]:
        assert f["observaciones_con_baliza"] <= f["observaciones"]


def test_calibracion_cuenta_cero_es_la_ordenada_de_la_recta():
    from telemetria_strand1.backend.app.services import strand_amsat as amsat

    cal = amsat.calibraciones()
    assert cal["battery_0_voltage"]["valor_con_cuenta_cero"] == pytest.approx(9.7488)
    # Las «corrientes de 508 a 528 mA» son las ordenadas de las rectas de panel.
    ordenadas = sorted(v["valor_con_cuenta_cero"] for k, v in cal.items() if k.endswith("array_current"))
    assert ordenadas[0] == pytest.approx(508.52, abs=0.01)
    assert ordenadas[-1] == pytest.approx(528.04, abs=0.01)
    # Y las tensiones negativas de los interruptores, las suyas.
    assert cal["switch_0_ppt_power_supply_tension"]["valor_con_cuenta_cero"] == pytest.approx(-1113.42, abs=0.01)
    baliza = amsat.decodificar(bytes.fromhex("C080020602" + "2C" + "03" + "02" + "0000"))
    assert baliza.valores["battery_0_voltage"] == cal["battery_0_voltage"]["valor_con_cuenta_cero"]
    assert baliza.valores["battery_0_voltage_adc"] == 0
