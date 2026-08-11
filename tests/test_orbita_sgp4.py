from datetime import timezone
from pathlib import Path

from orbita_sgp4 import Observer, load_tle, propagate_point, tle_epoch


TLE_PATH = Path("tle/strand1_2026-08-09.tle")


def test_tle_de_strand1_se_carga_y_tiene_epoca_utc():
    tle = load_tle(TLE_PATH)
    epoch = tle_epoch(tle)

    assert "STRAND" in tle.name.upper()
    assert tle.line1[2:7] == "39090"
    assert epoch.tzinfo == timezone.utc
    assert epoch.year == 2026


def test_sgp4_produce_geometria_y_doppler_fisicos():
    tle = load_tle(TLE_PATH)
    point = propagate_point(
        tle,
        Observer(lat_deg=4.7110, lon_deg=-74.0721, alt_m=2600),
        tle_epoch(tle),
        437.568e6,
    )

    assert 0.0 <= point.azimuth_deg < 360.0
    assert -90.0 <= point.elevation_deg <= 90.0
    assert point.range_km > 100.0
    assert abs(point.doppler_hz) < 20_000.0
