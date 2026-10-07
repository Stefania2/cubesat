const BASE = '/api'

async function peticion(path, options) {
  const r = await fetch(BASE + path, options)
  if (!r.ok) {
    let detalle = r.statusText
    try {
      detalle = (await r.json()).detail || detalle
    } catch {
      /* cuerpo no JSON */
    }
    throw new Error(`${r.status} ${detalle}`)
  }
  return r.json()
}

export const API = {
  get: (path) => peticion(path),
  simulate: (action, snr_db) =>
    peticion('/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, snr_db }),
    }),
}

export function wsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws`
}