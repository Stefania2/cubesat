import { Suspense, lazy, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { Hero } from '../components/Hero'
import { GraficaFrames, Leyenda, SERIES, type PuntoSerie } from '../components/charts'
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  MetricCard,
  Nota,
  Section,
  Skeleton,
  Tabs,
} from '../components/ui'
import { api, useApi, type Status } from '../lib/api'
import { etiquetaBucket, fechaUTC, horaUTC, numero } from '../lib/format'
import { FramesTable } from './Telemetry'

type Rango = '24h' | '7d' | '30d' | 'all'
type Pestana = 'frames' | 'telemetria' | 'analisis'

const RANGOS: { valor: Rango; etiqueta: string }[] = [
  { valor: '24h', etiqueta: '24 horas' },
  { valor: '7d', etiqueta: '7 días' },
  { valor: '30d', etiqueta: '30 días' },
  { valor: 'all', etiqueta: 'Todo' },
]

/* ── Tarjeta KPI ──────────────────────────────────────────────────────────── */

function KpiCard({
  etiqueta,
  valor,
  detalle,
  cargando,
  tono,
}: {
  etiqueta: string
  valor: string
  detalle: string
  cargando?: boolean
  tono?: 'info' | 'ok' | 'muted'
}) {
  return <MetricCard etiqueta={etiqueta} valor={valor} detalle={detalle} cargando={cargando} tono={tono} />
}

const SEVERIDAD = { critical: 'Crítico', warning: 'Aviso', normal: 'Normal', unknown: 'Sin evaluar' } as const

/* ── Pestaña de análisis ──────────────────────────────────────────────────── */

