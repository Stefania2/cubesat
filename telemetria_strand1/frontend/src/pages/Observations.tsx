/**
 * Observaciones: el movimiento de STRaND-1 sobre una estación de SatNOGS, en 3D.
 *
 * Cada observación de SatNOGS Network guarda la estación (dónde está) y el TLE
 * (la «dirección orbital» del satélite) con que se programó. El backend propaga
 * ese TLE con SGP4 y devuelve dónde estaba el satélite cada 5 segundos del pase.
 * La posición es ESTIMADA; la estación, la ventana y las tramas son REALES.
 */

import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { Badge, Card, CardHeader, EmptyState, ErrorState, Nota, Skeleton } from '../components/ui'
import { api, useApi } from '../lib/api'
import type { PaseResumen, PasoObservacion } from '../lib/api'
import { fechaHoraUTC, numero } from '../lib/format'

// three.js pesa: el globo se carga solo al entrar aquí.
const Globo3D = lazy(() =>
  import('../components/observaciones/Globo3D').then((m) => ({ default: m.Globo3D })),
)

const VELOCIDADES = [10, 30, 60, 120]

/** Número con coma decimal, como se escribe en español. */
function num(n: number, decimales = 1): string {
  return n.toLocaleString('es-ES', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })
}

function rumbo(az: number): string {
  const nombres = ['norte', 'noreste', 'este', 'sureste', 'sur', 'suroeste', 'oeste', 'noroeste']
  return nombres[Math.round(az / 45) % 8]
}

function Ayuda({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <details className="text-sm">
      <summary className="cursor-pointer select-none text-xs font-medium text-navy hover:underline">
        {titulo}
      </summary>
      <div className="mt-1 text-ink-soft">{children}</div>
    </details>
  )
}

/** El cielo visto desde la estación: el centro es «justo encima», el borde es el horizonte. */
function MapaCielo({ paso, indice }: { paso: PasoObservacion; indice: number }) {
  const R = 90
  const xy = (az: number, el: number) => {
    const r = ((90 - Math.max(el, 0)) / 90) * R
    const a = (az * Math.PI) / 180
    return [100 + r * Math.sin(a), 100 - r * Math.cos(a)]
  }
  const visibles = paso.puntos.filter((p) => p.el >= 0)
  const camino = visibles.map((p) => xy(p.az, p.el).join(',')).join(' ')
  const actual = paso.puntos[Math.floor(indice)]
  const [cx, cy] = xy(actual.az, actual.el)
  return (
    <svg viewBox="0 0 200 200" className="mx-auto h-56 w-56" role="img"
      aria-label="Mapa del cielo de la estación con el recorrido del satélite">
      <circle cx="100" cy="100" r={R} fill="#0b121c" stroke="#22324A" />
      <circle cx="100" cy="100" r={R * (2 / 3)} fill="none" stroke="#22324A" strokeDasharray="3 3" />
      <circle cx="100" cy="100" r={R / 3} fill="none" stroke="#22324A" strokeDasharray="3 3" />
      <line x1="100" y1="10" x2="100" y2="190" stroke="#22324A" />
      <line x1="10" y1="100" x2="190" y2="100" stroke="#22324A" />
      {[['N', 100, 7], ['S', 100, 199], ['E', 196, 103], ['O', 4, 103]].map(([t, x, y]) => (
        <text key={t as string} x={x as number} y={y as number} fill="#93A4B8" fontSize="9" textAnchor="middle">{t}</text>
      ))}
      <text x="104" y={100 - R / 3 + 9} fill="#6B7D92" fontSize="7">60°</text>
      <text x="104" y={100 - (2 * R) / 3 + 9} fill="#6B7D92" fontSize="7">30°</text>
      {camino && <polyline points={camino} fill="none" stroke="#22D3EE" strokeWidth="2" />}
      {actual.el >= 0 && <circle cx={cx} cy={cy} r="5" fill="#FBBF24" />}
    </svg>
  )
}

