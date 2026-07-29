import { useState } from 'react'
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
  StatusDot,
} from '../components/ui'
import { api, useApi, type AnomalyRule } from '../lib/api'
import { fechaHoraUTC, numero } from '../lib/format'

/* ── Editor de una regla ──────────────────────────────────────────────────── */

function FilaRegla({ regla, onCambio }: { regla: AnomalyRule; onCambio: () => void }) {
  const [guardando, setGuardando] = useState(false)
  const [params, setParams] = useState(regla.params ?? {})

  async function actualizar(cambios: Partial<AnomalyRule>) {
    setGuardando(true)
    try {
      await api.updateRule(regla.key, cambios)
      onCambio()
    } finally {
      setGuardando(false)
    }
  }

  const claves = Object.keys(params)

  return (
    <div className="border-b border-line py-4 last:border-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StatusDot tono={regla.enabled ? regla.severity : 'muted'} />
            <span className="text-sm font-semibold text-navy-dark">{regla.label}</span>
            <Badge tono={regla.severity} />
          </div>
          {regla.description && (
            <p className="mt-1 text-xs text-ink-soft">{regla.description}</p>
          )}
        </div>
        <label className="flex shrink-0 cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={regla.enabled}
            disabled={guardando}
            onChange={(e) => actualizar({ enabled: e.target.checked })}
            className="size-4 accent-navy"
          />
          <span className="text-ink-soft">Activa</span>
        </label>
      </div>

      {claves.length > 0 && (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          {claves.map((k) => (
            <div key={k}>
              <label className="label-caps block">{k.replace(/_/g, ' ')}</label>
              <input
                type="number"
                step="any"
                value={String(params[k])}
                onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })}
                className="mt-1 w-32 rounded-lg border border-line px-2.5 py-1.5 text-sm tnum focus:border-blue focus:outline-none"
              />
            </div>
          ))}
          <Button
            variante="ghost"
            disabled={guardando}
            onClick={() => actualizar({ params })}
            className="px-3 py-1.5"
          >
            {guardando ? 'Guardando…' : 'Aplicar umbral'}
          </Button>
        </div>
      )}
    </div>
  )
}

/* ── Página ───────────────────────────────────────────────────────────────── */

