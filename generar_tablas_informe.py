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

def tabla_ber_basico() -> str:
    filas_por_snr: dict[str, dict[str, str]] = {}
    for r in leer_csv("resultados_ber_fsk_bpsk.csv"):
        filas_por_snr.setdefault(r["snr_db"], {})[r["modulacion"]] = fmt_ber(float(r["ber"]))
    filas = [
        [snr, datos.get("BPSK", "-"), datos.get("FSK", "-")]
        for snr, datos in sorted(filas_por_snr.items(), key=lambda kv: float(kv[0]))
    ]
    return tabla_md(["SNR (dB)", "BER BPSK", "BER FSK"], filas)


def tabla_ancho_banda_basico() -> str:
    anchos = {r["modulacion"]: float(r["ancho_banda_estimado_hz"])
              for r in leer_csv("resultados_ber_fsk_bpsk.csv")}
    filas = [[m, f"{bw / 1000:.1f} kHz"] for m, bw in sorted(anchos.items())]
    return tabla_md(["Modulacion", "Ancho de banda (-20 dB)"], filas)


def _grupos_avanzado() -> dict[str, list[dict]]:
    rows = leer_csv("resultados_simulacion_avanzada.csv")
    grupos: dict[str, list[dict]] = {}
    for r in rows:
        if r["modulation"] == "AX.25":
            clave = "AX.25 + RRC"
        elif r["fec"] == "True":
            clave = "BPSK + FEC conv. (r=1/2, K=7)"
        else:
            clave = "BPSK + RRC (α=0.35)" if r["rrc"] == "True" else "BPSK rectangular (NRZ)"
            if r["fading"] == "True":
                clave += " + fading Rice"
            residual = float(r["doppler_residual_hz"])
            if residual > 0:
                clave += f" + Doppler residual {residual:g} Hz"
        grupos.setdefault(clave, []).append(r)
    for pts in grupos.values():
        pts.sort(key=lambda r: float(r["snr_db"]))
    return grupos


def tabla_avanzado_principal() -> str:
    grupos = _grupos_avanzado()
    orden = [
        "BPSK rectangular (NRZ)",
        "BPSK + RRC (α=0.35)",
        "BPSK rectangular (NRZ) + fading Rice",
        "BPSK + FEC conv. (r=1/2, K=7)",
    ]
    snrs = ["-8", "-6", "-4", "-2"]
    filas = []
    for clave in orden:
        if clave not in grupos:
            continue
        por_snr = {r["snr_db"]: r for r in grupos[clave]}
        fila = [clave]
        fila += [fmt_ber(float(por_snr[s]["ber"])) if s in por_snr else "-" for s in snrs]
        fila.append(f"{float(grupos[clave][0]['ancho_banda_hz']) / 1000:.1f} kHz")
        filas.append(fila)
    return tabla_md(
        ["Configuracion"] + [f"BER a {s} dB" for s in snrs] + ["Ancho de banda (99 %)"],
        filas,
    )


def tabla_doppler_residual() -> str:
    grupos = _grupos_avanzado()
    base = "BPSK rectangular (NRZ)"
    claves = [base] + sorted(
        (k for k in grupos if k.startswith(base + " + Doppler residual")),
        key=lambda k: float(re.search(r"([\d.]+) Hz", k).group(1)),
    )
    snrs = ["-8", "-4", "0", "4"]
    filas = []
    for clave in claves:
        m = re.search(r"residual ([\d.]+) Hz", clave)
        etiqueta = f"{m.group(1)} Hz" if m else "0 Hz"
        por_snr = {r["snr_db"]: r for r in grupos[clave]}
        filas.append([etiqueta] + [fmt_ber(float(por_snr[s]["ber"])) if s in por_snr else "-"
                                   for s in snrs])
    return tabla_md(["Residual de Doppler"] + [f"BER a {s} dB" for s in snrs], filas)


def tabla_ax25() -> str:
    filas = [
        [r["snr_db"], fmt_ber(float(r["ber"])), r["ax25_frames_validos"]]
        for r in _grupos_avanzado()["AX.25 + RRC"]
    ]
    return tabla_md(["SNR (dB)", "BER", "Tramas validas por FCS (de 37)"], filas)