function Paso({ paso }: { paso: PasoObservacion }) {
  const [indice, setIndice] = useState(0)
  const [reproduciendo, setReproduciendo] = useState(true)
  const [velocidad, setVelocidad] = useState(30)
  const n = paso.puntos.length

  useEffect(() => {
    setIndice(0)
    setReproduciendo(true)
  }, [paso.observation_id])

  useEffect(() => {
    if (!reproduciendo) return
    // Cada punto son `paso_s` segundos reales; a velocidad v se recorren v
    // segundos reales por segundo de pantalla.
    const id = window.setInterval(() => {
      setIndice((i) => {
        const siguiente = i + (velocidad / paso.paso_s) * 0.05
        return siguiente >= n - 1 ? 0 : siguiente
      })
    }, 50)
    return () => window.clearInterval(id)
  }, [reproduciendo, velocidad, paso.paso_s, n])

  const tramasIdx = useMemo(() => {
    const t0 = Date.parse(paso.puntos[0].t)
    return paso.tramas
      .map((tr) => Math.round((Date.parse(tr.t) - t0) / 1000 / paso.paso_s))
      .filter((k) => k >= 0 && k < n)
  }, [paso, n])

  const actual = paso.puntos[Math.floor(indice)]
  const oye = actual.el > 0 && actual.en_ventana
  const recibidas = tramasIdx.filter((k) => k <= indice).length
  const velocidadKmS = 7.46 // circular a 775 km: sqrt(GM / r)

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
      <div className="card overflow-hidden p-0">
        <div className="h-[520px] w-full">
          <Suspense fallback={<Skeleton className="h-full w-full" />}>
            <Globo3D puntos={paso.puntos} orbita={paso.orbita} estacion={paso.estacion}
              indice={indice} tramasIdx={tramasIdx} />
          </Suspense>
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3 text-sm">
          <button
            onClick={() => setReproduciendo(!reproduciendo)}
            className="rounded-md border border-navy bg-navy px-3 py-1 font-medium text-on-accent"
          >
            {reproduciendo ? '⏸ Pausa' : '▶ Reproducir'}
          </button>
          <input
            type="range" min={0} max={n - 1} step={1} value={Math.floor(indice)}
            onChange={(e) => { setReproduciendo(false); setIndice(Number(e.target.value)) }}
            className="min-w-[12rem] flex-1 accent-cyan-400" aria-label="Momento del pase"
          />
          <label className="flex items-center gap-1.5 text-ink-soft">
            Velocidad
            <select value={velocidad} onChange={(e) => setVelocidad(Number(e.target.value))}
              className="rounded-md border border-line bg-panel px-2 py-1 text-ink">
              {VELOCIDADES.map((v) => <option key={v} value={v}>×{v}</option>)}
            </select>
          </label>
          <span className="tnum text-xs text-ink-soft">{fechaHoraUTC(actual.t)}</span>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-2 text-xs text-ink-soft">
          <span><span className="text-cyan-300">━</span> Recorrido durante la observación</span>
          <span><span className="text-slate-400">┅</span> Resto de la órbita (una vuelta)</span>
          <span><span className="text-violet-300">━</span> Sombra del recorrido sobre la Tierra</span>
          <span><span className="text-ok">●</span> Trama recibida</span>
          <span><span className="text-danger">▲</span> Estación</span>
        </div>
      </div>

      <div className="space-y-4">
        <Card>
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-navy-dark">¿Qué pasa ahora?</h3>
            <Badge tono={oye ? 'normal' : 'not_available'}>
              {oye ? 'La estación puede oírlo' : actual.el > 0 ? 'Visible, fuera de la ventana' : 'Bajo el horizonte'}
            </Badge>
          </div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm tnum">
            <dt className="text-ink-soft">Altura en el cielo</dt>
            <dd className="text-ink">{num(actual.el)}°</dd>
            <dt className="text-ink-soft">Dirección</dt>
            <dd className="text-ink">{num(actual.az, 0)}° ({rumbo(actual.az)})</dd>
            <dt className="text-ink-soft">Distancia</dt>
            <dd className="text-ink">{numero(actual.dist_km)} km</dd>
            <dt className="text-ink-soft">Sobre la Tierra</dt>
            <dd className="text-ink">lat. {num(actual.lat)}°, long. {num(actual.lon)}°</dd>
            <dt className="text-ink-soft">Tramas recibidas</dt>
            <dd className="text-ink">{recibidas} de {paso.tramas.length}</dd>
          </dl>
          <div className="mt-3 space-y-1.5">
            <Ayuda titulo="¿Qué es la «altura en el cielo»?">
              Es la elevación: el ángulo entre el horizonte y el satélite. 0° es el horizonte y 90°
              es justo encima de la cabeza. Cuanto más alto, más cerca pasa y mejor se oye.
            </Ayuda>
            <Ayuda titulo="¿Por qué se mueve tan rápido?">
              STRaND-1 da una vuelta a la Tierra en unos 100 minutos, a unos {num(velocidadKmS)} km cada
              segundo. Por eso una estación solo lo oye durante unos minutos en cada pase.
            </Ayuda>
            <Ayuda titulo="¿Qué es una trama?">
              Un mensaje digital que envía el satélite con datos sobre sí mismo. Los puntos verdes
              marcan dónde estaba el satélite cuando la estación recibió cada uno.
            </Ayuda>
          </div>
        </Card>
        <Card>
          <h3 className="mb-1 text-sm font-semibold text-navy-dark">Mapa del cielo de la estación</h3>
          <p className="mb-2 text-xs text-ink-soft">
            Así ve el cielo la antena: el centro es «justo encima», el borde es el horizonte. La
            línea es el camino del satélite y el punto amarillo, dónde está ahora.
          </p>
          <MapaCielo paso={paso} indice={indice} />
        </Card>
      </div>
    </div>
  )
}

