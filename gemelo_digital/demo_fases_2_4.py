#!/usr/bin/env python3
"""Demostracion encadenada de las fases 2, 3 y 4 del gemelo digital.

Recorre el motor de datos completo sin nada de visualizacion: reconstruye el
estado, lo reproduce y detecta el fallo de la instrumentacion de energia.

Uso
---
    python -m gemelo_digital.demo_fases_2_4
    python -m gemelo_digital.demo_fases_2_4 --campo adc13_px_array_current
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemelo_digital import anomalias, datos, estado, reproduccion  # noqa: E402


def titulo(t: str) -> None:
    print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campo", default="battery_voltage")
    args = p.parse_args(argv)

    print("Cargando magnitudes desde PostgreSQL...")
    campos = datos.cargar_campos()
    unidades = estado.unidades(campos)
    unidad = unidades.get(args.campo, "")

    # --- FASE 2 -----------------------------------------------------------
    titulo("FASE 2 --- Reconstruccion de estado por ultimo valor conocido")
    est = estado.reconstruir(campos)
    magnitudes = [c for c in est.columns if not c.endswith("__edad_s") and c != "pase"]
    print(f"  eventos           : {len(est)}")
    print(f"  magnitudes        : {len(magnitudes)}")
    print(f"  pases detectados  : {int(est['pase'].max()) + 1}")
    cob = estado.cobertura(est)
    print(f"\n  Frescura (fraccion del tiempo con lectura de menos de "
          f"{estado.EDADES_UMBRAL['fresca']} s):")
    print(cob[["fresca", "vieja", "obsoleta", "%_fresca"]].head(5).to_string())

    # --- FASE 3 -----------------------------------------------------------
    titulo("FASE 3 --- Reproduccion temporal sobre eje comprimido")
    r = reproduccion.Reproductor(est)
    span = (est.index[-1] - est.index[0]).total_seconds()
    print(f"  eje real          : {span / 86400:.0f} dias")
    print(f"  eje virtual       : {r.duracion_virtual_s / 3600:.1f} h "
          f"(huecos entre pases recortados a {reproduccion.SALTO_ENTRE_PASES:.0f} s)")
    r.velocidad = 5.0
    r.reproducir()
    print(f"\n  Reproduciendo a x{r.velocidad:g}, tres ticks de 1 s real:")
    for _ in range(3):
        n = r.tick(1.0)
        print(f"    +{n:2d} eventos -> {r.momento}  pase {r.pase}")
    r.pausar()
    r.ir_a_tiempo("2021-02-24")
    print(f"\n  Salto al dia del fallo -> evento {r.indice} de {len(r)}, {r.momento}")

    # --- FASE 4 -----------------------------------------------------------
    titulo(f"FASE 4 --- Deteccion de anomalias en '{args.campo}'")
    clas = anomalias.clasificar(campos, args.campo)
    print(f"  lecturas          : {len(clas)}")
    print("\n  Reparto de etiquetas:")
    print(clas["etiqueta"].value_counts().to_string())

    evs = anomalias.eventos(clas, args.campo)
    print(f"\n  Tramos detectados : {len(evs)}")

    muertos = [e for e in evs if e.etiqueta == "canal_enrielado"]
    if muertos:
        primero = min(muertos, key=lambda e: e.inicio)
        print("\n  Primer tramo con el canal enrielado --- el fallo que se buscaba:")
        print()
        for linea in anomalias.describir_evento(primero, unidad).splitlines():
            print(f"    {linea}")
    else:
        print("\n  No se detecto ningun canal enrielado en esta magnitud.")

    print("\n  Estado del CubeSat por ano (lo que pintara el modelo 3D):")
    tabla = pd.crosstab(clas.index.year, clas["etiqueta"])
    print(tabla.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
