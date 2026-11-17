/**
 * LIRA AI en el navegador: API, bus de acciones, contexto compartido y voz.
 *
 * El bus solo transporta acciones que el backend ya validó. Cada página se
 * suscribe a las suyas (`gemelo_*` el gemelo, `enlace_*` Enlace RF) y las
 * ejecuta con sus propios setters: LIRA no toca el estado de ninguna página
 * por dentro. Si una acción llega antes de que su página esté montada (por
 * ejemplo, «inicia la simulación del enlace» desde el inicio), espera en cola
 * hasta 15 s y se entrega al suscribirse.
 *
 * Voz: Web Speech API, sin dependencias. La síntesis existe en todos los
 * navegadores; el reconocimiento solo en Chrome y Edge, que envían el audio a
 * los servidores de Google o Microsoft. Donde no existe, LIRA funciona por texto.
 */

export interface AccionLira {
  nombre: string
  parametros: Record<string, any>
  critica: boolean
  descripcion: string
}

export interface RespuestaLira {
  texto: string
  modo: 'determinista' | 'ia' | 'sin_acceso'
  acciones: AccionLira[]
  pendiente: { ficha: string; descripcion: string; caduca_s: number } | null
  rechazadas: { nombre: string; motivo: string }[]
  consultas: { herramienta: string; argumentos: Record<string, any> }[]
  verificacion: { cifras_comprobadas: number; no_verificadas: string[]; ok: boolean } | null
  uso: Record<string, number> | null
  aclaracion: boolean
  confirmacion?: 'confirmar' | 'cancelar'
}

export interface EstadoLira {
  version: string
  ia_configurada: boolean
  requiere_clave: boolean
  modelo: string | null
  registro_activo: boolean
}

const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')
const CLAVE_FICHA = 'lira:ficha'

