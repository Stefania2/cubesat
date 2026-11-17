"""Informes cientificos de una reconstruccion: JSON y PDF.

El PDF se escribe a mano (PDF 1.4, fuentes Type 1 estandar, WinAnsiEncoding)
para no añadir dependencias a la funcion de Vercel. Es texto, sin graficas.

Cada valor del informe lleva su naturaleza entre corchetes: [MEDIDO],
[CALCULADO], [DERIVADO] o [ESTIMADO]. Las conclusiones se construyen a partir
de los estados de las pruebas; no hay texto que afirme algo que una prueba no
haya mostrado.
"""

from __future__ import annotations

import textwrap

from . import estados as E
from . import panel
from . import reconstruccion as R
from . import sincronizacion as S

LIMITACIONES = [
    "STRaND-1 no está operativo: todo es reconstrucción de un archivo, no hay telemetría en directo.",
    "La baliza no lleva fecha de medición; se asocia a la fecha de recepción en tierra de SatNOGS (resolución 1 s).",
    "No existen rangos de operación documentados de los componentes: ninguna magnitud está validada físicamente.",
    "La telemetría decodificada abarca 2016-11-30 a 2023-01-29; los TLE históricos del proyecto empiezan a "
    "finales de 2022 (SatNOGS Network). Para la mayor parte del archivo no hay posición orbital con cota de error.",
    "El criterio de antigüedad del TLE se estimó con TLE de 2022-2026 (consistencia entre TLE, no error absoluto).",
    "La plataforma convierte TEME a terrestre con UT1≈UTC y sin movimiento del polo (error < 0,6 km, prueba ORB-D2).",
    "El archivo sella la capa original tal como está en la base; las respuestas originales de la API de SatNOGS "
    "no se guardaron al ingerir.",
    "STRaND-1 no transmite actitud: la orientación del modelo 3D no es un dato.",
    "Una desviación estadística no se interpreta como falla física: no hay registro de operaciones que lo confirme.",
    "En 552 instantes hay dos valores distintos de una magnitud con la misma marca de tiempo; el gemelo leído "
    "desde la base puede elegir cualquiera de los dos (el archivo desempata de forma estable).",
]


