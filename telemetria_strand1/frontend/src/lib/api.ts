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
  /** Unidad y recta de calibración publicada; null si el campo no tiene. */
  unidad?: string | null
  conversion?: string | null
  origen?: string | null
  /** Cuánto puede sostenerse el valor como medida física. */
  validacion?: {
    estado:
      | 'calibrado'
      | 'canal_sin_medida'
      | 'pendiente_de_validacion'
      | 'sin_calibrar'
      | 'dato_crudo'
      | 'estructural'
      | 'texto'
    detalle: string
    fraccion_en_cuenta_cero?: number
  }
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

// --- Gemelo digital (fases 5-7) -------------------------------------------

export type EtiquetaAnomalia =
  | 'normal' | 'advertencia' | 'anomalia' | 'canal_enrielado' | 'sin_referencia'

export type EstadoCubeSat =
  | 'NOMINAL' | 'ADVERTENCIA' | 'CRITICO' | 'INSTRUMENTACION_PERDIDA' | 'SIN_REFERENCIA'

export interface GemeloResumen {
  eventos: number
  pases: number
  inicio: string
  fin: string
  duracion_real_dias: number
  duracion_virtual_s: number
  velocidades: number[]
  campo_por_defecto: string
  magnitudes: { campo: string; unidad: string }[]
  /** Procedencia de los datos y estado de la fuente (no hay enlace en vivo). */
  fuente?: string
  fuente_calibracion?: string
  tipo_dato?: string
  en_vivo?: boolean
  nota_conexion?: string
}

/** Cuánto puede sostenerse una lectura como medida física. */
export interface ValidacionLectura {
  estado:
    | 'calibrado'
    | 'canal_sin_medida'
    | 'pendiente_de_validacion'
    | 'sin_calibrar'
    | 'dato_crudo'
    | 'decodificado'
  detalle: string
  conversion?: string
}

export interface LecturaGemelo {
  campo: string
  valor: number
  unidad: string
  medida_en: string
  edad_s: number
  frescura: 'fresca' | 'vieja' | 'obsoleta'
  validacion?: ValidacionLectura
}

export interface EstadoGemelo {
  indice: number
  total: number
  momento: string
  pase: number
  campo_gobernante: string
  etiqueta: EtiquetaAnomalia
  estado_cubesat: EstadoCubeSat
  tipo_dato?: string
  nota_estado?: string
  lecturas: LecturaGemelo[]
}

export interface PuntoSerie {
  t: string
  valor: number | null
  mediana: number | null
  z: number | null
  etiqueta: EtiquetaAnomalia
}

export interface SerieGemelo {
  campo: string
  unidad: string
  n_total: number
  n_enviados: number
  submuestreo: number
  /** Lecturas dentro del intervalo pedido (igual a n_total si no se acota). */
  n_en_intervalo?: number
  inicio_serie?: string
  fin_serie?: string
  estadisticas: { media: number; minimo: number; maximo: number } | null
  puntos: PuntoSerie[]
}

export interface EventoGemelo {
  campo: string
  etiqueta: EtiquetaAnomalia
  inicio: string
  fin: string
  duracion_s: number
  n_lecturas: number
  valor_esperado: number
  valor_registrado: number
  diferencia: number
  z_max: number
  estado_cubesat: EstadoCubeSat
}

export interface EventosGemelo {
  campo: string
  unidad: string
  n_total: number
  eventos: EventoGemelo[]
}

/**
 * Base de la API.
 *
 * Vacia por omision, que es lo correcto en desarrollo: las rutas quedan
 * relativas y las sirve el proxy de Vite, sin CORS de por medio.
 *
 * En un despliegue donde el frontend y el backend viven en dominios distintos
 * --- el SPA en Vercel, FastAPI en Render o Railway --- hay que definir
 * `VITE_API_URL` con la raiz del backend, sin barra final. Ese dominio tiene
 * que figurar ademas en `cors_origins` del backend, o el navegador rechazara
 * las respuestas.
 */
