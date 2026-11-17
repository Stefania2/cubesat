"""MODULO 6 — Diagnostic Validation.

Documenta y re-ejecuta los diagnosticos estadisticos que ya usa la plataforma.
No los cambia: el gemelo pinta el modelo 3D con ellos, y cambiar un umbral aqui
cambiaria lo que ve el usuario. Lo que se añade es su ficha tecnica, su
reproducibilidad y una escala de interpretacion que nunca llega a «falla».

Escala de interpretacion (de menos a mas fuerte)
------------------------------------------------
    sin_desviacion_estadistica    |z| < 3,5
    comportamiento_inusual        3,5 ≤ |z| < 6
    anomalia_estadistica          |z| ≥ 6
    posible_anomalia_operacional  canal enrielado: el convertidor deja de moverse
    no_evaluable                  sin referencia valida (ventana corta o demasiado extendida)
    falla_confirmada              NUNCA desde estadistica. Exigiria un registro del operador o
                                  documentacion de la mision que la confirme; para STRaND-1 no
                                  existe en las fuentes del proyecto.

La etiqueta que pinta el modelo 3D («CRITICO» para |z| ≥ 6) es una codificacion
visual de la plataforma, no una afirmacion sobre el satelite. Esta tabla es la
que debe usarse en cualquier informe.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from gemelo_digital import anomalias as A

from . import conjunto as C
from . import estados as E

INTERPRETACION = {
    "normal": "sin_desviacion_estadistica",
    "advertencia": "comportamiento_inusual",
    "anomalia": "anomalia_estadistica",
    "canal_enrielado": "posible_anomalia_operacional",
    "sin_referencia": "no_evaluable",
}
FALLA_CONFIRMADA = {
    "estado": E.NOT_AVAILABLE,
    "detalle": "Ninguna desviación estadística se declara falla física. Confirmarla requeriría un "
               "registro de operaciones o documentación de la misión, que el proyecto no tiene.",
}

# Magnitudes cuyo diagnostico se documenta: la que gobierna el modelo 3D y las
# que tienen recta de calibracion y suficientes lecturas.
CAMPOS_DIAGNOSTICO = ("battery_voltage", "battery_0_voltage", "battery_1_voltage",
                      "adc1_py_array_current", "adc4_my_array_current", "adc7_mx_array_current",
                      "adc10_pz_array_current", "adc13_px_array_current", "adc31_mz_array_current")

REF_MAD = ("Iglewicz, B. y Hoaglin, D. C. (1993). How to Detect and Handle Outliers. ASQC Basic "
           "References in Quality Control, vol. 16. (z modificado con MAD; umbral recomendado 3,5.)")


def fichas() -> list[dict]:
    """Ficha tecnica de cada diagnostico, con los parametros leidos del codigo vigente."""
    return [
        {
            "id": "DIAG-Z",
            "nombre": "z-score robusto (mediana móvil y MAD)",
            "codigo": "gemelo_digital/anomalias.py · zscore_robusto, clasificar",
            "usado_por": "modelo 3D del inicio (/api/gemelo/estado), gráficas y eventos del gemelo; "
                         "desviaciones del HMTA",
            "formula": "z_i = (x_i − med_W(x)_i) / (1,4826 · MAD_W(x)_i),  MAD_W = med_W(|x − med_W(x)|)",
            "ventana": {"tipo": "por número de lecturas (muestreo irregular)", "lecturas": A.VENTANA,
                        "min_lecturas": A.VENTANA // 2,
                        "alineacion": "final: la ventana de x_i son las lecturas i−50…i e INCLUYE x_i",
                        "amplitud_temporal_maxima": str(A.MAX_SPAN_VENTANA)},
            "metodo": "pandas rolling(window=51, min_periods=25).median() y .apply(MAD)",
            "umbrales": [
                {"valor": A.UMBRAL_ADVERTENCIA, "etiqueta": "advertencia",
                 "justificacion": "Umbral recomendado para el z modificado (Iglewicz y Hoaglin, 1993).",
                 "referencia": REF_MAD},
                {"valor": A.UMBRAL_ANOMALIA, "etiqueta": "anomalia",
                 "justificacion": "Elección del proyecto para separar desviaciones claras. "
                                  "SIN respaldo bibliográfico: es un parámetro de diseño, no un límite físico.",
                 "referencia": None}],
            "ventanas_incompletas": "Con menos de 25 lecturas previas la mediana es NaN y la lectura "
                                    "queda «sin_referencia». Entre 25 y 50 se calcula con las disponibles "
                                    "(ventana parcial). Si las 51 lecturas abarcan más de 30 días, la "
                                    "lectura queda «sin_referencia»: la referencia no es comparable.",
            "mad_nula": "Con MAD = 0 el z no se define (NaN) y la decide la regla de canal enrielado.",
            "limitaciones": [
                "La ventana incluye la lectura evaluada (el docstring dice «lecturas previas»): un atípico "
                "aislado contamina su propia referencia; con 51 lecturas el efecto sobre la mediana es "
                "pequeño, pero existe.",
                "Recepciones múltiples de la misma baliza cuentan como lecturas distintas de la ventana.",
                "Lecturas en la ordenada de la recta (cuenta ADC 0, canal sin medida) entran en la "
                "estadística como si fueran medidas.",
                "Supone que la serie es estacionaria dentro de la ventana; las variaciones orbitales "
                "(iluminación) quedan dentro de la dispersión."],
        },
        {
            "id": "DIAG-RIEL",
            "nombre": "canal enrielado",
            "codigo": "gemelo_digital/anomalias.py · enrielado",
            "usado_por": "modelo 3D (INSTRUMENTACION_PERDIDA), eventos del gemelo",
            "formula": "max_W(x) − min_W(x) ≤ 1e-3 · |med_W(x)|  (W = 20 lecturas; si la mediana es 0, "
                       "se usa max|x| de la serie)",
            "ventana": {"tipo": "por número de lecturas", "lecturas": A.MIN_ENRIELADO,
                        "min_lecturas": A.MIN_ENRIELADO, "alineacion": "final, incluye la lectura"},
            "metodo": "pandas rolling(20).max/min/median",
            "umbrales": [{"valor": A.TOLERANCIA_ENRIELADO, "etiqueta": "canal_enrielado",
                          "justificacion": "Amplitud relativa por debajo de una milésima de la escala: "
                                           "el convertidor no se mueve. Parámetro de diseño del proyecto.",
                          "referencia": None}],
            "ventanas_incompletas": "Con menos de 20 lecturas no se evalúa (falso).",
            "limitaciones": ["No distingue un canal muerto de una magnitud realmente constante; en "
                             "órbita, con iluminación variable, lo segundo es improbable pero no imposible."],
        },
    ]


@lru_cache(maxsize=16)
def clasificacion(campo: str) -> pd.DataFrame:
    return A.clasificar(C.campos_gemelo(), campo)


def resultado_campo(campo: str) -> dict:
    clas = clasificacion(campo)
    et = clas["etiqueta"].astype(str)
    mediana = clas["mediana"]
    n_parcial = int((mediana.notna() & (np.arange(len(clas)) < A.VENTANA - 1)).sum())
    evs = A.eventos(clas, campo)
    return E.limpiar({
        "campo": campo, "n_lecturas": len(clas),
        "desde": clas.index.min().isoformat(), "hasta": clas.index.max().isoformat(),
        "por_etiqueta": et.value_counts().to_dict(),
        "por_interpretacion": et.map(INTERPRETACION).value_counts().to_dict(),
        "ventanas_parciales": n_parcial,
        "sin_mediana_por_ventana_corta": int(mediana.isna().sum()),
        "sin_referencia_por_amplitud": int((clas["sin_referencia"] & mediana.notna()).sum()),
        "eventos": len(evs),
        "eventos_por_tipo": pd.Series([e.etiqueta for e in evs]).value_counts().to_dict() if evs else {},
        "evento_mas_largo": max((e.dict() for e in evs), key=lambda e: e["duracion_s"], default=None),
        "falla_confirmada": FALLA_CONFIRMADA,
    })


def huella_clasificacion(campo: str) -> str:
    from .procedencia import sha256

    c = clasificacion(campo)
    tabla = pd.DataFrame({"t": c.index.astype("int64"), "z": c["z"].round(9),
                          "m": c["mediana"].round(9), "e": c["etiqueta"].astype(str)})
    return sha256(tabla.to_csv(index=False).encode())


def prueba_reproducibilidad(campo: str = "battery_voltage") -> E.Resultado:
    """Dos ejecuciones independientes (sin cache) dan la misma clasificacion."""
    a = A.clasificar(C.campos_gemelo(), campo)
    b = A.clasificar(C.campos_gemelo().copy(), campo)
    iguales = (a["etiqueta"].astype(str).equals(b["etiqueta"].astype(str))
               and np.array_equal(a["z"].to_numpy(), b["z"].to_numpy(), equal_nan=True))
    return E.ejecutado("DIAG-REP", "diagnosticos", f"Reproducibilidad del diagnóstico · {campo}", iguales,
                       esperado="clasificación idéntica en dos ejecuciones",
                       obtenido={"lecturas": len(a), "identicas": iguales,
                                 "sha256": huella_clasificacion(campo)},
                       tolerancia="0 (z con NaN tratados como iguales)",
                       detalle="Mismo archivo, misma versión de gemelo_digital/anomalias.py.")


def prueba_ventanas_incompletas() -> E.Resultado:
    """Comprueba el tratamiento documentado de ventanas incompletas con datos sinteticos."""
    idx = pd.date_range("2020-01-01", periods=60, freq="min", tz="UTC")
    s = pd.Series(np.arange(60, dtype=float) % 7, index=idx)
    z = A.zscore_robusto(s)
    ok = (z["mediana"].iloc[:A.VENTANA // 2 - 1].isna().all()
          and z["mediana"].iloc[A.VENTANA // 2 - 1:].notna().all())
    # mediana en la lectura 24 (25 disponibles) = mediana de las 25 primeras
    ok = ok and z["mediana"].iloc[24] == float(np.median(s.iloc[:25]))
    return E.ejecutado("DIAG-VENT", "diagnosticos", "Tratamiento de ventanas incompletas", bool(ok),
                       esperado="NaN con < 25 lecturas; mediana de las disponibles con 25-50",
                       obtenido={"nan_hasta_lectura": int(z["mediana"].isna().sum()),
                                 "mediana_lectura_25": float(z["mediana"].iloc[24])},
                       tolerancia="exacta", detalle="Serie sintética de 60 lecturas (solo prueba el "
                       "mecanismo; no se presenta como dato).")


def resumen() -> dict:
    return {"fichas": fichas(), "interpretacion": INTERPRETACION, "falla_confirmada": FALLA_CONFIRMADA,
            "resultados": [resultado_campo(c) for c in CAMPOS_DIAGNOSTICO
                           if c in set(C.campos_gemelo()["field_name"].astype(str))],
            "pruebas": [prueba_reproducibilidad().dict(), prueba_ventanas_incompletas().dict()]}
