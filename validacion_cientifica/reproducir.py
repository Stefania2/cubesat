"""Reconstruir un instante o repetir una reconstruccion desde su manifest.

    # generar: reconstruccion + manifest.json + informe (JSON y PDF)
    ../strand/bin/python -m validacion_cientifica.reproducir --instante 2021-03-01T12:00:00Z --salida rec/

    # repetir y comprobar: misma huella de resultados → VALIDATED
    ../strand/bin/python -m validacion_cientifica.reproducir rec/manifest.json

No necesita base de datos ni red: lee el archivo sellado del repositorio.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validacion_cientifica import estados as E  # noqa: E402
from validacion_cientifica import informe as I  # noqa: E402
from validacion_cientifica import reconstruccion as R  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", nargs="?", help="manifest.json que repetir")
    ap.add_argument("--instante", help="instante ISO 8601 con zona (p. ej. 2021-03-01T12:00:00Z)")
    ap.add_argument("--campo", default=R.CAMPO_POR_DEFECTO)
    ap.add_argument("--salida", default=".", help="carpeta de salida al generar")
    a = ap.parse_args()

    if a.manifest:
        man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        res = R.verificar_manifest(man)
        for r in res:
            print(f"{r.estado:13s} {r.id:11s} {r.nombre}")
        return 0 if all(r.estado in (E.VALIDATED, E.WARNING) for r in res) else 1

    if not a.instante:
        ap.error("indique un manifest o --instante")
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    inf = I.generar(a.instante, a.campo)
    (out / "manifest.json").write_text(json.dumps(inf["manifest"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "informe.json").write_text(json.dumps(inf, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "informe.pdf").write_bytes(I.pdf(inf))
    print(f"reconstruccion {inf['manifest']['reconstruccion']['id']} → {out}/manifest.json, informe.json, informe.pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