def generar(instante: str, campo: str = R.CAMPO_POR_DEFECTO) -> dict:
    rec = R.reconstruir(instante, campo)
    man = R.manifest(rec)
    sync = [r.dict() for r in S.verificar(rec)]
    val = panel.resumen()
    orb = rec["orbita"]
    prop = orb.get("propagacion") or {}
    lect = rec["telemetria"]["lecturas"]

    conclusiones = []
    if all(r["estado"] in (E.VALIDATED, E.NOT_AVAILABLE) for r in sync):
        conclusiones.append("La telemetría, el gemelo, el modelo 3D y la órbita se refieren al mismo "
                            "instante UTC (pruebas SYNC sin fallos).")
    else:
        conclusiones.append("Hay pruebas de sincronización FALLIDAS: la reconstrucción no es coherente.")
    if orb["estado"] == E.NOT_AVAILABLE:
        conclusiones.append("No se presenta posición orbital: el TLE más cercano queda fuera del intervalo "
                            "caracterizado.")
    else:
        conclusiones.append(f"Posición orbital calculada con un TLE de {orb['antiguedad_dias']} días; estado "
                            f"{orb['estado']} según el criterio empírico de antigüedad.")
    frescas = sum(1 for l in lect if l.get("frescura") == "fresca")
    conclusiones.append(f"{frescas} de {len(lect)} magnitudes tienen una medición de menos de 10 min antes del "
                        "instante; el resto describe el pasado del satélite.")
    d = rec["diagnostico"]
    conclusiones.append(f"Diagnóstico de {campo}: {d['interpretacion']} (estadístico; no es una falla confirmada).")
    rv = [r for r in val["secciones"].get("reproducibilidad", [])]
    if rv and all(r["estado"] == E.VALIDATED for r in rv):
        conclusiones.append("La reconstrucción de referencia se reproduce bit a bit desde su manifest.")

    return E.limpiar({
        "1_identificacion": {"reconstruccion_id": man["reconstruccion"]["id"], "mision": "STRaND-1",
                             "norad_id": 39090, "campo_gobernante": campo},
        "2_fecha_utc": {"instante_reconstruido": rec["instante_utc"], "generado": man["reconstruccion"]["generado_utc"]},
        "3_fuentes": {"telemetria": man["fuente_telemetria"]["descripcion"],
                      "archivo": man["datos"], "orbita": orb["tle"]["fuente"] if orb.get("tle") else None},
        "4_procedencia_telemetria": rec["procedencia"]["tramas"],
        "5_tle": orb.get("tle"),
        "6_metodologia_sgp4": {"implementacion": prop.get("implementacion_sgp4"), "marco": man["orbita"]["marco_referencia"],
                               "modelo_tiempo": man["orbita"]["modelo_tiempo"], "modelo_tierra": man["orbita"]["modelo_tierra"],
                               "referencia": "Vallado et al. (2006), AIAA 2006-6753"},
        "7_resultados_orbitales": {"naturaleza": E.CALCULADO, "estado": orb["estado"],
                                   "antiguedad_dias": orb.get("antiguedad_dias"),
                                   "evaluacion": orb["evaluacion_antiguedad"], "propagacion": prop or None},
        "8_validacion_coordenadas": [r for r in val["secciones"].get("orbital", [])
                                     if r["id"].startswith(("ORB-C", "ORB-D"))],
        "9_telemetria": {"naturaleza": E.MEDIDO, "lecturas": lect},
        "10_sincronizacion": sync,
        "11_diagnosticos": {"naturaleza": E.DERIVADO, **d},
        "12_pruebas": {"servidor": val["recuento"], "automatizadas": val.get("pruebas_automatizadas"),
                       "detalle": val["secciones"]},
        "13_limitaciones": LIMITACIONES,
        "14_conclusiones": conclusiones,
        "manifest": man,
    })


# ── PDF ─────────────────────────────────────────────────────────────────────

_SUSTITUTOS = {"≤": "<=", "≥": ">=", "≈": "~", "→": "->", "←": "<-", "↔": "<->", "−": "-", "ω": "w",
               "⊕": "E", "″": '"', "′": "'", "Δ": "D", "σ": "s", "×": "x", "·": "·", "√": "sqrt"}


def _latin(texto: str) -> bytes:
    for a, b in _SUSTITUTOS.items():
        texto = texto.replace(a, b)
    return texto.encode("cp1252", errors="replace")


def _esc(b: bytes) -> bytes:
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class _Pdf:
    ANCHO, ALTO, MARGEN = 595, 842, 50

    def __init__(self) -> None:
        self.paginas: list[list[bytes]] = [[]]
        self.y = self.ALTO - self.MARGEN

    def linea(self, texto: str, tam: float = 9, negrita: bool = False, sangria: int = 0) -> None:
        ancho = int((self.ANCHO - 2 * self.MARGEN - sangria) / (tam * 0.5))
        for trozo in textwrap.wrap(texto, ancho) or [""]:
            if self.y < self.MARGEN + tam:
                self.paginas.append([])
                self.y = self.ALTO - self.MARGEN
            fuente = b"/F2" if negrita else b"/F1"
            self.paginas[-1].append(b"BT %s %.1f Tf %d %d Td (%s) Tj ET" % (
                fuente, tam, self.MARGEN + sangria, self.y, _esc(_latin(trozo))))
            self.y -= tam * 1.35

    def espacio(self, n: float = 6) -> None:
        self.y -= n

    def bytes(self) -> bytes:
        objs: list[bytes] = []
        n_pag = len(self.paginas)
        # 1 catalogo, 2 paginas, 3 F1, 4 F2, luego (pagina, contenido) por pagina
        kids = b" ".join(b"%d 0 R" % (5 + 2 * i) for i in range(n_pag))
        objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objs.append(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n_pag))
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        for i, cont in enumerate(self.paginas):
            pie = b"BT /F1 7 Tf %d 25 Td (%s) Tj ET" % (self.MARGEN, _esc(_latin(
                f"STRaND-1 Scientific Validation - página {i + 1} de {n_pag}")))
            flujo = b"\n".join(cont + [pie])
            objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << "
                        b"/F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>" % (self.ANCHO, self.ALTO, 6 + 2 * i))
            objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(flujo), flujo))
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        desp = []
        for k, o in enumerate(objs, start=1):
            desp.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (k, o)
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for d in desp:
            out += b"%010d 00000 n \n" % d
        out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
        return bytes(out)


