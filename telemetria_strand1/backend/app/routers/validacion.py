"""API de STRaND-1 SCIENTIFIC VALIDATION.

Capa delgada sobre el paquete `validacion_cientifica/` de la raiz del
repositorio (como `gemelo.py` lo es sobre `gemelo_digital/`): aqui solo hay
validacion de entradas, cache del proceso y serializacion.

Ninguna ruta escribe en la base ni la lee: todo sale del archivo sellado del
repositorio y del catalogo de TLE. Por eso funciona igual en local y en
Vercel, y seguiria funcionando sin PostgreSQL ni SatNOGS.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

# parents[0] routers [1] app [2] backend [3] telemetria_strand1 [4] cubesat
RAIZ_REPO = Path(__file__).resolve().parents[4]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from validacion_cientifica import conjunto as C  # noqa: E402
from validacion_cientifica import diagnosticos as D  # noqa: E402
from validacion_cientifica import estados as E  # noqa: E402
from validacion_cientifica import informe as I  # noqa: E402
from validacion_cientifica import orbital as O  # noqa: E402
from validacion_cientifica import panel  # noqa: E402
from validacion_cientifica import procedencia as P  # noqa: E402
from validacion_cientifica import reconstruccion as R  # noqa: E402
from validacion_cientifica import sincronizacion as S  # noqa: E402
from validacion_cientifica import telemetria as T  # noqa: E402
from validacion_cientifica.tiempo import FechaInvalida, a_datetime, instante_utc  # noqa: E402

router = APIRouter(prefix="/api/validacion", tags=["validación científica"])

CAMPO_VALIDO = re.compile(r"^[a-z0-9_]{1,64}$")
MAX_MANIFEST_BYTES = 2_000_000


def _archivo() -> None:
    if not P.archivo_disponible():
        raise HTTPException(status_code=503, detail="Falta el archivo sellado (validacion_cientifica/archivo).")


def _t(t: str | None) -> str:
    if not t or len(t) > 64:
        raise HTTPException(status_code=422, detail="Indique «t» como fecha ISO 8601 con zona (p. ej. 2021-03-01T12:00:00Z).")
    try:
        instante_utc(t)
    except FechaInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return t


def _campo(campo: str) -> str:
    if not CAMPO_VALIDO.match(campo):
        raise HTTPException(status_code=422, detail="Nombre de campo no válido.")
    return campo


def _reconstruir(t: str, campo: str) -> dict:
    _archivo()
    try:
        return R.reconstruir(_t(t), _campo(campo))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from exc


@router.get("/resumen")
def resumen() -> dict:
    """Validation Overview: todas las comprobaciones de servidor y la suite registrada."""
    return panel.resumen()


@router.get("/procedencia")
def procedencia() -> dict:
    sello = P.leer_sello()
    return E.limpiar({
        "sello": sello, "huella_conjunto": P.huella_conjunto(),
        "integridad": [r.dict() for r in P.verificar_archivo()],
        "comparacion_base": panel.comparacion_base(),
        "versiones": P.versiones(),
        "fuentes": {k or "sin_registrar": v for k, v in P.FUENTE_SATNOGS.items()},
        "por_fuente": C.tramas()["app_source"].fillna("sin_registrar").value_counts().to_dict()
                      if P.archivo_disponible() else {},
        "catalogo_tle": {"tle": len(O.catalogo_tle()),
                         "epoca_min": O.catalogo_tle()[0].dict()["epoca_utc"] if O.catalogo_tle() else None,
                         "epoca_max": O.catalogo_tle()[-1].dict()["epoca_utc"] if O.catalogo_tle() else None,
                         "fuente": "validacion_cientifica/archivo/catalogo_tle.jsonl.gz (copia sellada de "
                                   f"{O.GEOMETRIA.relative_to(RAIZ_REPO)} y tle/)",
                         "vivo_frente_a_sellado": O.comparar_catalogo_vivo().dict()},
        "limitaciones": [
            "Las respuestas originales de la API de SatNOGS no se guardaron al ingerir: el archivo "
            "sella la capa ORIGINAL tal como está en la base.",
            "La fecha de medición no existe en la baliza; se usa la de recepción.",
            "La fecha de descarga desde SatNOGS no se registró; se conserva la de ingesta en la base.",
        ],
    })


@router.get("/procedencia/trama/{trama_id}")
def procedencia_trama(trama_id: int) -> dict:
    _archivo()
    tr = C.tramas()
    if trama_id not in tr.index:
        raise HTTPException(status_code=404, detail=f"La trama {trama_id} no está en el archivo.")
    fila = P.cargar_fila("tramas_originales", trama_id)
    d = C.decodificados()
    campos = d[d["frame_id"] == trama_id].drop_duplicates("field_name", keep="last")
    return P.procedencia_trama(fila, [
        {"field_name": r.field_name, "value_numeric": None if r.value_numeric != r.value_numeric else r.value_numeric,
         "value_text": r.value_text, "unit": r.unit} for r in campos.itertuples()])


@router.get("/orbital")
def orbital(t: str | None = None) -> dict:
    secciones = panel.ejecutar()["secciones"]
    out = {"pruebas": secciones.get("orbital", []), "divergencia": O.divergencia(),
           "marco": O.MARCO, "unidades": O.UNIDADES,
           "catalogo": {"tle": len(O.catalogo_tle()),
                        "epocas": [r.dict()["epoca_utc"] for r in O.catalogo_tle()[::max(1, len(O.catalogo_tle()) // 200)]]}}
    if t:
        out["posicion"] = O.posicion_en(a_datetime(instante_utc(_t(t))))
    return E.limpiar(out)


@router.get("/telemetria")
def telemetria() -> dict:
    _archivo()
    return T.resumen()


@router.get("/temporal")
def temporal(t: str = Query(panel.INSTANTE_REFERENCIA), campo: str = R.CAMPO_POR_DEFECTO) -> dict:
    rec = _reconstruir(t, campo)
    return {"instante_utc": rec["instante_utc"], "pruebas": [r.dict() for r in S.verificar(rec)],
            "globales": panel.ejecutar()["secciones"].get("temporal", []),
            "lecturas": rec["telemetria"]["lecturas"], "metodos": R.METODOS,
            "gemelo": {k: v for k, v in rec["gemelo"].items() if k != "lecturas_gemelo"},
            "orbita": {k: rec["orbita"].get(k) for k in ("instante_utc", "estado", "antiguedad_dias", "asociacion_temporal")},
            "modelo3d": rec["modelo3d"]}


@router.get("/diagnosticos")
def diagnosticos() -> dict:
    _archivo()
    return D.resumen()


@router.get("/reconstruccion")
def reconstruccion(t: str, campo: str = R.CAMPO_POR_DEFECTO) -> dict:
    rec = _reconstruir(t, campo)
    return {"reconstruccion": rec, "manifest": R.manifest(rec),
            "sincronizacion": [r.dict() for r in S.verificar(rec)]}


@router.get("/manifest")
def manifest(t: str, campo: str = R.CAMPO_POR_DEFECTO) -> Response:
    man = R.manifest(_reconstruir(t, campo))
    nombre = f"manifest_strand1_{man['reconstruccion']['id']}.json"
    return JSONResponse(man, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/manifest/verificar")
async def verificar_manifest(request: Request) -> dict:
    _archivo()
    cuerpo = await request.body()
    if len(cuerpo) > MAX_MANIFEST_BYTES:
        raise HTTPException(status_code=413, detail="Manifest demasiado grande.")
    try:
        man = json.loads(cuerpo)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail="El cuerpo no es JSON válido.") from exc
    if not isinstance(man, dict):
        raise HTTPException(status_code=422, detail="El manifest debe ser un objeto JSON.")
    try:
        _t(man["reconstruccion"]["instante_utc"])
        _campo(man["reconstruccion"]["parametros"]["campo_gobernante"])
    except (KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Al manifest le falta {exc}.") from exc
    try:
        res = R.verificar_manifest(man)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"resultados": [r.dict() for r in res], "recuento": E.recuento(res)}


@router.get("/informe")
def informe(t: str, campo: str = R.CAMPO_POR_DEFECTO, formato: str = Query("json", pattern="^(json|pdf)$")) -> Response:
    _reconstruir(t, campo)  # valida entradas antes del trabajo pesado
    inf = I.generar(t, campo)
    rid = inf["1_identificacion"]["reconstruccion_id"]
    if formato == "pdf":
        return Response(I.pdf(inf), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="informe_strand1_{rid}.pdf"'})
    return JSONResponse(inf, headers={"Content-Disposition": f'attachment; filename="informe_strand1_{rid}.json"'})


@router.get("/pruebas")
def pruebas() -> dict:
    return panel.pruebas_registradas()
