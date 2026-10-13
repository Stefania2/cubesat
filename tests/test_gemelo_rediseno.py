"""Gemelo digital: validacion de lecturas y separacion entre fuentes.

Dos garantias del rediseño que no dependen de la base de datos:
  - una lectura que vale la ordenada de su recta no se presenta como medida;
  - los resultados del estudio estructural 1U no se mezclan con STRaND-1 (3U).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "telemetria_strand1" / "frontend" / "src"
REFERENCIA = (FRONT / "data" / "referenciaStrand1.ts").read_text(encoding="utf-8")
MODELO = (FRONT / "components" / "gemelo" / "Modelo3D.tsx").read_text(encoding="utf-8")
PAGINA = (FRONT / "pages" / "GemeloDigital.tsx").read_text(encoding="utf-8")
PANELES = (FRONT / "components" / "gemelo" / "Paneles.tsx").read_text(encoding="utf-8")

VALORES_1U = ["142,70", "0,0015123", "3,4001", "79,409", "6061-T6"]


@pytest.fixture(scope="module")
def gemelo():
    return pytest.importorskip(
        "telemetria_strand1.backend.app.routers.gemelo",
        reason="el router necesita pandas y fastapi")


# ── Validacion de lecturas ──────────────────────────────────────────────────

def test_lectura_en_la_ordenada_es_canal_sin_medida(gemelo):
    for campo, valor in (("battery_0_voltage", 9.7488), ("battery_voltage", 9.7526),
                         ("adc10_pz_array_current", 508.5204547)):
        v = gemelo.validacion_lectura(campo, valor, "V")
        assert v["estado"] == "canal_sin_medida", campo
        assert "conversion" in v


def test_lectura_calibrada_y_negativa(gemelo):
    assert gemelo.validacion_lectura("battery_0_voltage", 7.615, "V")["estado"] == "calibrado"
    v = gemelo.validacion_lectura("switch_6_sgr05_tension", -788.7, "mV")
    assert v["estado"] == "pendiente_de_validacion"


def test_cuentas_crudas_y_campos_sin_recta(gemelo):
    assert gemelo.validacion_lectura("battery_0_voltage_adc", 0.0, "cuenta")["estado"] == "dato_crudo"
    assert gemelo.validacion_lectura("magnetometer_x", 317692.0, "cuenta")["estado"] == "sin_calibrar"
    assert gemelo.validacion_lectura("obc_uptime", 2.0, "s")["estado"] == "decodificado"


def test_la_validacion_no_altera_el_valor(gemelo):
    # Solo devuelve estado y explicacion: el dato historico se sirve tal cual.
    assert set(gemelo.validacion_lectura("battery_0_voltage", 9.7488, "V")) <= {
        "estado", "detalle", "conversion"}


def test_el_gemelo_se_declara_historico_y_sin_enlace_en_vivo(gemelo):
    assert gemelo.TIPO_DATO == "historico real"
    assert "SatNOGS" in gemelo.FUENTE_DATOS


# ── 1U frente a 3U ──────────────────────────────────────────────────────────

def test_los_valores_del_estudio_1u_viven_solo_en_su_bloque():
    bloque = REFERENCIA[REFERENCIA.index("export const ESTRUCTURA_1U"):
                        REFERENCIA.index("/* ── Discrepancias")]
    resto = REFERENCIA.replace(bloque, "")
    for valor in VALORES_1U:
        assert valor in bloque, valor
        assert valor not in resto, f"{valor} aparece fuera del bloque 1U"
        for fuente in (MODELO, PAGINA):
            assert valor not in fuente


def test_el_bloque_1u_se_rotula_como_otro_satelite():
    assert "Modelo estructural de referencia CubeSat 1U" in REFERENCIA
    assert "NO es STRaND-1" in REFERENCIA
    assert "No es STRaND-1." in PANELES
    assert "Análisis estructural propio: no existe." in PANELES


def test_el_modelo_3d_no_usa_el_estudio_1u():
    assert "ESTRUCTURA_1U" not in MODELO
    # Y es un 3U: cuerpo de 1 x 3 x 1 unidades de 10 cm.
    assert "<boxGeometry args={[1, 3, 1]} />" in MODELO


def test_la_masa_de_strand1_es_la_del_documento_de_la_mision():
    assert "lanzamiento: 3.9" in REFERENCIA and "{ subsistema: 'Estructura', masa: 1.0 }" in REFERENCIA


# ── Sin datos inventados ────────────────────────────────────────────────────

@pytest.mark.parametrize("fuente", [MODELO, PAGINA, PANELES])
def test_ningun_valor_aleatorio_en_la_interfaz(fuente):
    assert "Math.random" not in fuente


def test_la_pagina_no_aparenta_tiempo_real():
    assert "sin enlace en vivo" in PAGINA
    assert "Actualización interrumpida" in PAGINA
    assert "connectNulls={false}" in PAGINA          # los huecos no se unen
    assert 'type="monotone"' not in PAGINA           # ni se suavizan


def test_el_modelo_no_deriva_orientacion_de_la_telemetria():
    # El modelo anterior inclinaba el satelite con las cuentas del magnetometro.
    assert "magnetometer" not in MODELO
    assert not re.search(r"rotation=\{\[\s*inclinacion", MODELO)


def test_todo_componente_sin_telemetria_explica_por_que():
    bloques = re.findall(r"\{\s*id: '[a-z_]+',.*?\n  \},", REFERENCIA, re.DOTALL)
    assert len(bloques) >= 12
    for b in bloques:
        if "campos: []" in b:
            assert "sinTelemetria:" in b, b[:60]
