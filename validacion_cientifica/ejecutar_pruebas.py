"""Ejecuta la suite de pytest y registra el resultado de cada caso.

    ../strand/bin/python -m validacion_cientifica.ejecutar_pruebas          # pruebas de validacion
    ../strand/bin/python -m validacion_cientifica.ejecutar_pruebas --todo   # toda la suite del repositorio

Escribe `validacion_cientifica/resultados/pruebas_automatizadas.json`, que la
seccion «Validation Overview» muestra con su fecha y su commit. El estado de
cada caso es el que devolvio pytest al ejecutarlo; los casos de validacion
añaden con `record_property` el resultado esperado, el obtenido y la
tolerancia. Un caso omitido (skip) queda NOT_VERIFIED, nunca aprobado.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validacion_cientifica import estados as E  # noqa: E402
from validacion_cientifica import procedencia as P  # noqa: E402
from validacion_cientifica.panel import PRUEBAS_REGISTRADAS  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVOS_VALIDACION = ["tests/test_validacion_cientifica.py"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--todo", action="store_true", help="toda la suite, no solo la de validacion")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "junit.xml"
        args = [sys.executable, "-m", "pytest", "-q", f"--junitxml={xml}", "-o", "junit_family=xunit1"]
        if not a.todo:
            args += ARCHIVOS_VALIDACION
        proc = subprocess.run(args, cwd=RAIZ)
        raiz = ET.parse(xml).getroot()
    casos = []
    for tc in raiz.iter("testcase"):
        props = {p.get("name"): p.get("value") for p in tc.iter("property")}
        if tc.find("failure") is not None or tc.find("error") is not None:
            estado = E.FAILED
            nodo = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
            mensaje = (nodo.get("message") or "")[:500]
        elif tc.find("skipped") is not None:
            estado, mensaje = E.NOT_VERIFIED, (tc.find("skipped").get("message") or "")[:300]
        else:
            estado, mensaje = E.VALIDATED, ""
        casos.append({"id": f"{tc.get('classname')}::{tc.get('name')}", "estado": estado,
                      "duracion_s": float(tc.get("time") or 0), "categoria": props.get("categoria"),
                      "esperado": props.get("esperado"), "obtenido": props.get("obtenido"),
                      "tolerancia": props.get("tolerancia"), "mensaje": mensaje})
    reg = {"ejecutado_utc": E.ahora_utc(), "commit": P.commit_aplicacion(),
           "cambios_sin_confirmar": P.arbol_modificado(),
           "alcance": "suite completa" if a.todo else "tests/test_validacion_cientifica.py",
           "python": sys.version.split()[0], "codigo_salida_pytest": proc.returncode,
           "recuento": E.recuento(casos), "casos": casos}
    PRUEBAS_REGISTRADAS.parent.mkdir(parents=True, exist_ok=True)
    PRUEBAS_REGISTRADAS.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{reg['recuento']} → {PRUEBAS_REGISTRADAS.relative_to(RAIZ)}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
