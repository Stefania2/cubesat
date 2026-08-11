# Validación de captura IQ real

La simulación no sustituye una recepción SDR. Para contrastar el modelo con una
captura real se debe conservar el binario IQ y un manifiesto JSON con su contexto de
adquisición. El script `validar_captura_iq.py` comprueba que esa información exista,
calcula métricas objetivas y produce un informe que puede citarse junto al experimento.

## Formato admitido

- `complex64_le`: muestras complejas IEEE-754 de 32 bits por componente.
- `ci16_le`: pares I/Q de enteros con signo de 16 bits, *little endian*.

## Manifiesto mínimo

```json
{
  "iq_path": "strand1_2026-08-09.c64",
  "sample_format": "complex64_le",
  "sample_rate_hz": 76800,
  "center_frequency_hz": 437568000,
  "timestamp_utc": "2026-08-09T10:55:44Z",
  "satellite_norad_id": 39090,
  "receiver": "modelo de SDR y ganancia configurada",
  "antenna": "modelo, ganancia y polarización"
}
```

Puede añadir `reference_bits_path` cuando se disponga de la secuencia transmitida o de
un frame de referencia. Sin esa referencia el script informa duración, potencia, DC y
pico espectral, pero no declara una BER ni una decodificación como si estuvieran
validadas.

## Ejecución

```bash
python validar_captura_iq.py captura/strand1.json
```

El resultado se escribe como `captura/strand1_validacion.json`. La captura y sus
metadatos deben conservarse como un par inmutable: cambiar el binario sin actualizar
el manifiesto invalida la trazabilidad del experimento.
