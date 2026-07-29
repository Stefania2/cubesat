#!/usr/bin/env python3
"""Series temporales por canal de telemetria: cuando dejo de medir cada uno.

El problema que resuelve
------------------------
En las balizas de 2022-2023 todas las magnitudes del subsistema de energia
salen constantes. La causa no es que el satelite midiera siempre lo mismo, sino
que la **cuenta ADC esta clavada en 0** y la recta de calibracion de AMSAT-UK
convierte ese 0 en un valor fijo. Como las rectas son decrecientes, ese valor
fijo no es cero: para las baterias es 9,75 V, que es exactamente la ordenada al
origen (`c = 9,7488`). Un canal muerto se disfraza asi de bateria sana.

Con solo esa ventana no se puede distinguir «el satelite nunca instrumento el
canal» de «lo instrumento y dejo de hacerlo». Con el historico de SatNOGS DB si:
entre 2016 y 2020 esos mismos canales entregan cuentas que cambian de una
baliza a otra. Este script recorre todo el material disponible, agrupa por mes y
por canal, y fecha la transicion.

Lo que decide es la dispersion sobre una muestra, nunca una trama suelta: una
cuenta aislada de 1023 es el tope de escala de un convertidor de 10 bits, y por
si sola no distingue un canal sano de uno enrielado —`adc7_mx_array_current`
esta clavado justo en 1023 desde 2016—. De ahi el umbral `--min-lecturas`.

Criterio
--------
Se clasifica cada mes de cada canal por la **dispersion del dato crudo**, antes
de calibrar, que es lo unico que no depende de interpretar la escala:

  viva        el dato toma mas de un valor distinto en el mes
  clavada     toma siempre el mismo valor  (se anota cual)
  clavada_0   toma siempre el valor 0, el caso caracteristico de ADC sin lectura

Un canal cuya cuenta no varia en un mes entero no esta midiendo: la orbita, la
iluminacion y la temperatura si varian en ese plazo.

Uso
---
    python analizar_series_canales.py telemetria_db_historico.csv \
        telemetria_satnogs.csv --salida series_canales.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services import strand_amsat as sa  # noqa: E402

# Nombres que las distintas exportaciones dan a las mismas dos columnas.
COL_HEX = ("frame", "telemetry_hex", "hex", "raw_hex")
COL_TS = ("timestamp", "fecha", "time")


def columnas(cabecera: list[str]) -> tuple[str, str]:
    hexa = next((c for c in COL_HEX if c in cabecera), "")
    ts = next((c for c in COL_TS if c in cabecera), "")
    if not hexa or not ts:
        raise SystemExit(f"CSV sin columna de trama o de fecha: {cabecera}")
    return ts, hexa


def leer(rutas: list[Path]) -> list[tuple[str, str]]:
    """Devuelve `(timestamp, hex)` de todos los CSV, sin repetir tramas."""
    vistos: set[tuple[str, str]] = set()
    filas: list[tuple[str, str]] = []
    for ruta in rutas:
        if not ruta.exists():
            print(f"  aviso: {ruta} no existe, se omite")
            continue
        n = 0
        with ruta.open(newline="", encoding="utf-8", errors="replace") as fh:
            lector = csv.DictReader(fh)
            col_ts, col_hex = columnas(lector.fieldnames or [])
            for fila in lector:
                hexa = (fila.get(col_hex) or "").strip().upper().replace(" ", "")
                ts = (fila.get(col_ts) or "").strip()
                if not hexa or not ts or len(ts) < 7:
                    continue
                clave = (hexa, ts)
                if clave in vistos:
                    continue
                vistos.add(clave)
                filas.append((ts, hexa))
                n += 1
        print(f"  {ruta.name}: {n} tramas nuevas")
    return filas


def nombre_canal(baliza: sa.Baliza) -> str:
    """Nombre legible del canal, aunque la hoja de AMSAT no lo documente."""
    tabla = sa.NODOS.get(baliza.nodo, ("", None))[1]
    if baliza.nodo == 0x66:
        entrada = sa.INTERRUPTORES.get(baliza.canal)
        return entrada[0] if entrada else f"switch_0x{baliza.canal:02X}"
    if tabla and baliza.canal in tabla:
        spec = tabla[baliza.canal]
        return spec.componentes[0] if spec.componentes else spec.nombre
    return f"{baliza.nodo_nombre}_canal_0x{baliza.canal:02X}"


# Nodos cuyos canales son convertidores analogico-digitales de 10 bits: las
# rectas de calibracion de AMSAT-UK solo estan definidas para cuentas 0-1023.
NODOS_ADC = (0x2C, 0x2D)
ADC_MAX = 1023


def analizar(filas: list[tuple[str, str]]) -> tuple[dict, dict]:
    """Agrupa por (canal, mes) el dato crudo y el valor calibrado."""
    crudos: dict[tuple[str, str], list[int]] = defaultdict(list)
    fisicos: dict[tuple[str, str], list[float]] = defaultdict(list)
    unidades: dict[str, str] = {}
    no_balizas = 0
    fuera_de_rango = 0

    for ts, hexa in filas:
        try:
            trama = bytes.fromhex(hexa)
        except ValueError:
            continue
        baliza = sa.decodificar(trama)
        if baliza is None:
            no_balizas += 1
            continue

        canal = nombre_canal(baliza)
        mes = ts[:7]

        # Una cuenta por encima de 1023 no puede salir de un ADC de 10 bits, y
        # la recta de calibracion aplicada a ella da disparates (-19 V de
        # bateria). Se descarta la lectura entera en vez de arreglarla: los
        # bytes altos de estas tramas parecen llevar informacion de estado
        # —los 10 bits bajos si caen en rango—, pero la hoja de AMSAT-UK no
        # documenta ese empaquetado y enmascararlos seria inventarlo.
        if baliza.nodo in NODOS_ADC and int.from_bytes(baliza.datos, "little") > ADC_MAX:
            fuera_de_rango += 1
            continue
        # El dato crudo del canal: los bytes del cuerpo como entero. Es lo que
        # el ADC entrego, sin calibrar y sin depender del mapeo de la hoja.
        crudos[(canal, mes)].append(int.from_bytes(baliza.datos, "little"))

        for nombre, valor in baliza.valores.items():
            if nombre.endswith("_adc") or isinstance(valor, str):
                continue
            fisicos[(nombre, mes)].append(float(valor))
            if baliza.unidades.get(nombre):
                unidades[nombre] = baliza.unidades[nombre]

    print(f"  tramas que no son balizas: {no_balizas}")
    print(f"  lecturas ADC descartadas por cuenta > {ADC_MAX}: {fuera_de_rango}")
    return {"crudos": crudos, "fisicos": fisicos, "unidades": unidades}, {}


def estado(valores: list[int], min_lecturas: int = 5) -> str:
    """Clasifica un mes de un canal por la dispersion de su dato crudo.

    Una sola lectura no varia por definicion, asi que llamarla «clavada» seria
    un artefacto del muestreo, no un hallazgo. Por debajo de `min_lecturas` el
    mes se declara insuficiente y no cuenta ni a favor ni en contra.
    """
    distintos = set(valores)
    if len(distintos) > 1:
        return "viva"
    if len(valores) < min_lecturas:
        return "insuficiente"
    unico = next(iter(distintos))
    return "clavada_0" if unico == 0 else f"clavada_{unico}"


def informe(datos: dict, salida: Path, min_lecturas: int = 5) -> None:
    crudos = datos["crudos"]
    fisicos = datos["fisicos"]
    unidades = datos["unidades"]

    canales = sorted({c for c, _ in crudos})
    meses = sorted({m for _, m in crudos})
    print(f"\n{len(canales)} canales · {len(meses)} meses con datos "
          f"({meses[0]} a {meses[-1]})" if meses else "\nsin datos")

    with salida.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["canal", "mes", "lecturas", "valores_distintos",
                    "crudo_min", "crudo_max", "estado", "unidad"])
        for canal in canales:
            for mes in meses:
                v = crudos.get((canal, mes))
                if not v:
                    continue
                w.writerow([canal, mes, len(v), len(set(v)), min(v), max(v),
                            estado(v, min_lecturas), unidades.get(canal, "")])

    print(f"\nTabla mensual escrita en {salida}")

    print("\n=== Cuando dejo de medir cada canal ===")
    print("(entre parentesis, las lecturas de ese canal en ese mes)")
    print(f"{'canal':<34} {'meses':>5} {'ultimo mes vivo':>21} "
          f"{'primer mes clavado':>23}  valor")
    for canal in canales:
        por_mes = [(m, crudos[(canal, m)]) for m in meses if (canal, m) in crudos]
        clasificado = [(m, v, estado(v, min_lecturas)) for m, v in por_mes]
        vivos = [(m, v) for m, v, e in clasificado if e == "viva"]
        clavados = [(m, v, e) for m, v, e in clasificado if e.startswith("clavada")]

        # El cese es el primer mes clavado posterior al ultimo mes vivo: antes
        # de esa fecha el canal aun media, despues ya no vuelve a hacerlo.
        cese = valor_cese = ""
        n_cese = 0
        candidatos = [c for c in clavados if not vivos or c[0] > vivos[-1][0]]
        if candidatos:
            cese, v_cese, e_cese = candidatos[0]
            n_cese = len(v_cese)
            valor_cese = e_cese.replace("clavada_", "")

        ultimo = f"{vivos[-1][0]} ({len(vivos[-1][1])})" if vivos else "—"
        primero = f"{cese} ({n_cese})" if cese else "—"
        print(f"{canal:<34} {len(por_mes):>5} {ultimo:>21} {primero:>23}  "
              f"{valor_cese or '—'}")

    insuficientes = sum(1 for c in canales for m in meses
                        if (c, m) in crudos
                        and estado(crudos[(c, m)], min_lecturas) == "insuficiente")
    if insuficientes:
        print(f"\n{insuficientes} pares canal-mes con menos de {min_lecturas} "
              f"lecturas: no se clasifican, la muestra no da para afirmar nada.")

    # Serie mensual de las magnitudes ya calibradas. Es la tabla que va al
    # informe: mientras el canal mide, el rango es ancho; cuando deja de medir,
    # colapsa al valor unico que produce la recta con la cuenta clavada.
    salida_fisica = salida.with_name(salida.stem + "_magnitudes.csv")
    with salida_fisica.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["magnitud", "mes", "lecturas", "minimo", "media", "maximo",
                    "valores_distintos", "unidad"])
        for nombre in sorted({n for n, _ in fisicos}):
            for mes in meses:
                v = fisicos.get((nombre, mes))
                if not v:
                    continue
                w.writerow([nombre, mes, len(v), f"{min(v):.4f}",
                            f"{sum(v) / len(v):.4f}", f"{max(v):.4f}",
                            len({round(x, 6) for x in v}), unidades.get(nombre, "")])
    print(f"Serie mensual de magnitudes escrita en {salida_fisica}")

    print("\n=== Voltaje de bateria, mes a mes ===")
    print(f"{'mes':<9} {'lecturas':>8} {'minimo':>9} {'media':>9} {'maximo':>9} "
          f"{'distintos':>10}")
    for nombre in ("battery_0_voltage", "battery_1_voltage"):
        serie = [(m, fisicos[(nombre, m)]) for m in meses if (nombre, m) in fisicos]
        if not serie:
            continue
        print(f"\n  {nombre}")
        for mes, v in serie:
            distintos = len({round(x, 6) for x in v})
            marca = "" if distintos > 1 else "   ← sin variacion"
            print(f"  {mes:<9} {len(v):>8} {min(v):>9.2f} {sum(v)/len(v):>9.2f} "
                  f"{max(v):>9.2f} {distintos:>10}{marca}")

    print("\n=== Magnitudes fisicas: rango observado por periodo ===")
    for nombre in sorted({n for n, _ in fisicos}):
        serie = [(m, fisicos[(nombre, m)]) for m in meses if (nombre, m) in fisicos]
        if not serie:
            continue
        u = unidades.get(nombre, "")
        primero, ultimo = serie[0], serie[-1]
        distintos = len({round(x, 6) for _, vs in serie for x in vs})
        print(f"  {nombre:<36} {distintos:>4} valores distintos · "
              f"{primero[0]}: [{min(primero[1]):.2f}, {max(primero[1]):.2f}] → "
              f"{ultimo[0]}: [{min(ultimo[1]):.2f}, {max(ultimo[1]):.2f}] {u}")


def inventario(filas: list[tuple[str, str]]) -> None:
    """Que canales de la especificacion emite el satelite y cuales no.

    La hoja de AMSAT-UK define muchos mas canales de los que la baliza usa. Que
    un canal no aparezca nunca no es un fallo de decodificacion: es que el
    satelite no lo transmite, y conviene distinguirlo de un canal que si emite
    pero con la cuenta clavada.
    """
    presentes: dict[tuple[int, int], int] = defaultdict(int)
    for ts, hexa in filas:
        try:
            baliza = sa.decodificar(bytes.fromhex(hexa))
        except ValueError:
            continue
        if baliza is not None:
            presentes[(baliza.nodo, baliza.canal)] += 1

    tablas = [(0x2C, "EPS", sa.EPS), (0x2D, "Paneles solares", sa.BATERIA),
              (0x80, "OBC", sa.OBC), (0x89, "Magnetometros", sa.MAGNETOMETROS)]

    print("\n=== Canales de la especificacion AMSAT-UK: emitidos y no emitidos ===")
    emitidos = ausentes = 0
    for nodo, etiqueta, tabla in tablas:
        print(f"\n  nodo 0x{nodo:02X} · {etiqueta}")
        for canal, spec in sorted(tabla.items()):
            n = presentes.get((nodo, canal), 0)
            emitidos += n > 0
            ausentes += n == 0
            print(f"    0x{canal:02X} {spec.nombre:<38} "
                  f"{n if n else 'no emitido':>12}")
    print("\n  nodo 0x66 · Interruptores")
    for canal, entrada in sorted(sa.INTERRUPTORES.items()):
        n = presentes.get((0x66, canal), 0)
        emitidos += n > 0
        ausentes += n == 0
        print(f"    0x{canal:02X} {entrada[0]:<38} {n if n else 'no emitido':>12}")

    documentados = {(0x2C, c) for c in sa.EPS} | {(0x2D, c) for c in sa.BATERIA} \
        | {(0x80, c) for c in sa.OBC} | {(0x89, c) for c in sa.MAGNETOMETROS} \
        | {(0x66, c) for c in sa.INTERRUPTORES}
    otros = {k: v for k, v in presentes.items() if k not in documentados}
    if otros:
        print("\n  canales emitidos que la hoja no documenta")
        for (nodo, canal), n in sorted(otros.items(), key=lambda x: -x[1]):
            print(f"    nodo 0x{nodo:02X} canal 0x{canal:02X} {'':<26} {n:>12}")

    print(f"\n  resumen: {emitidos} canales emitidos, {ausentes} definidos "
          f"por la especificacion que el satelite nunca transmite")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="+", type=Path, help="CSV con tramas hexadecimales")
    p.add_argument("--salida", type=Path, default=Path("series_canales.csv"))
    p.add_argument("--min-lecturas", type=int, default=5,
                   help="lecturas minimas para clasificar un mes (por defecto 5)")
    args = p.parse_args(argv)

    print("Leyendo tramas:")
    filas = leer(args.csv)
    print(f"  total: {len(filas)} tramas unicas")
    print("\nDecodificando:")
    datos, _ = analizar(filas)
    inventario(filas)
    informe(datos, args.salida, args.min_lecturas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
