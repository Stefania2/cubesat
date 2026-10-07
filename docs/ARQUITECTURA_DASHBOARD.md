# Arquitectura del Dashboard STRAND-1

> **Nota**: la versión **canónica** está integrada en la plataforma
> `telemetria_strand1/` (página `/enlace`, módulo `backend/app/services/enlace_monitor.py`,
> router `/api/enlace/*` + `WS /ws/enlace`, frontend `pages/EnlaceRF.tsx`). Este
> dashboard (`cubesat/backend/` + `cubesat/dashboard/`) queda como implementación
> autónoma de referencia. La lógica documentada aquí es la misma.

Capa de **monitoreo y visualización** del enlace RF simulado de STRaND‑1. Se
superpone al flujo existente del proyecto **sin modificar la cadena de
18.776 bits** (regla crítica).

## Flujo de datos

```
                                  ┌───────────── cadena GNU Radio ───────────┐
   frames_STRAND1_bits.bin        │   cadena_strand1_awgn.py --snr-db X       │
   (TX · 18.776 bytes 0/1) ──────►│   BPSK RRC → AWGN → RRC match → slicer   │
                                  └────┬───────────────┬────────────────────┘
                                       │               │
                          bits_rx_sim.bin (18.776)   iq_sim.c64 (tap IQ real
                                       │               │  tras AWGN, Fs 76800)
                                       ▼               ▼
                            ┌── backen/ (FastAPI) ───────────────┐
                            │ integridad.py    metrics_service.py│
                            │ telemetry_service.py  gnuradio_if │
                            └───────────┬────────────────────────┘
                                        │  REST /api/*  +  WebSocket /ws
                                        ▼
                              dashboard/ (React + Vite, tema oscuro)
                              STRAND-1 Ground Station · RF Communication
                              Link Monitoring
```

El backend **lanza** la simulación como subproceso
(`GNU_RadioRunner` en `backend/gnuradio_interface.py`), espera a que termine y
calcula las métricas desde los **archivos reales** que produce la cadena; no
hay valores inventados. En paralelo, difunde el estado por WebSocket a cualquier
cliente conectado.

## Componentes del backend (`backend/`)

| Módulo | Responsabilidad |
| --- | --- |
| `config.py` | Parámetros del enlace (18.776 bits, 9600 baud, 76.800 Hz, 437.568 MHz), rutas y límites de ingeniería. |
| `models.py` | Esquemas Pydantic de salida (status, metrics, telemetry, spectrum, constellation, integrity, logs). |
| `websocket_manager.py` | Gestor de conexiones WS; única salida en tiempo real. |
| `gnuradio_interface.py` | Ejecuta `cadena_strand1_awgn.py` con `--input/--output/--iq-output/--snr-db/--seed`; estados `IDLE/RUNNING/STOPPED/ERROR`. |
| `integridad.py` | Verifica los 18.776 bits TX vs RX (longitud, diferencia por bit, SHA‑256). |
| `telemetry_service.py` | Reutiliza el decodificador validado `strand_amsat.py` (AMSAT‑UK) sobre las balizas reales del proyecto; fuente de verdad. |
| `metrics_service.py` | BER medido, potencia del tap IQ, ruido fuera de banda (Welch), FFT de espectro y constelación BPSK a tasa de símbolo. |
| `main.py` | Endpoints REST + WebSocket `/ws`. |

## Fuentes de verdad (no se inventa nada)

1. **Bits**: `frames_STRAND1_bits.bin` (TX) y `bits_rx_sim.bin` (RX, salida real
   de GNU Radio). El consumidor **no vuelve a desempaquetar**: 1 byte = 1 bit.
   `integridad.validar_bits()` exige `len == 18.776` y `SHA‑256` idénticos.
2. **Métricas de canal**: BER medido sobre los 18.776 bits; FFT Welch y
   constelación desde `iq_sim.c64` (tap de copia en paralelo; no altera el flujo).
3. **Telemetría**: decodificación con `telemetria_strand1/backend/app/services/strand_amsat.py`
   (spec AMSAT‑UK corregida) de las 5.830 balizas ya registradas por SatNOGS en
   `telemetria_strand1/telemetria_decodificada_good.csv`. El CSV histórico fue
   decodificado con el decoder oficial (bug de DATA_SIZE → voltajes de 2 V); el
   dashboard **re‑decodifica** con la versión corregida y obtiene los valores
   calibrados reales (~9.7 V de batería, corrientes de paneles, magnetómetros).

## Métricas honestas: qué se muestra y qué no

| Métrica | Valor |
| --- | --- |
| SNR configurada | 0–12 dB (slider, misma calibración del proyecto). |
| BER medido | No errores / N·errores sobre 18.776 bits. |
| Potencia relativa | `10·log10(mean(|iq|²))` del tap real (dBFs). |
| Ruido fuera de banda | Media Welch fuera de la banda RRC (±6.480 Hz). |
| FFT / constelación | Reales, desde el tap IQ. |
| RSSI | `None` + nota `N/A — modelo baseband-equivalente: no hay potencia RF en dBm`. |
| FER | `None` + nota `N/A — la cadena mínima no tiene tramas AX.25 ni FEC` (el modelo avanzado sí reporta `ax25_frames_validos`). |

## Frontend (`dashboard/`)

React 19 + Vite + Recharts, tema oscuro tipo consola de estación terrena.
Paneles: estado del enlace y controles (iniciar/detener/reset), métricas,
integridad de bits, espectro, constelación, BER‑vs‑SNR histórico y telemetría
AMSAT decodificada. En desarrollo el proxy de Vite redirige `/api` y `/ws` al
backend (puertos 5175/4175 → 8150).