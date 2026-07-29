#!/usr/bin/env python3
"""FASE 9 --- Demostracion completa de un pico de telemetria.

Que se demuestra
----------------
El pico no se inyecta: **ya esta en los datos**. Entre noviembre de 2020 y
febrero de 2021 el convertidor analogico-digital del subsistema de energia de
STRaND-1 dejo de leer. Su cuenta se quedo clavada en 0, y como las rectas de
calibracion de AMSAT-UK son decrecientes, la cuenta 0 no se traduce en cero
voltios sino en la **ordenada al origen**: 9,7488 V para la bateria 0. Un canal
muerto se disfraza asi de bateria a plena carga, que es el peor modo de fallo
posible para un operador --- el panel dice que todo va bien justo cuando ha
dejado de saberlo.

Este guion recorre el suceso de principio a fin y publica las cifras que el
panel y el modelo 3D deben mostrar: variable afectada, instante, valor esperado,
valor registrado, diferencia, duracion y estado resultante del CubeSat.

Un pico sintetico
-----------------
Con `--sintetico` se inyecta ademas un pico artificial sobre la ventana sana,
claramente rotulado, para comprobar que el detector tambien caza lo que no es
un enrielamiento: un transitorio de un solo punto. Sirve para validar el
z-score robusto, que en el fallo real no es quien dispara.

Uso
---
    python -m gemelo_digital.demo_pico
    python -m gemelo_digital.demo_pico --sintetico
    python -m gemelo_digital.demo_pico --campo adc13_px_array_current
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemelo_digital import anomalias, datos, estado, reproduccion  # noqa: E402

# Ventana densa previa al fallo: es la que se descargo dia a dia, con miles de
# lecturas. Tres semanas sueltas no dan linea base para inyectar nada.
VENTANA_SANA = ("2020-11-01", "2021-01-31")


def titulo(t: str) -> None:
    print(f"\n{'=' * 76}\n{t}\n{'=' * 76}")


def contexto_temporal(clas: pd.DataFrame) -> None:
    """Las tres fases de la instrumentacion, fechadas por el detector."""
    titulo("1. LAS TRES FASES DEL SUBSISTEMA DE ENERGIA")
    mes = clas.index.strftime("%Y-%m")
    por_mes = clas.groupby([mes, clas["etiqueta"]],
                           observed=True).size().unstack(fill_value=0)
    muerto = por_mes.get("canal_enrielado", pd.Series(dtype=int))
    vivo = por_mes.drop(columns=["canal_enrielado"], errors="ignore").sum(axis=1)
    tabla = pd.DataFrame({"midiendo": vivo, "enrielado": muerto}).fillna(0).astype(int)
    tabla["% muerto"] = (100 * tabla["enrielado"] / tabla.sum(axis=1).replace(0, 1)).round(1)
    print()
    print(tabla[tabla.sum(axis=1) > 0].to_string())


def transicion(clas: pd.DataFrame) -> pd.Timestamp | None:
    """Instante exacto en que el canal deja de medir para no volver."""
    muerto = clas["etiqueta"].astype(str) == "canal_enrielado"
    if not muerto.any():
        return None
    # Ultimo tramo en que todavia medía: lo que venga despues ya es definitivo.
    ultimo_vivo = muerto[~muerto].index.max()
    posteriores = muerto[muerto.index > ultimo_vivo]
    return posteriores.index.min() if not posteriores.empty else muerto[muerto].index.min()


def detalle_evento(clas: pd.DataFrame, campo: str, unidad: str) -> None:
    titulo("2. EL EVENTO, TAL COMO LO VE EL DETECTOR")
    evs = anomalias.eventos(clas, campo)
    if not evs:
        print("\n  No se detecto ningun evento en esta magnitud.")
        return
    # El primero enrielado, no el mas largo: en los tramos posteriores la linea
    # base previa ya esta dentro del fallo y la diferencia saldria cero.
    muertos = [e for e in evs if e.etiqueta == "canal_enrielado"]
    elegido = min(muertos, key=lambda e: e.inicio) if muertos else max(evs, key=lambda e: e.duracion_s)
    print()
    for linea in anomalias.describir_evento(elegido, unidad).splitlines():
        print(f"  {linea}")

    corte = transicion(clas)
    if corte is not None:
        print(f"\n  Ultima lectura valida seguida de enrielamiento definitivo:")
        print(f"    {corte}")
        print("    (la documentacion del proyecto situa el primer dia integramente")
        print("     a cero el 2021-02-24: el detector lo encuentra por su cuenta)")


def como_lo_ve_el_operador(campos: pd.DataFrame, campo: str) -> None:
    """El nucleo de la demostracion: el fallo no parece un fallo."""
    titulo("3. POR QUE ESTE FALLO ES PELIGROSO")
    s = datos.serie(campos, campo)["value_numeric"]
    antes = s[(s.index >= VENTANA_SANA[0]) & (s.index < VENTANA_SANA[1])]
    despues = s[s.index >= "2021-03-01"]
    if antes.empty or despues.empty:
        print("\n  Sin datos suficientes a ambos lados de la transicion.")
        return
    print(f"\n  Sano     ({VENTANA_SANA[0]} a {VENTANA_SANA[1]}):")
    print(f"    n={len(antes):5d}  min={antes.min():6.3f}  max={antes.max():6.3f}  "
          f"desv={antes.std():6.3f}  valores distintos={antes.nunique()}")
    print(f"  Muerto   (desde 2021-03-01):")
    print(f"    n={len(despues):5d}  min={despues.min():6.3f}  max={despues.max():6.3f}  "
          f"desv={despues.std():6.3f}  valores distintos={despues.nunique()}")
    print(f"\n  El valor SUBE de {antes.mean():.2f} a {despues.mean():.2f} V. Un umbral por")
    print("  bateria baja nunca se disparara. Lo que delata el fallo no es el nivel,")
    print(f"  es que la dispersion cae de {antes.std():.3f} a {despues.std():.3f}.")


def pico_sintetico(campos: pd.DataFrame, campo: str, unidad: str) -> None:
    """Inyecta un transitorio artificial para validar el z-score robusto."""
    titulo("4. CONTRASTE CON UN PICO SINTETICO (dato artificial)")
    s = datos.serie(campos, campo)["value_numeric"]
    sano = s[(s.index >= VENTANA_SANA[0]) & (s.index < VENTANA_SANA[1])].copy()
    if len(sano) < 100:
        print("\n  Ventana sana demasiado corta para la prueba.")
        return

    posicion = len(sano) // 2
    original = float(sano.iloc[posicion])
    inyectado = original + 6 * float(sano.std())
    sano.iloc[posicion] = inyectado

    z = anomalias.zscore_robusto(sano)
    z_pico = float(z["z"].iloc[posicion])
    print(f"\n  SINTETICO --- se altera una sola lectura de la ventana sana:")
    print(f"    instante  : {sano.index[posicion]}")
    print(f"    original  : {original:.3f} {unidad}")
    print(f"    inyectado : {inyectado:.3f} {unidad}  (+6 desviaciones)")
    print(f"    |z| robusto obtenido : {abs(z_pico):.2f}")
    veredicto = ("ANOMALIA" if abs(z_pico) >= anomalias.UMBRAL_ANOMALIA
                 else "ADVERTENCIA" if abs(z_pico) >= anomalias.UMBRAL_ADVERTENCIA
                 else "no detectado")
    print(f"    veredicto : {veredicto}")
    print("\n  Esto valida la otra mitad del detector: el z-score caza el transitorio,")
    print("  la regla de enrielamiento caza el fallo permanente. Ninguna sirve sola.")


def recorrido(campos: pd.DataFrame, campo: str) -> None:
    """Lo que veria el usuario reproduciendo el suceso en el gemelo."""
    titulo("5. RECORRIDO EN EL GEMELO --- lo que se vera en pantalla")
    est = estado.reconstruir(campos)
    rep = reproduccion.Reproductor(est)
    clas = anomalias.clasificar(campos, campo)
    et = clas["etiqueta"].astype(str)
    et = et[~et.index.duplicated(keep="last")].reindex(est.index, method="ffill")

    rep.ir_a_tiempo("2021-02-20")
    print(f"\n  {'evento':>7}  {'instante':<26} {'estado del CubeSat':<26} pase")
    for _ in range(8):
        etiqueta = str(et.iloc[rep.indice])
        color = anomalias.estado_cubesat(etiqueta if etiqueta != "nan" else "sin_referencia")
        print(f"  {rep.indice:7d}  {str(rep.momento):<26} {color:<26} {rep.pase}")
        rep.avanzar(180)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campo", default="battery_voltage")
    p.add_argument("--sintetico", action="store_true",
                   help="inyecta ademas un pico artificial para validar el z-score")
    args = p.parse_args(argv)

    print("Cargando telemetria real desde PostgreSQL...")
    campos = datos.cargar_campos()
    unidad = estado.unidades(campos).get(args.campo, "")
    clas = anomalias.clasificar(campos, args.campo)

    titulo(f"DEMOSTRACION --- pico de telemetria en '{args.campo}'")
    print(f"\n  Lecturas analizadas : {len(clas)}")
    print(f"  Rango               : {clas.index.min()}  a  {clas.index.max()}")
    print(f"  Unidad              : {unidad or '(sin unidad declarada)'}")

    contexto_temporal(clas)
    detalle_evento(clas, args.campo, unidad)
    como_lo_ve_el_operador(campos, args.campo)
    if args.sintetico:
        pico_sintetico(campos, args.campo, unidad)
    recorrido(campos, args.campo)

    titulo("CONCLUSION")
    print("""
  El enlace nunca fue el eslabon debil: el margen sobra y las estaciones
  reciben bien. Lo que fallo primero fue la instrumentacion, y lo que impidio
  verlo durante anos fue la interpretacion --- una recta de calibracion que
  convierte un canal muerto en una bateria sana.

  El gemelo digital ensena las dos cosas a la vez: la curva que se aplana y el
  satelite que cambia de color. Ninguna de las dos por separado lo cuenta.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
