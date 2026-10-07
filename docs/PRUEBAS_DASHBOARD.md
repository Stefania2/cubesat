# Pruebas del Dashboard STRAND-1

> **Nota**: la versión **canónica** vive integrada en la plataforma
> `telemetria_strand1/` (página `/enlace`). Se valida con su venv `strand_api`:
> tests unitarios en `cubesat/tests/test_plataforma_monitor.py` (corren con la
> suite completa) y los E2E del backend y del proxy Vite (REST + WS). Este
> dashboard (`cubesat/backend/` + `cubesat/dashboard/`) queda como referencia.

## Suite pytest

Requisitos: venv `strand` activado y dependencias de `backend/requirements.txt`.

```bash
source ../strand/bin/activate
cd cubesat
python -m pytest tests/test_dashboard_backend.py -q   # 16 pruebas del dashboard
python -m pytest tests/ -q                            # suite completa
```

Cobertura de `tests/test_dashboard_backend.py`:

| Grupo | Qué valida |
| --- | --- |
| Integridad | N_BITS = 18.776; TX = 18.776 bits {0,1}; RX de referencia válido (diff 0, SHA‑256 idénticos); detección de un error forzado; SHA‑256 reproducible. |
| Telemetría | Decodifica balizas reales (≥ 5.000); catálogo ≥ 15 parámetros con estados válidos; tensión de batería calibrada (~9.7 V); hay frames decodificados con payload. |
| Métricas | BER 0 con bits idénticos y tramas 100/100 válidas; sin datos → BER None y FFT/constelación no disponibles; FFT ordenada y constelación de 400 puntos desde un tap IQ sintético. |
| API/WS | 11 endpoints responden 200; `/api/config` expone 437.568 MHz y 18.776 bits; snapshot WS con status/metrics/integrity/telemetry y `ping`→`pong`. |

## Validación end-to-end

```bash
# 1. Backend
source ../strand/bin/activate
cd cubesat
uvicorn backend.main:app --port 8150

# 2. Frontend (otra terminal)
cd cubesat/dashboard
npm install        # solo la primera vez (o usar el node_modules del proyecto)
npm run dev        # http://localhost:5175  (proxy /api y /ws → 8150)

# 3. En el navegador
#    · inicia una simulación con SNR y espera a que termine
#    · comprueba BER, espectro, constelación e integridad con valores reales
#    · comprueba que RSSI y FER aparecen como "—" con su nota N/A
```

### Script de validación automática

`/tmp`/suite de prueba (ver también `tests/`):
`python -m pytest` + abrir el dashboard y lanzar `POST /api/simulate` con
`snr_db=10`: la integridad debe quedar `valido=True` con 18.776/18.776 y el
SHA‑256 de entrada y salida idénticos; el BER en la gráfica histórico debe
situarse en el eje bajo del rango.