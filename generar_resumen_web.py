#!/usr/bin/env python3
"""Genera el resumen que consume la pagina «Simulacion RF» de la plataforma.

La pagina tenia sus cifras escritas a mano en el componente React y se habian
quedado atras respecto de los resultados (mostraba 8.23 °/s, 2.62° y 0.09 dB
del rotor cuando el JSON decia 0.77° y 0.01 dB). Este script es ahora el unico
camino por el que un numero de `resultados_simulacion/` llega a esa pagina:

    resultados_simulacion/*.json|csv  ->  frontend/src/data/resumen_simulacion.json

El JSON se importa en tiempo de compilacion, asi que funciona igual en local y
en Vercel sin exponer un endpoint nuevo. `tests/test_coherencia_resultados.py`
falla si el archivo publicado no coincide con lo que este script produce a
partir de los resultados actuales.

    python generar_resumen_web.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
RESULTADOS = RAIZ / "resultados_simulacion"
SALIDA = RAIZ / "telemetria_strand1" / "frontend" / "src" / "data" / "resumen_simulacion.json"

SIMULADO = "simulado"
TEORICO = "teorico"
DERIVADO = "derivado de telemetria real"


def _json(nombre: str):
    return json.loads((RESULTADOS / nombre).read_text(encoding="utf-8"))


def _csv(nombre: str) -> list[dict]:
    with (RESULTADOS / nombre).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def construir() -> dict:
    lb = _json("link_budget_completo.json")
    paso = _json("margen_paso_sgp4.json")
    avz = _json("resultados_simulacion_avanzada.json")
    est = _json("estacion_terrena_seguimiento.json")
    up = _json("enlace_ascendente_resultados.json")
    snr = _json("estimacion_snr_iq.json")
    rec = _json("analisis_recepcion_telemetria.json")
    basico = _csv("resultados_ber_fsk_bpsk.csv")

    res = avz["resultados"]

    def fila(esquema: str, canal: str, ebn0: float) -> dict:
        return next(r for r in res if r["esquema"] == esquema and r["canal"] == canal
                    and r["ebn0_db"] == ebn0)

    def ancho(esquema: str) -> float:
        return next(r["ancho_banda_hz"] for r in res if r["esquema"] == esquema)

    vis = [r for r in est if r["elevacion_deg"] >= 5.0]
    documentado = paso["margen"]["fsk_no_coherente"]
    gan = {g["canal"]: g for g in avz["analisis"]["ganancia_codificacion"]}
    gan_fer = {g["canal"]: g for g in avz["analisis"]["ganancia_codificacion_fer"]}
    m_up = [r["margen_db"] for r in up]

    return {
        "procedencia": {
            "generado_por": "generar_resumen_web.py",
            "commit_resultados": avz["metadatos"]["commit"],
            "simulacion_avanzada_utc": avz["metadatos"]["generado_utc"],
            "paso_sgp4_utc": paso["generado_utc"],
            "recepcion_utc": rec["generado_utc"],
            "semilla_base": avz["metadatos"]["semilla_base"],
            "ensayos_por_punto": avz["metadatos"]["ensayos_por_punto"],
            "bits_por_ensayo": avz["metadatos"]["entrada"]["bits"],
        },
        "modulacion": {
            "documentada": "FSK a 9600 bit/s, tramas AX.25 (HDLC), NRZI",
            "fuentes": "AMSAT-UK; SatNOGS DB (transmisor «UHF 9k6 FSK TLM»)",
            "del_modelo": avz["metadatos"]["modulacion_del_modelo"],
            "esquemas": lb["esquemas"],
        },
        "link_budget": {
            "tipo": TEORICO,
            "fuente": "resultados_simulacion/link_budget_completo.json",
            "margen_fsk_min_db": lb["resumen"]["margen_minimo_db"],
            "margen_fsk_max_db": lb["resumen"]["margen_maximo_db"],
            "margen_bpsk_min_db": lb["resumen"]["margen_bpsk_minimo_db"],
            "margen_bpsk_max_db": lb["resumen"]["margen_bpsk_maximo_db"],
            "t_sys_k": lb["resultados"][0]["t_sys_k"],
            "ber_objetivo": lb["parametros"]["ber_target"],
            "parametros": [
                {"clave": k, "valor": v["valor"], "unidad": v["unidad"],
                 "procedencia": v["procedencia"], "fuente": v["fuente"]}
                for k, v in lb["procedencia"].items()] + [
                # Magnitudes derivadas de las anteriores que usa el link budget.
                {"clave": "tasa_simbolo_baud", "valor": lb["parametros"]["symbol_rate_bps"],
                 "unidad": "baud", "procedencia": "deducido",
                 "fuente": "tasa de bits con modulación binaria (1 bit por símbolo)"},
                {"clave": "t_sys_k", "valor": lb["resultados"][0]["t_sys_k"],
                 "unidad": "K", "procedencia": "deducido",
                 "fuente": "temperatura de antena, pérdida del cable y figura de ruido del receptor, "
                           "referidas a la entrada del receptor"},
                {"clave": "eb_n0_requerida_db", "valor": lb["resultados"][0]["eb_n0_requerida_db"],
                 "unidad": "dB", "procedencia": "deducido",
                 "fuente": f"curva teórica de FSK no coherente a BER {lb['parametros']['ber_target']:.0e} "
                           f"({lb['esquemas']['fsk_no_coherente']['eb_n0_teorica_db']} dB) + reserva de implementación "
                           f"({lb['parametros']['l_impl_db']} dB); "
                           f"modelo comparativo BPSK: {lb['resultados'][0]['eb_n0_requerida_bpsk_db']} dB"},
            ],
        },
        "paso_sgp4": {
            "tipo": SIMULADO,
            "fuente": "resultados_simulacion/margen_paso_sgp4.json",
            "tle_epoca_utc": paso["tle"]["epoca_utc"],
            "antiguedad_tle_h": paso["antiguedad_tle_en_el_paso_h"],
            "inicio_utc": paso["paso_analizado"]["inicio_utc"],
            "elev_max_deg": paso["paso_analizado"]["elev_max_deg"],
            "estacion": paso["estacion"]["nota"],
            "margen_fsk": {k: documentado[k] for k in (
                "margen_min_db", "margen_medio_db", "margen_max_db", "percentiles_db",
                "porcentaje_tiempo_margen_positivo", "duracion_total_margen_positivo_s")},
            "umbrales": paso["umbrales"],
            "margen_min_por_umbral_db": {k: v["margen_min_db"] for k, v in paso["margen"].items()},
            "doppler_min_hz": paso["doppler"]["doppler_min_hz"],
            "doppler_max_hz": paso["doppler"]["doppler_max_hz"],
            "tasa_doppler_max_hz_s": paso["doppler"]["tasa_doppler_max_abs_hz_s"],
            "residual": paso["doppler"]["residual_tras_precompensacion"],
            "montecarlo": paso["sensibilidad"]["montecarlo"],
            "sensibilidad": paso["sensibilidad"]["uno_a_la_vez"],
        },
        "modelo_avanzado": {
            "tipo": SIMULADO,
            "fuente": "resultados_simulacion/resultados_simulacion_avanzada.json",
            "rrc_rolloff": avz["metadatos"]["rrc"]["rolloff"],
            "ancho_banda_nrz_hz": ancho("nrz"),
            "ancho_banda_rrc_hz": ancho("rrc"),
            "reduccion_ancho_banda": round(ancho("nrz") / ancho("rrc"), 1),
            "ganancia_codificacion_ber": gan["awgn"],
            "ganancia_codificacion_fer": gan_fer["awgn"],
            "ganancia_codificacion_rice": gan["rice"],
            "umbrales": avz["analisis"]["umbrales"],
            "configuraciones": len({(r["esquema"], r["canal"]) for r in res}),
            "puntos_ebn0": len(avz["metadatos"]["ebn0_db"]),
            "canal_rice": avz["metadatos"]["canal_rice"],
            "curvas": [
                {k: r[k] for k in (
                    "esquema", "esquema_nombre", "canal", "canal_nombre", "ebn0_db", "ber",
                    "ber_ic95_inf", "ber_ic95_sup", "ber_diferencial", "ber_teorica_bpsk",
                    "per", "fer", "ax25_frames_validos", "ax25_frames_tx", "bits_evaluados",
                    "errores_bit")}
                for r in res],
            "limitaciones": avz["metadatos"]["limitaciones"],
            "definiciones": avz["metadatos"]["definiciones"],
        },
        "modelo_basico": {
            "tipo": SIMULADO,
            "fuente": "resultados_simulacion/resultados_ber_fsk_bpsk.csv",
            "nota": "SNR por muestra; Eb/N0 = SNR + 9.03 dB. Una realizacion por punto.",
            "filas": [{"modulacion": r["modulacion"], "snr_db": float(r["snr_db"]),
                       "ebn0_db": float(r["ebn0_db"]), "ber": float(r["ber"]),
                       "errores": int(r["errores_bit"]), "bits": int(r["bits_evaluados"])}
                      for r in basico],
        },
        "estacion_terrena": {
            "tipo": SIMULADO,
            "fuente": "resultados_simulacion/estacion_terrena_seguimiento.json",
            "elev_culminacion_deg": max(r["elevacion_deg"] for r in est),
            "error_apuntamiento_max_deg": max(r["error_apuntamiento_deg"] for r in vis),
            "perdida_apuntamiento_max_db": max(r["pointing_loss_db"] for r in vis),
            "c_n0_min_db_hz": min(r["c_n0_db_hz"] for r in vis),
            "c_n0_max_db_hz": max(r["c_n0_db_hz"] for r in vis),
        },
        "uplink": {
            "tipo": TEORICO,
            "fuente": "resultados_simulacion/enlace_ascendente_resultados.json",
            "margen_min_db": min(m_up), "margen_max_db": max(m_up),
            "nota": "escenario hipotetico (10 W, 435 MHz, 1200 bit/s); el enlace ascendente "
                    "real de STRaND-1 no esta caracterizado en el proyecto",
        },
        "estimador_snr": {
            "tipo": SIMULADO,
            "fuente": "resultados_simulacion/estimacion_snr_iq.json",
            "metodo": snr["metodo"],
            "filas": [f for f in snr["resultados"]
                      if f["ventana_simbolos"] == 1024 and f["reloj"] == "gardner"],
        },
        "recepcion": {
            "tipo": DERIVADO,
            "fuente": "resultados_simulacion/analisis_recepcion_telemetria.json",
            "balizas": rec["balizas"]["total"],
            "diversidad": rec["diversidad"],
            "par_M0KSF": rec["par_M0KSF"],
            "exito_por_observacion": rec["exito_por_observacion"],
            "perdida_por_secuencia": rec["perdida_por_secuencia"],
            "fer_empirica": rec["fer_empirica"],
        },
    }


INDEX_HTML = RAIZ / "index.html"
PATRON_DATO = re.compile(r'(<span data-dato="([a-z0-9_]+)">)(.*?)(</span>)', re.DOTALL)


def datos_pagina_estatica(r: dict) -> dict[str, str]:
    """Cifras que `index.html` muestra en sus `<span data-dato="...">`."""
    lb, paso, avz = r["link_budget"], r["paso_sgp4"], r["modelo_avanzado"]
    est, up = r["estacion_terrena"], r["uplink"]
    res05 = next(x for x in paso["residual"] if x["error_tiempo_s"] == 0.5)

    def na(v, fmt):
        return "N/A" if v is None else format(v, fmt)

    return {
        "margen_fsk_rango": f"{lb['margen_fsk_min_db']:.1f}–{lb['margen_fsk_max_db']:.1f} dB",
        "margen_bpsk_rango": f"{lb['margen_bpsk_min_db']:.1f}–{lb['margen_bpsk_max_db']:.1f} dB",
        "paso_margen_min": f"{paso['margen_fsk']['margen_min_db']:.1f}",
        "paso_margen_max": f"{paso['margen_fsk']['margen_max_db']:.1f}",
        "doppler_max_khz": f"{paso['doppler_max_hz'] / 1000:+.1f}",
        "doppler_min_khz": f"{paso['doppler_min_hz'] / 1000:+.1f}",
        "tasa_doppler": f"{paso['tasa_doppler_max_hz_s']:.0f}",
        "residual_05s": f"{res05['residual_max_abs_hz']:.0f}",
        "bw_nrz_khz": f"{avz['ancho_banda_nrz_hz'] / 1000:.1f}",
        "bw_rrc_khz": f"{avz['ancho_banda_rrc_hz'] / 1000:.1f}",
        "ganancia_ber": na(avz["ganancia_codificacion_ber"]["ganancia_db"], ".1f"),
        "ganancia_fer": na(avz["ganancia_codificacion_fer"]["ganancia_db"], ".1f"),
        "configuraciones": str(avz["configuraciones"]),
        "puntos_ebn0": str(avz["puntos_ebn0"]),
        "ensayos": str(r["procedencia"]["ensayos_por_punto"]),
        "est_culminacion": f"{est['elev_culminacion_deg']:.0f}",
        "est_cn0_min": f"{est['c_n0_min_db_hz']:.1f}",
        "est_cn0_max": f"{est['c_n0_max_db_hz']:.1f}",
        "est_error_max": f"{est['error_apuntamiento_max_deg']:.2f}",
        "est_perdida_max": f"{est['perdida_apuntamiento_max_db']:.2f}",
        "uplink_min": f"{up['margen_min_db']:.1f}",
        "uplink_max": f"{up['margen_max_db']:.1f}",
    }


def rellenar_index(html: str, datos: dict[str, str]) -> str:
    def sustituir(m: re.Match) -> str:
        clave = m.group(2)
        if clave not in datos:
            raise SystemExit(f"index.html pide el dato «{clave}», que el resumen no define")
        return m.group(1) + datos[clave] + m.group(4)
    return PATRON_DATO.sub(sustituir, html)


README = RAIZ / "README.md"
PATRON_README = re.compile(r"(<!-- RESULTADOS -->\n).*?(<!-- /RESULTADOS -->)", re.DOTALL)


def bloque_readme(r: dict) -> str:
    lb, paso, avz, est = r["link_budget"], r["paso_sgp4"], r["modelo_avanzado"], r["estacion_terrena"]
    rec, up, pr = r["recepcion"], r["uplink"], r["procedencia"]
    gb, gf = avz["ganancia_codificacion_ber"], avz["ganancia_codificacion_fer"]
    mc = paso["montecarlo"]

    def db(v):
        return "N/A" if v is None else f"{v:.1f} dB"

    def t(v, cota=None):
        if v is None:
            return "N/A"
        if v == 0:
            return f"0 (< {cota:.1e})" if cota else "0"
        return f"{v:.1e}"

    def curva(esquema, canal):
        return [c for c in avz["curvas"] if c["esquema"] == esquema and c["canal"] == canal]

    rrc, fec, ax, axf = (curva(e, "awgn") for e in ("rrc", "rrc_fec", "ax25", "ax25_fec"))
    filas = "\n".join(
        f"| {a['ebn0_db']:.1f} | {a['ber_teorica_bpsk']:.1e} | {t(a['ber'], a['ber_ic95_sup'])} | "
        f"{t(b['ber'], b['ber_ic95_sup'])} | {t(c['fer'])} ({c['ax25_frames_validos']}/{c['ax25_frames_tx']}) | "
        f"{t(d['fer'])} |"
        for a, b, c, d in zip(rrc, fec, ax, axf))
    perdida = rec["perdida_por_secuencia"]["global"]
    return f"""Corrida del modelo avanzado: {pr['simulacion_avanzada_utc']} · codigo `{pr['commit_resultados']}` · semilla {pr['semilla_base']} · {pr['ensayos_por_punto']} ensayos de {pr['bits_por_ensayo']} bits por punto.

