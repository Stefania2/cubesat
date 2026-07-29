import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkline } from '../components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  LinkButton,
  Nota,
  Section,
  Skeleton,
} from '../components/ui'
import { api, useApi, type Frame } from '../lib/api'
import { fechaHoraUTC, magnitud, numero, truncarHex } from '../lib/format'

/* ── Explorador de frames ─────────────────────────────────────────────────── */

export function FramesTable({
  limite = 25,
  compacto = false,
}: {
  limite?: number
  compacto?: boolean
}) {
  const [pagina, setPagina] = useState(0)
  const [busqueda, setBusqueda] = useState('')
  const [estado, setEstado] = useState('')
  const [aplicada, setAplicada] = useState('')

  const { data, error, loading, recargar } = useApi(
    () => api.frames({ limit: limite, offset: pagina * limite, search: aplicada, status: estado }),
    [pagina, aplicada, estado, limite],
  )

  const paginas = data ? Math.ceil(data.total / limite) : 0

  return (
    <Card padding={false}>
      <div className="p-5 sm:p-6">
        <CardHeader
          title="Explorador de Frames"
          description={
            data ? `${numero(data.total)} frames en la base de datos` : 'Cargando frames…'
          }
          actions={
            !compacto ? (
              <div className="flex flex-wrap gap-2">
                <input
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      setAplicada(busqueda)
                      setPagina(0)
                    }
                  }}
                  placeholder="Buscar HEX…"
                  className="w-40 rounded-lg border border-line px-3 py-2 font-mono text-xs placeholder:font-sans placeholder:text-slate-400 focus:border-blue focus:outline-none"
                />
                <select
                  value={estado}
                  onChange={(e) => {
                    setEstado(e.target.value)
                    setPagina(0)
                  }}
                  className="rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink focus:border-blue focus:outline-none"
                >
                  <option value="">Todos los estados</option>
                  <option value="unclassified">Unclassified</option>
                  <option value="partially_decoded">Partially Decoded</option>
                  <option value="decoded">Decoded</option>
                  <option value="error">Error</option>
                </select>
                <Button
                  variante="secondary"
                  onClick={() => {
                    setAplicada(busqueda)
                    setPagina(0)
                  }}
                >
                  Filtrar
                </Button>
              </div>
            ) : (
              <Link
                to="/telemetry"
                className="text-sm font-medium text-blue hover:underline"
              >
                Ver todos →
              </Link>
            )
          }
        />
      </div>

      {error ? (
        <div className="px-5 pb-5 sm:px-6">
          <ErrorState mensaje={error} onReintentar={recargar} />
        </div>
      ) : loading ? (
        <div className="px-5 pb-5 sm:px-6">
          <Skeleton className="h-64 w-full" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="px-5 pb-5 sm:px-6">
          <EmptyState titulo="Ningún frame coincide con el filtro" />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse text-sm">
            <thead>
              <tr className="border-y border-line bg-blue-lighter">
                {['Frame ID', 'Observation ID', 'Timestamp', 'Station', 'Raw HEX', 'Bytes', 'Frame Type', 'Status'].map(
                  (h) => (
                    <th
                      key={h}
                      className="label-caps px-4 py-2.5 text-left whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data.items.map((f: Frame) => (
                <tr
                  key={f.id}
                  className="border-b border-line last:border-0 hover:bg-blue-lighter"
                >
                  <td className="px-4 py-3 font-mono text-xs tnum text-navy">#{f.id}</td>
                  <td className="px-4 py-3 font-mono text-xs tnum text-ink-soft">
                    {f.observation_id ?? '—'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs tnum text-ink-soft">
                    {fechaHoraUTC(f.timestamp)}
                  </td>
                  <td className="px-4 py-3 text-xs text-ink">
                    {f.station_id ? `${f.station_id} · ` : ''}
                    {f.observer ?? '—'}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-ink">
                    {truncarHex(f.raw_hex, 7)}
                  </td>
                  <td className="px-4 py-3 text-xs tnum text-ink-soft">{f.byte_count}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-soft">
                    {f.frame_type}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tono={f.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!compacto && paginas > 1 && (
        <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3 sm:px-6">
          <span className="text-xs text-ink-soft">
            Página {pagina + 1} de {paginas}
          </span>
          <div className="flex gap-2">
            <Button
              variante="ghost"
              disabled={pagina === 0}
              onClick={() => setPagina((p) => p - 1)}
            >
              Anterior
            </Button>
            <Button
              variante="ghost"
              disabled={pagina + 1 >= paginas}
              onClick={() => setPagina((p) => p + 1)}
            >
              Siguiente
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}

/* ── Página de telemetría ─────────────────────────────────────────────────── */

/** Campos tal como los nombra la especificación de la baliza.
 *
 *  El catálogo de arriba son ocho etiquetas elegidas de antemano; esto es lo que
 *  las balizas traen de verdad. Se marca cuáles no varían nunca: un campo
 *  constante no está midiendo nada, y ocultarlo lo haría parecer una medida. */
function CamposDeLaBaliza() {
  const { data, error, loading, recargar } = useApi(() => api.telemetryCampos(), [])

  if (error) return <ErrorState mensaje={error} onReintentar={recargar} />
  if (loading || !data) return <Skeleton className="h-40 w-full" />
  if (!data.total)
    return (
      <EmptyState
        titulo="Ninguna baliza decodificada"
        descripcion="No hay campos que mostrar mientras no entre una baliza válida."
      />
    )

  return (
    <div className="space-y-4">
      <Nota tono={data.constantes ? 'warning' : 'info'}>{data.nota}</Nota>
      <p className="text-xs leading-snug text-ink-soft">
        El <strong className="font-semibold">rango típico</strong> son los percentiles 5 y 95: acota
        dónde está el grueso de las lecturas sin descartar ninguna. Un{' '}
        <span className="text-warn">⚠</span> junto al máximo avisa de que ese extremo queda lejos del
        resto — pasa el cursor por encima para ver por qué en cada caso.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr className="border-b border-line text-left label-caps">
              <th className="py-2 pr-3">Campo</th>
              <th className="py-2 pr-3 text-right">Balizas</th>
              <th className="py-2 pr-3 text-right">Valores distintos</th>
              <th className="py-2 pr-3 text-right">Mín</th>
              <th className="py-2 pr-3 text-right">Máx</th>
              <th className="py-2 pr-3 text-right">Rango típico (p5–p95)</th>
              <th className="py-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {data.campos.map((c) => (
              <tr key={c.campo} className="border-b border-line/60">
                <td className="py-2 pr-3 font-mono text-xs">{c.campo}</td>
                <td className="py-2 pr-3 text-right tnum">{numero(c.apariciones)}</td>
                <td className="py-2 pr-3 text-right tnum">{c.valores_distintos}</td>
                {c.tipo === 'texto' ? (
                  <td className="py-2 pr-3 text-right text-xs text-ink-soft" colSpan={3}>
                    valor textual, sin escala numérica
                  </td>
                ) : (
                  <>
                    <td className="py-2 pr-3 text-right tnum">{magnitud(c.minimo)}</td>
                    <td className="py-2 pr-3 text-right tnum">
                      {magnitud(c.maximo)}
                      {c.aviso && (
                        <span className="ml-1 cursor-help text-warn" title={c.aviso}>
                          ⚠
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-right tnum text-ink-soft">
                      {c.p05 === null ? '—' : `${magnitud(c.p05)} … ${magnitud(c.p95)}`}
                    </td>
                  </>
                )}
                <td className="py-2">
                  <Badge tono={c.constante ? 'warning' : 'normal'}>
                    {c.constante ? 'Constante' : 'Varía'}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function Telemetry() {
  const { data, error, loading, recargar } = useApi(() => api.telemetry(), [])

  return (
    <>
      <Section
        title="Parámetros de telemetría"
        description="La entropía se mide sobre los bytes recibidos; el resto solo se rellena si una definición de protocolo validada dice cómo leerlo."
        actions={
          <div className="flex gap-2">
            <LinkButton href={api.exportUrl('telemetry-decoded', 'csv')} download>
              Export CSV
            </LinkButton>
            <LinkButton href={api.exportUrl('telemetry-decoded', 'json')} download>
              Export JSON
            </LinkButton>
          </div>
        }
      >
        {error ? (
          <ErrorState mensaje={error} onReintentar={recargar} />
        ) : loading || !data ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <div className="space-y-5">
            {!data.protocolo_validado ? (
              <Nota tono="warning">
                <strong className="font-semibold">
                  El formato de telemetría de STRAND-1 no está identificado.
                </strong>{' '}
                {data.nota} Los frames se muestran en crudo y todas sus métricas de byte son reales,
                pero ningún parámetro físico se estima: mostrarlos supondría inventar el significado
                de los bytes. Registra una definición de protocolo validada para que esta sección se
                rellene.
              </Nota>
            ) : data.balizas === 0 ? (
              <Nota tono="warning">
                <strong className="font-semibold">
                  Hay decodificador oficial, pero ningún frame recibido es una baliza.
                </strong>{' '}
                {data.nota} Las celdas se quedan vacías por eso, no por falta de protocolo: el
                decodificador está cargado y listo, y en cuanto entre una baliza válida estos
                parámetros se rellenan solos.
              </Nota>
            ) : (
              <Nota>
                <strong className="font-semibold">
                  {numero(data.balizas)} balizas decodificadas con la especificación de AMSAT-UK.
                </strong>{' '}
                {data.nota} Los valores llevan aplicada la ecuación de calibración que publica la
                hoja de AMSAT-UK, salvo los magnetómetros, para los que la especificación no da
                ninguna: esos se muestran como cuenta cruda, no en µT. Un parámetro sin valor
                significa que su canal no aparece en las balizas recibidas. La entropía va aparte,
                marcada como <strong className="font-semibold">Medido</strong>: se calcula sobre los
                bytes de cada frame sin suponer ningún formato, de modo que tiene valor incluso
                cuando no hay protocolo con el que decodificar nada.
              </Nota>
            )}

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {data.parametros.map((p) => (
                <Card key={p.key} className="min-w-0">
                  <div className="label-caps">{p.label}</div>
                  <div className="mt-2 flex items-baseline gap-1.5">
                    <span
                      className={`text-2xl font-bold leading-none tnum ${
                        p.status === 'decoded' || p.status === 'measured'
                          ? 'text-navy-dark'
                          : 'text-slate-400'
                      }`}
                    >
                      {typeof p.value === 'number' ? magnitud(p.value) : (p.value ?? 'Not decoded')}
                    </span>
                    {p.value !== null && p.unit && (
                      <span className="text-sm font-medium text-ink-soft">{p.unit}</span>
                    )}
                  </div>

                  {p.history.length > 1 ? (
                    <div className="mt-3">
                      <Sparkline datos={p.history} />
                    </div>
                  ) : (
                    <div className="mt-3 h-10 rounded-md border border-dashed border-line bg-blue-lighter" />
                  )}

                  <div className="mt-3 flex items-center justify-between gap-2">
                    <Badge tono={p.status} />
                    {p.unit && <span className="text-xs text-ink-soft">{p.unit}</span>}
                  </div>
                  {p.reason && (
                    <p className="mt-2 text-[11px] leading-snug text-ink-soft">{p.reason}</p>
                  )}
                </Card>
              ))}
            </div>
          </div>
        )}
      </Section>

      <Section
        title="Campos de la baliza decodificados"
        description="Lo que las balizas contienen realmente, con el nombre que les da la especificación de AMSAT-UK."
      >
        <CamposDeLaBaliza />
      </Section>

      <Section
        title="Explorador de Frames"
        description="Los datos crudos tal como los entrega SatNOGS, con las métricas calculadas sobre sus bytes."
        actions={
          <div className="flex gap-2">
            <LinkButton href={api.exportUrl('frames-raw', 'csv')} download>
              Download Frames
            </LinkButton>
            <LinkButton href={api.exportUrl('frames-processed', 'csv')} download>
              Export procesados
            </LinkButton>
          </div>
        }
      >
        <FramesTable limite={25} />
      </Section>
    </>
  )
}