/* ── Salud del satélite (HMTA) ─────────────────────────────────────────────── */

export type EstadoSalud = 'NORMAL' | 'ADVERTENCIA' | 'CRITICO' | 'DESCONOCIDO'
export type Procedencia = 'REAL' | 'SIMULADO' | 'ESTIMADO' | 'DOCUMENTADO' | 'NO_DISPONIBLE'

export interface PuntoSalud {
  t: string
  v: number | null
  valida: boolean
  motivo: string | null
}

export interface HallazgoSalud {
  variable: string
  tipo: string
  lecturas: number
  primera: string
  ultima: string
  explicacion: string
}

export interface IndicadorSalud {
  clave: string
  nombre: string
  unidad: string | null
  que_es: string
  por_que_importa: string
  procedencia: Procedencia
  estado: EstadoSalud
  estado_motivo: string
  valor: number | string | null
  valor_fecha: string | null
  referencia: string
  rango_documentado: [number, number] | null
  estadisticas: Record<string, any>
  validacion: Record<string, any>
  hallazgos: HallazgoSalud[]
  tendencia: Record<string, any> | null
  serie: PuntoSalud[]
  notas: string[]
  fuente: string
}

export interface NoDisponibleSalud {
  clave: string
  nombre: string
  unidad: string | null
  que_es: string
  por_que_importa: string
  motivo: string
  disponibilidad: string
  notas: string[]
  nodo_canal: string | null
}

export interface AlertaSalud {
  id: string
  subsistema: string
  variable: string
  nivel: EstadoSalud
  mecanismo: string
  inicio: string
  fin: string
  que_ocurrio: string
  componente: string
  valor_registrado: number | string | null
  unidad: string | null
  valor_referencia: number | string | null
  referencia: string
  por_que_importa: string
  informacion_adicional: string
  procedencia: Procedencia
  lecturas: number
  registrado_utc?: string
}

export interface SubsistemaSalud {
  clave: string
  nombre: string
  explicacion: string
  estado: EstadoSalud
  resumen: string
  indicadores: IndicadorSalud[]
  no_disponibles: NoDisponibleSalud[]
  alertas: AlertaSalud[]
  procedencias: Procedencia[]
  extra: Record<string, any>
  notas: string[]
}

export interface PuntoTY {
  t: number
  y: number
}

export interface ComparacionModelo {
  planta: string
  controlador: string
  procedencia_medida: Procedencia
  rms_residuo_normalizado: number
  tolerancia: number
  sobrepaso_medido_pct: number
  sobrepaso_modelo_pct: number
  fuera_de_tolerancia: boolean
  referencia: PuntoTY[]
  medida: PuntoTY[]
}

export interface InformeSalud {
  proyecto: string
  solo_supervision: boolean
  generado_utc: string
  procedencia: Procedencia
  fuente: string
  descripcion_fuente: string
  escenario: string | null
  simulado: boolean
  periodo: { desde: string | null; hasta: string | null; ventana_dias: number | null }
  ultima_actualizacion: string | null
  ultima_trama: string | null
  antiguedad_dias: number | null
  vigencia: string
  estado_general: EstadoSalud
  estado_general_texto: string
  indicadores_por_procedencia: Record<string, number>
  subsistemas: Record<string, SubsistemaSalud>
  anomalias: {
    clave: string
    nombre: string
    explicacion: string
    estado: EstadoSalud
    resumen: {
      total: number
      por_nivel: Record<string, number>
      por_mecanismo: Record<string, number>
      por_subsistema: Record<string, number>
    }
    mecanismos: Record<string, string>
    comparacion_modelo: ComparacionModelo | null
    validacion: HallazgoSalud[]
    alertas: AlertaSalud[]
  }
  alertas_recientes: AlertaSalud[]
}