export function Observations() {
  const lista = useApi(() => api.pases(), [])
  const [soloConTramas, setSoloConTramas] = useState(true)
  const [seleccion, setSeleccion] = useState<number | null>(null)
  const items: PaseResumen[] = useMemo(
    () => (lista.data?.items ?? []).filter((p) => !soloConTramas || p.frame_count > 0),
    [lista.data, soloConTramas],
  )
  const id = seleccion ?? items[0]?.observation_id ?? null
  const paso = useApi(() => (id ? api.paso(id) : Promise.resolve(null)), [id])
  const elegido = lista.data?.items.find((p) => p.observation_id === id)

  return (
    <div>
      <div className="mb-6">
        <div className="label-caps">STRaND-1 · Red SatNOGS</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-navy-dark sm:text-3xl">
          Observaciones: el satélite pasando sobre una estación
        </h1>
        <p className="mt-1.5 max-w-3xl text-sm text-ink-soft">
          SatNOGS es una red de antenas de aficionados repartidas por el mundo. Cuando STRaND-1
          pasaba por encima de una de ellas, la antena lo seguía y grababa sus mensajes. Elige una
          observación y mira cómo se movía el satélite durante esos minutos.
        </p>
      </div>

      {lista.loading && <Skeleton className="h-[600px]" />}
      {lista.error && <ErrorState mensaje={lista.error} onReintentar={lista.recargar} />}
      {lista.data && lista.data.total === 0 && (
        <EmptyState titulo="No hay observaciones con geometría"
          descripcion="Hace falta descargar las estaciones y los TLE de SatNOGS Network (tools/descargar_geometria_observaciones.py)." />
      )}
      {lista.data && lista.data.total > 0 && (
        <>
          <Card className="mb-4">
            <div className="flex flex-wrap items-end gap-4">
              <label className="flex min-w-[18rem] flex-1 flex-col gap-1 text-sm">
                <span className="text-ink-soft">Observación</span>
                <select
                  value={id ?? ''}
                  onChange={(e) => setSeleccion(Number(e.target.value))}
                  className="rounded-md border border-line bg-panel px-2 py-1.5 text-ink"
                >
                  {items.map((p) => (
                    <option key={p.observation_id} value={p.observation_id}>
                      {fechaHoraUTC(p.start)} · {p.station_name ?? 'estación'} · {p.frame_count} tramas
                      {p.max_elevation_deg !== null ? ` · máx. ${p.max_elevation_deg}°` : ''}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm text-ink-soft">
                <input type="checkbox" checked={soloConTramas}
                  onChange={(e) => { setSoloConTramas(e.target.checked); setSeleccion(null) }} />
                Solo las que recibieron mensajes
              </label>
              <div className="text-xs text-ink-soft">
                {numero(lista.data.total)} observaciones · {numero(lista.data.con_tramas)} con mensajes ·{' '}
                {numero(lista.data.estaciones)} estaciones
              </div>
            </div>
            {elegido && (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                <Badge tono={elegido.status === 'good' ? 'normal' : elegido.status === 'bad' ? 'critical' : 'not_available'}>
                  {elegido.status === 'good' ? 'Buena' : elegido.status === 'bad' ? 'Sin señal útil' : 'Sin calificar'}
                </Badge>
                <span>Observación nº {elegido.observation_id} de SatNOGS</span>
                <span>· de {fechaHoraUTC(elegido.start)} a {fechaHoraUTC(elegido.end)}</span>
              </div>
            )}
          </Card>

          {!lista.data.completo && (
            <div className="mb-4">
              <Nota tono="warning">
                Por ahora solo están disponibles {numero(lista.data.total)} observaciones: la descarga
                de las estaciones y órbitas desde SatNOGS va por partes, porque SatNOGS limita cuántas
                consultas se pueden hacer por hora.
              </Nota>
            </div>
          )}
          {paso.loading && <Skeleton className="h-[520px]" />}
          {paso.error && <ErrorState mensaje={paso.error} onReintentar={paso.recargar} />}
          {paso.data && <Paso paso={paso.data} />}

          {paso.data && (
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <Nota>
                <strong>¿De dónde salen estos datos?</strong> La estación, la hora de la observación y
                las tramas recibidas son <strong>reales</strong> (SatNOGS Network). La posición del
                satélite es una <strong>estimación</strong>: se calcula con el modelo SGP4 a partir del
                TLE que SatNOGS usó para ese pase (de {num(paso.data.tle.antiguedad_dias)} días
                de antigüedad). Elevación máxima calculada:{' '}
                {num(paso.data.elevacion_max_calculada)}°; según SatNOGS:{' '}
                {paso.data.elevacion_max_satnogs ?? '—'}°.
              </Nota>
              <Card>
                <CardHeader title="TLE usado en este pase"
                  description="Dos líneas de números que describen la órbita: es la «dirección» del satélite en un momento dado." />
                <pre className="overflow-x-auto rounded bg-blue-lighter p-2 font-mono text-[11px] text-ink">
                  {paso.data.tle.linea1}{'\n'}{paso.data.tle.linea2}
                </pre>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  )
}
