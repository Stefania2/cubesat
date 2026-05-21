"""
Decodificación y análisis de frames de telemetría del STRAND-1 (NORAD 39090)
para caracterización del subsistema de comunicaciones.

Los frames están en formato hexadecimal crudo (raw payload).
Se analizan parámetros de la señal y se preparan para simulación en GNU Radio.

Proyecto de grado — Mayelin Stefania Aguilar Vásquez
UNAD — Ingeniería Electrónica
"""

import pandas as pd
import numpy as np
import struct
import json
from datetime import datetime

# ─────────────────────────────────────────────
# CARGAR FRAMES
# ─────────────────────────────────────────────
print("="*60)
print("DECODIFICACIÓN DE TELEMETRÍA REAL — STRAND-1")
print("="*60)

df = pd.read_csv("frames_STRAND1.csv")
frames = df[df['frame'].notna()].reset_index(drop=True)
print(f"\nTotal de frames cargados: {len(frames)}")
print(f"Rango de fechas:")
print(f"  Más reciente : {frames['timestamp'].iloc[0]}")
print(f"  Más antiguo  : {frames['timestamp'].iloc[-1]}")

# ─────────────────────────────────────────────
# ANÁLISIS DE PARÁMETROS DE LA SEÑAL
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("ANÁLISIS DE PARÁMETROS DE LA SEÑAL RF")
print("="*60)

longitudes_bytes = [len(f)//2 for f in frames['frame']]
print(f"\n--- Tamaño de los frames (bytes) ---")
print(f"  Promedio  : {np.mean(longitudes_bytes):.1f} bytes")
print(f"  Mínimo    : {np.min(longitudes_bytes)} bytes")
print(f"  Máximo    : {np.max(longitudes_bytes)} bytes")
print(f"  Desv. std : {np.std(longitudes_bytes):.1f} bytes")

# Frecuencia de transmisión conocida del STRAND-1
FREQ_HZ        = 437_568_000   # 437.568 MHz banda UHF
BAUD_RATE      = 9600          # 9600 bps BPSK estándar
BITS_POR_FRAME = np.mean(longitudes_bytes) * 8

print(f"\n--- Parámetros de la señal RF ---")
print(f"  Frecuencia de transmisión : {FREQ_HZ/1e6:.3f} MHz (banda UHF)")
print(f"  Modulación                : BPSK (Binary Phase Shift Keying)")
print(f"  Tasa de baudios           : {BAUD_RATE} bps")
print(f"  Bits promedio por frame   : {BITS_POR_FRAME:.0f} bits")
print(f"  Tiempo de transmisión     : {BITS_POR_FRAME/BAUD_RATE*1000:.1f} ms por frame")

# ─────────────────────────────────────────────
# ANÁLISIS DE ENTROPÍA (calidad de la señal)
# ─────────────────────────────────────────────
print(f"\n--- Análisis de entropía del payload ---")
print(f"  (Mayor entropía = señal más rica en información)")

entropias = []
for hex_frame in frames['frame']:
    raw = bytes.fromhex(hex_frame)
    # Calcular entropía de Shannon
    from collections import Counter
    counts = Counter(raw)
    total  = len(raw)
    entropia = -sum((c/total) * np.log2(c/total) for c in counts.values())
    entropias.append(entropia)

print(f"  Entropía promedio : {np.mean(entropias):.3f} bits/byte")
print(f"  Entropía máxima   : {np.max(entropias):.3f} bits/byte")
print(f"  Entropía mínima   : {np.min(entropias):.3f} bits/byte")
print(f"  Entropía teórica  : 8.000 bits/byte (señal perfectamente aleatoria)")

# ─────────────────────────────────────────────
# ANÁLISIS DE PATRONES EN LOS FRAMES
# ─────────────────────────────────────────────
print(f"\n--- Distribución de tamaños de frame ---")
from collections import Counter
dist = Counter(longitudes_bytes)
for tam, cnt in sorted(dist.items()):
    barra = "█" * cnt
    print(f"  {tam:3d} bytes: {barra} ({cnt} frames)")

# ─────────────────────────────────────────────
# MOSTRAR FRAMES DECODIFICADOS
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("CONTENIDO DE LOS PRIMEROS 5 FRAMES")
print("="*60)

for i in range(min(5, len(frames))):
    row      = frames.iloc[i]
    hex_data = row['frame']
    raw      = bytes.fromhex(hex_data)
    timestamp = row['timestamp']
    observer  = row['observer']

    print(f"\n{'─'*50}")
    print(f"Frame #{i+1}")
    print(f"  Timestamp  : {timestamp}")
    print(f"  Estación   : {observer}")
    print(f"  Tamaño     : {len(raw)} bytes ({len(raw)*8} bits)")
    print(f"  Hex        : {hex_data[:48]}{'...' if len(hex_data)>48 else ''}")
    print(f"  Binario    : {bin(raw[0])[2:].zfill(8)} {bin(raw[1])[2:].zfill(8)} {bin(raw[2])[2:].zfill(8)} ...")

    # Intentar interpretar primeros bytes como datos numéricos
    print(f"  Bytes dec  : {list(raw[:8])}")

# ─────────────────────────────────────────────
# EXPORTAR PARA GNU RADIO
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("EXPORTANDO DATOS PARA GNU RADIO")
print("="*60)

# Crear archivo binario concatenado para GNU Radio
with open("frames_STRAND1_gnuradio.bin", "wb") as f:
    for hex_frame in frames['frame']:
        raw = bytes.fromhex(hex_frame)
        f.write(raw)

total_bytes = sum(len(f)//2 for f in frames['frame'])
print(f"\nArchivo binario creado: frames_STRAND1_gnuradio.bin")
print(f"  Total bytes : {total_bytes}")
print(f"  Total bits  : {total_bytes * 8}")
print(f"  A {BAUD_RATE} bps esto representa {total_bytes*8/BAUD_RATE:.1f} segundos de señal")

# Crear resumen JSON para documentación
resumen = {
    "satelite": "STRAND-1",
    "norad_id": 39090,
    "frecuencia_mhz": FREQ_HZ / 1e6,
    "modulacion": "BPSK",
    "tasa_baudios": BAUD_RATE,
    "total_frames": len(frames),
    "bytes_promedio_por_frame": round(np.mean(longitudes_bytes), 1),
    "entropia_promedio": round(np.mean(entropias), 3),
    "fecha_mas_reciente": frames['timestamp'].iloc[0],
    "fecha_mas_antigua": frames['timestamp'].iloc[-1],
    "estaciones_observadoras": list(frames['observer'].unique())
}

with open("resumen_telemetria_STRAND1.json", "w", encoding="utf-8") as f:
    json.dump(resumen, f, indent=2, ensure_ascii=False)

print(f"\nResumen guardado en: resumen_telemetria_STRAND1.json")

print("\n" + "="*60)
print("ARCHIVOS GENERADOS PARA EL PROYECTO:")
print("  1. frames_STRAND1_gnuradio.bin  → cargar en GNU Radio")
print("  2. resumen_telemetria_STRAND1.json → documentación técnica")
print("="*60)
print("\nSiguiente paso: abrir GNU Radio y cargar el archivo .bin")
print("para simular la recepción y demodulación BPSK de la señal.")
print("="*60)