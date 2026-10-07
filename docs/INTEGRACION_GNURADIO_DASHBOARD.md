# Integración GNU Radio → Dashboard

El dashboard es la capa de visualización del enlace; **no reimplementa ni
altera la cadena validada** `cadena_strand1_awgn.py`.

## Cómo se lanza la cadena desde el backend

`backend/gnuradio_interface.py` lanza:

```bash
$PYTHON cadena_strand1_awgn.py \
    --input   frames_STRAND1_bits.bin \
    --output  backend/_estado/bits_rx_sim.bin \
    --iq-output backend/_estado/iq_sim.c64 \
    --snr-db  <0..12> \
    --seed    11
```

- `frames_STRAND1_bits.bin` = los **18.776 bits** del proyecto (1 byte = 1 bit,
  normalizado por `np.unpackbits` en `generar_iq_bpsk_desde_bin.py`).
- La cadena NO usar `Unpack Bits`: el File Source Byte alimenta directamente el
  mapeo `bytes→[−1,1]` (`chunks_to_symbols_bf`), shaping RRC (α=0.35, 8
  muestras/símbolo), AWGN calibrado, RRC match, `delay(7)`+`keep_one_in_n(8)`+
  `skiphead(11)` y `binary_slicer_fb`.
- `--iq-output` es un **tap de copia**: un `file_sink` complejo conectado en
  paralelo a la salida del AWGN, de modo que la rama de demodulación no cambia
  y el dashboard recibe el IQ real del canal a 76.800 Hz.

## Qué lee el backend de esos archivos

| Archivo | Consumido por | Uso |
| --- | --- | --- |
| `bits_rx_sim.bin` | `integridad.py`, `metrics_service.py` | Comparación bit a bit contra TX, SHA‑256, contador de errores → BER. |
| `iq_sim.c64` | `metrics_service.py` | FFT Welch (nfft 4096, ventana Hanning) y constelación muestreando a 1/8 (tasa de símbolo). |

## Reglas críticas preservadas

1. **18.776 bits exactos** de entrada a salida: `integridad.assert_bits_completos`
   y `validar_bits()` (longitud + diferencia + SHA‑256).
2. **Sin `Unpack Bits`** en la cadena de bits (el consumidor del binario ya
   normalizó con `np.unpackbits` en origen).
3. **Sin métricas inventadas**: todo proviene de los archivos reales de la
   cadena o del decodificador AMSAT. RSSI y FER → `None` con nota explicativa
   (modelo baseband‑equivalente; sin tramas AX.25/FEC).

## Verificación manual

```bash
source ../strand/bin/activate
cd cubesat
python cadena_strand1_awgn.py --snr-db 10
python - <<'PY'
from backend import integridad, config
print(integridad.validar_bits(config.BITS_RX_SIM))  # valido=True, diff=0
PY
```