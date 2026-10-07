import { useEffect, useReducer, useRef, useState } from 'react'
import { API, wsUrl } from './api.js'

const estadoInicial = {
  status: null,
  metrics: null,
  integrity: null,
  telemetry: null,
  spectrum: null,
  constellation: null,
  config: null,
  history: [],
  logs: [],
  conectado: false,
}

function reducer(state, accion) {
  switch (accion.tipo) {
    case 'ws':
      return { ...state, conectado: accion.valor }
    case 'set':
      return { ...state, [accion.clave]: accion.valor }
    default:
      return state
  }
}

export function useDash() {
  const [state, dispatch] = useReducer(reducer, estadoInicial)
  const [error, setError] = useState(null)
  const [ocupado, setOcupado] = useState(false)
  const wsRef = useRef(null)

  const cargarRest = async () => {
    try {
      const [config, status, metrics, integrity, telemetry, spectrum, constellation, history, logs] =
        await Promise.all([
          API.get('/config'),
          API.get('/status'),
          API.get('/metrics'),
          API.get('/integrity'),
          API.get('/telemetry'),
          API.get('/spectrum'),
          API.get('/constellation'),
          API.get('/history'),
          API.get('/log'),
        ])
      for (const [clave, valor] of Object.entries({
        config, status, metrics, integrity, telemetry, spectrum, constellation, history, logs,
      })) {
        dispatch({ tipo: 'set', clave, valor })
      }
    } catch (e) {
      setError(String(e))
    }
  }

  useEffect(() => {
    cargarRest()
    const ws = new WebSocket(wsUrl())
    wsRef.current = ws
    ws.onopen = () => dispatch({ tipo: 'ws', valor: true })
    ws.onclose = () => dispatch({ tipo: 'ws', valor: false })
    ws.onerror = () => setError('Error de conexión WebSocket')
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (!msg?.type) return
        const mapeo = {
          status_update: 'status',
          metrics_update: 'metrics',
          integrity_update: 'integrity',
          telemetry_update: 'telemetry',
          spectrum_ready: 'spectrum',
          constellation_ready: 'constellation',
          history_update: 'history',
        }
        if (mapeo[msg.type] === 'history') {
          dispatch({ tipo: 'set', clave: 'history', valor: msg.payload })
        } else if (mapeo[msg.type]) {
          dispatch({ tipo: 'set', clave: mapeo[msg.type], valor: msg.payload })
        }
      } catch {
        /* mensaje malformado: se ignora */
      }
    }
    return () => {
      ws.close()
      wsRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const simular = async (action) => {
    setOcupado(true)
    setError(null)
    try {
      dispatch({ tipo: 'set', clave: 'status', valor: await API.simulate(action, state.config?.snr_default_db) })
    } catch (e) {
      setError(String(e))
    } finally {
      setOcupado(false)
    }
  }

  return { state, error, ocupado, simular }
}