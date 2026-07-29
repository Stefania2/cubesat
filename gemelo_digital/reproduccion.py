"""FASE 3 --- Motor de reproduccion temporal.

El problema que resuelve
------------------------
Reproducir estos datos contra el reloj de pared no funciona. El archivo abarca
3511 dias de los que solo 657 tienen tramas, y el hueco mayor entre dos tramas
consecutivas es de **365 dias**. A velocidad real la proyeccion pasaria el 81 %
del tiempo en negro; a velocidad suficiente para cruzar los huecos, cada pase
--- que dura minutos --- se veria en un parpadeo.

La solucion es un **eje de tiempo comprimido**: dentro de un pase el tiempo
corre real, de modo que las rafagas conservan su ritmo; entre pases el hueco se
recorta a `SALTO_ENTRE_PASES`. Asi se conserva lo que tiene significado fisico
(la cadencia de las balizas dentro de un pase) y se descarta lo que no aporta
nada (semanas de silencio).

El motor es una maquina de estados sin hilos ni temporizadores: se le dice
cuanto tiempo real ha pasado con `tick()` y el mueve el cursor. Esto lo hace
gobernable igual desde un bucle de render, desde una API o desde una prueba.

Uso
---
    from gemelo_digital import datos, estado, reproduccion
    est = estado.reconstruir(datos.cargar_campos())
    r = reproduccion.Reproductor(est)
    r.velocidad = 10.0
    r.reproducir()
    r.tick(1.0)          # ha pasado 1 segundo real -> avanza 10 s virtuales
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# A cuanto se recorta el hueco entre dos pases, en segundos de eje virtual.
# Suficiente para que se lea como un corte y no como un tiron.
SALTO_ENTRE_PASES = 2.0

VELOCIDADES = (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 60.0, 300.0)


def eje_virtual(indice: pd.DatetimeIndex, pases: np.ndarray,
                salto: float = SALTO_ENTRE_PASES) -> np.ndarray:
    """Segundos acumulados en el eje comprimido, uno por evento.

    El intervalo se saca dividiendo un timedelta64 por otro, no restando los
    enteros del indice: su unidad aqui es el microsegundo, y tratarlos como
    nanosegundos encoge el eje por un factor de mil sin avisar.
    """
    reales = np.diff(indice.to_numpy()) / np.timedelta64(1, "s")
    cambia_pase = np.diff(pases) != 0
    pasos = np.where(cambia_pase, salto, reales)
    return np.concatenate([[0.0], np.cumsum(pasos)])


@dataclass
class Reproductor:
    """Cursor sobre los eventos, con control de transporte.

    No lanza hilos: el avance ocurre solo cuando alguien llama a `tick()` con
    el tiempo real transcurrido. Quien lo gobierne decide la cadencia.
    """

    estado: pd.DataFrame
    velocidad: float = 1.0
    reproduciendo: bool = False
    _i: int = 0
    _t: float = 0.0
    _eje: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.estado.empty:
            raise ValueError("No hay eventos que reproducir.")
        self._eje = eje_virtual(pd.DatetimeIndex(self.estado.index),
                                self.estado["pase"].to_numpy())

    # --- consulta ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self.estado)

    @property
    def indice(self) -> int:
        return self._i

    @property
    def momento(self) -> pd.Timestamp:
        """Instante real --- el del satelite --- del evento actual."""
        return pd.Timestamp(self.estado.index[self._i])

    @property
    def pase(self) -> int:
        return int(self.estado["pase"].iloc[self._i])

    @property
    def progreso(self) -> float:
        """Fraccion recorrida del eje virtual, entre 0 y 1."""
        return float(self._eje[self._i] / self._eje[-1]) if self._eje[-1] else 0.0

    @property
    def duracion_virtual_s(self) -> float:
        return float(self._eje[-1])

    def fila(self) -> pd.Series:
        return self.estado.iloc[self._i]

    # --- transporte -------------------------------------------------------

    def reproducir(self) -> None:
        self.reproduciendo = True

    def pausar(self) -> None:
        self.reproduciendo = False

    def alternar(self) -> None:
        self.reproduciendo = not self.reproduciendo

    def ir_a(self, i: int) -> None:
        """Salta a un evento por indice, recolocando el reloj virtual."""
        self._i = int(np.clip(i, 0, len(self) - 1))
        self._t = float(self._eje[self._i])

    def avanzar(self, n: int = 1) -> None:
        self.ir_a(self._i + n)

    def retroceder(self, n: int = 1) -> None:
        self.ir_a(self._i - n)

    def ir_a_tiempo(self, cuando: str | pd.Timestamp) -> None:
        """Salta al primer evento en o despues del instante real dado."""
        objetivo = pd.Timestamp(cuando)
        if objetivo.tzinfo is None:
            objetivo = objetivo.tz_localize("UTC")
        self.ir_a(int(self.estado.index.searchsorted(objetivo)))

    def ir_a_pase(self, pase: int) -> None:
        """Salta al primer evento de una sesion de recepcion."""
        coincide = np.flatnonzero(self.estado["pase"].to_numpy() == pase)
        if coincide.size == 0:
            raise KeyError(f"No existe el pase {pase}.")
        self.ir_a(int(coincide[0]))

    def ir_a_progreso(self, fraccion: float) -> None:
        """Barra de desplazamiento: coloca el cursor por fraccion del eje."""
        objetivo = float(np.clip(fraccion, 0.0, 1.0)) * self._eje[-1]
        self.ir_a(int(np.searchsorted(self._eje, objetivo)))

    def mas_rapido(self) -> None:
        siguientes = [v for v in VELOCIDADES if v > self.velocidad]
        self.velocidad = siguientes[0] if siguientes else VELOCIDADES[-1]

    def mas_lento(self) -> None:
        previas = [v for v in VELOCIDADES if v < self.velocidad]
        self.velocidad = previas[-1] if previas else VELOCIDADES[0]

    # --- avance -----------------------------------------------------------

    def tick(self, dt_real_s: float) -> int:
        """Avanza el reloj virtual y devuelve cuantos eventos se cruzaron."""
        if not self.reproduciendo:
            return 0
        self._t += dt_real_s * self.velocidad
        anterior = self._i
        self._i = int(np.searchsorted(self._eje, self._t, side="right")) - 1
        if self._i >= len(self) - 1:
            self._i = len(self) - 1
            self.reproduciendo = False
        return self._i - anterior

    def resumen(self) -> dict:
        """Lo que un panel necesita saber del transporte, sin la telemetria."""
        return {
            "indice": self._i,
            "total": len(self),
            "momento": self.momento.isoformat(),
            "pase": self.pase,
            "progreso": round(self.progreso, 4),
            "velocidad": self.velocidad,
            "reproduciendo": self.reproduciendo,
        }
