import { useState } from 'react'
import { GraficaBarras, GraficaFrames, Leyenda, SERIES, type PuntoSerie } from '../components/charts'
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  LinkButton,
  Nota,
  Section,
  Skeleton,
} from '../components/ui'
import { api, useApi } from '../lib/api'
import { etiquetaBucket, fechaHoraUTC, numero } from '../lib/format'

type Rango = '24h' | '7d' | '30d' | 'all'

export function Analytics() {
  const [rango, setRango] = useState<Rango>('all')
  const serie = useApi(() => api.series(rango), [rango])
  const dist = useApi(() => api.distribucion(), [])
  const estaciones = useApi(() => api.estaciones(), [])
  const telemetria = useApi(() => api.telemetry(), [])

  const puntos: PuntoSerie[] =
    serie.data?.puntos.map((p) => ({
      etiqueta: etiquetaBucket(p.bucket, serie.data!.granularidad),
      recibidos: p.recibidos,
      procesados: p.procesados,
      decodificados: p.decodificados,
    })) ?? []

  return (
    <>
      <Section
        title="Análisis de Telemetría"
        description="Series temporales y distribuciones sobre el conjunto de frames recibidos."
        actions={
          <div className="flex flex-wrap gap-2">
            <select
              value={rango}
              onChange={(e) => setRango(e.target.value as Rango)}
              className="rounded-lg border border-line bg-white px-3 py-2 text-sm focus:border-blue focus:outline-none"
            >
              <option value="24h">24 horas</option>
              <option value="7d">7 días</option>
              <option value="30d">30 días</option>
              <option value="all">Histórico</option>
            </select>
            <LinkButton href={api.exportUrl('frames-processed', 'csv')} download>
              Exportar datos
            </LinkButton>
          </div>
        }
      >
        <div className="space-y-5">
          {telemetria.data && !telemetria.data.protocolo_validado && (
            <Nota tono="warning">
              <strong className="font-semibold">
                Las gráficas de parámetros físicos están vacías a propósito.
              </strong>{' '}
              Battery Voltage, Temperature, OBC Uptime y System Status requieren una definición de
              protocolo validada para poder representarse frente al tiempo. Mientras no exista, esta
              pantalla analiza lo que sí es verificable: volumen de frames, longitudes, entropía y
              reparto por estación.
            </Nota>
          )}

          <Card>
            <CardHeader
              title="Frames a lo largo del tiempo"
              description={
                serie.data
                  ? `${numero(serie.data.total_en_rango)} frames · agrupados por ${serie.data.granularidad}`
                  : undefined
              }
            />
            {serie.error ? (
              <ErrorState mensaje={serie.error} onReintentar={serie.recargar} />
            ) : serie.loading ? (
              <Skeleton className="h-[320px] w-full" />
            ) : puntos.length === 0 ? (
              <EmptyState titulo="Sin datos en el rango seleccionado" />
            ) : (
              <>
                <GraficaFrames datos={puntos} alto={320} />
                <div className="mt-4 border-t border-line pt-4">
                  <Leyenda
                    items={[
                      { color: SERIES.recibidos, label: 'Recibidos' },
                      { color: SERIES.procesados, label: 'Procesados', discontinua: true },
                      { color: SERIES.decodificados, label: 'Decodificados' },
                    ]}
                  />
                </div>
              </>
            )}
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Distribución de longitudes"
                description="Tamaño de los frames recibidos, en bytes."
              />
              {dist.loading || !dist.data ? (
                <Skeleton className="h-[260px] w-full" />
              ) : (
                <GraficaBarras
                  datos={dist.data.longitudes}
                  claveX="bytes"
                  claveY="frames"
                  etiquetaX="Bytes por frame"
                  etiquetaY="Frames"
                  sufijoTooltip=" bytes"
                />
              )}
            </Card>

            <Card>
              <CardHeader
                title="Frames por estación terrena"
                description="Estaciones de la red SatNOGS que aportaron datos."
              />
              {estaciones.loading || !estaciones.data ? (
                <Skeleton className="h-[260px] w-full" />
              ) : (
                <div className="max-h-[260px] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-white">
                      <tr className="border-b border-line">
                        <th className="label-caps py-2 text-left">Estación</th>
                        <th className="label-caps py-2 text-right">Frames</th>
                        <th className="label-caps py-2 text-right">Último</th>
                      </tr>
                    </thead>
                    <tbody>
                      {estaciones.data.map((e) => (
                        <tr key={e.observer} className="border-b border-line last:border-0">
                          <td className="py-2 font-mono text-xs text-ink">{e.observer}</td>
                          <td className="py-2 text-right text-sm font-semibold tnum">{e.frames}</td>
                          <td className="py-2 text-right text-xs tnum text-ink-soft">
                            {fechaHoraUTC(e.ultimo).slice(0, 10)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </div>
      </Section>
    </>
  )
}
