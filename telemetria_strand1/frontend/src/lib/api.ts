/** Cliente de la API de telemetría. */

import { useCallback, useEffect, useState } from 'react'

export type FrameStatus = 'decoded' | 'partially_decoded' | 'unclassified' | 'error'

export interface Frame {
  id: number
  raw_hex: string
  norad_id: number
  observer: string | null
  timestamp: string
  observation_id: number | null
  station_id: number | null
  app_source: string | null
  byte_count: number
  entropy_bits_per_byte: number | null
  printable_ratio: number | null
  distinct_bytes: number | null
  status: FrameStatus
  frame_type: string
  protocol: string | null
  analysis: Record<string, any> | null
}

export interface FrameList {
  total: number
  items: Frame[]
  limit: number
  offset: number
}

export interface Kpis {
  frames_procesados: number
  frames_decodificados: number
  porcentaje_decodificado: number
  observaciones: number
  estaciones: number
  ultimo_frame: string | null
  primer_frame: string | null
  es_demo: boolean
  fuente: string
}

export interface SeriePunto {
  bucket: string
  recibidos: number
  procesados: number
  decodificados: number
}

export interface Serie {
  rango: string
  granularidad: string
  puntos: SeriePunto[]
  total_en_rango: number
}

export interface Observation {
  observation_id: number
  norad_id: number
  satellite_name: string | null
  station_id: number | null
  station_name: string | null
  station_owner: string | null
  observer: string | null
  status: string | null
  frequency_hz: number | null
  mode: string | null
  transmitter: string | null
  start: string | null
  end: string | null
  max_elevation_deg: number | null
  frame_count: number
}

export interface ObservationList {
  total: number
  items: Observation[]
  partial_metadata: boolean
}

export interface Parametro {
  key: string
  label: string
  unit: string | null
  value: number | string | null
  // `measured` es la entropía: se calcula sobre los bytes recibidos y no
  // depende de que exista una definición de protocolo validada, a diferencia
  // de `decoded`.
  status: 'decoded' | 'measured' | 'not_decoded' | 'not_available'
  reason: string | null
  history: { timestamp: string; value: number }[]
}

export interface Telemetria {
  parametros: Parametro[]
  protocolo_validado: boolean
  nota: string
  balizas: number
  campos_totales: number
  campos_constantes: number
}

/** Un campo tal como lo nombra la especificación, no como lo etiqueta la interfaz. */
export interface CampoDecodificado {
  campo: string
  apariciones: number
  valores_distintos: number
  /** Los estados de interruptor y `system_status` guardan texto, no número. */
  tipo: 'numerico' | 'texto'
  minimo: number | null
  maximo: number | null
  /** Rango típico (percentiles 5 y 95): acota la vista sin descartar nada. */
  p05: number | null
  p95: number | null
  /** Aviso sobre el extremo del campo, o null si no hay nada que señalar. */
  aviso: string | null
  desde: string | null
  hasta: string | null
  constante: boolean
}

export interface CamposDecodificados {
  total: number
  constantes: number
  campos: CampoDecodificado[]
  nota: string
}

export interface PipelinePaso {
  paso: string
  estado: 'ok' | 'pendiente'
  detalle: string
}

export interface DecodeResult {
  byte_count: number
  entropy_bits_per_byte: number
  printable_ratio: number
  distinct_bytes: number
  status: FrameStatus
  frame_type: string
  protocol: string | null
  analysis: Record<string, any>
  mensaje: string
  bytes: string[]
  decoded: boolean
  pipeline: PipelinePaso[]
  frame_id?: number
  timestamp?: string
  observer?: string
}

export interface AnomalyRule {
  id: number
  key: string
  label: string
  description: string | null
  enabled: boolean
  severity: 'normal' | 'warning' | 'critical'
  params: Record<string, any> | null
}

export interface AnomalyReport {
  resumen: Record<string, number>
  hallazgos: {
    rule: string
    label: string
    severity: 'normal' | 'warning' | 'critical'
    message: string
    frame_ids: number[]
    timestamp: string
  }[]
  reglas: AnomalyRule[]
}

export interface Status {
  satellite: string
  norad_id: number
  database: string
  frames: number
  observaciones: number
  protocolos_validados: number
  satnogs_token_configurado: boolean
}

export interface Distribucion {
  longitudes: { bytes: number; frames: number }[]
  estados: { estado: string; frames: number }[]
  tipos: { tipo: string; frames: number }[]
}

export interface Estacion {
  observer: string
  frames: number
  ultimo: string | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detalle = `${res.status} ${res.statusText}`
    try {
      const cuerpo = await res.json()
      if (cuerpo?.detail) detalle = cuerpo.detail
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new Error(detalle)
  }
  return res.json() as Promise<T>
}

export const api = {
  status: () => request<Status>('/api/status'),
  kpis: () => request<Kpis>('/api/frames/kpis'),
  series: (rango: string) => request<Serie>(`/api/frames/series?rango=${rango}`),
  frames: (params: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') q.set(k, String(v))
    })
    return request<FrameList>(`/api/frames?${q}`)
  },
  frame: (id: number) => request<Frame>(`/api/frames/${id}`),
  distribucion: () => request<Distribucion>('/api/frames/distribucion'),
  estaciones: () => request<Estacion[]>('/api/frames/estaciones'),
  observations: (limit = 100) => request<ObservationList>(`/api/observations?limit=${limit}`),
  syncObservations: () =>
    request<{ actualizadas: number; mensaje: string }>('/api/observations/sync', { method: 'POST' }),
  telemetry: () => request<Telemetria>('/api/telemetry'),
  telemetryCampos: () => request<CamposDecodificados>('/api/telemetry/campos'),
  decode: (hex: string) =>
    request<DecodeResult>('/api/decoder', { method: 'POST', body: JSON.stringify({ hex }) }),
  decodeFrame: (id: number) => request<DecodeResult>(`/api/decoder/frame/${id}`),
  anomalies: () => request<AnomalyReport>('/api/anomalies'),
  updateRule: (key: string, cambios: Partial<AnomalyRule>) =>
    request<AnomalyRule>(`/api/anomalies/rules/${key}`, {
      method: 'PATCH',
      body: JSON.stringify(cambios),
    }),
  ingestSatnogs: () =>
    request<{ insertados: number; duplicados: number; mensaje: string }>(
      '/api/ingest/satnogs',
      { method: 'POST' },
    ),
  exportUrl: (conjunto: string, formato: 'json' | 'csv') => `/api/export/${conjunto}.${formato}`,
}

/** Hook de carga con estados de carga y error explícitos. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const cargar = useCallback(() => {
    let vigente = true
    setLoading(true)
    setError(null)
    fn()
      .then((d) => vigente && setData(d))
      .catch((e: Error) => vigente && setError(e.message))
      .finally(() => vigente && setLoading(false))
    return () => {
      vigente = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(cargar, [cargar])

  return { data, error, loading, recargar: cargar }
}
