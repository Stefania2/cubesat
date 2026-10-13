#!/usr/bin/env python3
"""Analisis observacional de la recepcion: metadatos, coincidencias y diversidad.

Responde, sobre la base canonica, a tres preguntas que la simulacion no puede:

  1. ¿Que metadatos de recepcion existen realmente por trama y por observacion?
  2. ¿Las tramas «duplicadas» son la misma emision oida por varias estaciones,
     o emisiones distintas con el mismo contenido?
  3. ¿Cuanto añade combinar estaciones?

Tambien estima la perdida de paquetes con el numero de secuencia de la baliza,
y delimita lo que esa cifra significa: solo cuenta los paquetes que faltan
ENTRE dos recibidos de una misma rafaga. No ve los que se perdieron antes del
primero o despues del ultimo, ni los pasos sin ninguna recepcion, de modo que
no es la FER del paso. Tampoco hay SNR ni RSSI por trama.

Solo lee. Por defecto usa la base LOCAL; para otra, pasar --dsn de forma
explicita (no toma la cadena del .env, que apunta a produccion).

    ../../strand_api/bin/python tools/analizar_recepcion.py
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

DSN_LOCAL = "postgresql://strand:strand@localhost:5432/strand1"
SALIDA = Path(__file__).resolve().parents[2] / "resultados_simulacion" / "analisis_recepcion_telemetria.json"

# Dos recepciones son «la misma emision» si coinciden contenido e instante.
# La marca de tiempo de SatNOGS tiene resolucion de 1 s y la pone el reloj de
# cada estacion, de ahi la tolerancia. El contenido solo no basta: STRaND-1
# repite balizas identicas (el reloj del OBC se reinicia y vuelve a emitir los
# mismos bytes), de modo que igualdad de bytes no implica misma emision.
TOLERANCIA_S = 2
HUECO_PASO = timedelta(minutes=10)
PAR = ("M0KSF", "M0KSF-BB")


def cargar(conn) -> tuple[list[tuple], dict]:
    with conn.cursor() as cur:
        cur.execute("""
            select id, coalesce(observer, ''), timestamp, raw_hex, frame_type, observation_id
            from frames order by timestamp, id""")
        frames = cur.fetchall()
        cur.execute("""
            select count(*), count(observer), count(station_id), count(observation_id),
                   count(distinct raw_hex), min(timestamp), max(timestamp) from frames""")
        t = cur.fetchone()
        cur.execute("""
            select source, coalesce(status, '(sin estado)'), count(*), count(max_elevation_deg),
                   count(frequency_hz), count(mode)
            from observations group by 1, 2 order by 1, 2""")
        obs = cur.fetchall()
    inventario = {
        "frames": t[0],
        "frames_con_observador": t[1],
        "frames_con_station_id": t[2],
        "frames_con_observation_id": t[3],
        "contenidos_distintos": t[4],
        "primer_frame_utc": t[5].astimezone(timezone.utc).isoformat(),
        "ultimo_frame_utc": t[6].astimezone(timezone.utc).isoformat(),
        "observaciones_por_fuente_y_estado": [
            {"fuente": o[0], "estado": o[1], "observaciones": o[2],
             "con_elevacion_maxima": o[3], "con_frecuencia": o[4], "con_modo": o[5]}
            for o in obs],
        "metadatos_disponibles": {
            "por_trama": ["contenido (hex)", "instante (resolucion 1 s)", "observador",
                          "station_id (parcial)", "observation_id (parcial)"],
            "por_observacion_network": ["estado (good/bad/unknown, asignado en SatNOGS)",
                                        "elevacion maxima del paso", "inicio y fin",
                                        "frecuencia y modo del transmisor"],
            "no_disponibles": ["SNR o RSSI por trama", "elevacion en el instante de la trama",
                               "numero de tramas emitidas por el satelite",
                               "resultado del demodulador en las tramas no entregadas"],
        },
    }
    return frames, inventario


def emisiones(balizas: list[tuple]) -> list[dict]:
    """Agrupa recepciones en emisiones: mismo contenido, instantes a ±TOLERANCIA_S.

    Las recepciones de una misma estacion nunca se funden entre si: si una
    estacion entrega dos veces el mismo contenido son dos emisiones (o un
    duplicado de ingesta, que se cuenta aparte).
    """
    por_hex: dict[str, list[tuple]] = defaultdict(list)
    for f in balizas:
        por_hex[f[3]].append(f)
    grupos = []
    for hexa, lista in por_hex.items():
        lista.sort(key=lambda f: f[2])
        actual: dict | None = None
        for f in lista:
            _, obs, ts, _, _, _ = f
            if (actual is None or (ts - actual["t0"]).total_seconds() > TOLERANCIA_S
                    or obs in actual["estaciones"]):
                actual = {"hex": hexa, "t0": ts, "estaciones": {obs}, "exacta": True}
                grupos.append(actual)
            else:
                if ts != actual["t0"]:
                    actual["exacta"] = False
                actual["estaciones"].add(obs)
    return grupos


def pasos(grupos: list[dict]) -> list[list[dict]]:
    grupos = sorted(grupos, key=lambda g: g["t0"])
    lista, actual = [], [grupos[0]]
    for g in grupos[1:]:
        if g["t0"] - actual[-1]["t0"] > HUECO_PASO:
            lista.append(actual)
            actual = []
        actual.append(g)
    lista.append(actual)
    return lista


def diversidad(grupos: list[dict]) -> dict:
    por_n = Counter(min(len(g["estaciones"]), 4) for g in grupos)
    multi = [g for g in grupos if len(g["estaciones"]) > 1]
    simultaneos = [p for p in pasos(grupos) if len({e for g in p for e in g["estaciones"]}) > 1]
    union = sum(len(p) for p in simultaneos)
    mejor = sum(max(Counter(e for g in p for e in g["estaciones"]).values()) for p in simultaneos)
    return {
        "emisiones_distintas_recibidas": len(grupos),
        "por_numero_de_estaciones": {
            "1": por_n[1], "2": por_n[2], "3": por_n[3], "4_o_mas": por_n[4]},
        "emisiones_multiestacion": len(multi),
        "de_ellas_con_instante_identico": sum(1 for g in multi if g["exacta"]),
        "ventanas_con_varias_estaciones": len(simultaneos),
        "emisiones_en_esas_ventanas": union,
        "emisiones_de_la_mejor_estacion_de_cada_ventana": mejor,
        "ganancia_por_combinacion": round(union / mejor, 3) if mejor else None,
        "nota": "Ganancia = emisiones distintas recuperadas entre todas las estaciones de una "
                "ventana / las recuperadas por la mejor estacion sola. Es un resultado "
                "observacional: no demuestra diversidad fisica del canal, porque las estaciones "
                "difieren en antena, receptor, horario y disponibilidad.",
    }


def par_estaciones(grupos: list[dict], a: str, b: str) -> dict:
    ga = [g for g in grupos if a in g["estaciones"]]
    gb = [g for g in grupos if b in g["estaciones"]]
    if not ga or not gb:
        return {"disponible": False, "motivo": f"sin balizas de {a} o de {b}"}
    # Solo se comparan las ventanas en que ambas estaciones entregaron algo:
    # fuera de ellas una puede sencillamente no estar operando.
    comunes = [p for p in pasos([g for g in grupos if g["estaciones"] & {a, b}])
               if any(a in g["estaciones"] for g in p) and any(b in g["estaciones"] for g in p)]
    solo_a = solo_b = ambas = 0
    for p in comunes:
        for g in p:
            en_a, en_b = a in g["estaciones"], b in g["estaciones"]
            ambas += en_a and en_b
            solo_a += en_a and not en_b
            solo_b += en_b and not en_a
    total = solo_a + solo_b + ambas
    return {
        "disponible": True,
        "estaciones": [a, b],
        "emisiones_totales": {a: len(ga), b: len(gb)},
        "ventanas_comunes": len(comunes),
        "en_ventanas_comunes": {
            f"solo_{a}": solo_a, f"solo_{b}": solo_b, "ambas": ambas, "union": total},
        "fraccion_recibida_por_ambas": round(ambas / total, 3) if total else None,
        "ganancia_union_sobre_la_mejor": round(total / max(solo_a + ambas, solo_b + ambas), 3)
        if total else None,
        "interpretacion": "Una emision recibida por ambas no es una anomalia: es la misma trama "
                          "oida dos veces. Solo cuentan como duplicado de ingesta las filas "
                          "identicas en contenido, instante Y observador, que la clave unica de "
                          "la tabla ya impide.",
    }


def por_observacion(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            select o.status, least(floor(o.max_elevation_deg / 15)::int, 5) tramo,
                   count(*) obs,
                   count(*) filter (where b.n > 0) con_baliza,
                   coalesce(sum(b.n), 0) balizas
            from observations o
            left join (select observation_id, count(*) n from frames
                       where frame_type = 'strand_beacon' group by 1) b
                   on b.observation_id = o.observation_id
            where o.source = 'satnogs-network' and o.max_elevation_deg is not null
            group by 1, 2 order by 1, 2""")
        filas = cur.fetchall()
    tramos = ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90"]
    return {
        "tramos_elevacion_maxima_deg": tramos,
        "filas": [{"estado_satnogs": f[0], "elevacion_maxima_deg": tramos[f[1]],
                   "observaciones": f[2], "observaciones_con_baliza": f[3],
                   "fraccion_con_baliza": round(f[3] / f[2], 3) if f[2] else None,
                   "balizas": int(f[4])} for f in filas],
        "nota": "«Fraccion con baliza» es una tasa de exito de OBSERVACION, no una FER. Una "
                "observacion sin balizas puede deberse al canal, pero tambien a que el satelite "
                "no emitio en ese paso, a la estacion, al detector o al decodificador. La "
                "elevacion es la maxima del paso, no la del instante de cada trama.",
    }


