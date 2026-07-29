"""FASE 4 --- Deteccion de anomalias sobre la telemetria real.

Eleccion del metodo
-------------------
La fase 1 descarto la maquinaria pesada. Isolation Forest y los modelos de
series temporales suponen un muestreo regular y un vector de estado; aqui no
hay ni lo uno ni lo otro --- las lecturas llegan a rafagas y cada baliza trae
una sola magnitud. Ademas, la anomalia principal de este satelite no es un
punto disperso en un espacio de rasgos: es un **salto de nivel a una
constante**, cuando el ADC del subsistema de energia deja de leer y la recta de
calibracion convierte la cuenta 0 en el extremo de escala.

Se usan por tanto dos reglas, ambas suficientes y explicables ante un jurado:

**Z-score robusto (mediana + MAD).** La media y la desviacion tipica se
arrastran por los propios valores atipicos que buscamos; la mediana y la
desviacion absoluta mediana no. El factor 1,4826 devuelve la MAD a la escala de
una desviacion tipica cuando los datos son normales.

**Canal enrielado.** Si en toda la ventana la magnitud no cambia, el canal no
esta midiendo: la orbita, la iluminacion y la carga varian en cualquier plazo
apreciable. Es la regla que caza el fallo de febrero de 2021, y hace falta
porque en ese tramo la MAD vale exactamente cero y el z-score es indefinido ---
un canal muerto tiene dispersion nula, que es lo contrario de lo que un
detector de atipicos busca.

Ventanas sobre datos irregulares
--------------------------------
La ventana es por numero de lecturas, no por tiempo, porque el muestreo es
irregular. Eso arrastra un riesgo: las N lecturas previas pueden venir de otro
ano si hay un hueco de por medio, y entonces la referencia no es comparable.
Cuando la ventana abarca mas de `MAX_SPAN_VENTANA` el punto se marca
`sin_referencia` en lugar de compararse contra un pasado que no viene a cuento.

Uso
---
    from gemelo_digital import datos, anomalias
    campos = datos.cargar_campos()
    r = anomalias.clasificar(campos, "battery_voltage")
    print(anomalias.describir_evento(r, "battery_voltage"))
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

VENTANA = 51                       # lecturas previas que forman la referencia
UMBRAL_ADVERTENCIA = 3.5           # |z| a partir del cual algo se sale
UMBRAL_ANOMALIA = 6.0              # |z| claramente fuera
MAX_SPAN_VENTANA = pd.Timedelta("30D")
# Hueco que parte un evento en dos. Un pase dura minutos; mas de un dia sin
# lecturas no es la continuacion del mismo suceso.
MAX_HUECO_EVENTO = pd.Timedelta("1D")
MIN_ENRIELADO = 20                 # lecturas quietas seguidas para declarar canal muerto
# Amplitud relativa por debajo de la cual se considera que el canal no se mueve.
# Una milesima de la propia escala: por debajo de eso no hay medida, hay ruido
# de cuantizacion o un convertidor parado.
TOLERANCIA_ENRIELADO = 1e-3

# Devuelve la MAD a la escala de una desviacion tipica bajo normalidad.
ESCALA_MAD = 1.4826

ETIQUETAS = ("normal", "advertencia", "anomalia", "canal_enrielado", "sin_referencia")


@dataclass(frozen=True)
class Evento:
    """Un tramo anomalo continuo, con todo lo que el panel debe mostrar."""

    campo: str
    etiqueta: str
    inicio: str
    fin: str
    duracion_s: float
    n_lecturas: int
    valor_esperado: float
    valor_registrado: float
    diferencia: float
    z_max: float
    estado_cubesat: str

    def dict(self) -> dict:
        return asdict(self)


def _mad(x: np.ndarray) -> float:
    mediana = np.nanmedian(x)
    return float(np.nanmedian(np.abs(x - mediana)))


def zscore_robusto(valores: pd.Series, ventana: int = VENTANA) -> pd.DataFrame:
    """Mediana, MAD y z robusto sobre una ventana movil de lecturas previas."""
    mediana = valores.rolling(ventana, min_periods=ventana // 2).median()
    mad = valores.rolling(ventana, min_periods=ventana // 2).apply(_mad, raw=True)
    sigma = ESCALA_MAD * mad
    # Con MAD nula el z es indefinido; ese caso lo resuelve la regla de canal
    # enrielado, no un z inflado hasta el infinito.
    z = (valores - mediana) / sigma.where(sigma > 0)
    return pd.DataFrame({"mediana": mediana, "mad": mad, "z": z})


def enrielado(valores: pd.Series, ventana: int = MIN_ENRIELADO,
              tolerancia: float = TOLERANCIA_ENRIELADO) -> pd.Series:
    """True donde la magnitud lleva `ventana` lecturas practicamente quieta.

    No se exige un unico valor. `battery_voltage` agrega las dos baterias, y
    sus rectas de calibracion tienen ordenadas distintas (9,7488 y 9,7526), de
    modo que un canal completamente muerto sigue alternando **dos** valores
    separados por 4 mV. Exigir `nunique() == 1` deja escapar justo el fallo que
    se busca.

    El criterio es la amplitud relativa: si el recorrido de la ventana no llega
    a una milesima de su propia escala, el convertidor no se esta moviendo. Al
    ser adimensional vale igual para voltios, miliamperios o cuentas.
    """
    movil = valores.rolling(ventana, min_periods=ventana)
    rango = movil.max() - movil.min()
    escala = movil.median().abs()
    # Con mediana nula no hay escala relativa que valga: se compara contra el
    # recorrido total de la serie para no dividir por cero.
    referencia = escala.where(escala > 0, valores.abs().max() or 1.0)
    return (rango <= tolerancia * referencia).fillna(False)


def clasificar(campos: pd.DataFrame, campo: str, ventana: int = VENTANA,
               umbral_adv: float = UMBRAL_ADVERTENCIA,
               umbral_anom: float = UMBRAL_ANOMALIA) -> pd.DataFrame:
    """Etiqueta cada lectura de una magnitud como normal/advertencia/anomalia."""
    from gemelo_digital import datos as _datos

    s = _datos.serie(campos, campo)
    valores = s["value_numeric"].astype("float64")

    out = zscore_robusto(valores, ventana)
    out["valor"] = valores
    out["enrielado"] = enrielado(valores)

    # Amplitud temporal de la ventana: si es enorme, la referencia no sirve.
    span = valores.index.to_series().diff(ventana - 1)
    out["sin_referencia"] = (span > MAX_SPAN_VENTANA) | out["mediana"].isna()

    etiqueta = pd.Series("normal", index=valores.index, dtype="object")
    etiqueta[out["z"].abs() >= umbral_adv] = "advertencia"
    etiqueta[out["z"].abs() >= umbral_anom] = "anomalia"
    # El canal muerto manda sobre el z: es un diagnostico, no un atipico.
    etiqueta[out["enrielado"]] = "canal_enrielado"
    etiqueta[out["sin_referencia"] & ~out["enrielado"]] = "sin_referencia"
    out["etiqueta"] = pd.Categorical(etiqueta, categories=ETIQUETAS)
    return out


def estado_cubesat(etiqueta: str) -> str:
    """Traduce la etiqueta al estado que debe pintar el modelo 3D."""
    return {
        "normal": "NOMINAL",
        "advertencia": "ADVERTENCIA",
        "anomalia": "CRITICO",
        "canal_enrielado": "INSTRUMENTACION_PERDIDA",
        "sin_referencia": "SIN_REFERENCIA",
    }.get(etiqueta, "DESCONOCIDO")


def eventos(clasificacion: pd.DataFrame, campo: str,
            de_interes: tuple[str, ...] = ("advertencia", "anomalia", "canal_enrielado"),
            ) -> list[Evento]:
    """Agrupa lecturas contiguas con la misma etiqueta en tramos."""
    et = clasificacion["etiqueta"].astype(str)
    # Un tramo se corta al cambiar la etiqueta **o** al abrirse un hueco grande.
    # Sin lo segundo, once lecturas dispersas a lo largo de un ano se presentan
    # como un unico evento de 364 dias de duracion, que es falso.
    hueco = clasificacion.index.to_series().diff() > MAX_HUECO_EVENTO
    tramo = ((et != et.shift()) | hueco).cumsum()
    posicion = {marca: i for i, marca in enumerate(clasificacion.index)}
    fuera: list[Evento] = []
    for _, g in clasificacion.groupby(tramo, observed=True):
        marca = str(g["etiqueta"].iloc[0])
        if marca not in de_interes:
            continue
        # La referencia son las lecturas **previas** al tramo, no las de dentro.
        # En un canal enrielado la mediana movil ya esta contaminada por el
        # propio fallo, y comparar el tramo consigo mismo da diferencia cero.
        i0 = posicion[g.index[0]]
        previas = clasificacion["valor"].iloc[max(0, i0 - VENTANA):i0]
        sanas = previas[~enrielado(previas, min(MIN_ENRIELADO, max(2, len(previas))))]
        base = sanas if not sanas.empty else previas
        esperado = float(base.median()) if not base.empty else float("nan")
        registrado = float(g["valor"].median())
        z_max = float(g["z"].abs().max()) if g["z"].notna().any() else float("nan")
        fuera.append(Evento(
            campo=campo,
            etiqueta=marca,
            inicio=g.index[0].isoformat(),
            fin=g.index[-1].isoformat(),
            duracion_s=float((g.index[-1] - g.index[0]).total_seconds()),
            n_lecturas=len(g),
            valor_esperado=round(esperado, 4),
            valor_registrado=round(registrado, 4),
            diferencia=round(registrado - esperado, 4),
            z_max=round(z_max, 2) if np.isfinite(z_max) else float("nan"),
            estado_cubesat=estado_cubesat(marca),
        ))
    return fuera


def describir_evento(ev: Evento, unidad: str = "") -> str:
    """Texto de alerta con todo lo que se pidio mostrar en el panel."""
    u = f" {unidad}" if unidad else ""
    dias = ev.duracion_s / 86400
    return (
        f"ALERTA --- {ev.etiqueta.upper()}\n"
        f"  Variable afectada  : {ev.campo}\n"
        f"  Inicio             : {ev.inicio}\n"
        f"  Fin                : {ev.fin}\n"
        f"  Duracion           : {dias:.1f} dias ({ev.n_lecturas} lecturas)\n"
        f"  Valor esperado     : {ev.valor_esperado}{u}\n"
        f"  Valor registrado   : {ev.valor_registrado}{u}\n"
        f"  Diferencia         : {ev.diferencia:+}{u}\n"
        f"  |z| maximo         : {ev.z_max}\n"
        f"  Estado del CubeSat : {ev.estado_cubesat}"
    )