export function Advanced() {
  const anomalias = useApi(() => api.anomalies(), [])
  const estado = useApi(() => api.status(), [])
  const [ingiriendo, setIngiriendo] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)

  async function ingerir() {
    setIngiriendo(true)
    setAviso(null)
    try {
      const r = await api.ingestSatnogs()
      setAviso(r.mensaje)
      anomalias.recargar()
      estado.recargar()
    } catch (e) {
      setAviso(`No se pudo descargar de SatNOGS: ${(e as Error).message}`)
    } finally {
      setIngiriendo(false)
    }
  }

  const resumen = anomalias.data?.resumen

  return (
    <>
      <Section
        title="Detección de anomalías"
        description="Sobre hechos verificables de los frames: duplicados, corrupción, longitud, entropía y huecos temporales."
      >
        <div className="space-y-5">
          <Nota>
            <strong className="font-semibold">Sin límites físicos arbitrarios.</strong> Las reglas no
            evalúan magnitudes como voltaje o temperatura: el decodificador de la baliza está
            cargado, pero ningún frame recibido es una baliza, así que esas magnitudes no existen en
            los datos. Operan sobre propiedades de los bytes y de las marcas de tiempo, que sí son
            ciertas. Todos los umbrales son editables aquí abajo.
          </Nota>

          {anomalias.error ? (
            <ErrorState mensaje={anomalias.error} onReintentar={anomalias.recargar} />
          ) : anomalias.loading || !anomalias.data ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                {(
                  [
                    ['normal', 'Normal'],
                    ['warning', 'Warning'],
                    ['critical', 'Critical'],
                    ['unknown', 'Unknown'],
                  ] as const
                ).map(([k, etiqueta]) => (
                  <Card key={k}>
                    <div className="flex items-center gap-2">
                      <StatusDot tono={k === 'unknown' ? 'muted' : k} />
                      <span className="label-caps">{etiqueta}</span>
                    </div>
                    <div className="mt-1.5 text-2xl font-bold tnum text-navy-dark">
                      {numero(resumen?.[k] ?? 0)}
                    </div>
                    <div className="mt-1 text-xs text-ink-soft">
                      {k === 'unknown' ? 'frames sin clasificar' : 'frames'}
                    </div>
                  </Card>
                ))}
              </div>

              <Card padding={false}>
                <div className="p-5 sm:p-6">
                  <CardHeader
                    title="Hallazgos"
                    description={`${anomalias.data.hallazgos.length} incidencias con las reglas activas`}
                  />
                </div>
                {anomalias.data.hallazgos.length === 0 ? (
                  <div className="px-5 pb-5 sm:px-6">
                    <EmptyState titulo="Ninguna anomalía con la configuración actual" />
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[640px] text-sm">
                      <thead>
                        <tr className="border-y border-line bg-blue-lighter">
                          <th className="label-caps px-4 py-2.5 text-left">Severidad</th>
                          <th className="label-caps px-4 py-2.5 text-left">Regla</th>
                          <th className="label-caps px-4 py-2.5 text-left">Detalle</th>
                          <th className="label-caps px-4 py-2.5 text-right">Frames</th>
                        </tr>
                      </thead>
                      <tbody>
                        {anomalias.data.hallazgos.map((h, i) => (
                          <tr key={i} className="border-b border-line last:border-0">
                            <td className="px-4 py-3">
                              <Badge tono={h.severity} />
                            </td>
                            <td className="px-4 py-3 text-sm font-medium text-ink">
                              {h.label}
                            </td>
                            <td className="px-4 py-3 text-xs text-ink-soft">{h.message}</td>
                            <td className="px-4 py-3 text-right text-sm tnum text-ink-soft">
                              {h.frame_ids.length}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <Card>
                <CardHeader
                  title="Umbrales configurables"
                  description="Ajusta o desactiva cada regla; los cambios se aplican al recargar el informe."
                />
                <div>
                  {anomalias.data.reglas.map((r) => (
                    <FilaRegla key={r.key} regla={r} onCambio={anomalias.recargar} />
                  ))}
                </div>
              </Card>
            </>
          )}
        </div>
      </Section>

      <Section
        title="Exportación de datos"
        description="Cada conjunto conserva su capa: crudo, procesado y decodificado no se mezclan."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          {[
            {
              titulo: 'Observaciones',
              desc: 'Metadatos de pases registrados por las estaciones.',
              set: 'observations',
            },
            {
              titulo: 'Frames RAW',
              desc: 'Hexadecimal tal como lo entregó SatNOGS, sin métricas derivadas.',
              set: 'frames-raw',
            },
            {
              titulo: 'Frames procesados',
              desc: 'Longitud, entropía, bytes distintos y clasificación.',
              set: 'frames-processed',
            },
            {
              titulo: 'Telemetría decodificada',
              desc: 'Vacío mientras no exista una definición de protocolo validada.',
              set: 'telemetry-decoded',
            },
          ].map((c) => (
            <Card key={c.set}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-semibold text-navy-dark">{c.titulo}</h3>
                  <p className="mt-1 text-xs text-ink-soft">{c.desc}</p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <LinkButton href={api.exportUrl(c.set, 'csv')} download>
                    CSV
                  </LinkButton>
                  <LinkButton href={api.exportUrl(c.set, 'json')} download>
                    JSON
                  </LinkButton>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </Section>

      <Section
        title="Ingesta de datos"
        description="Estado del sistema y descarga de frames nuevos desde SatNOGS DB."
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader title="Estado del sistema" />
            {estado.data && (
              <dl className="space-y-2.5 text-sm">
                {[
                  ['Satélite', `${estado.data.satellite} · NORAD ${estado.data.norad_id}`],
                  ['Base de datos', estado.data.database],
                  ['Frames almacenados', numero(estado.data.frames)],
                  ['Observaciones', numero(estado.data.observaciones)],
                  ['Protocolos validados', numero(estado.data.protocolos_validados)],
                  ['Token SatNOGS', estado.data.satnogs_token_configurado ? 'configurado' : 'no configurado'],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-3">
                    <dt className="text-ink-soft">{k}</dt>
                    <dd className="font-medium tnum text-ink">{v}</dd>
                  </div>
                ))}
              </dl>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Descargar de SatNOGS"
              description="Añade frames nuevos sin duplicar los ya almacenados."
            />
            <Button onClick={ingerir} disabled={ingiriendo}>
              {ingiriendo ? 'Descargando…' : 'Descargar frames nuevos'}
            </Button>
            {aviso && (
              <div className="mt-4">
                <Nota>{aviso}</Nota>
              </div>
            )}
            <p className="mt-4 text-xs text-ink-soft">
              La ingesta es idempotente: la clave (hex, timestamp, observador) evita insertar dos
              veces el mismo frame, de modo que se puede repetir sin ensuciar el conjunto.
            </p>
          </Card>
        </div>
      </Section>
    </>
  )
}
