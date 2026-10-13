/**
 * Gemelo digital de STRaND-1: consola de monitorización sobre el archivo de
 * balizas.
 *
 * Lo que esta página es: un reproductor del histórico real. El cursor recorre
 * los eventos (instantes en que llegó alguna baliza) y las tres vistas —modelo
 * 3D, tarjetas de telemetría y gráfica— muestran el mismo instante.
 *
 * Lo que no es: un enlace en vivo. No hay telemetría en tiempo real, y la
 * página lo dice en la cabecera en lugar de aparentarlo. Tampoco controla
 * nada: solo lee.
 *
 * Sobre el transporte: el cursor avanza por **índice de evento**, no por tiempo
 * real; la velocidad se rotula en eventos por segundo para no dar a entender
 * que el navegador respeta la cadencia de las balizas.
 *
 * Sobre los datos: nada se interpola ni se rellena. Donde no hay lecturas la
 * gráfica se interrumpe, y un parámetro que la baliza no trae se muestra como
 * no disponible con su motivo.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { Modelo3D, estadoDeComponente } from '../components/gemelo/Modelo3D'
import type { Camara, ModoVista } from '../components/gemelo/Modelo3D'
import { PanelEstructura, PanelProcedencia, PanelSubsistemas } from '../components/gemelo/Paneles'
import {
  edadLegible, etiquetaCampo, fechaUTC, FilaLectura, Sello, SelloValidacion, valorLegible,
} from '../components/gemelo/comunes'
import { ErrorState, Skeleton } from '../components/ui'
import { COMPONENTES, FUENTE_MISION, NO_DISPONIBLES, SUBSISTEMAS } from '../data/referenciaStrand1'
import { api, useApi } from '../lib/api'
import type { EstadoGemelo, EtiquetaAnomalia, EventoGemelo, LecturaGemelo } from '../lib/api'

const VELOCIDADES = [1, 2, 5, 10, 25, 60]
const DIA_MS = 86_400_000
/** Sin lecturas durante más de esto, la línea de la gráfica se interrumpe. */
const HUECO_DIAS = 7

type Pestana = 'monitor' | 'subsistemas' | 'estructura' | 'procedencia'

const PESTANAS: { id: Pestana; texto: string }[] = [
  { id: 'monitor', texto: 'Monitor' },
  { id: 'subsistemas', texto: 'Subsistemas' },
  { id: 'estructura', texto: 'Estructura' },
  { id: 'procedencia', texto: 'Procedencia y discrepancias' },
]

/** Diagnóstico del canal gobernante: texto y color, con un único significado. */
const DIAGNOSTICO: Record<EtiquetaAnomalia, { texto: string; tono: string; color: string }> = {
  normal: { texto: 'Dentro de lo habitual', tono: 'gd-t-verde', color: '#34d399' },
  advertencia: { texto: 'Advertencia', tono: 'gd-t-ambar', color: '#fbbf24' },
  anomalia: { texto: 'Anomalía', tono: 'gd-t-rojo', color: '#f87171' },
  canal_enrielado: { texto: 'Instrumentación perdida', tono: 'gd-t-rojo', color: '#f87171' },
  sin_referencia: { texto: 'Sin referencia', tono: 'gd-t-gris', color: '#64748b' },
}

/** Agrupación de las lecturas en el panel: por función, no por orden de llegada. */
const GRUPOS: { titulo: string; nota: string; filtro: (c: string) => boolean }[] = [
  {
    titulo: 'Potencia · almacenamiento',
    nota: 'Tensión de las dos baterías',
    filtro: (c) => /^battery_[01]_voltage$/.test(c),
  },
  {
    titulo: 'Potencia · generación',
    nota: 'Corriente de panel por eje cuerpo',
    filtro: (c) => /_array_current$/.test(c),
  },
  { titulo: 'Computador de a bordo', nota: 'OBC', filtro: (c) => c === 'obc_uptime' },
  {
    titulo: 'Actitud · magnetómetro',
    nota: 'Cuentas sin calibrar; no determinan la orientación',
    filtro: (c) => c.startsWith('magnetometer_'),
  },
  {
    titulo: 'Cargas conmutadas',
    nota: 'Corriente y tensión de cada línea',
    filtro: (c) => /^switch_\d.*_(corriente|tension)$/.test(c),
  },
]

