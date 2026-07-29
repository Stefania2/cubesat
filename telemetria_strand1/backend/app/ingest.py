"""Ingesta de frames: desde el CSV local o desde la API de SatNOGS.

La ingesta es idempotente: la clave (raw_hex, timestamp, observer) evita insertar
dos veces el mismo frame, de modo que se puede reejecutar sin duplicar datos.
"""

from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import AnomalyRule, DecodedField, Frame, Observation, ProtocolDefinition
from .services import satnogs, strand_amsat, strand_telemetry
from .services.anomalies import REGLAS_POR_DEFECTO
from .services.decoder import analizar_frame, parse_hex

logger = logging.getLogger(__name__)


def _parse_ts(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def _protocolos_validados(db: Session) -> list[ProtocolDefinition]:
    return list(
        db.scalars(
            select(ProtocolDefinition).where(
                ProtocolDefinition.validated.is_(True),
                ProtocolDefinition.norad_id == settings.norad_id,
            )
        )
    )


def _existe(
    db: Session,
    raw_hex: str,
    ts: datetime,
    observer: str | None,
    observation_id: int | None = None,
) -> bool:
    """Decide si el frame ya esta almacenado.

    La identidad primaria es (raw_hex, timestamp, observer), que basta mientras
    una fuente no se solape con otra. Pero el mismo frame llega por dos vias con
    metadatos distintos: SatNOGS DB lo entrega con observador, y el archivo de
    demoddata de Network solo trae los bytes. Comparar solo por esa clave los
    tomaria por frames distintos y duplicaria la capa RAW.

    Por eso, cuando se conoce la observacion, la identidad es (raw_hex,
    observation_id, timestamp): los mismos bytes, en la misma observacion y en
    el mismo instante son una sola recepcion, la reporte quien la reporte. Los
    mismos bytes en observaciones distintas si son recepciones distintas —con
    tramas de uno o dos bytes ocurre— y se conservan por separado.
    """
    if observation_id is not None:
        return db.scalar(
            select(Frame.id).where(
                Frame.raw_hex == raw_hex,
                Frame.observation_id == observation_id,
                Frame.timestamp == ts,
            )
        ) is not None

    return db.scalar(
        select(Frame.id).where(
            Frame.raw_hex == raw_hex,
            Frame.timestamp == ts,
            Frame.observer == observer,
        )
    ) is not None


def _asegurar_observaciones(db: Session, registros: list[dict]) -> int:
    """Crea las observaciones referenciadas por los frames antes de insertarlos.

    `Frame.observation_id` es clave foranea de `observations`, asi que la fila de
    la observacion tiene que existir primero. Se crea un registro minimo con lo
    unico que traen los frames (identificador de estacion y observador) y se
    marca su procedencia como `frame-metadata`: la sincronizacion con SatNOGS
    Network lo completara despues.
    """
    referenciados = {
        r["observation_id"] for r in registros if r.get("observation_id") is not None
    }
    if not referenciados:
        return 0

    existentes = set(db.scalars(
        select(Observation.observation_id).where(
            Observation.observation_id.in_(referenciados)
        )
    ))
    faltantes = referenciados - existentes
    if not faltantes:
        return 0

    # Primer frame de cada observacion: aporta estacion y observador.
    muestra: dict[int, dict] = {}
    for r in registros:
        oid = r.get("observation_id")
        if oid in faltantes and oid not in muestra:
            muestra[oid] = r

    for oid, r in muestra.items():
        db.add(Observation(
            observation_id=oid,
            norad_id=r.get("norad_id") or settings.norad_id,
            satellite_name=settings.satellite_name,
            station_id=r.get("station_id"),
            observer=r.get("observer"),
            source="frame-metadata",
        ))

    db.flush()
    return len(faltantes)


def guardar_frames(db: Session, registros: list[dict], fuente: str) -> dict:
    """Analiza y persiste una lista de frames ya normalizados."""
    protocolos = _protocolos_validados(db)
    insertados = duplicados = 0
    ahora = datetime.now(timezone.utc)
    # La sesion va con autoflush=False, de modo que los frames aun pendientes no
    # los ve una consulta: sin esto, un lote que trae dos veces la misma trama la
    # insertaria duplicada porque ninguna de las dos esta todavia en la base.
    vistos: set[tuple] = set()

    # Las observaciones referenciadas deben existir antes que los frames.
    _asegurar_observaciones(db, registros)

    for registro in registros:
        raw = (registro.get("raw_hex") or "").upper()
        ts = registro.get("timestamp")
        if not raw or ts is None:
            continue
        obs_id = registro.get("observation_id")
        clave = (raw, obs_id, ts) if obs_id is not None else (raw, ts, registro.get("observer"))
        if clave in vistos or _existe(db, raw, ts, registro.get("observer"), obs_id):
            duplicados += 1
            continue
        vistos.add(clave)

        try:
            datos = parse_hex(raw)
        except ValueError:
            logger.warning("Hex invalido, se omite el frame de %s", registro.get("observer"))
            continue

        analisis = analizar_frame(datos, protocolos)
        db.add(Frame(
            raw_hex=raw,
            norad_id=registro.get("norad_id") or settings.norad_id,
            sat_id=registro.get("sat_id"),
            observer=registro.get("observer"),
            timestamp=ts,
            app_source=registro.get("app_source"),
            transmitter=registro.get("transmitter"),
            version=registro.get("version"),
            station_id=registro.get("station_id"),
            observation_id=registro.get("observation_id"),
            byte_count=analisis.byte_count,
            entropy_bits_per_byte=analisis.entropy_bits_per_byte,
            printable_ratio=analisis.printable_ratio,
            distinct_bytes=analisis.distinct_bytes,
            status=analisis.status,
            frame_type=analisis.frame_type,
            protocol=analisis.protocol,
            analysis=analisis.analysis,
            ingested_at=ahora,
        ))
        insertados += 1

    db.commit()
    total = db.scalar(select(func.count(Frame.id))) or 0
    logger.info("Ingesta (%s): %d nuevos, %d duplicados", fuente, insertados, duplicados)
    return {"insertados": insertados, "duplicados": duplicados, "total": total, "fuente": fuente}


def ingerir_csv(db: Session, ruta: Path | None = None) -> dict:
    """Carga el CSV de telemetria real exportado del proyecto de analisis."""
    ruta = Path(ruta or settings.seed_csv_path)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el CSV de telemetria: {ruta}")

    registros = []
    with ruta.open(newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            raw = (fila.get("frame") or "").strip()
            if not raw:
                continue
            registros.append({
                "raw_hex": raw.upper(),
                "norad_id": int(fila["norad_cat_id"]) if fila.get("norad_cat_id") else settings.norad_id,
                "sat_id": fila.get("sat_id") or None,
                "observer": fila.get("observer") or None,
                "timestamp": _parse_ts(fila.get("timestamp")),
                "app_source": fila.get("app_source") or None,
                "transmitter": fila.get("transmitter") or None,
                "version": fila.get("version") or None,
                "station_id": int(fila["station_id"]) if fila.get("station_id") else None,
                "observation_id": int(fila["observation_id"]) if fila.get("observation_id") else None,
            })

    return guardar_frames(db, registros, fuente=f"csv:{ruta.name}")


def eliminar_frames_duplicados(db: Session) -> dict:
    """Colapsa los frames que son la misma recepcion guardada dos veces.

    Se agrupa por (raw_hex, observation_id, timestamp) —la identidad que usa
    `_existe`— y de cada grupo se conserva una sola fila: la que mas metadatos
    trae, midiendo cuantos de observador, estacion, transmisor, identificador de
    satelite y procedencia estan informados. Asi la copia que sobrevive es la de
    SatNOGS DB, con observador y estacion, y no la de demoddata, que solo tiene
    los bytes. A igualdad de metadatos gana la fila mas antigua.

    Los grupos sin `observation_id` no se tocan: sin observacion no hay forma de
    afirmar que dos tramas identicas sean la misma recepcion y no dos pasos
    distintos, y ante la duda no se borra nada.
    """
    grupos = db.execute(
        select(Frame.raw_hex, Frame.observation_id, Frame.timestamp)
        .where(Frame.observation_id.is_not(None))
        .group_by(Frame.raw_hex, Frame.observation_id, Frame.timestamp)
        .having(func.count(Frame.id) > 1)
    ).all()

    def riqueza(f: Frame) -> tuple:
        informados = sum(1 for v in (
            f.observer, f.station_id, f.transmitter, f.sat_id, f.app_source,
        ) if v is not None)
        return (informados, -f.id)

    eliminados = 0
    detalle: list[dict] = []

    for raw_hex, obs_id, ts in grupos:
        filas = db.scalars(
            select(Frame).where(
                Frame.raw_hex == raw_hex,
                Frame.observation_id == obs_id,
                Frame.timestamp == ts,
            )
        ).all()
        if len(filas) < 2:
            continue

        conservada, *sobrantes = sorted(filas, key=riqueza, reverse=True)
        detalle.append({
            "raw_hex": raw_hex,
            "observation_id": obs_id,
            "conservado": conservada.app_source,
            "eliminados": [f.app_source for f in sobrantes],
        })
        for f in sobrantes:
            db.delete(f)
            eliminados += 1

    if eliminados:
        db.commit()

    total = db.scalar(select(func.count(Frame.id))) or 0
    logger.info("Deduplicacion: %d frames eliminados, %d grupos afectados",
                eliminados, len(detalle))
    return {"eliminados": eliminados, "grupos": len(detalle), "total": total, "detalle": detalle}


SIN_TELEMETRIA = "SIN_TELEMETRIA"


def ingerir_csv_extraccion(db: Session, ruta: Path) -> dict:
    """Carga el CSV que produce `tools/extraer_telemetria_satnogs.py`.

    Ese CSV recorre las observaciones de SatNOGS Network y guarda el hexadecimal
    de cada archivo de demoddata, con estructura distinta a la del CSV de
    SatNOGS DB:

        observation_id | frame_number | telemetry_hex | timestamp | byte_count

    Las filas marcadas `SIN_TELEMETRIA` registran que la observacion se recorrio
    y no tenia demoddata. No son frames y no se insertan: hacerlo llenaria la
    capa RAW de entradas que no contienen ningun byte recibido.

    El origen del dato es el mismo que el de `ingerir_demoddata` —bytes crudos
    demodulados por la red—, de modo que se etiquetan igual (`app_source =
    "demoddata"`). La estacion no viaja en el archivo: la completa despues la
    sincronizacion con SatNOGS Network.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el CSV de extraccion: {ruta}")

    registros: list[dict] = []
    sin_telemetria = 0
    sin_marca_de_tiempo = 0

    with ruta.open(newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            raw = (fila.get("telemetry_hex") or "").strip()
            if not raw or raw == SIN_TELEMETRIA:
                sin_telemetria += 1
                continue

            ts = _parse_ts(fila.get("timestamp"))
            if ts is None:
                # Sin marca de tiempo no hay identidad de frame (la clave es
                # raw_hex + timestamp + observer) ni sitio en la serie temporal.
                sin_marca_de_tiempo += 1
                continue

            registros.append({
                "raw_hex": raw.upper(),
                "norad_id": settings.norad_id,
                "sat_id": None,
                "observer": None,
                "timestamp": ts,
                "app_source": "demoddata",
                "transmitter": None,
                "version": None,
                "station_id": None,
                "observation_id": int(fila["observation_id"]) if fila.get("observation_id") else None,
            })

    if not registros:
        return {
            "insertados": 0, "duplicados": 0,
            "total": db.scalar(select(func.count(Frame.id))) or 0,
            "fuente": f"extraccion:{ruta.name}",
            "sin_telemetria": sin_telemetria,
            "sin_marca_de_tiempo": sin_marca_de_tiempo,
        }

    resultado = guardar_frames(db, registros, fuente=f"extraccion:{ruta.name}")
    resultado["sin_telemetria"] = sin_telemetria
    resultado["sin_marca_de_tiempo"] = sin_marca_de_tiempo
    return resultado


# Nombre de archivo de demoddata de SatNOGS:
#   data_<observation_id>_<YYYY-MM-DDTHH-MM-SS>_g<n>
# El identificador de observacion y la marca de tiempo van en el propio nombre.
PATRON_DEMODDATA = re.compile(
    r"^data_(?P<obs>\d+)_(?P<fecha>\d{4}-\d{2}-\d{2})T(?P<hora>\d{2}-\d{2}-\d{2})(?:_g(?P<g>\d+))?$"
)


def ingerir_demoddata(db: Session, directorio: Path) -> dict:
    """Carga archivos de demoddata descargados de SatNOGS Network.

    A diferencia del CSV de SatNOGS DB, cada archivo contiene los **bytes crudos**
    de una trama demodulada, no su representacion hexadecimal. Son el mismo tipo
    de dato: telemetria ya procesada por la red desde la cascada de espectro
    hasta bytes, pero sin interpretar su significado.
    """
    directorio = Path(directorio)
    if not directorio.is_dir():
        raise FileNotFoundError(f"No es un directorio: {directorio}")

    registros: list[dict] = []
    ignorados: list[str] = []

    for ruta in sorted(directorio.iterdir()):
        if not ruta.is_file():
            continue
        m = PATRON_DEMODDATA.match(ruta.name)
        if m is None:
            continue

        datos = ruta.read_bytes()
        if not datos:
            ignorados.append(f"{ruta.name} (vacio)")
            continue

        ts = datetime.strptime(
            f"{m['fecha']}T{m['hora']}", "%Y-%m-%dT%H-%M-%S"
        ).replace(tzinfo=timezone.utc)

        registros.append({
            "raw_hex": datos.hex().upper(),
            "norad_id": settings.norad_id,
            "sat_id": None,
            "observer": None,          # lo aporta la sincronizacion con Network
            "timestamp": ts,
            "app_source": "demoddata",
            "transmitter": None,
            "version": None,
            "station_id": None,
            "observation_id": int(m["obs"]),
        })

    if not registros:
        return {
            "insertados": 0, "duplicados": 0,
            "total": db.scalar(select(func.count(Frame.id))) or 0,
            "fuente": f"demoddata:{directorio.name}",
            "ignorados": ignorados,
        }

    resultado = guardar_frames(db, registros, fuente=f"demoddata:{directorio.name}")
    resultado["ignorados"] = ignorados
    return resultado


def ingerir_satnogs(db: Session, limite: int = 100) -> dict:
    """Descarga frames de SatNOGS DB y los persiste."""
    registros = satnogs.fetch_telemetry(limite=limite)
    return guardar_frames(db, registros, fuente="satnogs-db")


def sincronizar_observaciones(db: Session, limite: int = 100, incluir_recientes: bool = False) -> dict:
    """Completa los metadatos de observacion desde SatNOGS Network.

    Sincroniza primero las observaciones que referencian nuestros frames, pidiendo
    cada una por su identificador. El listado general de la API devuelve solo las
    mas recientes del satelite, que no tienen por que coincidir con los frames
    almacenados: con este conjunto de datos no coinciden en absoluto (los frames
    apuntan a observaciones de la serie 11-13 M y el listado empieza en la 14 M).
    """
    pendientes = [
        oid for oid in db.scalars(
            select(Observation.observation_id).where(Observation.source != "satnogs-network")
        )
    ]

    remotas = satnogs.fetch_observations_by_ids(pendientes[:limite]) if pendientes else []
    resueltas_por_id = len(remotas)

    if incluir_recientes:
        sat_id = db.scalar(select(Frame.sat_id).where(Frame.sat_id.is_not(None)).limit(1))
        remotas += satnogs.fetch_observations(sat_id=sat_id, limite=limite)

    existentes = {o.observation_id: o for o in db.scalars(select(Observation))}
    nuevas = actualizadas = 0

    for datos in remotas:
        obs_id = datos.get("observation_id")
        if obs_id is None:
            continue
        actual = existentes.get(obs_id)
        if actual is None:
            nueva = Observation(**datos)
            db.add(nueva)
            existentes[obs_id] = nueva
            nuevas += 1
        else:
            for campo, valor in datos.items():
                if valor is not None:
                    setattr(actual, campo, valor)
            actualizadas += 1

    db.commit()
    completados = _completar_estacion_en_frames(db)
    logger.info(
        "Observaciones: %d resueltas por ID, %d nuevas, %d actualizadas, "
        "%d frames completados con su estacion",
        resueltas_por_id, nuevas, actualizadas, completados,
    )
    return {
        "solicitadas": len(pendientes),
        "resueltas_por_id": resueltas_por_id,
        "nuevas": nuevas,
        "actualizadas": actualizadas,
    }


def _completar_estacion_en_frames(db: Session) -> int:
    """Rellena estacion y observador en los frames que no los traian.

    Los archivos de demoddata contienen solo los bytes: la estacion no viaja en
    el archivo. Se toma de la observacion a la que pertenece el frame, que es un
    enlace real y trazable, no una suposicion.
    """
    huerfanos = db.scalars(
        select(Frame).where(
            Frame.observation_id.is_not(None),
            (Frame.observer.is_(None)) | (Frame.station_id.is_(None)),
        )
    ).all()
    if not huerfanos:
        return 0

    observaciones = {
        o.observation_id: o
        for o in db.scalars(
            select(Observation).where(
                Observation.observation_id.in_({f.observation_id for f in huerfanos})
            )
        )
    }

    # Rellenar el observador puede colisionar con la clave (raw_hex, timestamp,
    # observer): dos frames identicos, del mismo instante y de la misma estacion,
    # que hasta ahora se distinguian solo porque ambos tenian el observador a
    # nulo. Son la misma recepcion, asi que se colapsan en lugar de reventar la
    # transaccion entera, que es lo que ocurria antes.
    ocupadas = {
        (raw, ts, obs)
        for raw, ts, obs in db.execute(
            select(Frame.raw_hex, Frame.timestamp, Frame.observer).where(
                Frame.observer.is_not(None)
            )
        )
    }

    completados = colapsados = 0
    for frame in huerfanos:
        obs = observaciones.get(frame.observation_id)
        if obs is None:
            continue

        nuevo_observer = frame.observer or obs.station_name
        clave = (frame.raw_hex, frame.timestamp, nuevo_observer)
        if nuevo_observer is not None and clave in ocupadas:
            db.delete(frame)
            colapsados += 1
            continue

        if frame.observer is None and obs.station_name:
            frame.observer = obs.station_name
            ocupadas.add(clave)
        if frame.station_id is None and obs.station_id is not None:
            frame.station_id = obs.station_id
        completados += 1

    if completados or colapsados:
        db.commit()
    if colapsados:
        logger.info(
            "%d frames colapsados al completar la estacion: misma trama, mismo "
            "instante y misma estacion que otra ya almacenada", colapsados,
        )
    return completados


def registrar_protocolo_strand(db: Session) -> ProtocolDefinition | None:
    """Registra la baliza de STRaND-1 como protocolo validado.

    Se marca `validated=True` porque cumple lo que este proyecto exige para
    serlo: existe una especificacion publicada (AMSAT-UK) y una implementacion
    de referencia mantenida por terceros (`satnogsdecoders`), que es ademas la
    que SatNOGS DB declara para este satelite. No es una interpretacion propia
    de los bytes.

    Que el protocolo este validado no rellena ningun parametro por si solo: los
    valores siguen saliendo unicamente de frames que encajen en el formato.
    """
    if not strand_telemetry.disponible():
        logger.warning(
            "satnogsdecoders no esta disponible: no se registra el protocolo de STRaND-1"
        )
        return None

    existente = db.scalar(
        select(ProtocolDefinition).where(
            ProtocolDefinition.name == strand_telemetry.NOMBRE_PROTOCOLO
        )
    )
    if existente is not None:
        return existente

    definicion = ProtocolDefinition(
        name=strand_telemetry.NOMBRE_PROTOCOLO,
        norad_id=settings.norad_id,
        description=(
            "Baliza de telemetria de STRaND-1: flag HDLC C0 80, numero de "
            "secuencia, longitud, tipo de paquete (1 = modem, 2 = OBC), cuerpo "
            "y CRC-16/CCITT. La decodificacion la realiza el decodificador "
            "oficial, no una implementacion propia."
        ),
        reference=strand_telemetry.REFERENCIA,
        validated=True,
        field_spec=strand_telemetry.field_spec(),
        created_at=datetime.now(timezone.utc),
    )
    db.add(definicion)
    db.commit()
    logger.info("Protocolo registrado y validado: %s", definicion.name)
    return definicion


def decodificar_frames_almacenados(db: Session, solo_pendientes: bool = True) -> dict:
    """Pasa el decodificador oficial por los frames ya guardados.

    Necesario despues de registrar el protocolo: los frames ingeridos antes se
    analizaron cuando no habia ninguna definicion validada y quedaron todos en
    `unclassified`.
    """
    consulta = select(Frame)
    if solo_pendientes:
        consulta = consulta.where(Frame.status != "decoded")
    frames = db.scalars(consulta).all()

    con_flag = decodificados = campos_creados = 0

    for frame in frames:
        try:
            datos = parse_hex(frame.raw_hex)
        except ValueError:
            continue

        if not strand_telemetry.tiene_estructura(datos):
            continue
        con_flag += 1

        # La decodificacion la hace el modulo que sigue la hoja de AMSAT-UK. El
        # decodificador oficial de satnogs-decoders reconoce la estructura pero
        # lee un solo byte por canal, devolviendo el DATA_SIZE en lugar de la
        # medida (ver strand_amsat para el detalle), asi que no sirve para los
        # valores.
        baliza = strand_amsat.decodificar(datos)
        campos = dict(baliza.valores) if baliza else {}
        if baliza is None:
            # Tiene el flag pero no encaja: es una baliza corrupta, no otra cosa.
            frame.status = "error"
            frame.frame_type = "strand_beacon_corrupta"
            continue
        if baliza is not None:
            campos.setdefault("seq_no", baliza.seq_no)
            campos.setdefault("i2c_node_address", baliza.nodo)
            campos.setdefault("node_channel", baliza.canal)

        # Se guardan todos los campos que produce el decodificador, con su
        # nombre real. Los tres del catalogo de la interfaz se guardan ademas
        # bajo su clave, pero el registro completo es el que manda: es la
        # telemetria tal como la define la especificacion, sin recortar a las
        # etiquetas que la interfaz decidio mostrar.
        parametros = strand_telemetry.a_parametros(campos)
        registros = {campo: valor for campo, valor in campos.items()}
        registros.update({clave: valor for clave, (valor, _) in parametros.items()})

        for clave, valor in registros.items():
            numerico = valor if isinstance(valor, (int, float)) and not isinstance(valor, bool) else None
            db.add(DecodedField(
                frame_id=frame.id,
                protocol_name=strand_telemetry.NOMBRE_PROTOCOLO,
                field_name=clave,
                value_numeric=numerico,
                value_text=None if numerico is not None else str(valor),
                unit=strand_telemetry.UNIDADES.get(clave) or (baliza.unidades.get(clave) if baliza else None),
                timestamp=frame.timestamp,
            ))
            campos_creados += 1

        frame.status = "decoded" if parametros else "partially_decoded"
        frame.frame_type = "strand_beacon"
        frame.protocol = strand_telemetry.NOMBRE_PROTOCOLO
        frame.analysis = {**(frame.analysis or {}), "strand": campos}
        decodificados += 1

    db.commit()
    logger.info(
        "Decodificacion STRaND-1: %d frames con flag HDLC, %d decodificados, %d campos",
        con_flag, decodificados, campos_creados,
    )
    return {
        "frames_revisados": len(frames),
        "con_flag_hdlc": con_flag,
        "decodificados": decodificados,
        "campos": campos_creados,
    }


def crear_reglas_por_defecto(db: Session) -> int:
    """Inserta las reglas de anomalias que aun no existan."""
    existentes = set(db.scalars(select(AnomalyRule.key)))
    creadas = 0
    for regla in REGLAS_POR_DEFECTO:
        if regla["key"] in existentes:
            continue
        db.add(AnomalyRule(**regla))
        creadas += 1
    if creadas:
        db.commit()
    return creadas
