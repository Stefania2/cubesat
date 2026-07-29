"""Endpoints de parametros de telemetria.

Este router es el que materializa la regla de no inventar datos. Los parametros
se declaran en un catalogo, pero su valor solo se rellena si existe una
definicion de protocolo **validada** que diga como extraerlo. Mientras no la
haya, cada parametro se devuelve con estado `not_decoded` y el motivo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import DecodedField, Frame, ProtocolDefinition
from ..schemas import ParametroTelemetria, TelemetriaOut

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

# Catalogo de parametros que un CubeSat como STRaND-1 publica habitualmente en
# su baliza. Estan aqui para dar estructura a la interfaz, NO como afirmacion de
# que estos bytes existan en el frame o de que tengan estos valores.
CATALOGO = [
    {"key": "battery_voltage", "label": "Battery Voltage", "unit": "V"},
    {"key": "obc_uptime", "label": "OBC Uptime", "unit": "s"},
    {"key": "magnetometer_x", "label": "Magnetometer X", "unit": "µT"},
    {"key": "magnetometer_y", "label": "Magnetometer Y", "unit": "µT"},
    {"key": "magnetometer_z", "label": "Magnetometer Z", "unit": "µT"},
    {"key": "system_status", "label": "System Status", "unit": None},
]

# «Battery Current» y «Temperature» estaban en este catalogo y se retiraron: la
# especificacion de AMSAT-UK define sus canales (0x01 y 0x04 del nodo 0x2C),
# pero ninguna de las balizas recibidas los transmite, de modo que su tarjeta no
# podia mostrar nunca otra cosa que «Not available». Enumerar un parametro que el
# satelite no envia no informa de nada. Si en el futuro llega una baliza con esos
# canales, basta con volver a anadirlos aqui: la decodificacion ya los soporta.
CANALES_NO_RECIBIDOS = ("battery_current", "temperature")

MOTIVO_SIN_PROTOCOLO = (
    "No hay una definicion de protocolo validada para NORAD "
    f"{settings.norad_id}. Los bytes se conservan en crudo sin interpretar."
)

# La entropia no pertenece al catalogo anterior porque no es de la misma clase:
# los demas parametros son DECODED —existen solo si un protocolo validado dice
# como leerlos— y este es PROCESSED, medido sobre los bytes recibidos sin
# suponer nada del formato. Por eso tiene estado propio y aparece aunque no haya
# ningun protocolo registrado: es la unica magnitud de esta pantalla que no
# depende de interpretar la carga util.
CLAVE_ENTROPIA = "payload_entropy"


def _parametro_entropia(db: Session) -> ParametroTelemetria:
    """Entropia de Shannon del payload, medida frame a frame.

    Se informa junto al techo teorico porque el numero suelto no dice nada: una
    trama de n bytes no puede superar log2(n) bits/byte, y con longitudes de ~15
    bytes ese techo esta en torno a 3,7, no en los 8 de un byte arbitrario.
    """
    filas = db.execute(
        select(Frame.timestamp, Frame.entropy_bits_per_byte)
        .where(Frame.entropy_bits_per_byte.is_not(None))
        .order_by(Frame.timestamp.desc())
        .limit(200)
    ).all()

    if not filas:
        return ParametroTelemetria(
            key=CLAVE_ENTROPIA, label="Entropía del payload", unit="bits/byte",
            value=None, status="not_available",
            reason="No hay ningun frame con entropia calculada.",
        )

    fila = db.execute(
        select(
            func.avg(Frame.entropy_bits_per_byte),
            func.avg(func.log(2, func.greatest(Frame.byte_count, 1))),
        ).where(Frame.entropy_bits_per_byte.is_not(None), Frame.byte_count > 0)
    ).one()
    # `log()` de PostgreSQL devuelve numeric, que llega como Decimal y no se
    # mezcla con float en una division.
    media, techo = float(fila[0]), float(fila[1])

    historia = [
        {"timestamp": ts.isoformat(), "value": valor}
        for ts, valor in reversed(filas)
    ]
    razon = (
        f"Medida sobre los bytes, sin depender del protocolo. Promedio del "
        f"conjunto: {media:.3f} bits/byte frente a un maximo posible de "
        f"{techo:.3f} para estas longitudes de trama ({100 * media / techo:.0f} %)."
    )
    return ParametroTelemetria(
        key=CLAVE_ENTROPIA, label="Entropía del payload", unit="bits/byte",
        value=round(filas[0][1], 3), status="measured", reason=razon,
        history=historia,
    )


def _motivo_sin_balizas(db: Session) -> str:
    """Explica por que un protocolo validado no ha rellenado ningun parametro.

    Decir solo «ningun frame contiene este campo» no informa. Lo que importa es
    cuantos frames hay y cuantos son realmente balizas del satelite, que es una
    comprobacion objetiva: el formato empieza por el flag HDLC C0 80.
    """
    total = db.scalar(select(func.count(Frame.id))) or 0
    balizas = db.scalar(
        select(func.count(Frame.id)).where(Frame.raw_hex.startswith("C080"))
    ) or 0

    if balizas:
        return (
            f"{balizas} de {total} frames son balizas de STRaND-1, pero ninguna "
            "llego con este campo intacto."
        )
    return (
        f"Protocolo validado y decodificador oficial disponible, pero ninguno de "
        f"los {total} frames almacenados es una baliza de STRaND-1: cero llevan el "
        "flag HDLC C0 80 con el que empieza el formato. Los bytes recibidos no se "
        "interpretan por aproximacion."
    )


@router.get("", response_model=TelemetriaOut)
def parametros(db: Session = Depends(get_db)):
    validados = list(db.scalars(
        select(ProtocolDefinition).where(
            ProtocolDefinition.validated.is_(True),
            ProtocolDefinition.norad_id == settings.norad_id,
        )
    ))

    parametros: list[ParametroTelemetria] = []
    for entrada in CATALOGO:
        if not validados:
            parametros.append(ParametroTelemetria(
                **entrada, value=None, status="not_decoded", reason=MOTIVO_SIN_PROTOCOLO
            ))
            continue

        # Con protocolo validado, los valores salen de decoded_fields y de
        # ningun otro sitio.
        registros = db.scalars(
            select(DecodedField)
            .where(DecodedField.field_name == entrada["key"])
            .order_by(DecodedField.timestamp.desc())
            .limit(200)
        ).all()

        if not registros:
            parametros.append(ParametroTelemetria(
                **entrada,
                value=None,
                status="not_available",
                reason=_motivo_sin_balizas(db),
            ))
            continue

        ultimo = registros[0]
        historia = [
            {"timestamp": r.timestamp.isoformat(), "value": r.value_numeric}
            for r in reversed(registros)
            if r.value_numeric is not None
        ]
        # La unidad la manda el dato decodificado, no el catalogo: la hoja de
        # AMSAT-UK publica ecuacion de calibracion para las magnitudes del EPS y
        # de los paneles, pero no para los magnetometros, que quedan en cuentas.
        # Anunciar µT donde solo hay un entero sin escalar seria falsearlo.
        entrada_con_unidad = {**entrada, "unit": ultimo.unit or entrada["unit"]}
        parametros.append(ParametroTelemetria(
            **entrada_con_unidad,
            value=ultimo.value_numeric if ultimo.value_numeric is not None else ultimo.value_text,
            status="decoded",
            reason=None,
            history=historia,
        ))

    # Va la primera: es la unica que siempre tiene valor, y deja claro de un
    # vistazo que la pantalla distingue lo medido de lo decodificado.
    parametros.insert(0, _parametro_entropia(db))

    balizas = db.scalar(
        select(func.count(Frame.id)).where(Frame.frame_type == "strand_beacon")
    ) or 0
    resumen = _resumen_campos(db)

    if not validados:
        nota = MOTIVO_SIN_PROTOCOLO
    elif not balizas:
        nota = _motivo_sin_balizas(db)
    else:
        total = db.scalar(select(func.count(Frame.id))) or 0
        nota = (
            f"{balizas} de {total} frames son balizas de STRaND-1 y estan "
            f"decodificadas con {', '.join(p.name for p in validados)}. "
            f"De los {resumen['total']} campos que traen, "
            f"{resumen['constantes']} no varian nunca: su valor procede de un "
            "byte estructural del paquete o de una carga util a cero, no de una "
            "medida."
        )

    return TelemetriaOut(
        parametros=parametros,
        protocolo_validado=bool(validados),
        nota=nota,
        balizas=balizas,
        campos_totales=resumen["total"],
        campos_constantes=resumen["constantes"],
    )


def _resumen_campos(db: Session) -> dict[str, int]:
    """Cuenta campos decodificados y cuantos de ellos no varian nunca."""
    filas = db.execute(
        select(
            DecodedField.field_name,
            func.count(func.distinct(DecodedField.value_numeric)),
            # Igual que en `/campos`: un campo textual varia en su texto, no en
            # un numero, y contarlo solo por lo numerico lo daba por constante.
            func.count(func.distinct(DecodedField.value_text)),
        )
        .group_by(DecodedField.field_name)
    ).all()
    return {
        "total": len(filas),
        "constantes": sum(1 for _, num, txt in filas if max(num, txt) <= 1),
    }


def _aviso_campo(
    nombre: str, maximo: float | None, p95: float | None, fuera_dominio: int
) -> str | None:
    """Aviso sobre el extremo de un campo, o None si no hay nada que decir.

    Se distinguen dos casos que no valen lo mismo. En los campos `*_adc` el
    dominio esta definido —un convertidor de 10 bits no puede pasar de 1023—, de
    modo que el exceso es un hecho objetivo. En el resto solo puede decirse que
    el maximo queda lejos del grueso de la distribucion, y eso admite dos
    explicaciones que la interfaz no debe zanjar: una cola larga real o una
    trama con bytes alterados.
    """
    if nombre.endswith("_adc") and fuera_dominio:
        return (
            f"{fuera_dominio} lecturas por encima de 1023, fuera del fondo de "
            "escala de un convertidor de 10 bits. Se conservan como cuenta cruda, "
            "pero no se les aplica la ecuacion de calibracion: extrapolarla fuera "
            "de su dominio da valores imposibles."
        )
    if maximo is not None and p95 not in (None, 0) and abs(maximo) > 10 * abs(p95):
        return (
            "El maximo queda mas de un orden de magnitud por encima del percentil "
            "95. Puede ser una cola larga real —el reloj del OBC alcanzo de verdad "
            "3043 s— o una trama con el ultimo byte alterado. Estas balizas no "
            "llevan CRC, asi que no hay forma estructural de distinguirlas: el "
            "dato se conserva sin filtrar y se senala el extremo."
        )
    return None


@router.get("/campos")
def campos_decodificados(db: Session = Depends(get_db)):
    """Inventario de los campos realmente presentes en las balizas decodificadas.

    El catalogo de la pantalla principal son ocho etiquetas elegidas de antemano;
    esto es lo contrario: lo que la especificacion define y las balizas traen de
    verdad, con su nombre original. Se incluye el numero de valores distintos
    porque un campo que nunca cambia no esta midiendo nada, y eso hay que poder
    verlo.
    """
    filas = db.execute(
        select(
            DecodedField.field_name,
            func.count(DecodedField.id),
            func.count(func.distinct(DecodedField.value_numeric)),
            # Los estados de los interruptores y `system_status` no son numeros
            # sino texto (`ON`, `OFF`, ...). Contar solo valores numericos los
            # dejaba en «0 valores distintos · Constante», que confunde «no
            # varia» con «no es numerico».
            func.count(func.distinct(DecodedField.value_text)),
            func.min(DecodedField.value_numeric),
            func.max(DecodedField.value_numeric),
            # Rango tipico: acota la vista sin descartar nada. Cuando el maximo
            # queda muy lejos del percentil 95, el extremo viene de una trama con
            # bytes alterados, no del comportamiento del canal.
            func.percentile_cont(0.05).within_group(DecodedField.value_numeric),
            func.percentile_cont(0.95).within_group(DecodedField.value_numeric),
            # Lecturas por encima del fondo de escala de un ADC de 10 bits. Solo
            # significa algo en los campos `*_adc`, que son cuentas crudas.
            func.count(DecodedField.id).filter(DecodedField.value_numeric > 1023),
            func.min(DecodedField.timestamp),
            func.max(DecodedField.timestamp),
        )
        .group_by(DecodedField.field_name)
        .order_by(func.count(DecodedField.id).desc())
    ).all()

    campos = []
    for (nombre, apariciones, distintos_num, distintos_txt,
         minimo, maximo, p05, p95, fuera_dominio, desde, hasta) in filas:
        # Un campo es textual si no trae ningun valor numerico.
        textual = distintos_num == 0 and distintos_txt > 0
        distintos = distintos_txt if textual else distintos_num
        campos.append({
            "campo": nombre,
            "apariciones": apariciones,
            "valores_distintos": distintos,
            "tipo": "texto" if textual else "numerico",
            "minimo": minimo,
            "maximo": maximo,
            "p05": p05,
            "p95": p95,
            # El aviso describe lo que se observa, sin diagnosticar la causa. Un
            # maximo lejos del p95 puede ser una cola larga legitima —el reloj
            # del OBC llego de verdad a 3043 s— o una trama con bytes alterados;
            # solo en los campos `*_adc` hay un criterio objetivo, porque su
            # dominio esta definido por el fondo de escala del convertidor.
            "aviso": _aviso_campo(nombre, maximo, p95, fuera_dominio),
            "desde": desde.isoformat() if desde else None,
            "hasta": hasta.isoformat() if hasta else None,
            "constante": distintos <= 1,
        })
    constantes = sum(1 for c in campos if c["constante"])

    return {
        "total": len(campos),
        "constantes": constantes,
        "campos": campos,
        "nota": (
            f"{constantes} de {len(campos)} campos no varian nunca en todo el "
            "conjunto. Un campo constante no es una medida: procede de un byte "
            "estructural del paquete o de una carga util a cero."
            if constantes else
            "Todos los campos presentan variacion a lo largo del conjunto."
        ),
    }


@router.get("/protocolos")
def protocolos(db: Session = Depends(get_db)):
    """Definiciones de protocolo registradas y su estado de validacion."""
    filas = db.scalars(select(ProtocolDefinition)).all()
    return {
        "total": len(filas),
        "validados": sum(1 for f in filas if f.validated),
        "items": [
            {
                "name": f.name,
                "norad_id": f.norad_id,
                "description": f.description,
                "reference": f.reference,
                "validated": f.validated,
                "campos": len(f.field_spec or []),
            }
            for f in filas
        ],
        "nota": (
            "Un protocolo solo debe marcarse como validado cuando su estructura "
            "se ha contrastado contra documentacion oficial de la mision o "
            "contra frames de referencia con valores conocidos."
        ),
    }