def _v(x) -> str:
    if x is None:
        return "NO DISPONIBLE"
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def pdf(inf: dict) -> bytes:
    p = _Pdf()
    p.linea("STRaND-1 · Informe de validación científica de una reconstrucción", 14, True)
    p.linea(f"Reconstrucción {inf['1_identificacion']['reconstruccion_id']} · instante "
            f"{inf['2_fecha_utc']['instante_reconstruido']} · generado {inf['2_fecha_utc']['generado']}", 8)
    p.linea("Naturaleza de cada valor: [MEDIDO] recibido del satélite, [CALCULADO] modelo determinista, "
            "[DERIVADO] estadístico sobre medidas, [ESTIMADO] depende de supuestos no verificados.", 8)
    p.espacio(8)

    def titulo(t: str) -> None:
        p.espacio(6)
        p.linea(t, 11, True)

    titulo("1. Identificación")
    for k, v in inf["1_identificacion"].items():
        p.linea(f"{k}: {_v(v)}", sangria=10)
    titulo("2. Fecha y hora UTC")
    for k, v in inf["2_fecha_utc"].items():
        p.linea(f"{k}: {_v(v)}", sangria=10)
    titulo("3. Fuentes de datos")
    f = inf["3_fuentes"]
    p.linea(f"Telemetría: {f['telemetria']}", sangria=10)
    p.linea(f"Archivo sellado: huella SHA-256 {f['archivo']['huella_conjunto_sha256']} (sellado "
            f"{f['archivo']['sellado_utc']})", sangria=10)
    for n, m in f["archivo"]["ficheros"].items():
        p.linea(f"{m['ruta']} · {m['capa']} · {m['filas']} filas · {m['sha256_contenido']}", 7, sangria=20)
    p.linea(f"Órbita: {_v(f['orbita'])}", sangria=10)
    titulo("4. Procedencia de la telemetría")
    for e in inf["4_procedencia_telemetria"]:
        p.linea(f"trama {e['trama_id']} · recibida {e['recibida_utc']} · obs {_v(e['observacion_id'])} · "
                f"{e['raw_hex']} · sha256 {e['sha256'][:16]}…", 7, sangria=10)
    titulo("5. TLE utilizado")
    tle = inf["5_tle"]
    if tle:
        p.linea(tle["linea1"], 8, sangria=10)
        p.linea(tle["linea2"], 8, sangria=10)
        p.linea(f"Época {tle['epoca_utc']} · {tle['fuente']}", 8, sangria=10)
    else:
        p.linea("NO DISPONIBLE: no hay TLE en el catálogo.", sangria=10)
    titulo("6. Metodología SGP4")
    for k, v in inf["6_metodologia_sgp4"].items():
        p.linea(f"{k}: {_v(v)}", 8, sangria=10)
    titulo("7. Resultados orbitales [CALCULADO]")
    r7 = inf["7_resultados_orbitales"]
    p.linea(f"Estado: {r7['estado']} · antigüedad del TLE: {_v(r7['antiguedad_dias'])} días", sangria=10)
    p.linea(r7["evaluacion"]["detalle"], 8, sangria=10)
    for k, c in (r7["evaluacion"].get("por_proposito") or {}).items():
        p.linea(f"{c['descripcion']}: {c['estado']} (admisible {c['antiguedad_admisible_dias']} d, "
                f"tolerancia {c['tolerancia_km']} km) [ESTIMADO]", 8, sangria=20)
    pr = r7.get("propagacion")
    if pr and pr.get("posicion_km"):
        p.linea(f"r TEME (km): {pr['posicion_km']['x']:.3f}, {pr['posicion_km']['y']:.3f}, {pr['posicion_km']['z']:.3f}", 8, sangria=10)
        p.linea(f"v TEME (km/s): {pr['velocidad_km_s']['vx']:.6f}, {pr['velocidad_km_s']['vy']:.6f}, "
                f"{pr['velocidad_km_s']['vz']:.6f}", 8, sangria=10)
        te = pr["terrestre"]
        p.linea(f"Latitud {te['latitud_deg']}°, longitud {te['longitud_deg']}°, altura {te['altura_km']} km (WGS-84)", 8, sangria=10)
    titulo("8. Validación de coordenadas y del propagador")
    for r in inf["8_validacion_coordenadas"]:
        p.linea(f"{r['id']} {r['estado']} · {r['nombre']} · tolerancia {_v(r['tolerancia'])}", 8, sangria=10)
    titulo("9. Telemetría en el instante [MEDIDO]")
    for l in inf["9_telemetria"]["lecturas"]:
        p.linea(f"{l['campo']}: {_v(l['valor'])} {l['unidad'] or ''} · {l['asociacion']} · medida "
                f"{_v(l['medida_utc'])} · desfase {_v(l['desfase_s'])} s · {l['estado']}", 7, sangria=10)
    titulo("10. Sincronización temporal")
    for r in inf["10_sincronizacion"]:
        p.linea(f"{r['id']} {r['estado']} · {r['nombre']}", 8, sangria=10)
    titulo("11. Diagnóstico estadístico [DERIVADO]")
    d = inf["11_diagnosticos"]
    p.linea(f"{d['campo']}: etiqueta {d['etiqueta']} → {d['interpretacion']} · z = {_v(d['z'])} · "
            f"mediana móvil {_v(d['mediana_movil'])}", 8, sangria=10)
    p.linea(f"Parámetros: {d['parametros']}", 7, sangria=10)
    p.linea(f"Falla confirmada: {d['falla_confirmada']['detalle']}", 8, sangria=10)
    titulo("12. Pruebas ejecutadas")
    rc = inf["12_pruebas"]["servidor"]
    p.linea(f"En servidor: {rc['total']} · VALIDATED {rc['VALIDATED']} · WARNING {rc['WARNING']} · FAILED "
            f"{rc['FAILED']} · NOT_VERIFIED {rc['NOT_VERIFIED']} · NOT_AVAILABLE {rc['NOT_AVAILABLE']}", 8, sangria=10)
    for sec, lista in inf["12_pruebas"]["detalle"].items():
        for r in lista:
            p.linea(f"[{sec}] {r['id']} {r['estado']} · {r['nombre']}", 7, sangria=20)
    au = inf["12_pruebas"].get("automatizadas") or {}
    p.linea(f"Suite automatizada (registrada): {au.get('ejecutado_utc', 'NO EJECUTADA')} · commit "
            f"{_v(au.get('commit'))} · {au.get('recuento', au.get('detalle', ''))}", 8, sangria=10)
    titulo("13. Limitaciones conocidas")
    for l in inf["13_limitaciones"]:
        p.linea(f"- {l}", 8, sangria=10)
    titulo("14. Conclusiones técnicas")
    for c in inf["14_conclusiones"]:
        p.linea(f"- {c}", 9, sangria=10)
    return p.bytes()
