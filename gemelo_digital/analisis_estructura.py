#!/usr/bin/env python3
"""FASE 1 --- Estructura real de los DataFrames del gemelo digital.

Este informe existe para no disenar la simulacion sobre supuestos. Contesta
tres preguntas antes de escribir una linea de visualizacion:

  1. Que columnas hay realmente, con que tipo y que rango.
  2. Cuales sirven para mover algo en pantalla y cuales estan muertas.
  3. Que forma tiene el eje temporal --- si es una serie regular o no.

La tercera es la que condiciona el diseno. Las balizas de STRaND-1 no son
telemetria continua: llegan a rafagas durante los pases de una estacion, cada
trama transporta de uno a tres campos, y entre pase y pase hay dias. No existe
un instante en el que se conozcan todas las magnitudes a la vez.

Uso
---
    python -m gemelo_digital.analisis_estructura
    python -m gemelo_digital.analisis_estructura --campo battery_voltage
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemelo_digital import datos  # noqa: E402

# Un campo cuya desviacion tipica es nula en una ventana no esta midiendo: la
# orbita, la iluminacion y la carga varian en cualquier plazo apreciable.
UMBRAL_VIVO = 1e-9


def titulo(texto: str) -> None:
    print(f"\n{'=' * 78}\n{texto}\n{'=' * 78}")


def estructura(df: pd.DataFrame, nombre: str) -> None:
    print(f"\n--- {nombre}: {len(df)} filas x {len(df.columns)} columnas ---")
    resumen = pd.DataFrame({
        "tipo": df.dtypes.astype(str),
        "nulos": df.isna().sum(),
        "%nulos": (100 * df.isna().mean()).round(1),
        "distintos": df.nunique(),
    })
    print(resumen.to_string())


def inventario_campos(campos: pd.DataFrame) -> pd.DataFrame:
    """Una fila por magnitud, con lo necesario para decidir si sirve."""
    g = campos.groupby("field_name", observed=True)["value_numeric"]
    inv = pd.DataFrame({
        "n": g.count(),
        "distintos": g.nunique(),
        "min": g.min().round(2),
        "max": g.max().round(2),
        "desv": g.std().round(3),
    })
    unidades = campos.groupby("field_name", observed=True)["unit"].first()
    fechas = campos.groupby("field_name", observed=True)["timestamp"]
    inv["unidad"] = unidades
    inv["desde"] = fechas.min().dt.date
    inv["hasta"] = fechas.max().dt.date
    inv = inv[inv["n"] > 0].sort_values("distintos", ascending=False)
    return inv


def clasificar(inv: pd.DataFrame) -> pd.Series:
    """Etiqueta cada campo por su utilidad para mover algo en pantalla."""
    def etiqueta(fila: pd.Series) -> str:
        if pd.isna(fila["desv"]) or fila["desv"] <= UMBRAL_VIVO:
            return "MUERTO (constante)"
        if fila["distintos"] < 15:
            return "POBRE (poca variacion)"
        if fila["n"] < 500:
            return "ESCASO (pocas lecturas)"
        return "UTIL"
    return inv.apply(etiqueta, axis=1)


def forma_temporal(frames: pd.DataFrame, campos: pd.DataFrame) -> None:
    titulo("FORMA DEL EJE TEMPORAL --- lo que condiciona el diseno")

    ts = frames["timestamp"].sort_values()
    span = (ts.max() - ts.min()).days
    dias = ts.dt.date.nunique()
    print(f"\nRango           : {ts.min():%Y-%m-%d} a {ts.max():%Y-%m-%d}  ({span} dias)")
    print(f"Dias con tramas : {dias}  ({100 * dias / span:.1f} % del periodo)")

    huecos = ts.diff().dropna()
    print(f"\nSeparacion entre tramas consecutivas:")
    print(f"  mediana : {huecos.median()}")
    print(f"  p90     : {huecos.quantile(0.90)}")
    print(f"  maxima  : {huecos.max()}   <-- no es una serie regular")

    por_trama = campos.groupby("frame_id", observed=True)["field_name"].nunique()
    print(f"\nMagnitudes fisicas por trama (nunca el estado completo):")
    print(por_trama.value_counts().sort_index().to_string())
    print(f"\n  -> ningun instante tiene mas de {por_trama.max()} magnitudes medidas a la vez.")
    print("     El panel de telemetria necesita reconstruccion de estado por ultimo")
    print("     valor conocido, con la edad de cada lectura a la vista (fase 2).")


def ventana_util(campos: pd.DataFrame, campo: str) -> None:
    titulo(f"VENTANA UTIL DE '{campo}' --- donde la variable esta viva")
    s = datos.serie(campos, campo)
    por_anio = s.groupby(s.index.year)["value_numeric"].agg(
        n="count", distintos="nunique", minimo="min", maximo="max", desv="std")
    por_anio["dias"] = s.groupby(s.index.year).apply(
        lambda d: d.index.date.max().toordinal() - d.index.date.min().toordinal() + 1)
    print()
    print(por_anio.round(3).to_string())
    vivos = por_anio[por_anio["desv"] > UMBRAL_VIVO]
    if not vivos.empty:
        mejor = vivos["n"].idxmax()
        print(f"\n  -> mejor ano para la demostracion: {mejor} "
              f"({int(vivos.loc[mejor, 'n'])} lecturas, desv {vivos.loc[mejor, 'desv']:.3f})")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campo", default="battery_voltage",
                   help="campo cuya ventana util se detalla (por defecto battery_voltage)")
    args = p.parse_args(argv)

    print("Cargando desde PostgreSQL...")
    frames = datos.cargar_frames()
    campos = datos.cargar_campos()
    obs = datos.cargar_observaciones()

    titulo("FASE 1 --- ESTRUCTURA DE LOS DATAFRAMES")
    estructura(frames, "frames")
    estructura(campos, "decoded_fields (formato largo, solo magnitudes fisicas)")
    estructura(obs, "observations")

    titulo("INVENTARIO DE MAGNITUDES --- que se puede mover en pantalla")
    inv = inventario_campos(campos)
    inv["veredicto"] = clasificar(inv)
    print()
    print(inv.to_string())
    print("\nReparto:")
    print(inv["veredicto"].value_counts().to_string())

    forma_temporal(frames, campos)
    ventana_util(campos, args.campo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