async function pedir<T>(ruta: string, cuerpo?: unknown): Promise<T> {
  const ficha = leerFicha()
  const r = await fetch(`${BASE}/api/lira/${ruta}`, {
    method: cuerpo === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', ...(ficha ? { 'X-Lira-Ficha': ficha } : {}) },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  })
  if (!r.ok) {
    let detalle = `${r.status} ${r.statusText}`
    try {
      const j = await r.json()
      if (j?.detail) detalle = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* sin cuerpo JSON */
    }
    throw new Error(detalle)
  }
  return r.json() as Promise<T>
}

/* La ficha de sesión se guarda solo en esta pestaña (sessionStorage). */
export function leerFicha(): string | null {
  try {
    return sessionStorage.getItem(CLAVE_FICHA)
  } catch {
    return null
  }
}
export function guardarFicha(f: string | null) {
  try {
    if (f) sessionStorage.setItem(CLAVE_FICHA, f)
    else sessionStorage.removeItem(CLAVE_FICHA)
  } catch {
    /* almacenamiento bloqueado: la ficha vive solo en memoria de la página */
  }
}

export const liraApi = {
  estado: () => pedir<EstadoLira>('estado'),
  acceso: (clave: string) => pedir<{ ficha: string }>('acceso', { clave }),
  turno: (texto: string, contexto: Record<string, unknown>, historial: { rol: 'usuario' | 'lira'; texto: string }[]) =>
    pedir<RespuestaLira>('turno', { texto, contexto, historial }),
  confirmar: (ficha: string, decision: 'confirmar' | 'cancelar') =>
    pedir<{ ok: boolean; texto: string; acciones: AccionLira[] }>('confirmar', { ficha, decision }),
}

/* ── Bus de acciones ──────────────────────────────────────────────────────── */

type Manejador = (a: AccionLira) => void
const manejadores = new Map<string, Set<Manejador>>()
const cola: { a: AccionLira; t: number }[] = []
const ESPERA_MS = 15_000

function prefijo(nombre: string) {
  return nombre === 'restablecer_vista' ? 'gemelo' : nombre.split('_')[0]
}

/** Entrega la acción a quien la maneje. Devuelve false si quedó en cola. */
export function emitir(a: AccionLira): boolean {
  const hs = manejadores.get(prefijo(a.nombre))
  if (hs && hs.size) {
    hs.forEach((h) => h(a))
    return true
  }
  cola.push({ a, t: Date.now() })
  return false
}

export function suscribir(pref: string, h: Manejador): () => void {
  if (!manejadores.has(pref)) manejadores.set(pref, new Set())
  manejadores.get(pref)!.add(h)
  const ahora = Date.now()
  for (let i = 0; i < cola.length; ) {
    const { a, t } = cola[i]
    if (ahora - t > ESPERA_MS) cola.splice(i, 1)
    else if (prefijo(a.nombre) === pref) {
      cola.splice(i, 1)
      h(a)
    } else i++
  }
  return () => manejadores.get(pref)?.delete(h)
}

/* ── Contexto de la interfaz (lo que LIRA sabe de la pantalla) ────────────── */

const contexto: Record<string, unknown> = {}
export function actualizarContexto(parcial: Record<string, unknown>) {
  Object.assign(contexto, parcial)
}
export function leerContexto() {
  return { ...contexto }
}

/* ── Voz ──────────────────────────────────────────────────────────────────── */

/*
 * La Web Speech API no dice si una voz es de hombre o de mujer: solo da su
 * nombre y su idioma. Se reconocen por el nombre las voces femeninas en
 * español más comunes (Windows/Edge, macOS/iOS, Android, Chrome) y se
 * prefieren las de Colombia y Latinoamérica. Si el sistema no tiene ninguna,
 * se usa la primera en español; el panel deja elegir cualquiera.
 */
const FEMENINAS = /(salom[eé]|dalia|sabina|helena|laura|elvira|paloma|elena|ximena|catalina|luc[ií]a|camila|paula|m[oó]nica|paulina|marisol|isabela|valentina|abril|larissa|triana|irene|estrella|vera|lupe|pen[eé]lope|conchita|google espa[nñ]ol|female|mujer)/i
const MASCULINAS = /(gonzalo|jorge|pablo|ra[uú]l|alvaro|álvaro|jos[eé]|diego|carlos|juan|enrique|miguel|male\b|hombre)/i
const CLAVE_VOZ = 'lira:voz'
let vozEnMemoria: string | null = null

function puntuar(v: SpeechSynthesisVoice): number {
  let p = 0
  if (FEMENINAS.test(v.name)) p += 100
  if (MASCULINAS.test(v.name)) p -= 100
  const lang = v.lang.toLowerCase()
  if (lang === 'es-co') p += 12
  else if (/^es-(419|mx|us|ar|cl|pe|ve|ec)/.test(lang)) p += 8
  else if (lang === 'es-es') p += 4
  if (/natural|online|neural/i.test(v.name)) p += 3   // voces de mayor calidad en Edge
  return p
}

function leerPreferencia(): string | null {
  try {
    return localStorage.getItem(CLAVE_VOZ) ?? vozEnMemoria
  } catch {
    return vozEnMemoria
  }
}

type Reconocedor = {
  lang: string
  interimResults: boolean
  continuous: boolean
  start(): void
  stop(): void
  abort(): void
  onresult: ((e: any) => void) | null
  onerror: ((e: any) => void) | null
  onend: (() => void) | null
}

function claseReconocimiento(): (new () => Reconocedor) | null {
  const w = window as any
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export const voz = {
  reconocimiento: () => claseReconocimiento() !== null,
  sintesis: () => typeof window !== 'undefined' && 'speechSynthesis' in window,

  escuchar(cb: { parcial?: (t: string) => void; final: (t: string) => void; error: (m: string) => void; fin: () => void }) {
    const Clase = claseReconocimiento()
    if (!Clase) {
      cb.error('Este navegador no reconoce voz. Escribe la orden.')
      cb.fin()
      return () => {}
    }
    const r = new Clase()
    r.lang = 'es-ES'
    r.interimResults = true
    r.continuous = false
    r.onresult = (e: any) => {
      let texto = ''
      let final = false
      for (let i = e.resultIndex; i < e.results.length; i++) {
        texto += e.results[i][0].transcript
        final = final || e.results[i].isFinal
      }
      if (final) cb.final(texto.trim())
      else cb.parcial?.(texto)
    }
    r.onerror = (e: any) => {
      const m: Record<string, string> = {
        'not-allowed': 'Permiso de micrófono denegado.',
        'no-speech': 'No te he oído.',
        'audio-capture': 'No hay micrófono disponible.',
        network: 'El reconocimiento de voz necesita conexión.',
      }
      if (e.error !== 'aborted') cb.error(m[e.error] ?? `Error de voz: ${e.error}`)
    }
    r.onend = () => cb.fin()
    r.start()
    return () => r.abort()
  },

  /** Voces en español del navegador, la preferida primero. */
  voces(): SpeechSynthesisVoice[] {
    if (!voz.sintesis()) return []
    return window.speechSynthesis.getVoices()
      .filter((v) => v.lang.toLowerCase().startsWith('es'))
      .sort((a, b) => puntuar(b) - puntuar(a))
  },

  /** La voz elegida por el usuario si existe; si no, la mejor femenina disponible. */
  vozActual(): SpeechSynthesisVoice | null {
    const lista = voz.voces()
    const guardada = leerPreferencia()
    return lista.find((v) => v.name === guardada) ?? lista[0] ?? null
  },

  elegirVoz(nombre: string) {
    try {
      localStorage.setItem(CLAVE_VOZ, nombre)
    } catch {
      /* sin almacenamiento: la elección dura lo que la página */
    }
    vozEnMemoria = nombre
  },

  hablar(texto: string, fin?: () => void) {
    if (!voz.sintesis()) {
      fin?.()
      return
    }
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(texto)
    const elegida = voz.vozActual()
    u.lang = elegida?.lang ?? 'es-ES'
    if (elegida) u.voice = elegida
    u.rate = 1.03
    u.onend = () => fin?.()
    u.onerror = () => fin?.()
    window.speechSynthesis.speak(u)
  },

  callar() {
    if (voz.sintesis()) window.speechSynthesis.cancel()
  },
}