export interface MetricasPid {
  estable_discreto: boolean
  estable_continuo: boolean
  max_modulo_polo_z: number
  max_parte_real_polo_s: number
  sobrepaso_pct: number | null
  tiempo_subida_s: number | null
  tiempo_pico_s: number | null
  tiempo_asentamiento_s: number | null
  error_estacionario: number | null
  valor_final: number | null
}

export interface ControladorPid {
  controlador: 'P' | 'PI' | 'PID'
  sintonia: { Kp: number; Ti: number | null; Td: number | null; metodo: string }
  metricas: MetricasPid
  margenes: {
    margen_ganancia_db: number | null
    margen_fase_deg: number | null
    w_cruce_ganancia: number | null
    w_cruce_fase: number | null
  }
  polos_discretos: { re: number; im: number; modulo: number }[]
  respuesta: PuntoTY[]
}

export interface InformePid {
  procedencia: Procedencia
  ts_s: number
  n_filtro_derivativo: number
  discretizacion: string
  entrada: string
  banda_asentamiento: number
  limitaciones: string[]
  modelos: {
    planta: string
    expresion: string
    descripcion: string
    ganancia_ultima: { Ku: number; wu_rad_s: number; Pu_s: number }
    controladores: ControladorPid[]
  }[]
}

export interface MesHistorial {
  mes: string
  variable: string
  lecturas: number
  validas: number
  fraccion_valida: number
  mediana_valida: number | null
  motivo_dominante: string | null
  procedencia: Procedencia
}

export interface EventosSalud {
  persistente: boolean
  ruta: string
  total: number
  nota: string | null
  eventos: AlertaSalud[]
}

const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const opciones = {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  }
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, opciones)
  } catch (e) {
    // Fallo de red, no de la API: tipicamente una conexion en reposo que el
    // servidor ya habia cerrado. Las lecturas son idempotentes, asi que se
    // reintenta una vez; una escritura nunca se repite sola.
    if ((init?.method ?? 'GET').toUpperCase() !== 'GET') throw e
    await new Promise((r) => setTimeout(r, 300))
    res = await fetch(`${BASE}${path}`, opciones)
  }
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
  gemeloResumen: () => request<GemeloResumen>('/api/gemelo/resumen'),
  gemeloEstado: (indice: number, campo: string) =>
    request<EstadoGemelo>(`/api/gemelo/estado?indice=${indice}&campo=${encodeURIComponent(campo)}`),
  gemeloSerie: (campo: string, desde?: string, hasta?: string) => {
    const q = new URLSearchParams()
    if (desde) q.set('desde', desde)
    if (hasta) q.set('hasta', hasta)
    const cola = q.toString() ? `?${q}` : ''
    return request<SerieGemelo>(`/api/gemelo/serie/${encodeURIComponent(campo)}${cola}`)
  },
  gemeloIndice: (t: string) =>
    request<{ indice: number; momento: string; total: number }>(
      `/api/gemelo/indice?t=${encodeURIComponent(t)}`,
    ),
  gemeloEventos: (campo: string) =>
    request<EventosGemelo>(`/api/gemelo/eventos/${encodeURIComponent(campo)}`),
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
  saludResumen: (hasta?: string, ventanaDias?: number) => {
    const q = new URLSearchParams()
    if (hasta) q.set('hasta', hasta)
    if (ventanaDias) q.set('ventana_dias', String(ventanaDias))
    const cola = q.toString() ? `?${q}` : ''
    return request<InformeSalud>(`/api/salud/resumen${cola}`)
  },
  saludEscenarios: () =>
    request<{ escenarios: { nombre: string; descripcion: string }[]; nota: string }>(
      '/api/salud/escenarios',
    ),
  saludEscenario: (nombre: string) =>
    request<InformeSalud>(`/api/salud/escenario/${encodeURIComponent(nombre)}`),
  saludPid: (ts: number) => request<InformePid>(`/api/salud/pid?ts=${ts}`),
  saludHistorial: () => request<{ fuente: string; meses: MesHistorial[] }>('/api/salud/historial'),
  saludEventos: () => request<EventosSalud>('/api/salud/eventos?limite=200'),
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
