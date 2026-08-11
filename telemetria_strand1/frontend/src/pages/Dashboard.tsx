import { useState } from 'react'
import { Hero } from '../components/Hero'
import { GraficaFrames, Leyenda, SERIES, type PuntoSerie } from '../components/charts'
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
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
  { valor: 'all', etiqueta: 'Histórico' },
]

/* ── Tarjeta KPI ──────────────────────────────────────────────────────────── */

function KpiCard({
  etiqueta,
  valor,
  detalle,
  cargando,
}: {
  etiqueta: string
  valor: string
  detalle: string
  cargando?: boolean
}) {
  return (
    <Card className="min-w-0">
      <div className="label-caps">{etiqueta}</div>
      {cargando ? (
        <Skeleton className="mt-2 h-8 w-20" />
      ) : (
        <div className="mt-1.5 text-[1.75rem] font-bold leading-none tracking-tight tnum text-navy-dark">
          {valor}
        </div>
      )}
      <div className="mt-2 text-xs text-ink-soft">{detalle}</div>
    </Card>
  )
}

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
          title="Clasificación de frames"
          description="Estado de decodificación del conjunto completo."
        />
        <div className="space-y-3">
          {data.estados.map((e) => (
            <div key={e.estado} className="flex items-center gap-3">
              <Badge tono={e.estado} />
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
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
          title="Detección de anomalías"
          description="Sobre metadatos verificables: duplicados, longitud, entropía y huecos."
        />
        {anomalias.loading || !anomalias.data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {(['critical', 'warning', 'normal', 'unknown'] as const).map((k) => (
                <div key={k} className="rounded-lg border border-line px-3 py-2.5">
                  <div className="label-caps">{k}</div>
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
        {data.nota} Los frames se conservan en crudo y sus métricas de byte son reales; ningún valor
        se rellena por estimación, y los que se muestran llevan la ecuación de calibración publicada.
      </Nota>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {data.parametros.map((p) => (
          <Card key={p.key} className="min-w-0">
            <div className="label-caps">{p.label}</div>
            <div className="mt-1.5 text-xl font-semibold text-slate-400">
              {p.value ?? 'Not decoded'}
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

export function Dashboard({ status }: { status: Status | null }) {
  const [rango, setRango] = useState<Rango>('all')
  const [pestana, setPestana] = useState<Pestana>('frames')

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

      <Section
        title="Resultados de telemetría"
        description="Resumen de los frames recibidos, procesados y decodificados a partir de observaciones de STRAND-1."
        actions={
          <Tabs
            valor={pestana}
            onChange={setPestana}
            opciones={[
              { valor: 'frames', etiqueta: 'Frames' },
              { valor: 'telemetria', etiqueta: 'Telemetría' },
              { valor: 'analisis', etiqueta: 'Análisis' },
            ]}
          />
        }
      >
        {pestana === 'frames' && (
          <div className="space-y-5">
            <Card>
              <CardHeader
                title="Frames de telemetría procesados"
                description={
                  serie.data
                    ? `${numero(serie.data.total_en_rango)} frames · agrupados por ${serie.data.granularidad}`
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
                            ? 'border-navy bg-navy text-white'
                            : 'border-line bg-white text-ink-soft hover:border-navy hover:text-navy'
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
                  titulo="Sin frames en este rango"
                  descripcion="El conjunto es histórico; prueba con «Histórico» para ver la serie completa."
                />
              ) : (
                <>
                  <GraficaFrames datos={puntos} />
                  <div className="mt-4 border-t border-line pt-4">
                    <Leyenda
                      items={[
                        { color: SERIES.recibidos, label: 'Recibidos' },
                        { color: SERIES.procesados, label: 'Procesados', discontinua: true },
                        { color: SERIES.decodificados, label: 'Decodificados' },
                      ]}
                    />
                    <p className="mt-3 text-xs text-ink-soft">
                      «Procesados» son frames con bytes analizables y métricas calculadas; cuando
                      todos los recibidos traen bytes, su línea queda superpuesta a la de
                      «Recibidos». «Decodificados» son los que la definición de protocolo validada
                      logró interpretar, entera o parcialmente; el resto quedó sin clasificar o dio
                      error de decodificación.
                    </p>
                  </div>
                </>
              )}
            </Card>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <KpiCard
                etiqueta="Frames procesados"
                valor={numero(kpis.data?.frames_procesados)}
                detalle="Telemetría recibida"
                cargando={kpis.loading}
              />
              <KpiCard
                etiqueta="Frames decodificados"
                valor={numero(kpis.data?.frames_decodificados)}
                detalle={`${kpis.data?.porcentaje_decodificado ?? 0}% del total`}
                cargando={kpis.loading}
              />
              <KpiCard
                etiqueta="Observaciones"
                valor={numero(kpis.data?.observaciones)}
                detalle="Datos disponibles"
                cargando={kpis.loading}
              />
              <KpiCard
                etiqueta="Estaciones"
                valor={numero(kpis.data?.estaciones)}
                detalle="Ground stations"
                cargando={kpis.loading}
              />
              <KpiCard
                etiqueta="Último frame"
                valor={fechaUTC(kpis.data?.ultimo_frame)}
                detalle={horaUTC(kpis.data?.ultimo_frame)}
                cargando={kpis.loading}
              />
            </div>

            {kpis.data && (
              <p className="text-xs text-ink-soft">
                Fuente: {kpis.data.fuente}. Rango temporal {fechaUTC(kpis.data.primer_frame)} –{' '}
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
