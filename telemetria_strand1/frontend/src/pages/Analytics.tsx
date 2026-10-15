import { useState } from 'react'
import {
  GraficaBarras,
  GraficaFrames,
  GraficaRanking,
  Leyenda,
  SERIES,
  type PuntoSerie,
} from '../components/charts'
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

/** Longitud máxima del eje de la distribución. Por encima solo hay una cola
 *  de frames raros que aplastaría el eje; se cuentan aparte, no se ocultan. */
const MAX_BYTES_EJE = 64
const ESTACIONES_EN_GRAFICA = 10

function Conmutador<T extends string>({
  opciones,
  valor,
  onChange,
}: {
  opciones: { valor: T; etiqueta: string }[]
  valor: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex gap-1.5" role="group">
      {opciones.map((o) => (
        <button
          key={o.valor}
          aria-pressed={o.valor === valor}
          onClick={() => onChange(o.valor)}
          className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
            o.valor === valor
              ? 'border-navy bg-navy text-on-accent'
              : 'border-line bg-panel text-ink-soft hover:border-navy hover:text-navy'
          }`}
        >
          {o.etiqueta}
        </button>
      ))}
    </div>
  )
}

function resumirLongitudes(longitudes: { bytes: number; frames: number }[]) {
  const total = longitudes.reduce((t, l) => t + l.frames, 0)
  const porBytes = new Map(longitudes.map((l) => [l.bytes, l.frames]))
  const eje = Array.from({ length: MAX_BYTES_EJE }, (_, i) => ({
    bytes: i + 1,
    frames: porBytes.get(i + 1) ?? 0,
  }))
  const cola = longitudes.filter((l) => l.bytes > MAX_BYTES_EJE)
  const dominantes = [...longitudes].sort((a, b) => b.frames - a.frames).slice(0, 3)
  return {
    eje,
    fuera: cola.reduce((t, l) => t + l.frames, 0),
    maximo: Math.max(...longitudes.map((l) => l.bytes)),
    dominantes: dominantes.map((d) => d.bytes).sort((a, b) => a - b),
    porcentajeDominantes: total ? (100 * dominantes.reduce((t, d) => t + d.frames, 0)) / total : 0,
  }
}

export function Analytics() {
  const [rango, setRango] = useState<Rango>('all')
  const serie = useApi(() => api.series(rango), [rango])
  const dist = useApi(() => api.distribucion(), [])
  const estaciones = useApi(() => api.estaciones(), [])
  const telemetria = useApi(() => api.telemetry(), [])
  const [escala, setEscala] = useState<'lineal' | 'log'>('lineal')
  const [vistaEstaciones, setVistaEstaciones] = useState<'grafica' | 'tabla'>('grafica')
  const longitudes = dist.data ? resumirLongitudes(dist.data.longitudes) : null

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
              className="rounded-lg border border-line bg-panel px-3 py-2 text-sm focus:border-blue focus:outline-none"
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
                <GraficaFrames datos={puntos} alto={340} zoom />
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
                  <Leyenda
                    items={[
                      { color: SERIES.recibidos, label: 'Recibidos' },
                      { color: SERIES.procesados, label: 'Procesados', discontinua: true },
                      { color: SERIES.decodificados, label: 'Decodificados' },
                    ]}
                  />
                  {puntos.length > 12 && (
                    <span className="text-xs text-ink-soft">
                      Arrastra los extremos de la barra inferior para acotar el intervalo.
                    </span>
                  )}
                </div>
              </>
            )}
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Distribución de longitudes"
                description="Tamaño de los frames recibidos, en bytes."
                actions={
                  <Conmutador
                    opciones={[
                      { valor: 'lineal', etiqueta: 'Lineal' },
                      { valor: 'log', etiqueta: 'Logarítmica' },
                    ]}
                    valor={escala}
                    onChange={setEscala}
                  />
                }
              />
              {dist.error ? (
                <ErrorState mensaje={dist.error} onReintentar={dist.recargar} />
              ) : !longitudes ? (
                <Skeleton className="h-[260px] w-full" />
              ) : (
                <>
                  <GraficaBarras
                    datos={longitudes.eje}
                    claveX="bytes"
                    claveY="frames"
                    etiquetaX="Bytes por frame"
                    etiquetaY={escala === 'log' ? 'Frames (log)' : 'Frames'}
                    sufijoTooltip=" bytes"
                    escalaLog={escala === 'log'}
                  />
                  <p className="mt-3 text-xs leading-snug text-ink-soft">
                    El {longitudes.porcentajeDominantes.toLocaleString('es-ES', { maximumFractionDigits: 1 })} % de
                    los frames mide {longitudes.dominantes.join(', ').replace(/, (\d+)$/, ' o $1')} bytes; la escala
                    logarítmica deja ver el resto.
                    {longitudes.fuera > 0 &&
                      ` ${numero(longitudes.fuera)} frames de más de ${MAX_BYTES_EJE} bytes (hasta ${longitudes.maximo}) quedan fuera del eje.`}
                  </p>
                </>
              )}
            </Card>

            <Card>
              <CardHeader
                title="Frames por estación terrena"
                description="Estaciones de la red SatNOGS que aportaron datos."
                actions={
                  <Conmutador
                    opciones={[
                      { valor: 'grafica', etiqueta: 'Gráfica' },
                      { valor: 'tabla', etiqueta: 'Tabla' },
                    ]}
                    valor={vistaEstaciones}
                    onChange={setVistaEstaciones}
                  />
                }
              />
              {estaciones.error ? (
                <ErrorState mensaje={estaciones.error} onReintentar={estaciones.recargar} />
              ) : estaciones.loading || !estaciones.data ? (
                <Skeleton className="h-[260px] w-full" />
              ) : vistaEstaciones === 'grafica' ? (
                <>
                  <GraficaRanking
                    datos={estaciones.data.slice(0, ESTACIONES_EN_GRAFICA)}
                    claveNombre="observer"
                    claveValor="frames"
                    detalle={(e) => `Último frame: ${fechaHoraUTC(e.ultimo).slice(0, 10)}`}
                  />
                  {estaciones.data.length > ESTACIONES_EN_GRAFICA && (
                    <p className="mt-3 text-xs text-ink-soft">
                      Las {ESTACIONES_EN_GRAFICA} estaciones con más frames de {estaciones.data.length}; la
                      tabla las muestra todas.
                    </p>
                  )}
                </>
              ) : (
                <div className="tabla-scroll max-h-[300px]">
                  <table className="tabla w-full text-sm">
                    <thead>
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
