/**
 * LIRA AI — panel de la copiloto de misión, disponible en todas las páginas.
 *
 * Solo presenta y despacha: la interpretación, la validación y las respuestas
 * vienen de /api/lira. Las acciones recibidas ya están validadas; se emiten al
 * bus y cada página las ejecuta. Las críticas esperan a «Confirmar».
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  actualizarContexto, emitir, guardarFicha, leerContexto, leerFicha, liraApi, suscribir, voz,
} from '../../lib/lira'
import type { AccionLira, EstadoLira, RespuestaLira } from '../../lib/lira'

type Fase = 'inactiva' | 'escuchando' | 'procesando' | 'hablando' | 'ejecutando'

interface Linea {
  id: number
  rol: 'usuario' | 'lira' | 'sistema'
  texto: string
  respuesta?: RespuestaLira
}

const FASE: Record<Fase, { texto: string; color: string }> = {
  inactiva: { texto: 'En espera', color: 'var(--color-ink-mute)' },
  escuchando: { texto: 'Escuchando', color: 'var(--color-ok)' },
  procesando: { texto: 'Procesando', color: 'var(--color-navy)' },
  hablando: { texto: 'Respondiendo', color: 'var(--color-blue)' },
  ejecutando: { texto: 'Ejecutando orden', color: 'var(--color-warn)' },
}

const SUGERENCIAS = [
  '¿Cuál es el estado de la batería?',
  'Vista explotada',
  '¿Hay datos de temperatura?',
  'Ve al 15 de marzo de 2020 y reproduce',
]

function Indicador({ fase }: { fase: Fase }) {
  const activo = fase !== 'inactiva'
  return (
    <span className="relative flex size-3 items-center justify-center" aria-hidden>
      {activo && (
        <span className="absolute inline-flex size-full animate-ping rounded-full opacity-60"
              style={{ background: FASE[fase].color }} />
      )}
      <span className="relative inline-flex size-2.5 rounded-full" style={{ background: FASE[fase].color }} />
    </span>
  )
}

/** Onda de actividad de voz: barras que solo se mueven mientras escucha o habla. */
function Onda({ fase }: { fase: Fase }) {
  const viva = fase === 'escuchando' || fase === 'hablando'
  return (
    <div className="flex h-5 items-end gap-[3px]" aria-hidden>
      {[0, 1, 2, 3, 4].map((i) => (
        <span key={i} className={`w-[3px] rounded-full ${viva ? 'animate-pulse' : ''}`}
              style={{ height: viva ? `${6 + ((i * 7) % 13)}px` : '4px', background: FASE[fase].color,
                       animationDelay: `${i * 120}ms` }} />
      ))}
    </div>
  )
}

