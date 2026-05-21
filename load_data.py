"""
Descarga de frames de telemetría reales del STRAND-1 (NORAD 39090)
desde la API abierta de SatNOGS DB.

Proyecto de grado: Caracterización del subsistema electrónico de
comunicaciones de un CubeSat mediante simulación de señales RF.

Autora: Mayelin Stefania Aguilar Vásquez
Universidad: UNAD — Ingeniería Electrónica
"""

import requests
import json
import csv
import os
""
#─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

SATELLITE_NORAD = 39090
MAX_FRAMES      = 100
OUTPUT_JSON     = "frames_STRAND1.json"
OUTPUT_CSV      = "frames_STRAND1.csv"

BASE_URL = "https://db.satnogs.org/api/telemetry/"
API_TOKEN = os.getenv("SATNOGS_API_TOKEN", "")
HEADERS  = {"Authorization": f"Token {API_TOKEN}"} if API_TOKEN else {}

# ─────────────────────────────────────────────
# DESCARGA DE FRAMES
# ─────────────────────────────────────────────
print(f"Conectando a SatNOGS API para STRAND-1 (NORAD {SATELLITE_NORAD})...")
print(f"Descargando hasta {MAX_FRAMES} frames...\n")

params     = {"satellite": SATELLITE_NORAD, "format": "json"}
all_frames = []
page_url   = BASE_URL
count      = 0

while page_url and count < MAX_FRAMES:
    response = requests.get(
        page_url,
        params=params if page_url == BASE_URL else None,
        headers=HEADERS
    )

    if response.status_code != 200:
        print(f"Error al conectar: {response.status_code}")
        print(f"Detalle: {response.text[:200]}")
        break

    data = response.json()

    if isinstance(data, list):
        frames   = data
        page_url = None
    else:
        frames   = data.get("results", [])
        page_url = data.get("next", None)
        params   = None

    for frame in frames:
        if count >= MAX_FRAMES:
            break
        all_frames.append(frame)
        count += 1

    print(f"  Frames descargados hasta ahora: {count}")

    if not page_url:
        break

print(f"\nTotal de frames descargados: {len(all_frames)}")

# ─────────────────────────────────────────────
# GUARDAR EN JSON Y CSV
# ─────────────────────────────────────────────
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(all_frames, f, indent=2, ensure_ascii=False)
print(f"Frames guardados en: {OUTPUT_JSON}")

if all_frames:
    keys = all_frames[0].keys()
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(all_frames)
    print(f"Frames guardados en: {OUTPUT_CSV}")

# ─────────────────────────────────────────────
# MOSTRAR PRIMEROS 3 FRAMES
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("MUESTRA DE LOS PRIMEROS 3 FRAMES DE TELEMETRÍA REAL")
print("="*60)

for i, frame in enumerate(all_frames[:3]):
    print(f"\n--- Frame #{i+1} ---")
    for key, value in frame.items():
        print(f"  {key:30s}: {value}")

# ─────────────────────────────────────────────
# ANÁLISIS BÁSICO DEL PAYLOAD
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("ANÁLISIS BÁSICO DE FRAMES")
print("="*60)

payloads = [f.get("frame", f.get("payload", "")) for f in all_frames
            if f.get("frame") or f.get("payload")]

print(f"\nFrames con payload disponible : {len(payloads)}")
if payloads:
    longitudes = [len(p) for p in payloads]
    print(f"Longitud promedio del payload : {sum(longitudes)/len(longitudes):.1f} caracteres hex")
    print(f"Longitud mínima              : {min(longitudes)} caracteres hex")
    print(f"Longitud máxima              : {max(longitudes)} caracteres hex")
    print(f"\nEjemplo de payload hex (frame 1):")
    print(f"  {payloads[0][:80]}{'...' if len(payloads[0]) > 80 else ''}")
    print(f"\nEso equivale a {len(payloads[0])//2} bytes de telemetría real.")

print("\n" + "="*60)
print("Listo. Archivos generados:")
print(f"  - {OUTPUT_JSON}  -> para procesar en GNU Radio")
print(f"  - {OUTPUT_CSV}   -> para analizar en Excel o Python")
print("="*60)