def elevaciones(conn) -> dict[int, float]:
    with conn.cursor() as cur:
        cur.execute("select observation_id, max_elevation_deg from observations "
                    "where max_elevation_deg is not null")
        return {o: e for o, e in cur.fetchall()}


def cadencia(balizas: list[tuple]) -> dict:
    por_obs: dict[int, list[datetime]] = defaultdict(list)
    for f in balizas:
        if f[5] is not None:
            por_obs[f[5]].append(f[2])
    dts = []
    for ts in por_obs.values():
        ts.sort()
        dts += [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    if not dts:
        return {"disponible": False}
    c = Counter(round(d) for d in dts)
    return {
        "disponible": True,
        "intervalos_medidos": len(dts),
        "mediana_s": statistics.median(dts),
        "mas_frecuentes_s": [{"intervalo_s": k, "veces": v} for k, v in c.most_common(8)],
        "conclusion": "La separacion entre balizas consecutivas no tiene un unico valor "
                      "dominante (rafagas de 0-2 s y huecos de ~13-15 s): la cadencia no sirve "
                      "para contar tramas ausentes. Para eso se usa el contador de secuencia.",
    }


SALTO_MAX = 32          # un salto mayor del contador no es una perdida: es otra rafaga
HUECO_RAFAGA_S = 30


def perdida_por_secuencia(balizas: list[tuple], elevaciones: dict[int, float]) -> dict:
    """Paquetes ausentes entre los recibidos, usando el contador de 8 bits.

    Hipotesis: el satelite incrementa el contador en uno por paquete emitido.
    La respaldan las rafagas de 2016-2021, donde llegan dos paquetes por
    segundo con contadores consecutivos. Deja de cumplirse cuando el OBC se
    reinicia en bucle (desde 2022 abundan balizas con el contador clavado en
    1): esos tramos se excluyen en lugar de contarlos.

    Detalle que importa: la marca de tiempo tiene 1 s de resolucion y en ese
    segundo caben dos paquetes, que la base puede devolver en cualquier orden.
    Restar contadores consecutivos tal cual convierte cada par desordenado en
    un «salto de 2» mas un «salto de 255». Aqui el contador se desenrolla con
    signo y se cuentan valores DISTINTOS dentro del tramo, que no depende del
    orden.
    """
    por_estacion: dict[str, list[tuple]] = defaultdict(list)
    for f in balizas:
        if f[1]:
            por_estacion[f[1]].append(f)

    tramos = []          # (emitidos, recibidos, año, observation_id)
    excluidos_reinicio = 0
    for lista in por_estacion.values():
        lista.sort(key=lambda f: (f[2], f[0]))
        actual: list[int] = []
        meta = None

        def cerrar():
            if len(set(actual)) >= 2:
                tramos.append((max(actual) - min(actual) + 1, len(set(actual)), *meta))

        previo_ts = previo_seq = None
        u = 0
        for f in lista:
            seq = int(f[3][4:6], 16)
            ts = f[2]
            if previo_ts is not None:
                delta = (seq - previo_seq + 128) % 256 - 128      # con signo
                gap = (ts - previo_ts).total_seconds()
                reinicio = delta == 0 and gap > TOLERANCIA_S
                if reinicio:
                    excluidos_reinicio += 1
                if gap > HUECO_RAFAGA_S or abs(delta) > SALTO_MAX or reinicio:
                    cerrar()
                    actual, u = [], 0
                else:
                    u += delta
            if not actual:
                meta = (ts.year, f[5])
            actual.append(u)
            previo_ts, previo_seq = ts, seq
        cerrar()

    def resumen(sel: list[tuple]) -> dict:
        emitidos = sum(t[0] for t in sel)
        recibidos = sum(t[1] for t in sel)
        return {"rafagas": len(sel), "paquetes_emitidos_estimados": emitidos,
                "paquetes_recibidos": recibidos,
                "perdida": round(1 - recibidos / emitidos, 4) if emitidos else None}

    limites = [0, 15, 30, 45, 60, 75, 91]
    por_elev = []
    for a, b in zip(limites, limites[1:]):
        sel = [t for t in tramos if t[3] in elevaciones and a <= elevaciones[t[3]] < b]
        por_elev.append({"elevacion_maxima_deg": f"{a}-{min(b, 90)}", **resumen(sel)})
    return {
        "hipotesis": "contador de secuencia de 8 bits incrementado en 1 por paquete emitido",
        "definicion": "perdida = 1 - paquetes distintos recibidos / (contador max - min + 1), "
                      f"por rafaga (misma estacion, huecos <= {HUECO_RAFAGA_S} s, saltos <= "
                      f"{SALTO_MAX})",
        "global": resumen(tramos),
        "por_año": {str(a): resumen([t for t in tramos if t[2] == a])
                    for a in sorted({t[2] for t in tramos})},
        "por_elevacion_maxima_de_la_observacion": por_elev,
        "transiciones_excluidas_por_contador_clavado": excluidos_reinicio,
        "alcance": "Solo mide lo que falta ENTRE paquetes recibidos de una rafaga. No incluye "
                   "lo perdido antes del primero ni despues del ultimo, ni los pasos sin "
                   "recepcion: es una cota inferior de la perdida del paso, no su FER. La "
                   "perdida no es atribuible solo al canal (tambien cuentan estacion, detector "
                   "y decodificador).",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DSN_LOCAL)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    with psycopg.connect(args.dsn, autocommit=True) as conn:
        conn.execute("set default_transaction_read_only = on")
        frames, inventario = cargar(conn)
        balizas = [f for f in frames if f[4] == "strand_beacon"]
        con_estacion = [f for f in balizas if f[1]]
        grupos = emisiones(con_estacion)
        salida = {
            "tipo_de_dato": "derivado de telemetria real (SatNOGS); analisis observacional",
            "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "base": args.dsn.split("@")[-1],
            "criterio_misma_emision": f"mismo contenido e instantes a ±{TOLERANCIA_S} s, "
                                      "de estaciones distintas",
            "inventario": inventario,
            "balizas": {"total": len(balizas), "con_observador": len(con_estacion),
                        "sin_observador_excluidas_del_analisis_por_estacion":
                            len(balizas) - len(con_estacion)},
            "diversidad": diversidad(grupos),
            "par_M0KSF": par_estaciones(grupos, *PAR),
            "exito_por_observacion": por_observacion(conn),
            "cadencia_de_baliza": cadencia(balizas),
            "perdida_por_secuencia": perdida_por_secuencia(balizas, elevaciones(conn)),
            "fer_empirica": {
                "disponible": False,
                "motivo": "No existe denominador para un paso completo: SatNOGS solo registra "
                          "las tramas demoduladas. Lo unico estimable es la perdida entre "
                          "paquetes recibidos de una misma rafaga (perdida_por_secuencia).",
            },
        }
    args.salida.parent.mkdir(exist_ok=True)
    args.salida.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")

    d, p = salida["diversidad"], salida["par_M0KSF"]
    print(f"Balizas: {len(balizas)} ({len(con_estacion)} con observador)")
    print(f"Emisiones distintas: {d['emisiones_distintas_recibidas']} · por nº de estaciones: "
          f"{d['por_numero_de_estaciones']}")
    print(f"Ventanas con varias estaciones: {d['ventanas_con_varias_estaciones']} · "
          f"ganancia por combinacion: {d['ganancia_por_combinacion']}")
    if p.get("disponible"):
        print(f"{PAR[0]} / {PAR[1]}: {p['en_ventanas_comunes']} · ganancia "
              f"{p['ganancia_union_sobre_la_mejor']}")
    for f in salida["exito_por_observacion"]["filas"]:
        print(f"  {f['estado_satnogs']:>8} {f['elevacion_maxima_deg']:>6}°: "
              f"{f['observaciones_con_baliza']}/{f['observaciones']} con baliza "
              f"({f['fraccion_con_baliza']}), {f['balizas']} balizas")
    ps = salida["perdida_por_secuencia"]
    print(f"Perdida por secuencia (global): {ps['global']}")
    for a, v in ps["por_año"].items():
        print(f"  {a}: {v}")
    for v in ps["por_elevacion_maxima_de_la_observacion"]:
        print(f"  elev {v['elevacion_maxima_deg']}: {v}")
    print(f"Salida: {args.salida}")


if __name__ == "__main__":
    main()
