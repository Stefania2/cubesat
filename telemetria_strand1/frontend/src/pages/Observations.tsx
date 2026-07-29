import { useState } from 'react'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LinkButton,
  Nota,
  Section,
  Skeleton,
  StatusDot,
} from '../components/ui'
import { api, useApi, type Observation } from '../lib/api'
import { fechaHoraUTC, frecuenciaMHz, numero } from '../lib/format'

function Campo({ etiqueta, valor }: { etiqueta: string; valor: string | number | null | undefined }) {
  const vacio = valor === null || valor === undefined || valor === ''
  return (
    <div>
      <div className="label-caps">{etiqueta}</div>
      <div className={`mt-0.5 text-sm ${vacio ? 'text-slate-400' : 'font-medium text-ink'}`}>
        {vacio ? 'Not available' : valor}
      </div>
    </div>
  )
}

function TarjetaObservacion({ obs }: { obs: Observation }) {
  const estado = (obs.status ?? '').toLowerCase()
  const tono =
    estado === 'good' ? 'normal' : estado === 'bad' ? 'critical' : estado ? 'warning' : 'muted'

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4">
        <div>
          <div className="label-caps">Observation ID</div>
          <div className="mt-0.5 font-mono text-lg font-bold tnum text-navy-dark">
            {obs.observation_id}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {obs.status ? (
            <span className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-xs font-medium">
              <StatusDot tono={tono} />
              {obs.status}
            </span>
          ) : (
            <Badge tono="unclassified">Status desconocido</Badge>
          )}
          <span className="rounded-md border border-line bg-blue-lighter px-2.5 py-1 text-xs font-medium text-navy">
            {numero(obs.frame_count)} frames
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-3">
        <Campo etiqueta="Satellite" valor={obs.satellite_name} />
        <Campo etiqueta="NORAD" valor={obs.norad_id} />
        <Campo
          etiqueta="Station"
          valor={
            obs.station_id
              ? `${obs.station_id}${obs.station_name ? ` - ${obs.station_name}` : ''}`
              : null
          }
        />
        <Campo etiqueta="Station Owner" valor={obs.station_owner} />
        <Campo etiqueta="Observer" valor={obs.observer} />
        <Campo etiqueta="Frequency" valor={obs.frequency_hz ? frecuenciaMHz(obs.frequency_hz) : null} />
        <Campo etiqueta="Mode" valor={obs.mode} />
        <Campo etiqueta="Start" valor={obs.start ? fechaHoraUTC(obs.start) : null} />
        <Campo etiqueta="End" valor={obs.end ? fechaHoraUTC(obs.end) : null} />
        <Campo
          etiqueta="Max Elevation"
          valor={obs.max_elevation_deg !== null ? `${obs.max_elevation_deg.toFixed(1)}°` : null}
        />
      </div>
    </Card>
  )
}

export function Observations() {
  const { data, error, loading, recargar } = useApi(() => api.observations(100), [])
  const [sincronizando, setSincronizando] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)

  async function sincronizar() {
    setSincronizando(true)
    setAviso(null)
    try {
      const r = await api.syncObservations()
      setAviso(r.mensaje)
      recargar()
    } catch (e) {
      setAviso(`No se pudo sincronizar: ${(e as Error).message}`)
    } finally {
      setSincronizando(false)
    }
  }

  return (
    <Section
      title="Observaciones SatNOGS"
      description="Pases del satélite registrados por las estaciones terrenas de la red."
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variante="secondary" onClick={sincronizar} disabled={sincronizando}>
            {sincronizando ? 'Sincronizando…' : 'Sincronizar con SatNOGS'}
          </Button>
          <LinkButton href={api.exportUrl('observations', 'csv')} download>
            Export CSV
          </LinkButton>
          <LinkButton href={api.exportUrl('observations', 'json')} download>
            Export JSON
          </LinkButton>
        </div>
      }
    >
      <div className="space-y-5">
        {aviso && <Nota>{aviso}</Nota>}

        {data?.partial_metadata && (
          <Nota tono="warning">
            <strong className="font-semibold">Metadatos incompletos.</strong> Estas observaciones se
            derivan del <code className="font-mono text-xs">observation_id</code> que traen los
            frames de SatNOGS DB, cuyo endpoint de telemetría no devuelve estación, ventana temporal
            ni elevación máxima. Los campos que faltan aparecen como «Not available» en lugar de
            rellenarse. Pulsa «Sincronizar con SatNOGS» para completarlos desde la API de Network.
          </Nota>
        )}

        {error ? (
          <ErrorState mensaje={error} onReintentar={recargar} />
        ) : loading ? (
          <div className="grid gap-5 lg:grid-cols-2">
            <Skeleton className="h-56 w-full" />
            <Skeleton className="h-56 w-full" />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            titulo="Sin observaciones registradas"
            descripcion="Los frames cargados no traen identificador de observación. Sincroniza con SatNOGS Network para traerlas."
          />
        ) : (
          <>
            <p className="text-sm text-ink-soft">
              {numero(data.total)} observaciones · mostrando {data.items.length}
            </p>
            <div className="grid gap-5 lg:grid-cols-2">
              {data.items.map((o) => (
                <TarjetaObservacion key={o.observation_id} obs={o} />
              ))}
            </div>
          </>
        )}
      </div>
    </Section>
  )
}
