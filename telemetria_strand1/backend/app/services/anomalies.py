"""Deteccion de anomalias sobre metadatos de frames.

Todas las reglas operan sobre hechos verificables (bytes, marcas de tiempo,
duplicados) y **no** sobre magnitudes fisicas interpretadas, que no existen
mientras no haya un protocolo validado. Los umbrales no estan grabados en el
codigo: viven en la tabla `anomaly_rules` y se editan desde la interfaz.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

REGLAS_POR_DEFECTO = [
    {
        "key": "duplicate_frames",
        "label": "Frames duplicados",
        "description": "Mismo contenido hexadecimal recibido mas de una vez.",
        "severity": "warning",
        "params": {"min_repeticiones": 2},
    },
    {
        "key": "corrupt_constant",
        "label": "Frames constantes o vacios",
        "description": "Todos los bytes iguales, o frame sin contenido: apunta a fallo de recepcion.",
        "severity": "critical",
        "params": {},
    },
    {
        "key": "short_frames",
        "label": "Frames demasiado cortos",
        "description": "Longitud por debajo del minimo para contener una cabecera de enlace.",
        "severity": "warning",
        "params": {"min_bytes": 8},
    },
    {
        "key": "data_gap",
        "label": "Huecos en la serie temporal",
        "description": "Intervalo sin frames superior al umbral configurado.",
        "severity": "warning",
        "params": {"max_horas_sin_datos": 720},
    },
    {
        "key": "length_outlier",
        "label": "Longitud atipica",
        "description": "Longitud alejada de la mediana mas de N desviaciones absolutas medianas.",
        "severity": "warning",
        "params": {"umbral_mad": 4.0},
    },
    {
        "key": "low_entropy",
        "label": "Entropia baja",
        "description": "Entropia por debajo del umbral: posible relleno o degradacion de la señal.",
        "severity": "warning",
        "params": {"min_entropia": 1.5},
    },
]


def _mediana(valores: list[float]) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    n = len(ordenados)
    medio = n // 2
    return ordenados[medio] if n % 2 else (ordenados[medio - 1] + ordenados[medio]) / 2.0


def evaluar(frames: list, reglas: list) -> list[dict]:
    """Aplica las reglas activas al conjunto de frames.

    `frames` son instancias del modelo Frame; `reglas`, instancias de AnomalyRule.
    Devuelve una lista de hallazgos, cada uno con su severidad y los frames
    implicados.
    """
    activas = {r.key: r for r in reglas if r.enabled}
    hallazgos: list[dict] = []
    if not frames:
        return hallazgos

    ordenados = sorted(frames, key=lambda f: f.timestamp)

    if "duplicate_frames" in activas:
        regla = activas["duplicate_frames"]
        minimo = (regla.params or {}).get("min_repeticiones", 2)
        conteo = Counter(f.raw_hex for f in frames)
        for raw, n in conteo.items():
            if n >= minimo:
                implicados = [f for f in frames if f.raw_hex == raw]
                hallazgos.append({
                    "rule": regla.key,
                    "label": regla.label,
                    "severity": regla.severity,
                    "message": f"{n} frames con contenido identico ({len(raw) // 2} bytes).",
                    "frame_ids": [f.id for f in implicados],
                    "timestamp": max(f.timestamp for f in implicados).isoformat(),
                })

    if "corrupt_constant" in activas:
        regla = activas["corrupt_constant"]
        for f in frames:
            patrones = (f.analysis or {}).get("patrones", {})
            if patrones.get("todos_iguales") or f.byte_count == 0:
                hallazgos.append({
                    "rule": regla.key,
                    "label": regla.label,
                    "severity": regla.severity,
                    "message": (
                        f"Frame de {f.byte_count} bytes con un unico valor "
                        f"({patrones.get('byte_dominante', 'n/d')})."
                    ),
                    "frame_ids": [f.id],
                    "timestamp": f.timestamp.isoformat(),
                })

    if "short_frames" in activas:
        regla = activas["short_frames"]
        minimo = (regla.params or {}).get("min_bytes", 8)
        cortos = [f for f in frames if 0 < f.byte_count < minimo]
        if cortos:
            hallazgos.append({
                "rule": regla.key,
                "label": regla.label,
                "severity": regla.severity,
                "message": f"{len(cortos)} frames por debajo de {minimo} bytes.",
                "frame_ids": [f.id for f in cortos],
                "timestamp": max(f.timestamp for f in cortos).isoformat(),
            })

    if "data_gap" in activas and len(ordenados) > 1:
        regla = activas["data_gap"]
        max_horas = (regla.params or {}).get("max_horas_sin_datos", 720)
        limite = timedelta(hours=max_horas)
        for anterior, siguiente in zip(ordenados, ordenados[1:]):
            hueco = siguiente.timestamp - anterior.timestamp
            if hueco > limite:
                hallazgos.append({
                    "rule": regla.key,
                    "label": regla.label,
                    "severity": regla.severity,
                    "message": (
                        f"{hueco.days} dias sin frames entre "
                        f"{anterior.timestamp:%Y-%m-%d} y {siguiente.timestamp:%Y-%m-%d}."
                    ),
                    "frame_ids": [anterior.id, siguiente.id],
                    "timestamp": siguiente.timestamp.isoformat(),
                })

    if "length_outlier" in activas:
        regla = activas["length_outlier"]
        umbral = (regla.params or {}).get("umbral_mad", 4.0)
        longitudes = [float(f.byte_count) for f in frames]
        med = _mediana(longitudes)
        mad = _mediana([abs(x - med) for x in longitudes]) or 1.0
        atipicos = [f for f in frames if abs(f.byte_count - med) / mad > umbral]
        if atipicos:
            hallazgos.append({
                "rule": regla.key,
                "label": regla.label,
                "severity": regla.severity,
                "message": (
                    f"{len(atipicos)} frames se apartan mas de {umbral} MAD de la "
                    f"mediana ({med:.0f} bytes)."
                ),
                "frame_ids": [f.id for f in atipicos],
                "timestamp": max(f.timestamp for f in atipicos).isoformat(),
            })

    if "low_entropy" in activas:
        regla = activas["low_entropy"]
        minimo = (regla.params or {}).get("min_entropia", 1.5)
        bajos = [
            f for f in frames
            if f.byte_count >= 8 and (f.entropy_bits_per_byte or 0) < minimo
        ]
        if bajos:
            hallazgos.append({
                "rule": regla.key,
                "label": regla.label,
                "severity": regla.severity,
                "message": f"{len(bajos)} frames con entropia por debajo de {minimo} bits/byte.",
                "frame_ids": [f.id for f in bajos],
                "timestamp": max(f.timestamp for f in bajos).isoformat(),
            })

    orden_severidad = {"critical": 0, "warning": 1, "normal": 2}
    hallazgos.sort(key=lambda h: (orden_severidad.get(h["severity"], 3), h["timestamp"]))
    return hallazgos