export function Lira() {
  const navigate = useNavigate()
  const [abierta, setAbierta] = useState(false)
  const [fase, setFase] = useState<Fase>('inactiva')
  const [estado, setEstado] = useState<EstadoLira | null>(null)
  const [conectado, setConectado] = useState<boolean | null>(null)
  const [lineas, setLineas] = useState<Linea[]>([])
  const [entrada, setEntrada] = useState('')
  const [parcial, setParcial] = useState('')
  const [hablarActivo, setHablarActivo] = useState(true)
  const [ficha, setFicha] = useState<string | null>(() => leerFicha())
  const [pidiendoClave, setPidiendoClave] = useState(false)
  const [clave, setClave] = useState('')
  const [errorClave, setErrorClave] = useState<string | null>(null)
  const [pendiente, setPendiente] = useState<RespuestaLira['pendiente']>(null)
  const [restante, setRestante] = useState(0)
  const detenerEscucha = useRef<() => void>(() => {})
  // Generación de cancelación: solo «Cancelar» invalida las respuestas en vuelo.
  // Una orden nueva NO descarta la anterior: ambas se completan en orden.
  const cancelacion = useRef(0)
  const idLinea = useRef(0)
  const fin = useRef<HTMLDivElement>(null)

  useEffect(() => {
    liraApi.estado().then((e) => { setEstado(e); setConectado(true) }).catch(() => setConectado(false))
  }, [])

  // Navegación: la ejecuta el propio panel (vive dentro del router).
  useEffect(() => suscribir('navegar', (a) => {
    const { ruta, pagina, seccion } = a.parametros
    if (pagina === 'inicio' && seccion) navigate({ pathname: '/', hash: `#${seccion}` })
    else if (pagina === 'validacion' && seccion) navigate(`/validacion?seccion=${seccion}`)
    else navigate(ruta)
  }), [navigate])

  useEffect(() => { fin.current?.scrollIntoView({ block: 'end' }) }, [lineas, abierta])

  // Página en pantalla: decide órdenes ambiguas («pausa la simulación»).
  const { pathname } = useLocation()
  useEffect(() => {
    const pagina = ({ '/': 'inicio', '/observations': 'observaciones', '/telemetry': 'telemetria', '/enlace': 'enlace',
      '/simulacion': 'simulacion', '/analytics': 'analisis', '/advanced': 'avanzado', '/validacion': 'validacion',
      '/docs': 'documentacion' } as Record<string, string>)[pathname] ?? pathname
    actualizarContexto({ pagina })
  }, [pathname])

  // Cuenta atrás de la confirmación pendiente.
  useEffect(() => {
    if (!pendiente) return
    setRestante(pendiente.caduca_s)
    const id = window.setInterval(() => setRestante((s) => {
      if (s <= 1) { setPendiente(null); return 0 }
      return s - 1
    }), 1000)
    return () => window.clearInterval(id)
  }, [pendiente])

  const anadir = (l: Omit<Linea, 'id'>) => {
    const id = ++idLinea.current
    setLineas((xs) => [...xs, { ...l, id }])
    return id
  }

  const decir = useCallback((texto: string) => {
    if (!hablarActivo || !voz.sintesis()) { setFase('inactiva'); return }
    setFase('hablando')
    voz.hablar(texto, () => setFase('inactiva'))
  }, [hablarActivo])

  const ejecutar = useCallback((acciones: AccionLira[]) => {
    if (!acciones.length) return
    setFase('ejecutando')
    // La navegación primero: las demás acciones pueden ir a una página que aún no está montada.
    const orden = [...acciones].sort((a, b) => (a.nombre === 'navegar' ? -1 : b.nombre === 'navegar' ? 1 : 0))
    // Una acción de una página que no está en pantalla la lleva allí; la acción
    // espera en la cola del bus hasta que la página se monte.
    const destinos: Record<string, string> = { enlace: '/enlace', gemelo: '/' }
    const ruta = window.location.pathname
    const prefijoDe = (n: string) => (n === 'restablecer_vista' ? 'gemelo' : n.split('_')[0])
    const navega = orden.some((a) => a.nombre === 'navegar')
    const destino = orden.map((a) => destinos[prefijoDe(a.nombre)]).find((d) => d && d !== ruta)
    if (!navega && destino) navigate(destino === '/' ? { pathname: '/', hash: '#gemelo' } : destino)
    orden.forEach((a) => emitir(a))
  }, [navigate])

  const resolverPendiente = useCallback(async (decision: 'confirmar' | 'cancelar') => {
    if (!pendiente) return
    const f = pendiente.ficha
    setPendiente(null)
    try {
      const r = await liraApi.confirmar(f, decision)
      anadir({ rol: 'sistema', texto: r.texto })
      ejecutar(r.acciones)
      decir(r.texto)
    } catch (e) {
      anadir({ rol: 'sistema', texto: `No se pudo ${decision}: ${(e as Error).message}` })
      setFase('inactiva')
    }
  }, [pendiente, ejecutar, decir])

  // Las órdenes se procesan una tras otra, en el orden en que se dieron. Cada
  // una lee el historial, la confirmación pendiente y el contexto al empezar,
  // así que ve el efecto de la anterior (p. ej. el gemelo ya movido de fecha).
  const cadena = useRef<Promise<void>>(Promise.resolve())
  const lineasRef = useRef(lineas)
  lineasRef.current = lineas
  const pendienteRef = useRef(pendiente)
  pendienteRef.current = pendiente

  const procesar = useCallback(async (t: string, generacion: number, idPregunta: number) => {
    if (generacion !== cancelacion.current) return
    setFase('procesando')
    // Historial: lo dicho ANTES de esta pregunta (no depende de cuándo se re-renderice).
    const historial = lineasRef.current.filter((l) => l.rol !== 'sistema' && l.id < idPregunta).slice(-6)
      .map((l) => ({ rol: l.rol as 'usuario' | 'lira', texto: l.texto }))
    try {
      const r = await liraApi.turno(t, { ...leerContexto(), pendiente: Boolean(pendienteRef.current) }, historial)
      if (generacion !== cancelacion.current) return // cancelada mientras se procesaba
      if (r.confirmacion && pendienteRef.current) {
        await resolverPendiente(r.confirmacion)
        return
      }
      anadir({ rol: 'lira', texto: r.texto, respuesta: r })
      if (r.pendiente) setPendiente(r.pendiente)
      ejecutar(r.acciones)
      const aviso = r.verificacion && !r.verificacion.ok
        ? ' Atención: hay cifras en esta respuesta que no puedo respaldar con los datos.' : ''
      decir(r.texto + aviso)
    } catch (e) {
      if (generacion !== cancelacion.current) return
      const m = (e as Error).message
      if (/sesi|401/.test(m)) { guardarFicha(null); setFicha(null) }
      anadir({ rol: 'sistema', texto: m })
      setFase('inactiva')
    }
  }, [ejecutar, decir, resolverPendiente])

  const enviar = useCallback((texto: string) => {
    const t = texto.trim()
    if (!t) return
    voz.callar()
    setEntrada('')
    setParcial('')
    const idPregunta = anadir({ rol: 'usuario', texto: t })
    const generacion = cancelacion.current
    cadena.current = cadena.current.then(() => procesar(t, generacion, idPregunta))
  }, [procesar])

  const cancelarTodo = () => {
    cancelacion.current++
    detenerEscucha.current()
    voz.callar()
    setParcial('')
    setFase('inactiva')
    if (pendiente) void resolverPendiente('cancelar')
  }

  const escuchar = () => {
    if (fase === 'escuchando') { detenerEscucha.current(); return }
    voz.callar()
    setFase('escuchando')
    detenerEscucha.current = voz.escuchar({
      parcial: setParcial,
      final: (t) => { setParcial(''); enviar(t) },
      error: (m) => anadir({ rol: 'sistema', texto: m }),
      fin: () => setFase((f) => (f === 'escuchando' ? 'inactiva' : f)),
    })
  }

  const desbloquear = async () => {
    setErrorClave(null)
    try {
      const r = await liraApi.acceso(clave)
      guardarFicha(r.ficha)
      setFicha(r.ficha)
      setClave('')
      setPidiendoClave(false)
      anadir({ rol: 'sistema', texto: 'IA desbloqueada en esta pestaña.' })
    } catch (e) {
      setErrorClave((e as Error).message)
    }
  }

  const iaAbierta = estado?.ia_configurada && (!estado.requiere_clave || ficha)
  const etiquetaIA = !estado ? '…' : !estado.ia_configurada ? 'IA no configurada'
    : iaAbierta ? `IA activa · ${(estado.modelo ?? '').replace('claude-', '').replace(/-(\d+)-(\d+)$/, ' $1.$2')}` : 'IA bloqueada'

  return (
    <>
      <button
        onClick={() => setAbierta((a) => !a)}
        className="fixed bottom-5 right-5 z-40 flex items-center gap-2.5 rounded-full border border-navy/40 bg-panel/95 py-2 pl-3 pr-4 shadow-lg shadow-black/40 backdrop-blur transition-colors hover:border-navy"
        aria-expanded={abierta} aria-controls="lira-panel"
        title="LIRA AI · copiloto de misión"
      >
        <Indicador fase={fase} />
        <span className="text-[13px] font-bold tracking-[0.18em] text-navy">LIRA</span>
        <span className="hidden text-[11px] text-ink-soft sm:inline">{FASE[fase].texto}</span>
      </button>

      {abierta && (
        <section id="lira-panel" aria-label="LIRA AI"
          className="fixed inset-x-3 bottom-20 z-40 flex max-h-[72vh] flex-col overflow-hidden rounded-xl border border-line bg-panel/97 shadow-2xl shadow-black/60 backdrop-blur-md sm:inset-x-auto sm:right-5 sm:w-[430px]">
          {/* Cabecera */}
          <header className="border-b border-line px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[13px] font-bold tracking-[0.2em] text-navy-dark">LIRA <span className="text-navy">AI</span></div>
                <div className="truncate text-[10px] uppercase tracking-wider text-ink-mute">
                  Language Intelligence for Real-time Aerospace Operations
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Onda fase={fase} />
                <button onClick={() => setAbierta(false)} className="rounded p-1 text-ink-soft hover:text-navy" aria-label="Cerrar LIRA">✕</button>
              </div>
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wide">
              <span className="flex items-center gap-1.5 rounded border border-line px-2 py-0.5">
                <span className={`size-1.5 rounded-full ${conectado ? 'bg-ok' : conectado === false ? 'bg-danger' : 'bg-ink-mute'}`} />
                <span className={conectado ? 'text-ok' : 'text-ink-soft'}>{conectado ? 'Enlace' : conectado === false ? 'Sin servidor' : 'Conectando'}</span>
              </span>
              <span className="flex items-center gap-1.5 rounded border border-line px-2 py-0.5 text-ink-soft">
                <Indicador fase={fase} /> {FASE[fase].texto}
              </span>
              <span className={`rounded border px-2 py-0.5 ${iaAbierta ? 'border-navy/40 text-navy' : 'border-line text-ink-soft'}`}>{etiquetaIA}</span>
              {estado?.ia_configurada && estado.requiere_clave && !ficha && (
                <button onClick={() => setPidiendoClave((p) => !p)} className="rounded px-1.5 py-0.5 normal-case text-navy underline-offset-2 hover:underline">
                  Desbloquear IA
                </button>
              )}
            </div>
            {pidiendoClave && (
              <form className="mt-2.5 flex gap-2" onSubmit={(e) => { e.preventDefault(); void desbloquear() }}>
                <input type="password" value={clave} onChange={(e) => setClave(e.target.value)} autoFocus
                  placeholder="Contraseña de la IA" aria-label="Contraseña de la IA"
                  className="min-w-0 flex-1 rounded-md border border-line bg-canvas px-2.5 py-1.5 text-sm text-ink" />
                <button className="rounded-md bg-navy px-3 py-1.5 text-sm font-medium text-on-accent" disabled={!clave}>Entrar</button>
              </form>
            )}
            {errorClave && <p className="mt-1.5 text-xs text-danger">{errorClave}</p>}
          </header>

          {/* Conversación */}
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm" aria-live="polite">
            {!lineas.length && (
              <div className="space-y-2 text-ink-soft">
                <p>Soy LIRA. Consulto la telemetría archivada de STRaND-1, explico lo que significa y manejo
                  la interfaz. No envío nada al satélite: está inactivo y no hay canal de comandos.</p>
                <div className="flex flex-wrap gap-1.5">
                  {SUGERENCIAS.map((s) => (
                    <button key={s} onClick={() => enviar(s)}
                      className="rounded-md border border-line px-2 py-1 text-xs text-navy hover:border-navy">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {lineas.map((l) => (
              <div key={l.id} className={l.rol === 'usuario' ? 'ml-8 text-right' : ''}>
                {l.rol === 'usuario' && (
                  <span className="inline-block rounded-lg bg-blue-light px-3 py-1.5 text-left text-ink">{l.texto}</span>
                )}
                {l.rol === 'sistema' && <p className="text-xs italic text-ink-soft">{l.texto}</p>}
                {l.rol === 'lira' && (
                  <div className="border-l-2 border-navy/50 pl-3">
                    <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider">
                      <span className="text-navy">LIRA</span>
                      <span className="text-ink-mute">
                        {l.respuesta?.modo === 'ia' ? 'IA · herramientas' : l.respuesta?.modo === 'determinista' ? 'orden directa · sin IA' : 'sin IA'}
                      </span>
                      {l.respuesta?.verificacion && l.respuesta.verificacion.cifras_comprobadas > 0 && (
                        <span className={l.respuesta.verificacion.ok ? 'text-ok' : 'text-warn'}
                          title={l.respuesta.verificacion.ok ? 'Cada cifra sale de una herramienta de este turno'
                            : `Sin respaldo: ${l.respuesta.verificacion.no_verificadas.join(', ')}`}>
                          {l.respuesta.verificacion.ok
                            ? `${l.respuesta.verificacion.cifras_comprobadas} ${l.respuesta.verificacion.cifras_comprobadas === 1 ? 'cifra respaldada' : 'cifras respaldadas'}`
                            : `${l.respuesta.verificacion.no_verificadas.length} ${l.respuesta.verificacion.no_verificadas.length === 1 ? 'cifra' : 'cifras'} SIN respaldo`}
                        </span>
                      )}
                    </div>
                    <p className="whitespace-pre-line text-ink">{l.texto}</p>
                    {!!l.respuesta?.acciones.length && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {l.respuesta.acciones.map((a, i) => (
                          <span key={i} className="rounded border border-ok/30 bg-ok-bg px-1.5 py-0.5 text-[11px] text-ok">✓ {a.descripcion}</span>
                        ))}
                      </div>
                    )}
                    {!!l.respuesta?.rechazadas.some((r) => !l.texto.includes(r.motivo)) && (
                      <div className="mt-1 space-y-0.5">
                        {l.respuesta.rechazadas.filter((r) => !l.texto.includes(r.motivo)).map((r, i) => (
                          <p key={i} className="text-[11px] text-danger">✕ {r.motivo}</p>
                        ))}
                      </div>
                    )}
                    {!!l.respuesta?.consultas.length && (
                      <p className="mt-1 text-[10.5px] text-ink-mute">
                        Fuentes: {l.respuesta.consultas.map((c) => c.herramienta).join(', ')} · archivo sellado de SatNOGS
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
            {parcial && <p className="ml-8 text-right text-xs italic text-ink-soft">{parcial}…</p>}
            <div ref={fin} />
          </div>

          {/* Confirmación de acción crítica */}
          {pendiente && (
            <div className="border-t border-warn/30 bg-warn-bg px-4 py-3" role="alertdialog" aria-label="Confirmar acción">
              <p className="text-[10.5px] font-semibold uppercase tracking-wider text-warn">Acción crítica · confirma en {restante} s</p>
              <p className="mt-1 text-sm text-ink">{pendiente.descripcion}</p>
              <div className="mt-2 flex gap-2">
                <button onClick={() => void resolverPendiente('confirmar')} className="rounded-md bg-warn px-3 py-1.5 text-sm font-semibold text-canvas">Confirmar</button>
                <button onClick={() => void resolverPendiente('cancelar')} className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-soft hover:text-ink">Cancelar</button>
              </div>
            </div>
          )}

          {/* Entrada */}
          <form className="flex items-center gap-2 border-t border-line px-3 py-2.5"
                onSubmit={(e) => { e.preventDefault(); enviar(entrada) }}>
            <button type="button" onClick={escuchar} disabled={!voz.reconocimiento()}
              title={voz.reconocimiento() ? (fase === 'escuchando' ? 'Dejar de escuchar' : 'Hablar (el audio lo procesa el navegador)')
                : 'Este navegador no reconoce voz: usa el texto'}
              aria-label="Hablar"
              className={`flex size-9 shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-40 ${
                fase === 'escuchando' ? 'border-ok bg-ok-bg text-ok' : 'border-line text-navy hover:border-navy'}`}>
              <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
              </svg>
            </button>
            <input value={entrada} onChange={(e) => setEntrada(e.target.value)} maxLength={2000}
              placeholder={fase === 'escuchando' ? 'Escuchando…' : 'Escribe una orden o una pregunta'}
              aria-label="Orden para LIRA"
              className="min-w-0 flex-1 rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-mute" />
            {fase !== 'inactiva' ? (
              <button type="button" onClick={cancelarTodo} className="rounded-md border border-danger/40 px-2.5 py-2 text-xs font-semibold text-danger" title="Cancelar la operación en curso">
                Cancelar
              </button>
            ) : (
              <button className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-on-accent disabled:opacity-40" disabled={!entrada.trim()}>Enviar</button>
            )}
            <button type="button" onClick={() => { setHablarActivo((h) => !h); voz.callar() }}
              aria-pressed={hablarActivo} title={hablarActivo ? 'Silenciar la voz de LIRA' : 'Activar la voz de LIRA'}
              className={`shrink-0 rounded p-1.5 text-xs ${hablarActivo ? 'text-navy' : 'text-ink-mute'}`}>
              {hablarActivo ? '🔊' : '🔇'}
            </button>
          </form>
        </section>
      )}
    </>
  )
}