| Resultado | Valor | Tipo |
| --- | --- | --- |
| Margen descendente por elevacion (5°–90°), FSK no coherente | {lb['margen_fsk_min_db']:.1f} – {lb['margen_fsk_max_db']:.1f} dB | teorico |
| Idem con BPSK coherente (modelo comparativo) | {lb['margen_bpsk_min_db']:.1f} – {lb['margen_bpsk_max_db']:.1f} dB | teorico |
| Margen FSK en un paso SGP4 (culminacion {paso['elev_max_deg']:.0f}°) | {paso['margen_fsk']['margen_min_db']:.1f} – {paso['margen_fsk']['margen_max_db']:.1f} dB, {paso['margen_fsk']['porcentaje_tiempo_margen_positivo']:.0f} % del tiempo positivo | simulado |
| Margen minimo del paso con los supuestos variados (Monte Carlo, p5–p95) | {mc['margen_min_db']['p5']:.1f} – {mc['margen_min_db']['p95']:.1f} dB; positivo en el {100 * mc['probabilidad_margen_min_positivo']:.0f} % | simulado |
| Doppler en el paso | {paso['doppler_min_hz'] / 1000:.1f} a {paso['doppler_max_hz'] / 1000:+.1f} kHz, hasta {paso['tasa_doppler_max_hz_s']:.0f} Hz/s | simulado |
| Ancho de banda ocupado al 99 %, NRZ → RRC | {avz['ancho_banda_nrz_hz'] / 1000:.1f} → {avz['ancho_banda_rrc_hz'] / 1000:.1f} kHz | simulado |
| Ganancia de codificacion a BER {gb['ber_objetivo']:g} (AWGN) | {db(gb['ganancia_db'])} (resolucion {gb['resolucion_db']} dB) | simulado |
| Ganancia de codificacion a FER {gf['fer_objetivo']:g} de tramas AX.25 (AWGN) | {db(gf['ganancia_db'])} | simulado |
| Ganancia de codificacion con desvanecimiento Rice | {avz['ganancia_codificacion_rice']['estado']} | simulado |
| Error maximo de apuntamiento del rotor / perdida | {est['error_apuntamiento_max_deg']:.2f}° / {est['perdida_apuntamiento_max_db']:.2f} dB | simulado |
| Margen ascendente (escenario hipotetico) | {up['margen_min_db']:.1f} – {up['margen_max_db']:.1f} dB | teorico |
| Emisiones recibidas por dos o mas estaciones | {rec['diversidad']['emisiones_multiestacion']} de {rec['diversidad']['emisiones_distintas_recibidas']} | derivado de telemetria real |
| Ganancia por combinar estaciones en ventanas simultaneas | ×{rec['diversidad']['ganancia_por_combinacion']:.2f} | derivado de telemetria real |
| Perdida de paquetes dentro de rafagas (contador de secuencia) | {100 * perdida['perdida']:.1f} % ({perdida['paquetes_recibidos']} de {perdida['paquetes_emitidos_estimados']}) | derivado, bajo hipotesis |
| FER empirica del enlace real | no disponible: falta el denominador | — |

BER y FER del modelo avanzado en AWGN (Eb/N0 por bit de informacion; receptor Costas + Gardner). «0 (< x)»: cero errores observados, con x como cota superior al 95 %.

| Eb/N0 (dB) | BER teorica BPSK | BER sin codigo | BER con FEC | FER AX.25 (validas/tx) | FER AX.25 + FEC |
| ---: | ---: | ---: | ---: | ---: | ---: |
{filas}
"""


def rellenar_readme(texto: str, resumen: dict) -> str:
    if not PATRON_README.search(texto):
        raise SystemExit("README.md no tiene el bloque <!-- RESULTADOS -->")
    return PATRON_README.sub(lambda m: m.group(1) + bloque_readme(resumen) + m.group(2), texto)


def main() -> None:
    resumen = construir()
    README.write_text(rellenar_readme(README.read_text(encoding="utf-8"), resumen), encoding="utf-8")
    INDEX_HTML.write_text(
        rellenar_index(INDEX_HTML.read_text(encoding="utf-8"), datos_pagina_estatica(resumen)),
        encoding="utf-8")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(resumen, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Resumen escrito en {SALIDA.relative_to(RAIZ)} ({SALIDA.stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