const diasDesde = (iso: string) => Math.floor((Date.now() - Date.parse(iso)) / DIA_MS)

function TarjetaLectura({ l }: { l: LecturaGemelo }) {
  return (
    <div className="gd-tarjeta" data-estado={l.validacion?.estado} data-frescura={l.frescura}
         title={`${l.campo} · medida el ${fechaUTC(l.medida_en)}${l.validacion ? ` · ${l.validacion.detalle}` : ''}`}>
      <div className="gd-tarjeta-nombre">{etiquetaCampo(l.campo)}</div>
      <div className="gd-tarjeta-valor">
        {valorLegible(l.valor, l.unidad)}<small>{l.unidad}</small>
      </div>
      <div className="gd-tarjeta-pie">
        hace {edadLegible(l.edad_s)} · <SelloValidacion v={l.validacion} />
      </div>
    </div>
  )
}

export function GemeloDigital() {
  const { data: resumen, error, loading } = useApi(() => api.gemeloResumen(), [])
  const [pestana, setPestana] = useState<Pestana>('monitor')

  /* ── Cursor de reproducción ─────────────────────────────────────────────── */
  const [campo, setCampo] = useState('battery_voltage')
  const [indice, setIndice] = useState(0)
  const [reproduciendo, setReproduciendo] = useState(false)
  const [velocidad, setVelocidad] = useState(10)

  /* ── Estado del instante: se conserva el último válido si la API falla ──── */
  const [estado, setEstado] = useState<EstadoGemelo | null>(null)
  const [fallo, setFallo] = useState<string | null>(null)
  const [ultimaRespuesta, setUltimaRespuesta] = useState<number | null>(null)
  const [ahora, setAhora] = useState(() => Date.now())
  const enVuelo = useRef(false)
  const pendiente = useRef<number | null>(null)

  const pedirEstado = useCallback((i: number, c: string) => {
    // Una petición a la vez. Si llega otra mientras tanto se recuerda solo la
    // última: reproducir deprisa no encola cientos de peticiones.
    if (enVuelo.current) {
      pendiente.current = i
      return
    }
    enVuelo.current = true
    api.gemeloEstado(i, c)
      .then((e) => {
        setEstado(e)
        setFallo(null)
        setUltimaRespuesta(Date.now())
      })
      .catch((e: Error) => setFallo(e.message))
      .finally(() => {
        enVuelo.current = false
        if (pendiente.current !== null && pendiente.current !== i) {
          const siguiente = pendiente.current
          pendiente.current = null
          pedirEstado(siguiente, c)
        } else {
          pendiente.current = null
        }
      })
  }, [])

  useEffect(() => pedirEstado(indice, campo), [indice, campo, pedirEstado])

  // Reloj solo para mostrar la antigüedad de la última respuesta cuando falla.
  useEffect(() => {
    if (!fallo) return
    const id = window.setInterval(() => setAhora(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [fallo])

  useEffect(() => {
    if (!reproduciendo || !resumen) return
    const id = window.setInterval(() => {
      setIndice((i) => (i + 1 >= resumen.eventos ? (setReproduciendo(false), i) : i + 1))
    }, 1000 / velocidad)
    return () => window.clearInterval(id)
  }, [reproduciendo, velocidad, resumen])

  /* ── Gráfica: intervalo de vista ────────────────────────────────────────── */
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const serie = useApi(() => api.gemeloSerie(campo, desde || undefined, hasta || undefined),
                       [campo, desde, hasta])
  const eventos = useApi(() => api.gemeloEventos(campo), [campo])

  /** Lleva el cursor al evento vigente en una fecha exacta. */
  const irA = useCallback((iso: string, margen = 0) => {
    api.gemeloIndice(iso)
      .then((r) => setIndice(Math.max(0, r.indice - margen)))
      .catch((e: Error) => setFallo(e.message))
  }, [])

  /* ── Modelo 3D ──────────────────────────────────────────────────────────── */
  const [modo, setModo] = useState<ModoVista>('exterior')
  const [camara, setCamara] = useState<Camara>('isometrica')
  const [desplegado, setDesplegado] = useState(true)
  const [giro, setGiro] = useState(false)
  const [etiquetas, setEtiquetas] = useState(true)
  const [seleccion, setSeleccion] = useState<string | null>(null)

  const lecturas = useMemo(() => {
    const m = new Map<string, LecturaGemelo>()
    estado?.lecturas.forEach((l) => m.set(l.campo, l))
    return m
  }, [estado])

  /** Puntos de la gráfica en eje de tiempo real, con los huecos sin unir. */
  const puntos = useMemo(() => {
    const salida: { ts: number; valor: number | null; mediana: number | null; etiqueta?: EtiquetaAnomalia }[] = []
    let previo: number | null = null
    for (const p of serie.data?.puntos ?? []) {
      const ts = Date.parse(p.t)
      if (previo !== null && ts - previo > HUECO_DIAS * DIA_MS) {
        // Marca de hueco: corta la línea. No es un dato, y no se interpola.
        salida.push({ ts: previo + 1, valor: null, mediana: null })
      }
      salida.push({ ts, valor: p.valor, mediana: p.mediana, etiqueta: p.etiqueta })
      previo = ts
    }
    return salida
  }, [serie.data])

  const extremos = useMemo(() => {
    const validos = puntos.filter((p) => p.valor !== null) as { ts: number; valor: number }[]
    if (!validos.length) return null
    const max = validos.reduce((a, b) => (b.valor > a.valor ? b : a))
    const min = validos.reduce((a, b) => (b.valor < a.valor ? b : a))
    return { max, min, huecos: puntos.filter((p) => p.valor === null && p.etiqueta === undefined).length }
  }, [puntos])

  if (loading) return <Skeleton className="h-96" />
  if (error) return <ErrorState mensaje={error} />
  if (!resumen) return null

  const diag = DIAGNOSTICO[estado?.etiqueta ?? 'sin_referencia']
  const antiguedadArchivo = diasDesde(resumen.fin)
  const tsCursor = estado ? Date.parse(estado.momento) : null
  const unidadSerie = serie.data?.unidad ?? ''
  const noNormales = (serie.data?.puntos ?? []).filter((p) => p.etiqueta !== 'normal' && p.etiqueta !== 'sin_referencia').length
  const listaEventos = [...(eventos.data?.eventos ?? [])].sort((a, b) => a.inicio.localeCompare(b.inicio))
  const comp = COMPONENTES.find((c) => c.id === seleccion)

  const intervalo = (d: string, h: string) => { setDesde(d); setHasta(h) }
  const alrededorDelCursor = () => {
    if (!tsCursor) return
    intervalo(new Date(tsCursor - 30 * DIA_MS).toISOString().slice(0, 10),
              new Date(tsCursor + 30 * DIA_MS).toISOString().slice(0, 10))
  }
  const reproducirEvento = (ev: EventoGemelo) => {
    // Unos eventos antes del suceso y despacio, para ver la transición.
    irA(ev.inicio, 40)
    setVelocidad(2)
    setReproduciendo(true)
  }

  return (
    <div className="gemelo">
      {/* ── Cabecera ───────────────────────────────────────────────────────── */}
      <header className="gd-cabecera">
        <div>
          <h1 className="gd-titulo">Gemelo digital · STRaND-1</h1>
          <p className="gd-sub">
            CubeSat 3U · NORAD 39090 · {resumen.eventos.toLocaleString('es-CO')} eventos en{' '}
            {resumen.pases} pases, {fechaUTC(resumen.inicio).slice(0, 10)} a {fechaUTC(resumen.fin).slice(0, 10)}
          </p>
        </div>
        <div className="gd-chips" role="status" aria-live="polite">
          <span className="gd-chip gd-t-ambar" title={resumen.nota_conexion}>
            <span className="gd-punto" /> Archivo histórico · sin enlace en vivo
          </span>
          <span className="gd-chip" title={`Última baliza decodificada: ${fechaUTC(resumen.fin)}`}>
            Última baliza: {fechaUTC(resumen.fin).slice(0, 10)} · hace {antiguedadArchivo.toLocaleString('es-CO')} días
          </span>
          {fallo ? (
            <span className="gd-chip gd-t-rojo" title={fallo}>
              <span className="gd-punto" /> Actualización interrumpida
              {ultimaRespuesta && ` · último dato válido hace ${edadLegible(Math.max(0, ahora - ultimaRespuesta) / 1000)}`}
            </span>
          ) : (
            <span className="gd-chip gd-t-cian"><span className="gd-punto" /> API de datos: responde</span>
          )}
        </div>
      </header>

      <div className="gd-tabs" role="tablist" aria-label="Secciones del gemelo digital">
        {PESTANAS.map((p) => (
          <button key={p.id} type="button" role="tab" className="gd-tab"
                  aria-selected={pestana === p.id} onClick={() => setPestana(p.id)}>
            {p.texto}
          </button>
        ))}
      </div>

      {pestana === 'subsistemas' && (
        <PanelSubsistemas lecturas={lecturas}
                          onVerEnModelo={(id) => { setSeleccion(id); if (id !== 'chasis' && !id.startsWith('panel') && id !== 'antenas') setModo('explotada'); setPestana('monitor') }} />
      )}
      {pestana === 'estructura' && <PanelEstructura />}
      {pestana === 'procedencia' && (
        <PanelProcedencia fuente={resumen.fuente} fuenteCalibracion={resumen.fuente_calibracion} />
      )}

      {pestana === 'monitor' && (
        <div className="gd-grid">
          {/* ── Modelo 3D + panel lateral ──────────────────────────────────── */}
          <div className="gd-grid gd-principal">
            <section className="gd-panel" aria-label="Modelo tridimensional">
              <h2 className="gd-panel-titulo">
                <span>Modelo 3D</span>
                <small>configuración general según {FUENTE_MISION.clave} · interior esquemático</small>
              </h2>
              <div className="gd-lienzo">
                <Modelo3D lecturas={estado?.lecturas ?? []} modo={modo} camara={camara}
                          desplegado={desplegado} giro={giro} etiquetas={etiquetas}
                          seleccion={seleccion} onSeleccion={setSeleccion} />
                <div className="gd-sobre gd-sobre-arriba">
                  <div className="gd-grupo" role="group" aria-label="Modo de vista">
                    {(['exterior', 'interior', 'explotada'] as ModoVista[]).map((m) => (
                      <button key={m} type="button" className="gd-btn" aria-pressed={modo === m}
                              onClick={() => setModo(m)}>
                        {m === 'exterior' ? 'Exterior' : m === 'interior' ? 'Interior' : 'Explotada'}
                      </button>
                    ))}
                  </div>
                  <div className="gd-grupo" role="group" aria-label="Vista de cámara">
                    {(['isometrica', 'frontal', 'lateral', 'superior'] as Camara[]).map((c) => (
                      <button key={c} type="button" className="gd-btn" aria-pressed={camara === c}
                              onClick={() => setCamara(c)}>
                        {c === 'isometrica' ? 'Isométrica' : c[0].toUpperCase() + c.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="gd-sobre gd-sobre-abajo">
                  <div className="gd-grupo" role="group" aria-label="Opciones de representación">
                    <button type="button" className="gd-btn" aria-pressed={desplegado}
                            title="Animación conceptual: la baliza no informa del despliegue"
                            onClick={() => setDesplegado((d) => !d)}>
                      Paneles y antenas: {desplegado ? 'desplegados' : 'plegados'}
                    </button>
                    <button type="button" className="gd-btn" aria-pressed={etiquetas}
                            title="Nombres de todas las piezas en la vista explotada"
                            onClick={() => setEtiquetas((e) => !e)}>Etiquetas</button>
                    <button type="button" className="gd-btn" aria-pressed={giro}
                            title="Giro de presentación: STRaND-1 no transmite actitud"
                            onClick={() => setGiro((g) => !g)}>Giro</button>
                  </div>
                </div>
              </div>
              <p className="gd-tarjeta-pie" style={{ marginTop: 8 }}>
                <Sello clase="conceptual" /> El despliegue, la separación de la vista explotada y el giro
                son representaciones: no corresponden a ningún dato. El modelo no adopta orientación
                alguna porque STRaND-1 no transmite actitud. Arrastra para orbitar, rueda para acercar,
                botón derecho para desplazar. Escala 1:1 entre piezas; el monopolo VHF mide ≈ 51 cm.
              </p>
              <div className="gd-lista-comp" style={{ marginTop: 10 }} aria-label="Componentes del modelo">
                {COMPONENTES.map((c) => {
                  const est = estadoDeComponente(c.id, lecturas)
                  const tono = est === 'con_lectura' ? 'gd-t-cian' : est === 'sin_medida' ? 'gd-t-ambar' : 'gd-t-gris'
                  return (
                    <button key={c.id} type="button" className={`gd-comp ${tono}`}
                            aria-pressed={seleccion === c.id}
                            onClick={() => {
                              setSeleccion(seleccion === c.id ? null : c.id)
                              if (modo === 'exterior' && !['chasis', 'antenas', 'panel_ala_a', 'panel_ala_b'].includes(c.id))
                                setModo('interior')
                            }}>
                      <span className="gd-punto" />{c.nombre}
                    </button>
                  )
                })}
              </div>
            </section>

            <div className="gd-grid" style={{ alignContent: 'start' }}>
              {/* ── Instante ───────────────────────────────────────────────── */}
              <section className="gd-panel" aria-label="Instante reproducido">
                <h2 className="gd-panel-titulo"><span>Instante reproducido</span><Sello clase="historico" /></h2>
                <div className="gd-mono" style={{ fontSize: 19, fontWeight: 600 }}>{fechaUTC(estado?.momento)}</div>
                <dl className="gd-dl" style={{ marginTop: 8 }}>
                  <dt>Evento</dt>
                  <dd>{(indice + 1).toLocaleString('es-CO')} de {resumen.eventos.toLocaleString('es-CO')}</dd>
                  <dt>Pase de recepción</dt><dd>n.º {estado ? estado.pase + 1 : '—'} de {resumen.pases}</dd>
                  <dt>Lecturas vigentes</dt><dd>{estado?.lecturas.length ?? '—'}</dd>
                </dl>
                <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                  <span className={`gd-chip ${diag.tono}`} title={estado?.nota_estado}>
                    <span className="gd-punto" /> {diag.texto}
                  </span>
                  <Sello clase="derivado" />
                </div>
                <p className="gd-tarjeta-pie">
                  Diagnóstico estadístico de «{etiquetaCampo(campo)}» (mediana móvil y desviación
                  robusta). No es un estado declarado por el satélite ni describe a los demás canales.
                </p>
              </section>

              {/* ── Componente seleccionado ───────────────────────────────── */}
              <section className="gd-panel" aria-live="polite" aria-label="Componente seleccionado">
                <h2 className="gd-panel-titulo">
                  <span>Componente</span>
                  {comp && <small>{SUBSISTEMAS.find((s) => s.id === comp.subsistema)?.titulo}</small>}
                </h2>
                {!comp ? (
                  <p className="gd-vacio" style={{ fontSize: 12.5 }}>
                    Selecciona un componente en el modelo o en la lista para ver su función y sus datos.
                  </p>
                ) : (
                  <>
                    <div style={{ fontWeight: 600, fontSize: 15 }}>{comp.nombre}</div>
                    <p style={{ fontSize: 12.5, marginTop: 4 }}>{comp.funcion}</p>
                    <p className="gd-tarjeta-pie">
                      <Sello clase="referencia" /> Geometría {comp.geometria}. {comp.notaGeometria}
                    </p>
                    <div style={{ marginTop: 10 }}>
                      {comp.campos.length === 0 ? (
                        <p className="gd-tarjeta-pie" style={{ fontSize: 12 }}>
                          <Sello clase="no_disponible" /> {comp.sinTelemetria}
                        </p>
                      ) : comp.campos.some((c) => lecturas.has(c)) ? (
                        <div className="gd-tabla-scroll">
                          <table className="gd-tabla">
                            <tbody>
                              {comp.campos.map((c) => lecturas.get(c)).filter(Boolean).map((l) => (
                                <FilaLectura key={l!.campo} l={l!} />
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="gd-vacio" style={{ fontSize: 12 }}>Sin datos hasta este instante</p>
                      )}
                    </div>
                  </>
                )}
              </section>
            </div>
          </div>

          {/* ── Transporte ─────────────────────────────────────────────────── */}
          <section className="gd-panel" aria-label="Reproducción">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
              <button type="button" className="gd-btn gd-btn-solo gd-btn-primario"
                      onClick={() => setReproduciendo((r) => !r)}>
                {reproduciendo ? '⏸ Pausar' : '▶ Reproducir'}
              </button>
              <div className="gd-grupo" role="group" aria-label="Mover el cursor">
                <button type="button" className="gd-btn" aria-label="Retroceder 10 eventos"
                        onClick={() => setIndice((i) => Math.max(0, i - 10))}>◀◀</button>
                <button type="button" className="gd-btn" aria-label="Evento anterior"
                        onClick={() => setIndice((i) => Math.max(0, i - 1))}>◀</button>
                <button type="button" className="gd-btn" aria-label="Evento siguiente"
                        onClick={() => setIndice((i) => Math.min(resumen.eventos - 1, i + 1))}>▶</button>
                <button type="button" className="gd-btn" aria-label="Avanzar 10 eventos"
                        onClick={() => setIndice((i) => Math.min(resumen.eventos - 1, i + 10))}>▶▶</button>
              </div>
              <select className="gd-select" aria-label="Velocidad de reproducción" value={velocidad}
                      onChange={(e) => setVelocidad(Number(e.target.value))}>
                {VELOCIDADES.map((v) => <option key={v} value={v}>{v} eventos/s</option>)}
              </select>
              <span className="gd-tarjeta-pie" style={{ margin: 0 }}>
                El cursor avanza por evento recibido, no en tiempo real.
              </span>
            </div>
            <input type="range" className="gd-rango" style={{ marginTop: 10 }} min={0}
                   max={resumen.eventos - 1} value={indice} aria-label="Posición en el archivo"
                   aria-valuetext={fechaUTC(estado?.momento)}
                   onChange={(e) => setIndice(Number(e.target.value))} />
          </section>

          {/* ── Telemetría del instante ────────────────────────────────────── */}
          <section className="gd-panel" aria-label="Telemetría del instante">
            <h2 className="gd-panel-titulo">
              <span>Telemetría en el instante</span>
              <small>último valor conocido de cada canal, con su antigüedad · {resumen.fuente}</small>
            </h2>
            {!estado ? <Skeleton className="h-40" /> : (
              <div className="gd-grid">
                {GRUPOS.map((g) => {
                  const ls = estado.lecturas.filter((l) => g.filtro(l.campo))
                    .sort((a, b) => a.campo.localeCompare(b.campo, 'es', { numeric: true }))
                  return (
                    <div key={g.titulo}>
                      <div className="gd-panel-titulo" style={{ marginBottom: 6 }}>
                        <span style={{ color: 'var(--g-texto)' }}>{g.titulo}</span><small>{g.nota}</small>
                      </div>
                      {ls.length ? (
                        <div className="gd-tarjetas">{ls.map((l) => <TarjetaLectura key={l.campo} l={l} />)}</div>
                      ) : (
                        <p className="gd-vacio" style={{ fontSize: 12.5 }}>Sin datos hasta este instante</p>
                      )}
                    </div>
                  )
                })}
                <div>
                  <div className="gd-panel-titulo" style={{ marginBottom: 6 }}>
                    <span style={{ color: 'var(--g-texto)' }}>No disponibles</span>
                    <small>la baliza o la fuente no los entregan</small>
                  </div>
                  <div className="gd-tarjetas">
                    {NO_DISPONIBLES.map((n) => (
                      <div key={n.magnitud} className="gd-tarjeta" title={n.motivo}>
                        <div className="gd-tarjeta-nombre">{n.magnitud}</div>
                        <div className="gd-tarjeta-valor gd-vacio" style={{ fontSize: 14 }}>{n.estado}</div>
                        <div className="gd-tarjeta-pie">{n.motivo}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <details>
                  <summary style={{ cursor: 'pointer', fontSize: 12.5, color: 'var(--g-suave)' }}>
                    Todas las lecturas vigentes, incluidas las cuentas crudas del ADC ({estado.lecturas.length})
                  </summary>
                  <div className="gd-tabla-scroll" style={{ marginTop: 8 }}>
                    <table className="gd-tabla">
                      <thead><tr><th>Canal</th><th style={{ textAlign: 'right' }}>Valor</th><th style={{ textAlign: 'right' }}>Antigüedad</th><th>Validación</th></tr></thead>
                      <tbody>{estado.lecturas.map((l) => <FilaLectura key={l.campo} l={l} />)}</tbody>
                    </table>
                  </div>
                </details>
              </div>
            )}
          </section>

          {/* ── Gráfica histórica ──────────────────────────────────────────── */}
          <section className="gd-panel" aria-label="Serie histórica">
            <h2 className="gd-panel-titulo">
              <span>Serie histórica · {etiquetaCampo(campo)}{unidadSerie && ` (${unidadSerie})`}</span>
              <Sello clase="historico" />
            </h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 10 }}>
              <select className="gd-select" aria-label="Magnitud" value={campo}
                      onChange={(e) => setCampo(e.target.value)}>
                {resumen.magnitudes.map((m) => (
                  <option key={m.campo} value={m.campo}>
                    {etiquetaCampo(m.campo)}{m.unidad && ` (${m.unidad})`}
                  </option>
                ))}
              </select>
              <div className="gd-grupo" role="group" aria-label="Intervalo de la gráfica">
                <button type="button" className="gd-btn" aria-pressed={!desde && !hasta}
                        onClick={() => intervalo('', '')}>Todo</button>
                {['2016', '2019', '2020', '2021', '2022'].map((a) => (
                  <button key={a} type="button" className="gd-btn"
                          aria-pressed={desde === `${a}-01-01` && hasta === `${a}-12-31`}
                          onClick={() => intervalo(`${a}-01-01`, `${a}-12-31`)}>{a}</button>
                ))}
                <button type="button" className="gd-btn" disabled={!tsCursor}
                        onClick={alrededorDelCursor}>±30 d del cursor</button>
              </div>
              <label className="gd-tarjeta-pie" style={{ margin: 0 }}>
                Desde <input type="date" className="gd-fecha" value={desde}
                             onChange={(e) => setDesde(e.target.value)} />
              </label>
              <label className="gd-tarjeta-pie" style={{ margin: 0 }}>
                Hasta <input type="date" className="gd-fecha" value={hasta}
                             onChange={(e) => setHasta(e.target.value)} />
              </label>
            </div>

            {serie.error ? (
              <div className="gd-nota gd-nota-rojo">No se pudo cargar la serie: {serie.error}</div>
            ) : serie.loading || !serie.data ? (
              <Skeleton className="h-64" />
            ) : puntos.length === 0 ? (
              <div className="gd-nota gd-nota-ambar">
                <strong>Sin datos en este intervalo.</strong> La serie completa va del{' '}
                {fechaUTC(serie.data.inicio_serie).slice(0, 10)} al {fechaUTC(serie.data.fin_serie).slice(0, 10)}.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={puntos} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}
                           onClick={(e) => {
                             const ts = Number((e as { activeLabel?: unknown } | null)?.activeLabel)
                             if (Number.isFinite(ts) && ts > 0) irA(new Date(ts).toISOString())
                           }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1d2a3c" />
                  <XAxis dataKey="ts" type="number" scale="time" domain={['dataMin', 'dataMax']}
                         tickFormatter={(t: number) => new Date(t).toISOString().slice(0, 10)}
                         minTickGap={48} stroke="#5d6f86" fontSize={11} />
                  <YAxis stroke="#5d6f86" fontSize={11} width={58} domain={['auto', 'auto']}
                         tickFormatter={(v: number) => v.toLocaleString('es-CO')} />
                  <Tooltip
                    contentStyle={{ background: '#0c1420', border: '1px solid #1d2a3c', fontSize: 12 }}
                    labelStyle={{ color: '#dbe6f3' }}
                    labelFormatter={(t) => fechaUTC(new Date(Number(t)).toISOString())}
                    formatter={(v, n) => [`${Number(v).toLocaleString('es-CO')} ${unidadSerie}`, String(n)]}
                  />
                  <Line type="linear" dataKey="mediana" stroke="#38bdf8" dot={false} connectNulls={false}
                        strokeDasharray="4 3" strokeWidth={1} name="Mediana móvil (derivado)"
                        isAnimationActive={false} />
                  <Line type="linear" dataKey="valor" stroke="#e2e8f0" strokeWidth={1.2} connectNulls={false}
                        name="Recibido" isAnimationActive={false}
                        dot={(d: { cx?: number; cy?: number; index?: number; payload?: { etiqueta?: EtiquetaAnomalia } }) => {
                          const et = d.payload?.etiqueta
                          if (!et || d.cx == null || d.cy == null) return <g key={d.index} />
                          // Toda lectura se marca: una aislada entre dos huecos no
                          // tiene segmento que la una a nada y sin punto no se vería.
                          const habitual = et === 'normal' || et === 'sin_referencia'
                          return <circle key={d.index} cx={d.cx} cy={d.cy} r={habitual ? 1.1 : 2.2}
                                         fill={habitual ? '#cbd5e1' : DIAGNOSTICO[et].color} />
                        }} />
                  {tsCursor && <ReferenceLine x={tsCursor} stroke="#22d3ee" strokeWidth={1.5} />}
                </LineChart>
              </ResponsiveContainer>
            )}

            {serie.data && puntos.length > 0 && (
              <>
                <p className="gd-tarjeta-pie" style={{ marginTop: 6 }}>
                  Línea cian: instante reproducido (haz clic en la gráfica para llevar allí el cursor).
                  Cada punto es una lectura recibida; en color, las que el clasificador no da por habituales. La línea se
                  interrumpe donde pasan más de {HUECO_DIAS} días sin lecturas: no se interpola ni se
                  rellena.
                </p>
                <dl className="gd-dl" style={{ marginTop: 8, gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '6px 18px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <dt>Lecturas en el intervalo</dt>
                    <dd>{(serie.data.n_en_intervalo ?? serie.data.n_total).toLocaleString('es-CO')} de {serie.data.n_total.toLocaleString('es-CO')}</dd>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <dt>Dibujadas</dt>
                    <dd>{serie.data.n_enviados.toLocaleString('es-CO')}{serie.data.submuestreo > 1 && ` (1 de cada ${serie.data.submuestreo})`}</dd>
                  </div>
                  {extremos && (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                        <dt>Máximo</dt>
                        <dd>
                          <button type="button" className="gd-comp" onClick={() => irA(new Date(extremos.max.ts).toISOString())}>
                            {valorLegible(extremos.max.valor, unidadSerie)} {unidadSerie} · {new Date(extremos.max.ts).toISOString().slice(0, 10)}
                          </button>
                        </dd>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                        <dt>Mínimo</dt>
                        <dd>
                          <button type="button" className="gd-comp" onClick={() => irA(new Date(extremos.min.ts).toISOString())}>
                            {valorLegible(extremos.min.valor, unidadSerie)} {unidadSerie} · {new Date(extremos.min.ts).toISOString().slice(0, 10)}
                          </button>
                        </dd>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                        <dt>Huecos de más de {HUECO_DIAS} días</dt><dd>{extremos.huecos}</dd>
                      </div>
                    </>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <dt>Lecturas no habituales</dt><dd>{noNormales.toLocaleString('es-CO')}</dd>
                  </div>
                </dl>
                {serie.data.submuestreo > 1 && (
                  <p className="gd-tarjeta-pie">
                    Para dibujar se toma 1 de cada {serie.data.submuestreo} lecturas, sin promediar; el
                    máximo y el mínimo indicados son los de las lecturas dibujadas. Acota el intervalo
                    para verlas todas.
                  </p>
                )}
              </>
            )}
          </section>

          {/* ── Eventos ────────────────────────────────────────────────────── */}
          <section className="gd-panel" aria-label="Eventos detectados">
            <h2 className="gd-panel-titulo">
              <span>Eventos detectados en «{etiquetaCampo(campo)}»</span>
              <small>
                <Sello clase="derivado" /> tramos que el clasificador separa de lo habitual
                {eventos.data && ` · ${listaEventos.length} de ${eventos.data.n_total}, los más largos`}
              </small>
            </h2>
            {eventos.error ? (
              <div className="gd-nota gd-nota-rojo">No se pudieron cargar los eventos: {eventos.error}</div>
            ) : eventos.loading ? <Skeleton className="h-24" /> : listaEventos.length === 0 ? (
              <p className="gd-vacio" style={{ fontSize: 12.5 }}>Ningún evento registrado en esta magnitud.</p>
            ) : (
              <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                {listaEventos.map((ev) => {
                  const d = DIAGNOSTICO[ev.etiqueta]
                  return (
                    <div key={`${ev.inicio}${ev.etiqueta}`} className="gd-evento">
                      <span className={`gd-chip ${d.tono}`}><span className="gd-punto" />{d.texto}</span>
                      <span className="gd-mono">{fechaUTC(ev.inicio)}</span>
                      <span style={{ color: 'var(--g-suave)' }}>
                        {(ev.duracion_s / 86400).toFixed(1)} d · {ev.n_lecturas} lecturas · habitual{' '}
                        {ev.valor_esperado} → recibido {ev.valor_registrado} {eventos.data?.unidad}
                      </span>
                      <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
                        <button type="button" className="gd-btn gd-btn-solo" onClick={() => irA(ev.inicio)}>Ir al inicio</button>
                        <button type="button" className="gd-btn gd-btn-solo" onClick={() => reproducirEvento(ev)}>▶ Reproducir</button>
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
