"""Reconstruccion del pase de una observacion de SatNOGS con SGP4.

Caso real: observacion 6836614 (estacion OE6EUR15, 2022-12-06), con el TLE y
la posicion de la estacion que publica SatNOGS Network. SatNOGS calcula para
ese pase una elevacion maxima de 18° y azimuts de salida y puesta de 119° y
358°; la reconstruccion del proyecto debe coincidir.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("sgp4")

from telemetria_strand1.backend.app.services import pasos  # noqa: E402

GEOMETRIA = {
    "fuente": "prueba",
    "estaciones": {"2859": {"nombre": "OE6EUR15", "lat": 47.07, "lng": 15.44, "alt_m": 430}},
    "tles": [["1 39090U 13009E   22339.36900428  .00000246  00000+0  10051-3 0  9996",
              "2 39090  98.3922 172.9877 0009970 118.8278 241.3910 14.35378738511913"]],
    "observaciones": {"6836614": {"estacion": 2859, "tle": 0,
                                  "azimut_salida": 119.0, "azimut_puesta": 358.0}},
}
INICIO = datetime(2022, 12, 6, 3, 23, 54, tzinfo=timezone.utc)
FIN = datetime(2022, 12, 6, 3, 36, 57, tzinfo=timezone.utc)


@pytest.fixture()
def paso(monkeypatch):
    monkeypatch.setattr(pasos, "geometria", lambda: GEOMETRIA)
    return pasos.reconstruir(6836614, INICIO, FIN)


def test_elevacion_maxima_coincide_con_satnogs(paso):
    assert paso["elevacion_max_calculada"] == pytest.approx(18.0, abs=1.0)


def test_azimuts_de_salida_y_puesta(paso):
    ventana = [p for p in paso["puntos"] if p["en_ventana"]]
    assert ventana[0]["az"] == pytest.approx(119.0, abs=2.0)
    assert ventana[-1]["az"] == pytest.approx(358.0, abs=2.0)
    # La ventana de SatNOGS va de horizonte a horizonte.
    assert abs(ventana[0]["el"]) < 2 and abs(ventana[-1]["el"]) < 2


def test_altura_y_orbita(paso):
    alturas = [p["alt_km"] for p in paso["puntos"]]
    assert 760 < min(alturas) and max(alturas) < 800       # TLE: ~775 km
    assert len(paso["orbita"]) == 101                        # una vuelta, cada minuto
    assert paso["tle"]["antiguedad_dias"] == pytest.approx(0.78, abs=0.05)


def test_observacion_sin_geometria(monkeypatch):
    monkeypatch.setattr(pasos, "geometria", lambda: GEOMETRIA)
    assert pasos.reconstruir(1, INICIO, FIN) is None
