"""Inventario de variables de telemetria del HMTA.

Cada entrada dice que se mide, en que unidad, para que sirve en palabras
sencillas y --- lo mas importante --- **si STRaND-1 la emite**. La hoja de
AMSAT-UK define bastantes mas canales de los que la baliza transmite de verdad
(comprobado sobre las balizas decodificadas con
`telemetria_strand1/tools/analizar_series_canales.py`): ninguna temperatura,
ninguna corriente de bateria ni de bus. Esas variables estan aqui igualmente,
marcadas como `DEFINIDA_NO_EMITIDA`, para que la interfaz pueda decir «el
satelite no envia este dato» en lugar de callar o, peor, de rellenarlo.

`rango_documentado` esta vacio en todas las variables reales. No es un olvido:
ni AMSAT-UK ni la documentacion de la mision publican limites de operacion de
los componentes. Lo unico documentado es el dominio del convertidor (0 a 1023
cuentas) y la recta de calibracion, y eso lo aplica `telemetry_validation`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Disponibilidad de una variable en la fuente real.
EMITIDA = "emitida"                    # llega en las balizas decodificadas
DEFINIDA_NO_EMITIDA = "definida_no_emitida"  # la hoja la define; la baliza nunca la trae
NO_EXISTE = "no_existe"                # ningun canal de STRaND-1 la mide
DERIVADA = "derivada"                  # se calcula a partir de otras

SUBSISTEMAS = {
    "eps": "Sistema de energía del satélite",
    "termico": "Temperatura de los componentes",
    "comunicaciones": "Comunicación entre el satélite y la estación terrestre",
    "obc": "Computador principal del satélite",
    "adcs": "Orientación y estabilidad del satélite",
    "anomalias": "Identificación de comportamientos anormales",
}

FUENTE_AMSAT = "AMSAT-UK, «STRAND-1 Packet Format» (amsat-strand-1-20130327.xlsx)"


@dataclass(frozen=True)
class Variable:
    clave: str
    nombre: str
    subsistema: str
    unidad: str | None
    que_es: str
    por_que_importa: str
    disponibilidad: str
    fuente: str = FUENTE_AMSAT
    # Campos de la tabla `decoded_fields` que alimentan la variable.
    campos: tuple[str, ...] = ()
    nodo_canal: str | None = None
    rango_documentado: tuple[float, float] | None = None
    notas: tuple[str, ...] = field(default_factory=tuple)

    def dict(self) -> dict:
        d = asdict(self)
        d["subsistema_nombre"] = SUBSISTEMAS[self.subsistema]
        return d


_V = Variable

_PANELES = (
    ("adc1_py_array_current", "+Y", "0x2D/0x01"),
    ("adc4_my_array_current", "−Y", "0x2D/0x04"),
    ("adc7_mx_array_current", "−X", "0x2D/0x07"),
    ("adc10_pz_array_current", "+Z", "0x2D/0x0A"),
    ("adc13_px_array_current", "+X", "0x2D/0x0D"),
    ("adc31_mz_array_current", "−Z", "0x2D/0x1F"),
)

VARIABLES: dict[str, Variable] = {
    # ── EPS ────────────────────────────────────────────────────────────────
    "battery_0_voltage": _V(
        "battery_0_voltage", "Voltaje de la batería 0", "eps", "V",
        "La diferencia de potencial eléctrico entre los bornes de la batería: "
        "cuánta energía entrega por cada unidad de carga que circula.",
        "Los computadores, sensores y la radio necesitan alimentación eléctrica. Si el voltaje "
        "baja de forma sostenida, la batería puede estar descargándose más de lo que se recarga.",
        EMITIDA, campos=("battery_0_voltage",), nodo_canal="0x2C/0x03",
        notas=("Con la cuenta del ADC en 0 la recta devuelve 9,7488 V: ese valor no es una medida.",)),
    "battery_1_voltage": _V(
        "battery_1_voltage", "Voltaje de la batería 1", "eps", "V",
        "Igual que la batería 0, para la segunda batería del satélite.",
        "Comparar las dos baterías ayuda a distinguir un problema de una batería de uno del sensor.",
        EMITIDA, campos=("battery_1_voltage",), nodo_canal="0x2C/0x08",
        notas=("Con la cuenta del ADC en 0 la recta devuelve 9,7526 V: ese valor no es una medida.",)),
    **{
        clave: _V(
            clave, f"Corriente del panel solar {cara}", "eps", "mA",
            "La corriente eléctrica es el flujo de carga: cuántos electrones por segundo "
            f"entrega el panel solar de la cara {cara} del satélite.",
            "Indica cuánta energía se está recogiendo del Sol. Cambia con la iluminación: "
            "en la sombra de la Tierra debe caer a casi cero, y eso es normal.",
            EMITIDA, campos=(clave,), nodo_canal=nc)
        for clave, cara, nc in _PANELES
    },
    "battery_current": _V(
        "battery_current", "Corriente de la batería", "eps", "mA",
        "Cuánta corriente entra (carga) o sale (descarga) de la batería.",
        "Junto con el voltaje permitiría conocer la potencia y el balance de carga.",
        DEFINIDA_NO_EMITIDA, campos=("battery_0_current", "battery_1_current"),
        nodo_canal="0x2C/0x01, 0x2C/0x06"),
    "bus_current": _V(
        "bus_current", "Corriente de los buses de alimentación", "eps", "mA",
        "Corriente que consumen los buses de batería, 5 V y 3,3 V.",
        "Es la medida directa del consumo eléctrico de los equipos.",
        DEFINIDA_NO_EMITIDA,
        campos=("adc17_battery_bus_current", "adc26_5v_bus_current", "adc27_33v_bus_current"),
        nodo_canal="0x2D/0x11, 0x2D/0x1A, 0x2D/0x1B"),
    "power": _V(
        "power", "Potencia eléctrica consumida", "eps", "W",
        "Potencia = voltaje × corriente de una misma rama del circuito.",
        "Dice cuánta energía por segundo usan los componentes.",
        DERIVADA,
        notas=("No se calcula: la baliza no trae ningún par voltaje-corriente de la misma rama. "
               "Multiplicar el voltaje de la batería por la corriente de un panel no es una "
               "potencia de nada.",
               "Los interruptores (nodo 0x66) traen corriente y tensión, pero en las lecturas "
               "están en OFF y sus tensiones calibradas salen negativas: la recta no es "
               "aplicable a ese estado.")),
    "state_of_charge": _V(
        "state_of_charge", "Nivel de carga de la batería", "eps", "%",
        "Porcentaje de energía que queda en la batería.",
        "Es la forma más intuitiva de saber si queda energía.",
        NO_EXISTE, fuente="—",
        notas=("Ningún canal lo mide, y estimarlo exigiría la curva de descarga de las celdas, "
               "que no está documentada.",)),
    # ── Termico ────────────────────────────────────────────────────────────
    "battery_temperature": _V(
        "battery_temperature", "Temperatura de las baterías", "termico", "°C",
        "Temperatura de las celdas de la batería.",
        "Las baterías pierden capacidad o se dañan fuera de su rango de temperatura.",
        DEFINIDA_NO_EMITIDA, campos=("battery_0_temperature", "battery_1_temperature"),
        nodo_canal="0x2C/0x04, 0x2C/0x09"),
    "panel_temperature": _V(
        "panel_temperature", "Temperatura de los paneles solares", "termico", "°C",
        "Temperatura de cada cara con paneles solares.",
        "Muestra cómo se calienta el satélite al sol y se enfría en la sombra.",
        DEFINIDA_NO_EMITIDA,
        campos=("adc2_py_array_temperature", "adc5_my_array_temperature",
                "adc8_mx_array_temperature", "adc11_pz_array_temperature",
                "adc14_px_array_temperature", "adc30_mz_array_temperature"),
        nodo_canal="0x2D/0x02, 0x05, 0x08, 0x0B, 0x0E, 0x1E"),
    "electronics_temperature": _V(
        "electronics_temperature", "Temperatura de la electrónica", "termico", "°C",
        "Temperatura del computador, la radio u otras tarjetas.",
        "Un circuito demasiado caliente o frío puede fallar.",
        NO_EXISTE, fuente="—"),
    # ── OBC ────────────────────────────────────────────────────────────────
    "obc_unix_time": _V(
        "obc_unix_time", "Campo de tiempo del OBC", "obc", "s",
        "Número de 4 bytes que la hoja de AMSAT-UK describe como «UNIX TIME» del computador.",
        "Un reloj que avanza indicaría que el computador funciona; uno que vuelve a cero, "
        "un reinicio.",
        EMITIDA, campos=("obc_unix_time",), nodo_canal="0x80/0x0C",
        notas=("En el archivo no se comporta como un reloj: vale 2 en más de la mitad de las "
               "lecturas y no avanza con el tiempo transcurrido entre balizas. Por eso no se usa "
               "para contar reinicios ni para afirmar que el computador funciona.",)),
    "cpu_load": _V("cpu_load", "Uso del procesador", "obc", "%",
                   "Fracción del tiempo en que el procesador está ocupado.",
                   "Un procesador saturado puede dejar tareas sin hacer.", NO_EXISTE, fuente="—"),
    "memory_use": _V("memory_use", "Uso de memoria", "obc", "%",
                     "Cuánta memoria de trabajo está ocupada.",
                     "Si se agota, los programas pueden fallar.", NO_EXISTE, fuente="—"),
    "reboots": _V("reboots", "Reinicios del computador", "obc", "reinicios",
                  "Cuántas veces el computador se apagó y volvió a arrancar.",
                  "Un reinicio inesperado puede indicar un problema que conviene investigar.",
                  NO_EXISTE, fuente="—",
                  notas=("No hay contador de reinicios en la baliza. Las balizas repetidas con el "
                         "contador de secuencia clavado sugieren reinicios en bucle desde 2022, "
                         "pero es una inferencia, no una medida.",)),
    "obc_errors": _V("obc_errors", "Errores de ejecución", "obc", "errores",
                     "Fallos registrados por los programas del computador.",
                     "Permiten investigar por qué un proceso no hizo lo que debía.",
                     NO_EXISTE, fuente="—"),
    # ── ADCS ───────────────────────────────────────────────────────────────
    **{
        f"magnetometer_{eje}": _V(
            f"magnetometer_{eje}", f"Magnetómetro, componente {eje.upper()}", "adcs", "cuenta",
            "Lectura del sensor que mide el campo magnético de la Tierra en una dirección.",
            "Comparando el campo medido con el esperado se puede deducir hacia dónde apunta "
            "el satélite.",
            EMITIDA, campos=(f"magnetometer_{eje}",), nodo_canal="0x89/0x03, 0x05",
            notas=("Es el entero recibido: AMSAT-UK no publica calibración ni la orientación de "
                   "los ejes, así que no se convierte a microteslas ni a orientación.",))
        for eje in ("x", "y", "z")
    },
    "reaction_wheels_switch": _V(
        "reaction_wheels_switch", "Interruptor de las ruedas de reacción", "adcs", None,
        "Estado (encendido/apagado) de la alimentación de las ruedas que giran el satélite.",
        "Si las ruedas están apagadas, el satélite no controla activamente su orientación.",
        EMITIDA, campos=("switch_7_reaction_wheels_estado",), nodo_canal="0x66/0xA4"),
    "attitude": _V("attitude", "Orientación (actitud)", "adcs", "°",
                   "Hacia dónde apunta el satélite en el espacio.",
                   "Las antenas y paneles funcionan mejor con cierta orientación.",
                   NO_EXISTE, fuente="—"),
    "angular_rate": _V("angular_rate", "Velocidad de giro", "adcs", "°/s",
                       "Cuán rápido gira el satélite sobre sí mismo.",
                       "Un giro descontrolado dificulta la comunicación y la carga.",
                       NO_EXISTE, fuente="—"),
}

# Variables reales que se analizan como series numericas.
SERIES_REALES = tuple(k for k, v in VARIABLES.items()
                      if v.disponibilidad == EMITIDA and v.unidad not in (None,))


def de_subsistema(subsistema: str) -> list[Variable]:
    return [v for v in VARIABLES.values() if v.subsistema == subsistema]


def inventario() -> list[dict]:
    return [v.dict() for v in VARIABLES.values()]
