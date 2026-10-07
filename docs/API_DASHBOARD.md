# API del Dashboard STRAND-1

Backend FastAPI at `backend/main.py`. Documentación interactiva en
`/docs` y `/redoc`. Todos los endpoints responden JSON; en desarrollo el
frontend habla con rutas relativas a través del proxy de Vite.

## REST

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/api/health` | Estado del proceso y nº de conexiones WebSocket activas. |
| GET | `/api/status` | `link_status` (ACTIVE/OFFLINE), `sim_status` (IDLE/RUNNING/STOPPED/ERROR), tramas recibidas/válidas/error y último mensaje del subproceso. |
| GET | `/api/config` | Parámetros del enlace: modulación, 437.568 MHz, 9600 bps, 8 muestras/símbolo, α=0.35, 18.776 bits esperados, rangos SNR. |
| GET | `/api/telemetry` | Balizas decodificadas con `strand_amsat`: total, último timestamp, catálogo de parámetros (15+, con estado OK/NORMAL/ALERTA o N/A) y últimas 20 balizas. |
| GET | `/api/frames` | Igual que `/api/telemetry` (las tramas útiles son las balizas AMSAT decodificadas). |
| GET | `/api/metrics` | SNR, BER medido, RSSI (None + nota), FER (None + nota), potencia relativa dBFs, ruido estimado, tramas. |
| GET | `/api/spectrum` | FFT Welch real del tap IQ: `datos[{freq_hz, power_db}]`, `disponible` y nota si no hay simulación todavía. |
| GET | `/api/constellation` | Constelación BPSK real: `puntos[{i,q}]` a tasa de símbolo. |
| GET | `/api/integrity` | Validación de los 18.776 bits: longitud entrada/salida, diferencia, SHA‑256 de ambos y `valido`. |
| GET | `/api/history` | Historial de la sesión (SNR, BER, potencia) para la gráfica BER‑vs‑SNR. |
| GET | `/api/log` | Log del subproceso GNU Radio. |
| POST | `/api/simulate` | `{"action": "start"|"stop"|"reset", "snr_db": 0–12}`. Inicia la cadena GNU Radio con SNR y seed fija; difunde resultados por WebSocket al terminar. `409` si ya hay una simulación corriendo. |

## WebSocket `/ws`

Mensajes JSON `{type, timestamp, payload}`:

| type | Payload | Cuándo |
| --- | --- | --- |
| `status_update` | estado del enlace | snapshot y cada cambio. |
| `metrics_update` | métricas | snapshot y al terminar una simulación. |
| `integrity_update` | resultado de los 18.776 bits | snapshot y al terminar. |
| `telemetry_update` | balizas decodificadas | snapshot y al terminar. |
| `spectrum_ready` | FFT del tap IQ | solo si hay simulación con tap disponible. |
| `constellation_ready` | constelación | solo si hay simulación. |
| `log_batch` | log del subproceso | al finalizar la simulación. |
| `pong` | `{}` | respuesta a un mensaje de texto `"ping"`. |

El cliente envía el texto `"ping"` y el servidor responde `pong` (protocolo de
ultraje de vida para detectar conexiones muertas).

## Ejemplos

```bash
curl http://127.0.0.1:8150/api/status
curl -X POST http://127.0.0.1:8150/api/simulate \
     -H 'Content-Type: application/json' -d '{"action":"start","snr_db":8}'
```