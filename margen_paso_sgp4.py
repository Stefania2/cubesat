#!/usr/bin/env python3
"""Serie temporal del margen de enlace y del Doppler durante un paso SGP4.

Une las piezas que antes vivian separadas:

    TLE versionado -> SGP4 -> azimut/elevacion/distancia/velocidad radial
        -> Doppler y su derivada -> precompensacion -> Doppler residual
        -> seguimiento del rotor -> perdida de apuntamiento
        -> P_rx -> C/N0 -> Eb/N0 -> margen por esquema de modulacion

El barrido de `calcular_link_budget.py` da el margen frente a la elevacion sobre
una orbita circular; aqui el margen es una funcion del tiempo sobre la
trayectoria real de un paso concreto, con sus estadisticas y su sensibilidad a
la incertidumbre de los parametros.

Lo que este script NO demuestra: que el enlace real cierre. La estacion es
hipotetica y la mayoria de los parametros son supuestos de diseño (ver
`parametros_enlace.py`); un margen positivo es una prediccion del modelo.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import parametros_enlace as pe
from geometria_orbital import densidad_ruido_dbm_hz, fspl_db, temperatura_sistema
from modelo_estacion_terrena import (
    AZ_RATE_DEG_S,
    EL_RATE_DEG_S,
    HPBW_DEG,
    GroundStationParams,
    antenna_tracking,
    pointing_loss_db,
)
from orbita_sgp4 import Observer, load_tle, propagate_point, tle_epoch

DEFAULT_TLE = Path("tle/strand1_2026-08-09.tle")
OUTPUT_DIR = Path("resultados_simulacion")
UMBRALES_SIMULADOS = OUTPUT_DIR / "umbrales_receptor_simulado.json"

ELEV_OPERATIVA_DEG = 5.0
VENTANA_BUSQUEDA_H = 48
PASO_BUSQUEDA_S = 20
SEMILLA_MC = 20261013
N_MONTECARLO = 5000
# Error de tiempo a lo largo de la traza con el que se evalua la
# precompensacion. Un TLE envejecido se equivoca sobre todo en la posicion a lo
# largo de la orbita, que equivale a adelantar o atrasar el paso. Los valores
# son ESCENARIOS: el error real de este TLE en la fecha del paso no se ha medido.
ERRORES_TIEMPO_S = [0.1, 0.5, 1.0, 2.0]


# ─── Pasos ──────────────────────────────────────────────────────────────────

def buscar_pasos(tle, observer, inicio: datetime, horas: int, freq_hz: float) -> list[dict]:
    """Localiza los pasos sobre el horizonte en la ventana, con paso grueso."""
    pasos, actual = [], None
    for k in range(0, horas * 3600 + 1, PASO_BUSQUEDA_S):
        t = inicio + timedelta(seconds=k)
        p = propagate_point(tle, observer, t, freq_hz)
        if p.elevation_deg >= 0.0:
            if actual is None:
                actual = {"inicio": t, "fin": t, "elev_max_deg": p.elevation_deg}
            actual["fin"] = t
            actual["elev_max_deg"] = max(actual["elev_max_deg"], p.elevation_deg)
        elif actual is not None:
            pasos.append(actual)
            actual = None
    # Un paso que ya estaba en curso al empezar la ventana queda truncado y no
    # sirve para estadisticas de paso completo.
    return [p for p in pasos if p["inicio"] > inicio]


def propagar_paso(tle, observer, paso: dict, freq_hz: float, dt_s: float = 1.0) -> list:
    inicio = paso["inicio"] - timedelta(seconds=PASO_BUSQUEDA_S)
    fin = paso["fin"] + timedelta(seconds=PASO_BUSQUEDA_S)
    n = int((fin - inicio).total_seconds() / dt_s) + 1
    puntos = [propagate_point(tle, observer, inicio + timedelta(seconds=i * dt_s), freq_hz)
              for i in range(n)]
    return [p for p in puntos if p.elevation_deg >= 0.0]


# ─── Presupuesto en el tiempo ───────────────────────────────────────────────

def eb_n0_db(dist_km: float, l_point_db: float, par: dict[str, float]) -> tuple[float, float, float]:
    """Devuelve (P_rx dBm, C/N0 dB-Hz, Eb/N0 dB) para una distancia dada.

    Mismas ecuaciones que `calcular_link_budget.calcular_link_budget`; la unica
    diferencia es que la perdida de apuntamiento es la calculada del rotor.
    """
    fspl = fspl_db(dist_km * 1e3, par["frecuencia_hz"])
    p_rx = (par["p_tx_dbm"] + par["g_tx_dbi"] - par["l_tx_db"]
            + par["g_rx_dbi"] - par["l_rx_db"]
            - fspl - par["l_atm_db"] - par["l_pol_db"] - l_point_db)
    t_sys = temperatura_sistema(par["t_ant_k"], par["l_rx_db"], par["nf_rx_db"])
    c_n0 = p_rx - densidad_ruido_dbm_hz(t_sys)
    return p_rx, c_n0, c_n0 - 10.0 * math.log10(par["tasa_bit_bps"])


def serie_paso(puntos: list, par: dict[str, float]) -> list[dict]:
    gs = GroundStationParams(0, 0, 0, par["g_rx_dbi"], HPBW_DEG, AZ_RATE_DEG_S,
                             EL_RATE_DEG_S, par["nf_rx_db"], ELEV_OPERATIVA_DEG, 0)
    prev_el, prev_az = puntos[0].elevation_deg, puntos[0].azimuth_deg
    t0 = datetime.fromisoformat(puntos[0].timestamp_utc.replace("Z", "+00:00"))
    filas = []
    for i, p in enumerate(puntos):
        t = datetime.fromisoformat(p.timestamp_utc.replace("Z", "+00:00"))
        dt = (t - datetime.fromisoformat(puntos[i - 1].timestamp_utc.replace("Z", "+00:00"))
              ).total_seconds() if i else 1.0
        error, prev_el, prev_az = antenna_tracking(
            p.elevation_deg, p.azimuth_deg, prev_el, prev_az, gs, dt)
        l_point = pointing_loss_db(error, HPBW_DEG)
        p_rx, c_n0, ebn0 = eb_n0_db(p.range_km, l_point, par)
        filas.append({
            "tiempo_s": round((t - t0).total_seconds(), 1),
            "timestamp_utc": p.timestamp_utc,
            "elevacion_deg": p.elevation_deg,
            "azimut_deg": p.azimuth_deg,
            "distancia_km": p.range_km,
            "velocidad_radial_km_s": p.range_rate_km_s,
            "doppler_hz": p.doppler_hz,
            "error_apuntamiento_deg": round(error, 3),
            "l_point_db": round(l_point, 3),
            "p_rx_dbm": round(p_rx, 2),
            "c_n0_db_hz": round(c_n0, 2),
            "eb_n0_db": round(ebn0, 2),
        })
    # Derivada del Doppler por diferencias centradas (Hz/s).
    d = np.array([f["doppler_hz"] for f in filas])
    tt = np.array([f["tiempo_s"] for f in filas])
    tasa = np.gradient(d, tt)
    for f, r in zip(filas, tasa):
        f["tasa_doppler_hz_s"] = round(float(r), 2)
    return filas


def umbrales(par: dict[str, float]) -> dict[str, dict]:
    """Umbrales de Eb/N0 contra los que se mide el margen."""
    u = {}
    for clave, esquema in pe.ESQUEMAS.items():
        teorico = pe.ebn0_requerida_db(clave)
        u[clave] = {
            "tipo": "teorico",
            "descripcion": f"{esquema.nombre}: curva teorica AWGN a BER {pe.BER_OBJETIVO:g} "
                           f"+ {par['l_impl_db']:g} dB de reserva de implementacion",
            "papel": esquema.papel,
            "eb_n0_db": round(teorico + par["l_impl_db"], 2),
        }
    if UMBRALES_SIMULADOS.exists():
        sim = json.loads(UMBRALES_SIMULADOS.read_text(encoding="utf-8"))
        for clave, dato in sim.get("umbrales", {}).items():
            if dato.get("eb_n0_db") is None:
                continue
            # El receptor simulado ya incluye sincronizacion y filtrado: no se
            # le suma la reserva de implementacion (seria contarla dos veces).
            u[f"simulado_{clave}"] = {
                "tipo": "calibrado_receptor_simulado",
                "descripcion": dato["descripcion"],
                "papel": "receptor BPSK simulado (modelo comparativo); sin reserva adicional",
                "eb_n0_db": dato["eb_n0_db"],
            }
    return u


def _intervalos(tiempos: np.ndarray, condicion: np.ndarray) -> list[float]:
    """Duracion (s) de cada tramo contiguo en que se cumple `condicion`."""
    duraciones, inicio = [], None
    for t, ok in zip(tiempos, condicion):
        if ok and inicio is None:
            inicio = t
        elif not ok and inicio is not None:
            duraciones.append(float(t - inicio))
            inicio = None
    if inicio is not None:
        duraciones.append(float(tiempos[-1] - inicio))
    return duraciones


def estadisticas(filas: list[dict], umbral_db: float) -> dict:
    op = [f for f in filas if f["elevacion_deg"] >= ELEV_OPERATIVA_DEG]
    if not op:
        return {"disponible": False, "motivo": "el paso no supera la elevacion operativa"}
    m = np.array([f["eb_n0_db"] - umbral_db for f in op])
    t = np.array([f["tiempo_s"] for f in op])
    positivos = _intervalos(t, m > 0.0)
    return {
        "disponible": True,
        "umbral_eb_n0_db": umbral_db,
        "muestras": len(op),
        "margen_min_db": round(float(m.min()), 2),
        "margen_max_db": round(float(m.max()), 2),
        "margen_medio_db": round(float(m.mean()), 2),
        "percentiles_db": {f"p{q}": round(float(np.percentile(m, q)), 2)
                           for q in (5, 25, 50, 75, 95)},
        "porcentaje_tiempo_margen_positivo": round(100.0 * float(np.mean(m > 0.0)), 1),
        "porcentaje_tiempo_margen_mayor_3db": round(100.0 * float(np.mean(m > 3.0)), 1),
        "intervalos_margen_positivo_s": [round(x, 1) for x in positivos],
        "duracion_total_margen_positivo_s": round(sum(positivos), 1),
    }


# ─── Sensibilidad ───────────────────────────────────────────────────────────

def _margen_min(puntos: list, par: dict[str, float], umbral_teorico_db: float) -> tuple[float, float]:
    filas = serie_paso(puntos, par)
    op = [f for f in filas if f["elevacion_deg"] >= ELEV_OPERATIVA_DEG]
    m = np.array([f["eb_n0_db"] for f in op]) - (umbral_teorico_db + par["l_impl_db"])
    return float(m.min()), 100.0 * float(np.mean(m > 0.0))


def sensibilidad(puntos: list, par: dict[str, float]) -> dict:
    """Uno a la vez (±incertidumbre) y Monte Carlo conjunto.

    La geometria y el seguimiento no dependen de estos parametros, asi que el
    efecto sobre Eb/N0 es un desplazamiento comun a todo el paso; se calcula
    una vez la serie base y se desplaza, en lugar de repropagar.
    """
    teorico = pe.ebn0_requerida_db(pe.ESQUEMA_DOCUMENTADO)
    base_min, base_pct = _margen_min(puntos, par, teorico)
    filas = serie_paso(puntos, par)
    op = [f for f in filas if f["elevacion_deg"] >= ELEV_OPERATIVA_DEG]
    ebn0_base = np.array([f["eb_n0_db"] for f in op])
    dist_ref, lp_ref = op[0]["distancia_km"], op[0]["l_point_db"]

    def desplazamiento(p: dict[str, float]) -> float:
        """Cambio de (Eb/N0 - umbral) respecto de la base, en dB."""
        d_ebn0 = eb_n0_db(dist_ref, lp_ref, p)[2] - eb_n0_db(dist_ref, lp_ref, par)[2]
        return d_ebn0 - (p["l_impl_db"] - par["l_impl_db"])

    variables = [k for k, v in pe.PARAMETROS.items()
                 if v.incertidumbre and k != "l_point_db"]
    uno_a_uno = []
    for k in variables:
        inc = pe.PARAMETROS[k].incertidumbre
        deltas = []
        for signo in (-1.0, 1.0):
            p = dict(par)
            p[k] = par[k] + signo * inc
            deltas.append(desplazamiento(p))
        uno_a_uno.append({
            "parametro": k,
            "valor_base": par[k],
            "incertidumbre": inc,
            "unidad": pe.PARAMETROS[k].unidad,
            "procedencia": pe.PARAMETROS[k].procedencia,
            "delta_margen_db_menos": round(deltas[0], 2),
            "delta_margen_db_mas": round(deltas[1], 2),
        })
    uno_a_uno.sort(key=lambda r: -max(abs(r["delta_margen_db_menos"]), abs(r["delta_margen_db_mas"])))

    rng = np.random.default_rng(SEMILLA_MC)
    minimos, pcts = [], []
    for _ in range(N_MONTECARLO):
        p = dict(par)
        for k in variables:
            inc = pe.PARAMETROS[k].incertidumbre
            p[k] = par[k] + rng.uniform(-inc, inc)
        # La incertidumbre del umbral (receptor FSK real no documentado) se
        # modela como hasta 4 dB adicionales sobre la cota no coherente.
        extra_umbral = rng.uniform(0.0, 4.0)
        m = ebn0_base + desplazamiento(p) - (teorico + par["l_impl_db"]) - extra_umbral
        minimos.append(float(m.min()))
        pcts.append(100.0 * float(np.mean(m > 0.0)))
    minimos, pcts = np.array(minimos), np.array(pcts)
    return {
        "esquema": pe.ESQUEMAS[pe.ESQUEMA_DOCUMENTADO].nombre,
        "margen_min_base_db": round(base_min, 2),
        "porcentaje_positivo_base": round(base_pct, 1),
        "uno_a_la_vez": uno_a_uno,
        "montecarlo": {
            "semilla": SEMILLA_MC,
            "corridas": N_MONTECARLO,
            "distribucion": "uniforme dentro de ±incertidumbre de cada parametro, "
                            "independientes; umbral del receptor con 0 a 4 dB adicionales",
            "margen_min_db": {f"p{q}": round(float(np.percentile(minimos, q)), 2)
                              for q in (5, 25, 50, 75, 95)},
            "probabilidad_margen_min_positivo": round(float(np.mean(minimos > 0.0)), 3),
            "porcentaje_tiempo_positivo": {f"p{q}": round(float(np.percentile(pcts, q)), 1)
                                           for q in (5, 50, 95)},
        },
        "nota": "Las incertidumbres son rangos de diseño asignados en parametros_enlace.py, "
                "no errores medidos. El resultado cuantifica cuanto depende la conclusion de "
                "los supuestos, no la probabilidad real de recibir.",
    }


# ─── Doppler ────────────────────────────────────────────────────────────────

def analisis_doppler(tle, observer, filas: list[dict], freq_hz: float) -> dict:
    op = [f for f in filas if f["elevacion_deg"] >= ELEV_OPERATIVA_DEG]
    d = np.array([f["doppler_hz"] for f in op])
    tasa = np.array([f["tasa_doppler_hz_s"] for f in op])
    # Coherencia interna: la velocidad radial que da SGP4 debe coincidir con la
    # derivada numerica de la distancia.
    rr = np.array([f["velocidad_radial_km_s"] for f in filas])
    dist = np.array([f["distancia_km"] for f in filas])
    tt = np.array([f["tiempo_s"] for f in filas])
    dif = np.gradient(dist, tt)[2:-2] - rr[2:-2]

    residuales = []
    for dt_err in ERRORES_TIEMPO_S:
        res = []
        for f in op:
            t = datetime.fromisoformat(f["timestamp_utc"].replace("Z", "+00:00"))
            pred = propagate_point(tle, observer, t + timedelta(seconds=dt_err), freq_hz)
            res.append(f["doppler_hz"] - pred.doppler_hz)
        res = np.array(res)
        residuales.append({
            "error_tiempo_s": dt_err,
            "residual_max_abs_hz": round(float(np.abs(res).max()), 1),
            "residual_rms_hz": round(float(np.sqrt(np.mean(res ** 2))), 1),
        })
    return {
        "portadora_hz": freq_hz,
        "convencion": "Doppler = -v_radial * f / c; v_radial < 0 (acercamiento) -> Doppler > 0",
        "doppler_max_hz": round(float(d.max()), 1),
        "doppler_min_hz": round(float(d.min()), 1),
        "tasa_doppler_max_abs_hz_s": round(float(np.abs(tasa).max()), 1),
        "coherencia_velocidad_radial_max_abs_km_s": round(float(np.abs(dif).max()), 5),
        "residual_tras_precompensacion": residuales,
        "nota_residual": "El residual se obtiene restando al Doppler del paso el que predice el "
                         "mismo TLE desplazado en el tiempo. Es un modelo del error a lo largo de "
                         "la traza; los desplazamientos evaluados son escenarios, no una medida "
                         "del error real del TLE.",
    }


# ─── Salidas ────────────────────────────────────────────────────────────────

def graficar(filas: list[dict], umb: dict, salida: Path) -> None:
    t = [f["tiempo_s"] for f in filas]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    fig.suptitle("Paso SGP4 de STRaND-1: geometria, Doppler y margen (resultado de modelo)",
                 fontsize=13, fontweight="bold")
    ax = axes[0, 0]
    ax.plot(t, [f["elevacion_deg"] for f in filas], "b-", label="Elevacion (°)")
    ax.axhline(ELEV_OPERATIVA_DEG, color="r", ls="--", alpha=0.5, label="Umbral operativo")
    ax2 = ax.twinx()
    ax2.plot(t, [f["distancia_km"] for f in filas], "g--", label="Distancia (km)")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Elevacion (°)"); ax2.set_ylabel("Distancia (km)")
    ax.set_title("Geometria"); ax.grid(True, ls=":"); ax.legend(fontsize=8, loc="upper left")
    ax = axes[0, 1]
    ax.plot(t, [f["doppler_hz"] / 1e3 for f in filas], "m-")
    ax2 = ax.twinx()
    ax2.plot(t, [f["tasa_doppler_hz_s"] for f in filas], color="orange", ls="--")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Doppler (kHz)"); ax2.set_ylabel("Tasa (Hz/s)")
    ax.set_title("Doppler orbital y su derivada"); ax.grid(True, ls=":")
    ax = axes[1, 0]
    ax.plot(t, [f["eb_n0_db"] for f in filas], "k-", label="Eb/N0 disponible")
    for (clave, u), color in zip(umb.items(), ["r", "tab:orange", "b", "tab:green", "tab:purple"]):
        ax.axhline(u["eb_n0_db"], color=color, ls="--", alpha=0.7,
                   label=f"{clave} ({u['eb_n0_db']} dB)")
    ax.set_xlabel("Tiempo (s)"); ax.set_ylabel("Eb/N0 (dB)")
    ax.set_title("Eb/N0 y umbrales"); ax.grid(True, ls=":"); ax.legend(fontsize=7)
    ax = axes[1, 1]
    ref = umb[pe.ESQUEMA_DOCUMENTADO]["eb_n0_db"]
    ax.plot([f["elevacion_deg"] for f in filas], [f["eb_n0_db"] - ref for f in filas], "b.", ms=3)
    ax.axhline(0, color="r", alpha=0.4)
    ax.set_xlabel("Elevacion (°)"); ax.set_ylabel("Margen (dB)")
    ax.set_title("Margen FSK no coherente frente a la elevacion"); ax.grid(True, ls=":")
    plt.tight_layout()
    plt.savefig(salida, dpi=160)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tle", type=Path, default=DEFAULT_TLE)
    parser.add_argument("--lat", type=float, default=4.7110)
    parser.add_argument("--lon", type=float, default=-74.0721)
    parser.add_argument("--alt-m", type=float, default=2600.0)
    args = parser.parse_args()

    par = {k: v.valor for k, v in pe.PARAMETROS.items()}
    tle = load_tle(args.tle)
    observer = Observer(args.lat, args.lon, args.alt_m)
    epoca = tle_epoch(tle)
    pasos = buscar_pasos(tle, observer, epoca, VENTANA_BUSQUEDA_H, par["frecuencia_hz"])
    if not pasos:
        raise SystemExit("No hay pasos completos en la ventana de busqueda.")
    elegido = max(pasos, key=lambda p: p["elev_max_deg"])
    puntos = propagar_paso(tle, observer, elegido, par["frecuencia_hz"])
    filas = serie_paso(puntos, par)
    umb = umbrales(par)

    salida = {
        "tipo_de_dato": "simulado (prediccion de modelo; no es una medicion del enlace)",
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tle": {"nombre": tle.name, "linea1": tle.line1, "linea2": tle.line2,
                "fuente": tle.source, "epoca_utc": epoca.isoformat()},
        "antiguedad_tle_en_el_paso_h": round((elegido["inicio"] - epoca).total_seconds() / 3600, 2),
        "estacion": {"lat_deg": args.lat, "lon_deg": args.lon, "alt_m": args.alt_m,
                     "nota": "estacion hipotetica (Bogota); no existe una estacion real del proyecto"},
        "sistema_de_referencia": "SGP4 en TEME; rotacion a terrestre por GMST (IAU 1982), "
                                 "elipsoide WGS-84; sin movimiento polar ni refraccion",
        "elevacion_operativa_deg": ELEV_OPERATIVA_DEG,
        "pasos_en_ventana": [
            {"inicio_utc": p["inicio"].isoformat(), "fin_utc": p["fin"].isoformat(),
             "elev_max_deg": round(p["elev_max_deg"], 1)} for p in pasos],
        "paso_analizado": {"inicio_utc": elegido["inicio"].isoformat(),
                           "elev_max_deg": round(max(f["elevacion_deg"] for f in filas), 2),
                           "duracion_sobre_horizonte_s": filas[-1]["tiempo_s"],
                           "criterio": "mayor elevacion de culminacion de la ventana"},
        "parametros": par,
        "umbrales": umb,
        "margen": {clave: estadisticas(filas, u["eb_n0_db"]) for clave, u in umb.items()},
        "apuntamiento": {
            "error_max_deg": max(f["error_apuntamiento_deg"] for f in filas),
            "perdida_max_db": max(f["l_point_db"] for f in filas),
            "nota": "sustituye a la reserva fija l_point_db del barrido por elevacion",
        },
        "doppler": analisis_doppler(tle, observer, filas, par["frecuencia_hz"]),
        "sensibilidad": sensibilidad(puntos, par),
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "margen_paso_sgp4.json").write_text(
        json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    with (OUTPUT_DIR / "margen_paso_sgp4_serie.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    graficar(filas, umb, OUTPUT_DIR / "margen_paso_sgp4.png")

    doc = salida["margen"][pe.ESQUEMA_DOCUMENTADO]
    print(f"TLE {tle.name}, epoca {epoca.isoformat()} · {len(pasos)} pasos completos en {VENTANA_BUSQUEDA_H} h")
    print(f"Paso analizado: {elegido['inicio'].isoformat()} · culminacion "
          f"{salida['paso_analizado']['elev_max_deg']}° · TLE con "
          f"{salida['antiguedad_tle_en_el_paso_h']} h de antiguedad")
    print(f"Margen FSK no coherente (elev >= {ELEV_OPERATIVA_DEG:g}°): min {doc['margen_min_db']} · "
          f"medio {doc['margen_medio_db']} · max {doc['margen_max_db']} dB · "
          f"{doc['porcentaje_tiempo_margen_positivo']} % del tiempo con margen positivo")
    dp = salida["doppler"]
    print(f"Doppler: {dp['doppler_min_hz']} a {dp['doppler_max_hz']} Hz · tasa maxima "
          f"{dp['tasa_doppler_max_abs_hz_s']} Hz/s")
    for r in dp["residual_tras_precompensacion"]:
        print(f"  residual con error de tiempo {r['error_tiempo_s']} s: "
              f"max {r['residual_max_abs_hz']} Hz, rms {r['residual_rms_hz']} Hz")
    mc = salida["sensibilidad"]["montecarlo"]
    print(f"Monte Carlo ({mc['corridas']} corridas): margen minimo p5/p50/p95 = "
          f"{mc['margen_min_db']['p5']}/{mc['margen_min_db']['p50']}/{mc['margen_min_db']['p95']} dB · "
          f"P(margen minimo > 0) = {mc['probabilidad_margen_min_positivo']}")
    print("Salidas: margen_paso_sgp4.json, margen_paso_sgp4_serie.csv, margen_paso_sgp4.png")


if __name__ == "__main__":
    main()