def tabla_link_budget() -> str:
    filas = [
        [r["elevacion_deg"], r["distancia_km"], r["fspl_db"],
         r["c_n0_db_hz"], r["eb_n0_db"], r["margen_db"]]
        for r in leer_csv("link_budget_resultados.csv")
        if int(float(r["elevacion_deg"])) % 10 == 5 or int(float(r["elevacion_deg"])) % 30 == 0
    ]
    return tabla_md(
        ["Elevacion (deg)", "Distancia (km)", "FSPL (dB)",
         "C/N0 (dB-Hz)", "Eb/N0 (dB)", "Margen (dB)"],
        filas,
    )


def tabla_link_budget_parametros() -> str:
    p = leer_json("link_budget_completo.json")["parametros"]
    r = leer_json("link_budget_completo.json")["resultados"]
    filas = [
        ["Frecuencia", f"{p['frecuencia_hz'] / 1e6:.3f}", "MHz"],
        ["Tasa de datos", f"{p['symbol_rate_bps']}", "bps"],
        ["Altura orbital", f"{p['orbit_height_km']:.0f}", "km"],
        ["Potencia TX (satelite)", f"{p['p_tx_dbm']:.1f}", "dBm"],
        ["Ganancia antena TX", f"{p['g_tx_dbi']:.1f}", "dBi"],
        ["Perdida cables TX", f"{p['l_tx_db']:.1f}", "dB"],
        ["Ganancia antena RX", f"{p['g_rx_dbi']:.1f}", "dBi"],
        ["Perdida cables RX", f"{p['l_rx_db']:.1f}", "dB"],
        ["Figura de ruido RX", f"{p['nf_rx_db']:.1f}", "dB"],
        ["Temperatura de antena", f"{p['t_ant_k']:.1f}", "K"],
        ["Temperatura de sistema", f"{r[0]['t_sys_k']:.1f}", "K"],
        ["Perdida atmosferica", f"{p['l_atm_db']:.1f}", "dB"],
        ["Perdida por polarizacion", f"{p['l_pol_db']:.1f}", "dB"],
        ["Perdida por apuntamiento", f"{p['l_point_db']:.1f}", "dB"],
        ["Perdida de implementacion", f"{p['l_impl_db']:.1f}", "dB"],
        ["Eb/N0 requerida", f"{p['eb_n0_req_db']:.1f}", "dB"],
        ["BER objetivo", f"{p['ber_target']:.0e}", "-"],
    ]
    return tabla_md(["Parametro", "Valor", "Unidad"], filas)


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
         f"{c['frecuencia_mhz']:.3f}", c["modulacion"], str(c["tasa_bps"])]
        for c in datos
    ]
    return tabla_md(
        ["CubeSat", "Pais", "Ano", "Formato", "Frecuencia (MHz)", "Modulacion", "Tasa (bps)"],
        filas,
    )


def tabla_concordancia() -> str:
    datos = leer_json("comparacion_parametros_cubesats_reales.json")["metricas"]
    filas = [
        [m["parametro"],
         m["simulado"].replace("\n", "<br>"),
         m["real_referencia"].split("\n")[0],
         m["concordancia"].split(".")[0]]
        for m in datos
    ]
    return tabla_md(["Parametro", "Valor simulado", "Referencia real", "Concordancia"],
                    filas, alineacion="l")


TABLAS = {
    "ber_basico": tabla_ber_basico,
    "ancho_banda_basico": tabla_ancho_banda_basico,
    "avanzado_principal": tabla_avanzado_principal,
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
            print(f"  aviso: no se encontro el marcador TABLA:{nombre} en {INFORME}")
            continue
        texto = patron.sub(lambda m: m.group(1) + generador() + m.group(2), texto)
        sustituidas += 1

    INFORME.write_text(texto, encoding="utf-8")
    return sustituidas


def main() -> None:
    faltan = [n for n in ("resultados_ber_fsk_bpsk.csv", "resultados_simulacion_avanzada.csv",
                          "link_budget_resultados.csv", "link_budget_completo.json",
                          "enlace_ascendente_resultados.json",
                          "estacion_terrena_seguimiento.json",
                          "cubesats_reales_referencia.json",
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