function ResumenAnalisis() {
  const { data, error, loading, recargar } = useApi(() => api.distribucion(), [])
  const anomalias = useApi(() => api.anomalies(), [])

  if (error) return <ErrorState mensaje={error} onReintentar={recargar} />
  if (loading || !data) return <Skeleton className="h-64 w-full" />

  const total = data.estados.reduce((s, e) => s + e.frames, 0)

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="¿Cuántos mensajes se pudieron leer?"
          description="Cada mensaje (trama) recibido se intenta descifrar con el formato publicado por AMSAT-UK."
        />
        <div className="space-y-3">
          {data.estados.map((e) => (
            <div key={e.estado} className="flex items-center gap-3">
              <Badge tono={e.estado} />
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-line">
                <div
                  className="h-full rounded-full bg-navy"
                  style={{ width: `${(e.frames / total) * 100}%` }}
                />
              </div>
              <span className="w-20 text-right text-sm font-semibold tnum text-ink">
                {numero(e.frames)} ({((e.frames / total) * 100).toFixed(0)}%)
              </span>
            </div>
          ))}
        </div>
        <div className="mt-5 border-t border-line pt-4">
          <div className="label-caps mb-2">Tipos identificados</div>
          <div className="flex flex-wrap gap-2">
            {data.tipos.map((t) => (
              <span
                key={t.tipo}
                className="rounded-md border border-line bg-blue-lighter px-2.5 py-1 text-xs text-ink-soft"
              >
                <span className="font-mono font-medium text-navy">{t.tipo}</span>
                <span className="ml-1.5 tnum">{t.frames}</span>
              </span>
            ))}
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Revisión automática de los mensajes"
          description="Busca mensajes repetidos, demasiado cortos, sin variedad de datos o huecos largos sin recibir nada."
        />
        {anomalias.loading || !anomalias.data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {(['critical', 'warning', 'normal', 'unknown'] as const).map((k) => (
                <div key={k} className="rounded-lg border border-line px-3 py-2.5">
                  <div className="label-caps">{SEVERIDAD[k]}</div>
                  <div className="mt-1 text-xl font-bold tnum text-navy-dark">
                    {numero(anomalias.data!.resumen[k] ?? 0)}
                  </div>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              {anomalias.data.hallazgos.slice(0, 4).map((h, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 rounded-lg border border-line px-3 py-2.5"
                >
                  <Badge tono={h.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-ink">{h.label}</div>
                    <div className="mt-0.5 text-xs text-ink-soft">{h.message}</div>
                  </div>
                </div>
              ))}
              {anomalias.data.hallazgos.length === 0 && (
                <EmptyState titulo="Sin anomalías detectadas con las reglas activas" />
              )}
            </div>
          </>
        )}
      </Card>
    </div>
  )
}

/* ── Panel de telemetría resumido ─────────────────────────────────────────── */

function ResumenTelemetria() {
  const { data, error, loading, recargar } = useApi(() => api.telemetry(), [])

  if (error) return <ErrorState mensaje={error} onReintentar={recargar} />
  if (loading || !data) return <Skeleton className="h-48 w-full" />

  return (
    <div className="space-y-5">
      <Nota tono={data.balizas ? 'info' : 'warning'}>
        <strong className="font-semibold">
          {!data.protocolo_validado
            ? 'Sin protocolo validado.'
            : data.balizas === 0
              ? 'Protocolo validado, pero ninguna baliza recibida.'
              : `${numero(data.balizas)} balizas decodificadas según AMSAT-UK.`}
        </strong>{' '}
        {data.nota} Los mensajes se conservan tal como llegaron y sus métricas de byte son reales; ningún valor
        se rellena por estimación, y los que se muestran llevan la ecuación de calibración publicada.
      </Nota>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {data.parametros.map((p) => (
          <Card key={p.key} className="min-w-0">
            <div className="label-caps">{p.label}</div>
            <div className="mt-1.5 text-xl font-semibold text-ink-mute">
              {p.value ?? 'Sin dato'}
            </div>
            <div className="mt-2">
              <Badge tono={p.status} />
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

/* ── Página ───────────────────────────────────────────────────────────────── */

// El gemelo y la salud arrastran three.js y bastante código: se cargan en
// diferido para que la cabecera del inicio aparezca enseguida.
const GemeloDigital = lazy(() =>
  import('./GemeloDigital').then((m) => ({ default: m.GemeloDigital })),
)
const Salud = lazy(() => import('./Salud').then((m) => ({ default: m.Salud })))

function Bloque({ id, titulo, children, intro }: { id: string; titulo: string; intro: string; children: ReactNode }) {
  return (
    <section id={id} className="mb-12 scroll-mt-20">
      <h2 className="text-xl font-semibold tracking-tight text-navy-dark sm:text-2xl">{titulo}</h2>
      <p className="mb-5 mt-1.5 max-w-3xl text-sm text-ink-soft">{intro}</p>
      <Suspense fallback={<Skeleton className="h-96" />}>{children}</Suspense>
    </section>
  )
}

export function Dashboard({ status }: { status: Status | null }) {
  const [rango, setRango] = useState<Rango>('all')
  const [pestana, setPestana] = useState<Pestana>('frames')
  const { hash } = useLocation()

  // /gemelo y /salud redirigen aquí con #gemelo o #salud.
  useEffect(() => {
    if (!hash) return
    const t = window.setTimeout(() => document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth' }), 400)
    return () => window.clearTimeout(t)
  }, [hash])

  const kpis = useApi(() => api.kpis(), [])
  const serie = useApi(() => api.series(rango), [rango])

  const puntos: PuntoSerie[] =
    serie.data?.puntos.map((p) => ({
      etiqueta: etiquetaBucket(p.bucket, serie.data!.granularidad),
      recibidos: p.recibidos,
      procesados: p.procesados,
      decodificados: p.decodificados,
    })) ?? []

  return (
    <>
      <Hero status={status} />

      <nav className="mb-10 flex flex-wrap gap-2 text-sm" aria-label="Secciones del inicio">
        {[['#gemelo', 'El satélite en 3D'], ['#salud', 'Salud del satélite'], ['#mensajes', 'Mensajes recibidos']].map(([h, t]) => (
          <a key={h} href={h} className="rounded-lg border border-line bg-panel px-3 py-1.5 font-medium text-navy hover:border-navy">
            {t}
          </a>
        ))}
      </nav>

      <Bloque
        id="gemelo"
        titulo="El satélite en 3D: gemelo digital"
        intro="Un «gemelo digital» es una copia del satélite en el ordenador que se mueve y cambia con sus datos reales. Pulsa reproducir para recorrer los años de mensajes recibidos y ver cómo cambiaban sus mediciones. Las piezas se colorean según su estado."
      >
        <GemeloDigital />
      </Bloque>

      <Bloque
        id="salud"
        titulo="Salud y supervisión del satélite"
        intro="Aquí se revisa, parte por parte, si el satélite funcionaba bien: su energía, su temperatura, sus comunicaciones, su computador y su orientación. Cada dato dice de dónde sale y qué significa."
      >
        <Salud embebido />
      </Bloque>

      <Section
        title="Mensajes recibidos"
        description="Cada vez que una estación de SatNOGS oía a STRaND-1 guardaba sus mensajes, llamados «tramas». Aquí se cuentan los que llegaron y los que se pudieron descifrar."
        actions={
          <Tabs
            valor={pestana}
            onChange={setPestana}
            opciones={[
              { valor: 'frames', etiqueta: 'Tramas' },
              { valor: 'telemetria', etiqueta: 'Telemetría' },
              { valor: 'analisis', etiqueta: 'Análisis' },
            ]}
          />
        }
      >
        <div id="mensajes" className="scroll-mt-20" />
        {pestana === 'frames' && (
          <div className="space-y-5">
            <Card>
              <CardHeader
                title="Tramas recibidas a lo largo del tiempo"
                description={
                  serie.data
                    ? `${numero(serie.data.total_en_rango)} tramas · agrupadas por ${serie.data.granularidad}`
                    : undefined
                }
                actions={
                  <div className="flex flex-wrap gap-1.5">
                    {RANGOS.map((r) => (
                      <button
                        key={r.valor}
                        onClick={() => setRango(r.valor)}
                        className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
                          rango === r.valor
                            ? 'border-navy bg-navy text-on-accent'
                            : 'border-line bg-panel text-ink-soft hover:border-navy hover:text-navy'
                        }`}
                      >
                        {r.etiqueta}
                      </button>
                    ))}
                  </div>
                }
              />
              {serie.error ? (
                <ErrorState mensaje={serie.error} onReintentar={serie.recargar} />
              ) : serie.loading ? (
                <Skeleton className="h-[300px] w-full" />
              ) : puntos.length === 0 ? (
                <EmptyState
                  titulo="No hay tramas en este periodo"
                  descripcion="Los datos son antiguos: prueba con «Todo» para ver la serie completa."
                />
              ) : (
                <>
                  <GraficaFrames datos={puntos} />
                  <div className="mt-4 border-t border-line pt-4">
                    <Leyenda
                      items={[
                        { color: SERIES.recibidos, label: 'Recibidas' },
                        { color: SERIES.procesados, label: 'Procesadas', discontinua: true },
                        { color: SERIES.decodificados, label: 'Descifradas' },
                      ]}
                    />
                    <p className="mt-3 text-xs text-ink-soft">
                      «Procesadas» son las tramas cuyos bytes se pudieron analizar; si coinciden con
                      las recibidas, las dos líneas se superponen. «Descifradas» son las que se
                      pudieron leer, entera o parcialmente, con el formato publicado del satélite.
                    </p>
                  </div>
                </>
              )}
            </Card>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <KpiCard
                etiqueta="Tramas procesadas"
                valor={numero(kpis.data?.frames_procesados)}
                detalle="Mensajes recibidos"
                cargando={kpis.loading}
              />
              <KpiCard
                etiqueta="Tramas descifradas"
                valor={numero(kpis.data?.frames_decodificados)}
                detalle={`${kpis.data?.porcentaje_decodificado ?? 0} % del total`}
                cargando={kpis.loading}
                tono="ok"
              />
              <KpiCard
                etiqueta="Observaciones"
                valor={numero(kpis.data?.observaciones)}
                detalle="Pases escuchados"
                cargando={kpis.loading}
              />
              <KpiCard
                etiqueta="Estaciones"
                valor={numero(kpis.data?.estaciones)}
                detalle="Antenas en tierra"
                cargando={kpis.loading}
              />
              <KpiCard
                etiqueta="Última trama"
                valor={fechaUTC(kpis.data?.ultimo_frame)}
                detalle={horaUTC(kpis.data?.ultimo_frame)}
                cargando={kpis.loading}
                tono="muted"
              />
            </div>

            {kpis.data && (
              <p className="text-xs text-ink-soft">
                Fuente: {kpis.data.fuente}. Desde {fechaUTC(kpis.data.primer_frame)} hasta{' '}
                {fechaUTC(kpis.data.ultimo_frame)}.
              </p>
            )}

            <FramesTable limite={10} compacto />
          </div>
        )}

        {pestana === 'telemetria' && <ResumenTelemetria />}
        {pestana === 'analisis' && <ResumenAnalisis />}
      </Section>
    </>
  )
}
