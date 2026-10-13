"""Genera las tablas de resultados del informe tecnico a partir de los datos.

Las tablas de `docs/INFORME_TECNICO_FINAL.md` estaban transcritas a mano y se
habian desincronizado de las simulaciones: la tabla de BER llego a mostrar una
BER que bajaba al empeorar el SNR y la de link budget, distancias que no eran
monotonas con la elevacion. Este script reemplaza el contenido delimitado por
marcadores HTML en el informe:

    <!-- TABLA:nombre -->
    ...contenido generado...
    <!-- /TABLA:nombre -->

Ejecutar despues de cualquier cambio en los modelos:

    python generar_tablas_informe.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

OUTPUT_DIR = Path("resultados_simulacion")
INFORME = Path("docs/INFORME_TECNICO_FINAL.md")


# ─── Utilidades ─────────────────────────────────────────────────────────────

def tabla_md(encabezados: list[str], filas: list[list[str]],
             alineacion: str = "r") -> str:
    sep = {"r": "---:", "l": ":---", "c": ":---:"}[alineacion]
    lineas = [
        "| " + " | ".join(encabezados) + " |",
        "|" + "|".join([":---"] + [sep] * (len(encabezados) - 1)) + "|",
    ]
    lineas += ["| " + " | ".join(f) + " |" for f in filas]
    return "\n".join(lineas)


def fmt_ber(valor: float) -> str:
    return "0 (sin errores)" if valor == 0.0 else f"{valor:.2e}"


def leer_csv(nombre: str) -> list[dict]:
    with (OUTPUT_DIR / nombre).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def leer_json(nombre: str):
    with (OUTPUT_DIR / nombre).open(encoding="utf-8") as f:
        return json.load(f)


# ─── Tablas ─────────────────────────────────────────────────────────────────

def fmt_tasa(valor, cota_sup=None) -> str:
    """Tasa de error. Un cero observado se escribe con su cota superior al 95 %."""
    if valor is None or valor == "":
        return "N/A"
    valor = float(valor)
    if valor == 0.0:
        return f"0 (< {float(cota_sup):.1e})" if cota_sup not in (None, "") else "0"
    return f"{valor:.2e}"


def tabla_ber_basico() -> str:
    filas_por_snr: dict[str, dict[str, str]] = {}
    ebn0: dict[str, str] = {}
    for r in leer_csv("resultados_ber_fsk_bpsk.csv"):
        filas_por_snr.setdefault(r["snr_db"], {})[r["modulacion"]] = fmt_ber(float(r["ber"]))
        ebn0[r["snr_db"]] = r["ebn0_db"]
    filas = [
        [snr, ebn0[snr], datos.get("BPSK", "-"), datos.get("FSK", "-")]
        for snr, datos in sorted(filas_por_snr.items(), key=lambda kv: float(kv[0]))
    ]
    return tabla_md(["SNR por muestra (dB)", "Eb/N0 (dB)", "BER BPSK", "BER FSK"], filas)


def tabla_ber_cadena_gnuradio() -> str:
    """Barrido de la cadena GNU Radio minima (`barrido_ber_strand1.py`)."""
    filas = []
    for r in leer_csv("ber_strand1_sweep.csv"):
        errores, bits = int(r["errores_totales"]), int(r["bits_totales"])
        # Mismo criterio que el resto del informe: un cero lleva su cota al 95 %.
        emp = f"0 (< {3.84 / bits:.1e})" if errores == 0 else f"{float(r['ber_empirica']):.2e}"
        filas.append([f"{float(r['snr_db']):.0f}", str(errores), str(bits), emp,
                      f"{float(r['ber_teorica']):.2e}"])
    return tabla_md(["Eb/N0 (dB)", "Errores", "Bits comparados", "BER medida", "BER teorica BPSK"],
                    filas)


def tabla_ancho_banda_basico() -> str:
    anchos = {r["modulacion"]: float(r["ancho_banda_estimado_hz"])
              for r in leer_csv("resultados_ber_fsk_bpsk.csv")}
    filas = [[m, f"{bw / 1000:.1f} kHz"] for m, bw in sorted(anchos.items())]
    return tabla_md(["Modulacion", "Ancho de banda (-20 dB)"], filas)


def _avanzado() -> dict:
    return leer_json("resultados_simulacion_avanzada.json")


def _curva(esquema: str, canal: str) -> list[dict]:
    return [r for r in _avanzado()["resultados"]
            if r["esquema"] == esquema and r["canal"] == canal]


def tabla_avanzado_principal() -> str:
    """BER en AWGN: teoria, sincronizacion ideal y receptor con lazos."""
    ideal, rrc, nrz, fec = (_curva(e, "awgn") for e in ("ideal_rrc", "rrc", "nrz", "rrc_fec"))
    filas = []
    for i, r in enumerate(rrc):
        filas.append([
            f"{r['ebn0_db']:.1f}", f"{r['snr_muestra_db']:.2f}", f"{r['ber_teorica_bpsk']:.2e}",
            fmt_tasa(ideal[i]["ber"], ideal[i]["ber_ic95_sup"]),
            fmt_tasa(r["ber"], r["ber_ic95_sup"]),
            fmt_tasa(nrz[i]["ber"], nrz[i]["ber_ic95_sup"]),
            fmt_tasa(fec[i]["ber"], fec[i]["ber_ic95_sup"]),
        ])
    return tabla_md(
        ["Eb/N0 (dB)", "SNR/muestra sin codigo (dB)", "Teoria BPSK", "RRC, sinc. ideal",
         "RRC, Costas+Gardner", "NRZ, Costas+Gardner", "RRC + FEC"], filas)


def tabla_avanzado_rice() -> str:
    rrc, fec, ax, axf = (_curva(e, "rice") for e in ("rrc", "rrc_fec", "ax25", "ax25_fec"))
    filas = []
    for i, r in enumerate(rrc):
        filas.append([
            f"{r['ebn0_db']:.1f}", fmt_tasa(r["ber"]), fmt_tasa(r["ber_diferencial"]),
            fmt_tasa(fec[i]["ber_diferencial"]), fmt_tasa(r["per"]),
            fmt_tasa(ax[i]["fer"]), fmt_tasa(axf[i]["fer"]),
        ])
    return tabla_md(
        ["Eb/N0 (dB)", "BER", "BER diferencial", "BER dif. con FEC", "PER",
         "FER AX.25", "FER AX.25 + FEC"], filas)


def tabla_doppler_residual() -> str:
    base = _curva("rrc", "awgn")
    canales = _avanzado()["metadatos"]["canales"]
    columnas = [("awgn", "0 Hz")] + [
        (k, canales[k]["nombre"].replace("AWGN + ", "")) for k in ("res10", "res50", "res100", "deriva")]
    curvas = {k: _curva("rrc", k) for k, _ in columnas}
    filas = [[f"{r['ebn0_db']:.1f}"] + [fmt_tasa(curvas[k][i]["ber_diferencial"]) for k, _ in columnas]
             for i, r in enumerate(base)]
    return tabla_md(["Eb/N0 (dB)"] + [n for _, n in columnas], filas)


def tabla_ax25() -> str:
    ax, axf = _curva("ax25", "awgn"), _curva("ax25_fec", "awgn")
    filas = []
    for i, r in enumerate(ax):
        f = axf[i]
        filas.append([
            f"{r['ebn0_db']:.1f}", fmt_tasa(r["ber"], r["ber_ic95_sup"]),
            f"{r['ax25_frames_validos']}/{r['ax25_frames_tx']}",
            f"{r['ax25_frames_invalidos']}", f"{r['ax25_frames_descartados']}",
            fmt_tasa(r["fer"], r["fer_ic95_sup"]), fmt_tasa(r["per"], r["per_ic95_sup"]),
            f"{f['ax25_frames_validos']}/{f['ax25_frames_tx']}",
            fmt_tasa(f["fer"], f["fer_ic95_sup"]),
        ])
    return tabla_md(
        ["Eb/N0 (dB)", "BER", "Tramas validas", "FCS invalido", "No recuperadas", "FER", "PER",
         "Validas con FEC", "FER con FEC"], filas)


def tabla_ganancia_codificacion() -> str:
    an = _avanzado()["analisis"]
    filas = []
    for g in an["ganancia_codificacion"]:
        filas.append([f"BER {g['ber_objetivo']:g}", g["canal"],
                      _na(g["ebn0_sin_codigo_db"]), _na(g["ebn0_con_codigo_db"]),
                      _na(g["ganancia_db"]), g["estado"]])
    for g in an["ganancia_codificacion_fer"]:
        filas.append([f"FER {g['fer_objetivo']:g} (AX.25)", g["canal"],
                      _na(g["ebn0_sin_codigo_db"]), _na(g["ebn0_con_codigo_db"]),
                      _na(g["ganancia_db"]), g["estado"]])
    return tabla_md(["Objetivo", "Canal", "Eb/N0 sin codigo (dB)", "Eb/N0 con codigo (dB)",
                     "Ganancia (dB)", "Estado"], filas, alineacion="l")


def _na(v) -> str:
    return "N/A" if v is None else f"{v:.2f}"


def tabla_procedencia() -> str:
    m = _avanzado()["metadatos"]
    paso = leer_json("margen_paso_sgp4.json")
    filas = [
        ["Commit del codigo", m["commit"]],
        ["Fecha de la simulacion avanzada (UTC)", m["generado_utc"]],
        ["Fecha del analisis del paso SGP4 (UTC)", paso["generado_utc"]],
        ["Semilla base", str(m["semilla_base"])],
        ["Semillas por corrida", m["semillas"]],
        ["Ensayos por punto", str(m["ensayos_por_punto"])],
        ["Bits de informacion por ensayo", str(m["entrada"]["bits"])],
        ["Valores de Eb/N0 (dB)", ", ".join(f"{x:g}" for x in m["ebn0_db"])],
        ["Definicion de Eb/N0", m["definicion_ebn0"]],
        ["Ambiguedad de fase", m["sincronizacion"]["ambiguedad_de_fase"]],
        ["Semilla y corridas del Monte Carlo de margen",
         f"{paso['sensibilidad']['montecarlo']['semilla']} · "
         f"{paso['sensibilidad']['montecarlo']['corridas']}"],
        ["TLE", f"{paso['tle']['fuente']} (epoca {paso['tle']['epoca_utc']})"],
    ]
    return tabla_md(["Elemento", "Valor"], filas, alineacion="l")


def tabla_link_budget() -> str:
    filas = [
        [r["elevacion_deg"], r["distancia_km"], r["fspl_db"], r["p_rx_dbm"],
         r["c_n0_db_hz"], r["eb_n0_db"], r["margen_db"], r["margen_bpsk_db"]]
        for r in leer_csv("link_budget_resultados.csv")
        if int(float(r["elevacion_deg"])) % 10 == 5 or int(float(r["elevacion_deg"])) % 30 == 0
    ]
    return tabla_md(
        ["Elevacion (deg)", "Distancia (km)", "FSPL (dB)", "P_rx (dBm)",
         "C/N0 (dB-Hz)", "Eb/N0 (dB)", "Margen FSK no coh. (dB)", "Margen BPSK, modelo (dB)"],
        filas,
    )


def tabla_link_budget_parametros() -> str:
    datos = leer_json("link_budget_completo.json")
    p, r, proc = datos["parametros"], datos["resultados"], datos["procedencia"]

    def fila(nombre, clave, valor, unidad):
        return [nombre, valor, unidad, proc[clave]["procedencia"] if clave in proc else "calculado"]

    filas = [
        fila("Frecuencia", "frecuencia_hz", f"{p['frecuencia_hz'] / 1e6:.3f}", "MHz"),
        fila("Tasa de bits", "tasa_bit_bps", f"{p['symbol_rate_bps']}", "bit/s"),
        fila("Altura orbital", "altura_orbital_km", f"{p['orbit_height_km']:.0f}", "km"),
        fila("Potencia TX (satelite)", "p_tx_dbm", f"{p['p_tx_dbm']:.1f}", "dBm"),
        fila("Ganancia antena TX", "g_tx_dbi", f"{p['g_tx_dbi']:.1f}", "dBi"),
        fila("Perdida cables TX", "l_tx_db", f"{p['l_tx_db']:.1f}", "dB"),
        fila("Ganancia antena RX", "g_rx_dbi", f"{p['g_rx_dbi']:.1f}", "dBi"),
        fila("Perdida cables RX", "l_rx_db", f"{p['l_rx_db']:.1f}", "dB"),
        fila("Figura de ruido RX", "nf_rx_db", f"{p['nf_rx_db']:.1f}", "dB"),
        fila("Temperatura de antena", "t_ant_k", f"{p['t_ant_k']:.1f}", "K"),
        fila("Temperatura de sistema", "-", f"{r[0]['t_sys_k']:.1f}", "K"),
        fila("Perdida atmosferica", "l_atm_db", f"{p['l_atm_db']:.1f}", "dB"),
        fila("Perdida por polarizacion", "l_pol_db", f"{p['l_pol_db']:.1f}", "dB"),
        fila("Perdida por apuntamiento", "l_point_db", f"{p['l_point_db']:.1f}", "dB"),
        fila("Reserva de implementacion", "l_impl_db", f"{p['l_impl_db']:.1f}", "dB"),
        fila("Eb/N0 teorica, FSK no coherente", "-", f"{p['eb_n0_req_db']:.2f}", "dB"),
        fila("Eb/N0 teorica, BPSK coherente", "-", f"{p['eb_n0_req_bpsk_db']:.2f}", "dB"),
        fila("BER objetivo", "-", f"{p['ber_target']:.0e}", "-"),
    ]
    return tabla_md(["Parametro", "Valor", "Unidad", "Procedencia"], filas)


def tabla_margen_paso() -> str:
    paso = leer_json("margen_paso_sgp4.json")
    filas = []
    for clave, m in paso["margen"].items():
        u = paso["umbrales"][clave]
        pc = m["percentiles_db"]
        filas.append([
            clave, u["tipo"].replace("_", " "), f"{u['eb_n0_db']:.2f}",
            f"{m['margen_min_db']:.2f}", f"{pc['p5']:.2f}", f"{pc['p50']:.2f}",
            f"{m['margen_medio_db']:.2f}", f"{m['margen_max_db']:.2f}",
            f"{m['porcentaje_tiempo_margen_positivo']:.1f}",
            f"{m['duracion_total_margen_positivo_s']:.0f}",
        ])
    return tabla_md(
        ["Umbral", "Tipo", "Eb/N0 umbral (dB)", "Min", "p5", "p50", "Medio", "Max",
         "% tiempo > 0", "Duracion > 0 (s)"], filas)


def tabla_doppler_paso() -> str:
    paso = leer_json("margen_paso_sgp4.json")
    d = paso["doppler"]
    filas = [
        ["Paso analizado (inicio UTC)", paso["paso_analizado"]["inicio_utc"]],
        ["Culminacion", f"{paso['paso_analizado']['elev_max_deg']:.2f}°"],
        ["Antiguedad del TLE en el paso", f"{paso['antiguedad_tle_en_el_paso_h']:.1f} h"],
        ["Doppler (elevacion >= 5°)", f"{d['doppler_min_hz']:.0f} a {d['doppler_max_hz']:+.0f} Hz"],
        ["Tasa de cambio maxima", f"{d['tasa_doppler_max_abs_hz_s']:.1f} Hz/s"],
        ["Coherencia v_radial vs d(distancia)/dt",
         f"diferencia maxima {d['coherencia_velocidad_radial_max_abs_km_s'] * 1000:.2f} m/s"],
    ] + [
        [f"Residual con error de tiempo de {r['error_tiempo_s']:g} s",
         f"max {r['residual_max_abs_hz']:.1f} Hz · rms {r['residual_rms_hz']:.1f} Hz"]
        for r in d["residual_tras_precompensacion"]
    ] + [
        ["Error de apuntamiento maximo del rotor",
         f"{paso['apuntamiento']['error_max_deg']:.2f}° ({paso['apuntamiento']['perdida_max_db']:.2f} dB)"],
    ]
    return tabla_md(["Magnitud", "Valor"], filas, alineacion="l")


def tabla_sensibilidad() -> str:
    s = leer_json("margen_paso_sgp4.json")["sensibilidad"]
    filas = [[r["parametro"], f"{r['valor_base']:g} {r['unidad']}", f"±{r['incertidumbre']:g}",
              r["procedencia"], f"{r['delta_margen_db_menos']:+.2f}", f"{r['delta_margen_db_mas']:+.2f}"]
             for r in s["uno_a_la_vez"]]
    mc = s["montecarlo"]
    filas.append(["**Monte Carlo conjunto**", f"{mc['corridas']} corridas", "todos", "-",
                  f"p5: {mc['margen_min_db']['p5']:+.2f}", f"p95: {mc['margen_min_db']['p95']:+.2f}"])
    return tabla_md(["Parametro", "Valor base", "Incertidumbre", "Procedencia",
                     "Δ margen con − (dB)", "Δ margen con + (dB)"], filas)


def tabla_estimador_snr() -> str:
    filas = [
        [f["canal"], f["reloj"], f"{f['esn0_real_db']:.0f}", str(f["ventana_simbolos"]),
         f"{f['ventanas_validas']}/{f['ventanas']}", _na(f["esn0_estimada_media_db"]),
         _na(f["sesgo_db"]), _na(f["desviacion_db"])]
        for f in leer_json("estimacion_snr_iq.json")["resultados"]
        if f["reloj"] == "gardner" and f["ventana_simbolos"] in (64, 1024)
        and f["esn0_real_db"] in (0.0, 6.0, 12.0)
    ]
    return tabla_md(["Canal", "Reloj", "Es/N0 real (dB)", "Ventana (simbolos)", "Ventanas validas",
                     "Media estimada (dB)", "Sesgo (dB)", "Desviacion (dB)"], filas)


def tabla_perdida_secuencia() -> str:
    ps = leer_json("analisis_recepcion_telemetria.json")["perdida_por_secuencia"]

    def fila(nombre, v):
        return [nombre, str(v["rafagas"]), str(v["paquetes_emitidos_estimados"]),
                str(v["paquetes_recibidos"]),
                "N/A" if v["perdida"] is None else f"{100 * v['perdida']:.1f} %"]

    filas = [fila(f"{v['elevacion_maxima_deg']}°", v)
             for v in ps["por_elevacion_maxima_de_la_observacion"]]
    filas.append(fila("**Global (todas las rafagas)**", ps["global"]))
    return tabla_md(["Elevacion maxima de la observacion", "Rafagas", "Emitidos (estimados)",
                     "Recibidos", "Perdida"], filas)


def tabla_diversidad() -> str:
    rec = leer_json("analisis_recepcion_telemetria.json")
    d, p = rec["diversidad"], rec["par_M0KSF"]
    n = d["por_numero_de_estaciones"]
    c = p["en_ventanas_comunes"]
    filas = [
        ["Balizas con observador", str(rec["balizas"]["con_observador"])],
        ["Emisiones distintas recibidas", str(d["emisiones_distintas_recibidas"])],
        ["Recibidas por 1 / 2 / 3 / 4 o mas estaciones",
         f"{n['1']} / {n['2']} / {n['3']} / {n['4_o_mas']}"],
        ["Ventanas con varias estaciones", str(d["ventanas_con_varias_estaciones"])],
        ["Emisiones en esas ventanas: union / mejor estacion sola",
         f"{d['emisiones_en_esas_ventanas']} / {d['emisiones_de_la_mejor_estacion_de_cada_ventana']}"],
        ["Ganancia por combinacion", f"×{d['ganancia_por_combinacion']:.2f}"],
        ["M0KSF y M0KSF-BB, ventanas comunes", str(p["ventanas_comunes"])],
        ["Solo M0KSF / solo M0KSF-BB / ambas",
         f"{c['solo_M0KSF']} / {c['solo_M0KSF-BB']} / {c['ambas']}"],
        ["Ganancia de la union sobre la mejor del par", f"×{p['ganancia_union_sobre_la_mejor']:.2f}"],
    ]
    return tabla_md(["Magnitud", "Valor"], filas, alineacion="l")


def tabla_uplink() -> str:
    datos = leer_json("enlace_ascendente_resultados.json")
    filas = [
        [f"{r['elevacion_deg']:.0f}", f"{r['distancia_km']:.1f}", f"{r['fspl_db']:.2f}",
         f"{r['c_n0_db_hz']:.2f}", f"{r['eb_n0_db']:.2f}", f"{r['margen_db']:.2f}",
         f"{r['capacidad_max_bps'] / 1000:.0f}"]
        for r in datos
        if int(r["elevacion_deg"]) % 10 == 5 or int(r["elevacion_deg"]) % 30 == 0
    ]
    return tabla_md(
        ["Elevacion (deg)", "Distancia (km)", "FSPL (dB)", "C/N0 (dB-Hz)",
         "Eb/N0 (dB)", "Margen (dB)", "Tasa max (kbps)"],
        filas,
    )


def tabla_estacion_terrena() -> str:
    datos = leer_json("estacion_terrena_seguimiento.json")
    vis = [r for r in datos if r["elevacion_deg"] >= 5.0]
    c_n0 = [r["c_n0_db_hz"] for r in vis]
    err = [r["error_apuntamiento_deg"] for r in vis]
    p_loss = [r["pointing_loss_db"] for r in vis]
    filas = [
        ["Duracion del paso (horizonte a horizonte)", f"{datos[-1]['tiempo_s'] / 60:.1f} min"],
        ["Duracion util (elevacion > 5°)", f"{len(vis) / 60:.1f} min"],
        ["Elevacion de culminacion", f"{max(r['elevacion_deg'] for r in datos):.1f}°"],
        ["Distancia oblicua", f"{min(r['distancia_km'] for r in vis):.0f} - "
                              f"{max(r['distancia_km'] for r in vis):.0f} km"],
        ["Temperatura de sistema", f"{min(r['t_sys_k'] for r in vis):.0f} - "
                                   f"{max(r['t_sys_k'] for r in vis):.0f} K"],
        ["C/N0 promedio", f"{sum(c_n0) / len(c_n0):.1f} dB-Hz"],
        ["C/N0 minimo / maximo", f"{min(c_n0):.1f} / {max(c_n0):.1f} dB-Hz"],
        ["Error de apuntamiento maximo", f"{max(err):.2f}°"],
        ["Perdida por apuntamiento maxima", f"{max(p_loss):.2f} dB"],
    ]
    return tabla_md(["Magnitud", "Valor"], filas, alineacion="l")


def tabla_cubesats() -> str:
    datos = leer_json("cubesats_reales_referencia.json")["cubesats_reales"]
    filas = [
        [c["nombre"], c["pais"], str(c["ano_lanzamiento"]), c["formato"],
         f"{c['frecuencia_mhz']:.3f}", c["modulacion"], str(c["tasa_bps"]),
         "si" if c.get("verificado") else "pendiente"]
        for c in datos
    ]
    return tabla_md(
        ["CubeSat", "Pais", "Ano", "Formato", "Frecuencia (MHz)", "Modulacion", "Tasa (bps)",
         "Verificado en fuente"],
        filas,
    )


def tabla_concordancia() -> str:
    datos = leer_json("comparacion_parametros_cubesats_reales.json")["metricas"]
    filas = [
        [m["parametro"],
         m["simulado"].replace("\n", "<br>"),
         m["real_referencia"].split("\n")[0],
         m["concordancia"].replace("\n", " ")]
        for m in datos
    ]
    return tabla_md(["Parametro", "Valor del modelo", "Referencia", "Relacion"],
                    filas, alineacion="l")


TABLAS = {
    "ber_basico": tabla_ber_basico,
    "ancho_banda_basico": tabla_ancho_banda_basico,
    "ber_cadena_gnuradio": tabla_ber_cadena_gnuradio,
    "procedencia": tabla_procedencia,
    "avanzado_principal": tabla_avanzado_principal,
    "avanzado_rice": tabla_avanzado_rice,
    "ganancia_codificacion": tabla_ganancia_codificacion,
    "estimador_snr": tabla_estimador_snr,
    "margen_paso": tabla_margen_paso,
    "doppler_paso": tabla_doppler_paso,
    "sensibilidad": tabla_sensibilidad,
    "perdida_secuencia": tabla_perdida_secuencia,
    "diversidad": tabla_diversidad,
    "doppler_residual": tabla_doppler_residual,
    "ax25": tabla_ax25,
    "link_budget_parametros": tabla_link_budget_parametros,
    "link_budget": tabla_link_budget,
    "uplink": tabla_uplink,
    "estacion_terrena": tabla_estacion_terrena,
    "cubesats": tabla_cubesats,
    "concordancia": tabla_concordancia,
}


# ─── Sustitucion en el informe ──────────────────────────────────────────────

def actualizar_informe() -> int:
    texto = INFORME.read_text(encoding="utf-8")
    sustituidas = 0

    for nombre, generador in TABLAS.items():
        patron = re.compile(
            rf"(<!-- TABLA:{re.escape(nombre)} -->\n).*?(\n<!-- /TABLA:{re.escape(nombre)} -->)",
            re.DOTALL,
        )
        if not patron.search(texto):
            # Una tabla sin marcador quedaria sin actualizar en silencio y el
            # informe volveria a contradecir a los datos: es un error.
            raise SystemExit(f"Falta el marcador TABLA:{nombre} en {INFORME}")
        texto = patron.sub(lambda m: m.group(1) + generador() + m.group(2), texto)
        sustituidas += 1

    INFORME.write_text(texto, encoding="utf-8")
    return sustituidas


def main() -> None:
    faltan = [n for n in ("resultados_ber_fsk_bpsk.csv", "ber_strand1_sweep.csv", "resultados_simulacion_avanzada.csv",
                          "link_budget_resultados.csv", "link_budget_completo.json",
                          "enlace_ascendente_resultados.json",
                          "estacion_terrena_seguimiento.json",
                          "cubesats_reales_referencia.json",
                          "resultados_simulacion_avanzada.json", "margen_paso_sgp4.json",
                          "estimacion_snr_iq.json", "analisis_recepcion_telemetria.json",
                          "comparacion_parametros_cubesats_reales.json")
             if not (OUTPUT_DIR / n).exists()]
    if faltan:
        raise SystemExit(
            "Faltan archivos de resultados: " + ", ".join(faltan)
            + "\nEjecuta primero el pipeline completo (ver README)."
        )

    n = actualizar_informe()
    print(f"Tablas actualizadas en {INFORME}: {n} de {len(TABLAS)}")


if __name__ == "__main__":
    main()
