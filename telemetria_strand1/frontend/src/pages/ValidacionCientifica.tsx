/**
 * STRaND-1 SCIENTIFIC VALIDATION.
 *
 * Solo presenta: todo cálculo vive en `validacion_cientifica/` (backend). El
 * verde se reserva para VALIDATED, que el backend solo emite si la prueba se
 * ejecutó; lo no verificado y lo no disponible van en gris, sin punto.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  Badge,
  Button,
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
import { api, useApi } from '../lib/api'
import type { EstadoValidacion, ResultadoValidacion } from '../lib/api'

type Pestana =
  | 'resumen'
  | 'procedencia'
  | 'orbital'
  | 'telemetria'
  | 'temporal'
  | 'diagnosticos'
  | 'reproducibilidad'
  | 'informes'

const PESTANAS: { valor: Pestana; etiqueta: string }[] = [
  { valor: 'resumen', etiqueta: 'A · Resumen' },
  { valor: 'procedencia', etiqueta: 'B · Procedencia' },
  { valor: 'orbital', etiqueta: 'C · Órbita' },
  { valor: 'telemetria', etiqueta: 'D · Telemetría' },
  { valor: 'temporal', etiqueta: 'E · Sincronización' },
  { valor: 'diagnosticos', etiqueta: 'F · Diagnósticos' },
  { valor: 'reproducibilidad', etiqueta: 'G · Reproducibilidad' },
  { valor: 'informes', etiqueta: 'H · Informes' },
]

const TONO: Record<EstadoValidacion, string> = {
  VALIDATED: 'normal',
  WARNING: 'warning',
  FAILED: 'critical',
  NOT_VERIFIED: 'not_available',
  NOT_AVAILABLE: 'not_available',
}

const INSTANTE_INICIAL = '2021-03-01T12:00:00'

/** Desfase legible: horas hasta dos días, días a partir de ahí. */
function desfase(s: number | null | undefined, signo = ''): string {
  if (s === null || s === undefined) return '—'
  const h = s / 3600
  return Math.abs(h) < 48 ? `${signo}${h.toFixed(2)} h` : `${signo}${(h / 24).toFixed(1)} d`
}

function Estado({ estado }: { estado: string | null | undefined }) {
  if (!estado) return <Badge tono="not_available" conPunto={false}>—</Badge>
  const tono = TONO[estado as EstadoValidacion] ?? 'info'
  return (
    <Badge tono={tono} conPunto={estado !== 'NOT_VERIFIED' && estado !== 'NOT_AVAILABLE'}>
      {estado.replace('_', ' ')}
    </Badge>
  )
}

function Json({ valor }: { valor: unknown }) {
  if (valor === null || valor === undefined) return <span className="text-ink-mute">null</span>
  if (typeof valor !== 'object') return <span className="font-mono text-xs">{String(valor)}</span>
  return (
    <details>
      <summary className="cursor-pointer text-xs text-navy">ver</summary>
      <pre className="mt-1 max-h-64 max-w-xl overflow-auto rounded bg-blue-lighter p-2 font-mono text-[11px] text-ink">
        {JSON.stringify(valor, null, 2)}
      </pre>
    </details>
  )
}

function Cargando({ cargando, error, reintentar, children }: {
  cargando: boolean
  error: string | null
  reintentar: () => void
  children: ReactNode
}) {
  if (error) return <ErrorState mensaje={error} onReintentar={reintentar} />
  if (cargando)
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-40 w-full" />
        <p className="text-xs text-ink-soft">
          La primera consulta ejecuta las pruebas en el servidor (unos segundos).
        </p>
      </div>
    )
  return <>{children}</>
}

function TablaResultados({ resultados }: { resultados: ResultadoValidacion[] }) {
  if (!resultados.length) return <EmptyState titulo="Sin resultados" />
  return (
    <div className="tabla-scroll">
      <table className="tabla w-full text-sm">
        <thead className="text-left text-xs text-ink-soft">
          <tr>
            <th className="py-2 pr-3">Prueba</th>
            <th className="py-2 pr-3">Estado</th>
            <th className="py-2 pr-3">Esperado</th>
            <th className="py-2 pr-3">Obtenido</th>
            <th className="py-2 pr-3">Tolerancia</th>
            <th className="py-2">Detalle</th>
          </tr>
        </thead>
        <tbody>
          {resultados.map((r) => (
            <tr key={r.id} className="align-top">
              <td className="py-2 pr-3">
                <div className="font-mono text-[11px] text-ink-soft">{r.id}</div>
                <div className="text-ink">{r.nombre}</div>
              </td>
              <td className="py-2 pr-3"><Estado estado={r.estado} /></td>
              <td className="py-2 pr-3"><Json valor={r.esperado} /></td>
              <td className="py-2 pr-3"><Json valor={r.obtenido} /></td>
              <td className="py-2 pr-3 text-xs text-ink-soft"><Json valor={r.tolerancia} /></td>
              <td className="py-2 text-xs text-ink-soft">
                {r.detalle}
                {r.referencia && <div className="mt-1 italic">Ref.: {r.referencia}</div>}
                <div className="mt-1 text-ink-mute">
                  {r.ejecutado_utc ? `Ejecutado ${r.ejecutado_utc}` : 'No ejecutado'}
                  {r.nota_origen ? ` · ${r.nota_origen}` : ''}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── A · Resumen ──────────────────────────────────────────────────────────── */

const NOMBRE_SECCION: Record<string, string> = {
  procedencia: 'Procedencia de datos',
  orbital: 'Validación orbital',
  telemetria: 'Validación de telemetría',
  temporal: 'Sincronización temporal',
  diagnosticos: 'Diagnósticos estadísticos',
  reproducibilidad: 'Reproducibilidad',
}

function Resumen() {
  const { data, error, loading, recargar } = useApi(() => api.valResumen(), [])
  return (
    <Cargando cargando={loading} error={error} reintentar={recargar}>
      {data && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <MetricCard etiqueta="Validated" valor={data.recuento.VALIDATED} tono="ok"
              detalle="ejecutadas y dentro de tolerancia" />
            <MetricCard etiqueta="Warning" valor={data.recuento.WARNING} tono="warning"
              detalle="utilizables con salvedad documentada" />
            <MetricCard etiqueta="Failed" valor={data.recuento.FAILED} tono="critical"
              detalle="ejecutadas, fuera de tolerancia" />
            <MetricCard etiqueta="Not verified" valor={data.recuento.NOT_VERIFIED} tono="muted"
              detalle="sin ejecutar o sin referencia" />
            <MetricCard etiqueta="Not available" valor={data.recuento.NOT_AVAILABLE} tono="muted"
              detalle="el dato no existe en las fuentes" />
          </div>
          <Nota>
            Comprobaciones ejecutadas en el servidor el {data.generado_utc} sobre el archivo sellado
            (no consultan la base ni SatNOGS). La suite automatizada y la comparación base↔archivo no
            caben en una función de 60 s: se ejecutan en local y se muestran con su fecha y commit.
          </Nota>
          <Card>
            <CardHeader title="Suite automatizada (pytest)"
              description="Resultado registrado por validacion_cientifica/ejecutar_pruebas.py." />
            {data.pruebas_automatizadas?.ejecutado_utc ? (
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <span>Ejecutada {data.pruebas_automatizadas.ejecutado_utc}</span>
                <span className="font-mono text-xs text-ink-soft">
                  commit {String(data.pruebas_automatizadas.commit ?? '—').slice(0, 10)}
                </span>
                {data.recuento_pruebas_automatizadas &&
                  (['VALIDATED', 'FAILED', 'NOT_VERIFIED'] as EstadoValidacion[]).map((e) => (
                    <span key={e} className="flex items-center gap-1.5">
                      <Estado estado={e} /> {data.recuento_pruebas_automatizadas?.[e] ?? 0}
                    </span>
                  ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm"><Estado estado="NOT_VERIFIED" />
                {data.pruebas_automatizadas?.detalle}</div>
            )}
            <PruebasRegistradas />
          </Card>
          {Object.entries(data.secciones).map(([sec, lista]) => (
            <Card key={sec}>
              <CardHeader title={NOMBRE_SECCION[sec] ?? sec} />
              <TablaResultados resultados={lista} />
            </Card>
          ))}
        </div>
      )}
    </Cargando>
  )
}

function PruebasRegistradas() {
  const [ver, setVer] = useState(false)
  const { data } = useApi(() => (ver ? api.valPruebas() : Promise.resolve(null)), [ver])
  return (
    <div className="mt-4">
      <Button variante="ghost" onClick={() => setVer(!ver)}>{ver ? 'Ocultar casos' : 'Ver cada caso'}</Button>
      {ver && data?.casos && (
        <div className="tabla-scroll mt-3">
          <table className="tabla w-full text-xs">
            <thead className="text-left text-ink-soft">
              <tr><th className="py-1 pr-2">Caso</th><th className="pr-2">Categoría</th><th className="pr-2">Estado</th>
                <th className="pr-2">Esperado</th><th className="pr-2">Obtenido</th><th>Tolerancia</th></tr>
            </thead>
            <tbody>
              {data.casos.map((c: Record<string, any>) => (
                <tr key={c.id} className="align-top">
                  <td className="py-1 pr-2 font-mono">{String(c.id).split('::').pop()}</td>
                  <td className="pr-2">{c.categoria ?? '—'}</td>
                  <td className="pr-2"><Estado estado={c.estado} /></td>
                  <td className="max-w-xs break-words pr-2 font-mono">{c.esperado ?? '—'}</td>
                  <td className="max-w-xs break-words pr-2 font-mono">{c.obtenido ?? '—'}</td>
                  <td>{c.tolerancia ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ── B · Procedencia ──────────────────────────────────────────────────────── */

function Procedencia() {
  const { data, error, loading, recargar } = useApi(() => api.valProcedencia(), [])
  const [id, setId] = useState('17348')
  const [ficha, setFicha] = useState<Record<string, any> | null>(null)
  const [errFicha, setErrFicha] = useState<string | null>(null)
  const consultar = () => {
    setErrFicha(null)
    api.valTrama(Number(id)).then(setFicha).catch((e) => { setFicha(null); setErrFicha(String(e.message)) })
  }
  return (
    <Cargando cargando={loading} error={error} reintentar={recargar}>
      {data && (
        <div className="space-y-6">
          <Card>
            <CardHeader title="Archivo sellado"
              description={`Huella del conjunto (SHA-256): ${data.huella_conjunto ?? 'sin sello'} · sellado ${data.sello?.sellado_utc ?? '—'}`} />
            <div className="overflow-x-auto">
              <table className="tabla w-full text-sm">
                <thead className="text-left text-xs text-ink-soft">
                  <tr><th className="py-2 pr-3">Fichero</th><th className="pr-3">Capa</th><th className="pr-3">Filas</th><th>SHA-256 del contenido</th></tr>
                </thead>
                <tbody>
                  {Object.entries<Record<string, any>>(data.sello?.ficheros ?? {}).map(([n, f]) => (
                    <tr key={n}>
                      <td className="py-2 pr-3 font-mono text-xs">{n}.jsonl.gz</td>
                      <td className="pr-3"><Badge tono={f.capa === 'ORIGINAL' ? 'measured' : 'info'} conPunto={false}>{f.capa}</Badge></td>
                      <td className="pr-3 tnum">{Number(f.filas).toLocaleString('es-CO')}</td>
                      <td className="break-all font-mono text-[11px] text-ink-soft">{f.sha256_contenido}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card>
            <CardHeader title="Integridad y correspondencia con la base" />
            <TablaResultados resultados={[...data.integridad, ...data.comparacion_base]} />
          </Card>
          <Card>
            <CardHeader title="Procedencia de una trama"
              description="Fuente, observación, fechas, valor original y procesado, conversión y versión del procesador." />
            <div className="flex flex-wrap items-center gap-2">
              <input value={id} onChange={(e) => setId(e.target.value.replace(/\D/g, ''))}
                className="w-32 rounded-lg border border-line bg-panel px-3 py-2 font-mono text-sm" aria-label="Id de trama" />
              <Button onClick={consultar} disabled={!id}>Consultar</Button>
            </div>
            {errFicha && <p className="mt-3 text-sm text-danger">{errFicha}</p>}
            {ficha && (
              <div className="mt-4 space-y-3 text-sm">
                <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                  {[
                    ['Fuente original', ficha.fuente_original],
                    ['Observación', ficha.observacion_id ?? 'NO DISPONIBLE'],
                    ['Recepción (UTC)', ficha.fecha_recepcion_utc],
                    ['Medición (UTC)', ficha.fecha_medicion_utc ?? 'NO DISPONIBLE'],
                    ['Ingesta en la base', ficha.fecha_ingesta_utc],
                    ['Trama original (hex)', ficha.valor_original_hex],
                    ['SHA-256 de la trama', ficha.sha256_trama],
                    ['Versión del decodificador', ficha.version_procesador?.sha256],
                  ].map(([k, v]) => (
                    <div key={String(k)} className="min-w-0">
                      <dt className="label-caps">{k}</dt>
                      <dd className="break-all font-mono text-xs text-ink">{String(v)}</dd>
                    </div>
                  ))}
                </dl>
                <p className="text-xs text-ink-soft">{ficha.fecha_medicion_nota} {ficha.fecha_ingesta_nota}</p>
                <table className="tabla w-full text-xs">
                  <thead className="text-left text-ink-soft">
                    <tr><th className="py-1 pr-2">Campo</th><th className="pr-2">Original</th><th className="pr-2">Procesado</th>
                      <th className="pr-2">Unidad</th><th className="pr-2">Conversión</th><th>Re-decodificado igual</th></tr>
                  </thead>
                  <tbody>
                    {ficha.valores.map((v: Record<string, any>) => (
                      <tr key={v.campo}>
                        <td className="py-1 pr-2 font-mono">{v.campo}</td>
                        <td className="pr-2 font-mono">{v.valor_original ? `${v.valor_original.valor} (${v.valor_original.tipo})` : '—'}</td>
                        <td className="pr-2 font-mono">{String(v.valor_procesado)}</td>
                        <td className="pr-2">{v.unidad ?? '—'}</td>
                        <td className="pr-2">{v.metodo_conversion}</td>
                        <td>{v.revalidado_con_codigo_vigente === null ? '—' : v.revalidado_con_codigo_vigente ? 'sí' : 'NO'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card>
            <CardHeader title="Versiones de procesamiento" description="Cada pieza se identifica por la huella SHA-256 de su código fuente." />
            <Json valor={data.versiones} />
            <h4 className="mt-4 label-caps">Catálogo de TLE</h4>
            <p className="text-sm text-ink-soft">
              {data.catalogo_tle.tle} TLE únicos, épocas {data.catalogo_tle.epoca_min} a {data.catalogo_tle.epoca_max} ·{' '}
              <span className="font-mono text-xs">{data.catalogo_tle.fuente}</span>
            </p>
            <h4 className="mt-4 label-caps">Limitaciones</h4>
            <ul className="mt-1 list-disc pl-5 text-sm text-ink-soft">
              {data.limitaciones.map((l: string) => <li key={l}>{l}</li>)}
            </ul>
          </Card>
        </div>
      )}
    </Cargando>
  )
}

/* ── C · Órbita ───────────────────────────────────────────────────────────── */

function Orbital({ t }: { t: string }) {
  const { data, error, loading, recargar } = useApi(() => api.valOrbital(t), [t])
  const pos = data?.posicion
  const prop = pos?.propagacion
  return (
    <Cargando cargando={loading} error={error} reintentar={recargar}>
      {data && (
        <div className="space-y-6">
          <Card>
            <CardHeader title={`Posición en ${t}`} description={`Marco ${data.marco}`} />
            {pos && (
              <div className="space-y-2 text-sm">
                <div className="flex flex-wrap items-center gap-2"><Estado estado={pos.estado} />
                  <span className="text-ink-soft">{pos.evaluacion_antiguedad?.detalle}</span></div>
                {pos.tle && (
                  <pre className="overflow-x-auto rounded bg-blue-lighter p-2 font-mono text-[11px]">
                    {pos.tle.linea1}{'\n'}{pos.tle.linea2}{'\n'}época {pos.tle.epoca_utc} · antigüedad {pos.antiguedad_dias} días
                  </pre>
                )}
                {prop?.posicion_km ? (
                  <dl className="grid gap-2 sm:grid-cols-3">
                    <div><dt className="label-caps">r TEME (km)</dt><dd className="font-mono text-xs">{['x', 'y', 'z'].map((k) => prop.posicion_km[k].toFixed(3)).join(', ')}</dd></div>
                    <div><dt className="label-caps">v TEME (km/s)</dt><dd className="font-mono text-xs">{['vx', 'vy', 'vz'].map((k) => prop.velocidad_km_s[k].toFixed(6)).join(', ')}</dd></div>
                    <div><dt className="label-caps">Lat / lon / altura</dt><dd className="font-mono text-xs">{prop.terrestre.latitud_deg}°, {prop.terrestre.longitud_deg}°, {prop.terrestre.altura_km} km</dd></div>
                  </dl>
                ) : (
                  <p className="text-sm text-ink-soft">Sin posición: no se propaga un TLE fuera del intervalo con error caracterizado.</p>
                )}
                {Object.entries<Record<string, any>>(pos.evaluacion_antiguedad?.por_proposito ?? {}).map(([k, c]) => (
                  <div key={k} className="flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                    <Estado estado={c.estado} /> {c.descripcion} · admisible ≤ {c.antiguedad_admisible_dias} d (tolerancia {c.tolerancia_km} km)
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card>
            <CardHeader title="Criterio de antigüedad del TLE (estimación empírica)"
              description={data.divergencia?.metodo ?? 'Falta el estudio de divergencia.'} />
            {data.divergencia && (
              <table className="tabla w-full text-sm tnum">
                <thead className="text-left text-xs text-ink-soft">
                  <tr><th className="py-2 pr-3">Antigüedad (días)</th><th className="pr-3">Pares</th><th className="pr-3">Mediana (km)</th><th className="pr-3">p95 (km)</th><th>Máx. (km)</th></tr>
                </thead>
                <tbody>
                  {data.divergencia.tramos.map((tr: Record<string, number>) => (
                    <tr key={tr.desde_dias}>
                      <td className="py-1.5 pr-3">{tr.desde_dias}–{tr.hasta_dias}</td><td className="pr-3">{tr.pares}</td>
                      <td className="pr-3">{tr.mediana_km}</td><td className="pr-3">{tr.p95_km}</td><td>{tr.max_km}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          <Card>
            <CardHeader title="Pruebas orbitales" description="A integridad · B repetibilidad · C referencias independientes · D coordenadas · E antigüedad." />
            <TablaResultados resultados={data.pruebas} />
          </Card>
        </div>
      )}
    </Cargando>
  )
}

/* ── D · Telemetría ───────────────────────────────────────────────────────── */

function Telemetria() {
  const { data, error, loading, recargar } = useApi(() => api.valTelemetria(), [])
  return (
    <Cargando cargando={loading} error={error} reintentar={recargar}>
      {data && (
        <div className="space-y-6">
          <Card>
            <CardHeader title="Controles sobre el archivo completo" />
            <TablaResultados resultados={data.controles} />
          </Card>
          <Card>
            <CardHeader title="Ficha de cada variable"
              description="Integridad del dato y validación física por separado. Sin rango de operación documentado, ninguna magnitud está validada físicamente." />
            <div className="tabla-scroll">
              <table className="tabla w-full text-xs">
                <thead className="text-left text-ink-soft">
                  <tr><th className="py-2 pr-2">Variable</th><th className="pr-2">Unidad</th><th className="pr-2">Lecturas</th>
                    <th className="pr-2">Conversión</th><th className="pr-2">Resolución</th><th className="pr-2">Integridad</th>
                    <th className="pr-2">Física</th><th>Observaciones</th></tr>
                </thead>
                <tbody>
                  {data.variables.map((v: Record<string, any>) => (
                    <tr key={v.campo} className="align-top">
                      <td className="py-1.5 pr-2"><div className="font-mono">{v.campo}</div>
                        {v.nombre && <div className="text-ink-soft">{v.nombre}</div>}</td>
                      <td className="pr-2">{v.unidad ?? '—'}</td>
                      <td className="pr-2 tnum">{v.n_lecturas}</td>
                      <td className="pr-2">{v.conversion ?? '—'}</td>
                      <td className="pr-2">{v.resolucion ?? '—'}</td>
                      <td className="pr-2"><Estado estado={v.estado_integridad} /></td>
                      <td className="pr-2"><Estado estado={v.estado_fisico} /></td>
                      <td className="text-ink-soft">{[v.nota_ordenada, v.nota, v.disponibilidad?.estado !== 'emitida' ? v.nota_fisica : null].filter(Boolean).join(' ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </Cargando>
  )
}

/* ── E · Sincronización ───────────────────────────────────────────────────── */

function Temporal({ t }: { t: string }) {
  const { data, error, loading, recargar } = useApi(() => api.valTemporal(`${t}Z`), [t])
  return (
    <Cargando cargando={loading} error={error} reintentar={recargar}>
      {data && (
        <div className="space-y-6">
          <Card>
            <CardHeader title={`Coherencia temporal en ${data.instante_utc}`}
              description={`Evento del gemelo: ${data.gemelo.momento_evento_utc ?? 'ninguno'} · modelo 3D: ${data.modelo3d.estado_cubesat} · órbita: ${data.orbita.estado}`} />
            <TablaResultados resultados={[...data.pruebas, ...data.globales]} />
          </Card>
          <Card>
            <CardHeader title="Asociación de cada variable al instante" description="Ninguna variable se interpola; los estados discretos tampoco." />
            <div className="tabla-scroll">
              <table className="tabla w-full text-xs">
                <thead className="text-left text-ink-soft">
                  <tr><th className="py-2 pr-2">Variable</th><th className="pr-2">Valor</th><th className="pr-2">Método</th>
                    <th className="pr-2">Medida (UTC)</th><th className="pr-2">Desfase</th><th className="pr-2">Siguiente</th><th>Estado</th></tr>
                </thead>
                <tbody>
                  {data.lecturas.map((l: Record<string, any>) => (
                    <tr key={l.campo}>
                      <td className="py-1 pr-2 font-mono">{l.campo}</td>
                      <td className="pr-2 font-mono">{l.valor === null ? 'NO DISPONIBLE' : `${l.valor} ${l.unidad ?? ''}`}</td>
                      <td className="pr-2">{l.asociacion}</td>
                      <td className="pr-2 font-mono">{l.medida_utc ?? '—'}</td>
                      <td className="pr-2 tnum">{desfase(l.desfase_s)}</td>
                      <td className="pr-2 tnum">{l.siguiente_medicion ? desfase(l.siguiente_medicion.desfase_s, '+') : '—'}</td>
                      <td><Estado estado={l.estado} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="mt-3 space-y-1 text-xs text-ink-soft">
              {Object.entries<string>(data.metodos).map(([k, v]) => <li key={k}><span className="font-mono">{k}</span>: {v}</li>)}
            </ul>
          </Card>
        </div>
      )}
    </Cargando>
  )
}

/* ── F · Diagnósticos ─────────────────────────────────────────────────────── */

function Diagnosticos() {
  const { data, error, loading, recargar } = useApi(() => api.valDiagnosticos(), [])
  return (
    <Cargando cargando={loading} error={error} reintentar={recargar}>
      {data && (
        <div className="space-y-6">
          <Nota tono="warning">{data.falla_confirmada.detalle}</Nota>
          {data.fichas.map((f: Record<string, any>) => (
            <Card key={f.id}>
              <CardHeader title={f.nombre} description={`${f.codigo} · usado por: ${f.usado_por}`} />
              <dl className="space-y-2 text-sm">
                <div><dt className="label-caps">Fórmula</dt><dd className="font-mono text-xs">{f.formula}</dd></div>
                <div><dt className="label-caps">Ventana</dt><dd className="text-xs"><Json valor={f.ventana} /></dd></div>
                <div><dt className="label-caps">Ventanas incompletas</dt><dd className="text-xs text-ink-soft">{f.ventanas_incompletas}</dd></div>
                <div><dt className="label-caps">Umbrales</dt>
                  <dd><ul className="text-xs text-ink-soft">{f.umbrales.map((u: Record<string, any>) => (
                    <li key={u.etiqueta}><span className="font-mono text-ink">{u.valor} → {u.etiqueta}</span>: {u.justificacion}</li>))}</ul></dd></div>
                <div><dt className="label-caps">Limitaciones</dt>
                  <dd><ul className="list-disc pl-5 text-xs text-ink-soft">{f.limitaciones.map((l: string) => <li key={l}>{l}</li>)}</ul></dd></div>
              </dl>
            </Card>
          ))}
          <Card>
            <CardHeader title="Resultados por variable (archivo completo)" description="Escala: sin desviación → comportamiento inusual → anomalía estadística → posible anomalía operacional. Nunca «falla confirmada»." />
            <div className="overflow-x-auto">
              <table className="tabla w-full text-xs">
                <thead className="text-left text-ink-soft">
                  <tr><th className="py-2 pr-2">Variable</th><th className="pr-2">Muestras</th><th className="pr-2">Ventanas parciales</th>
                    <th className="pr-2">Sin referencia</th><th className="pr-2">Interpretación</th><th>Eventos</th></tr>
                </thead>
                <tbody>
                  {data.resultados.map((r: Record<string, any>) => (
                    <tr key={r.campo} className="align-top">
                      <td className="py-1.5 pr-2 font-mono">{r.campo}</td>
                      <td className="pr-2 tnum">{r.n_lecturas}</td>
                      <td className="pr-2 tnum">{r.ventanas_parciales}</td>
                      <td className="pr-2 tnum">{r.sin_mediana_por_ventana_corta + r.sin_referencia_por_amplitud}</td>
                      <td className="pr-2">{Object.entries<number>(r.por_interpretacion).map(([k, n]) => <div key={k}>{k}: {n}</div>)}</td>
                      <td className="tnum">{r.eventos}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card>
            <CardHeader title="Pruebas de los diagnósticos" />
            <TablaResultados resultados={data.pruebas} />
          </Card>
        </div>
      )}
    </Cargando>
  )
}

/* ── G · Reproducibilidad ─────────────────────────────────────────────────── */

function Reproducibilidad({ t }: { t: string }) {
  const { data, error, loading, recargar } = useApi(() => api.valReconstruccion(`${t}Z`), [t])
  const [verif, setVerif] = useState<{ resultados: ResultadoValidacion[] } | null>(null)
  const [errVerif, setErrVerif] = useState<string | null>(null)
  const subir = (archivo: File | undefined) => {
    if (!archivo) return
    setErrVerif(null)
    archivo.text().then((txt) => api.valVerificarManifest(txt)).then(setVerif)
      .catch((e) => { setVerif(null); setErrVerif(String(e.message)) })
  }
  const man = data?.manifest
  return (
    <Cargando cargando={loading} error={error} reintentar={recargar}>
      {man && (
        <div className="space-y-6">
          <Card>
            <CardHeader title={`Reconstrucción ${man.reconstruccion.id}`}
              description={`Instante ${man.reconstruccion.instante_utc} · resultados SHA-256 ${man.resultados.sha256}`}
              actions={<a className="inline-flex items-center rounded-lg border border-navy px-4 py-2 text-sm font-medium text-navy hover:bg-blue-light"
                href={api.valUrl('manifest', `${t}Z`)}>Descargar manifest.json</a>} />
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div><dt className="label-caps">Huella de las entradas</dt><dd className="break-all font-mono text-xs">{man.datos.huella_conjunto_sha256}</dd></div>
              <div><dt className="label-caps">TLE</dt><dd className="font-mono text-xs">{man.orbita.tle ? `${man.orbita.epoca_tle_utc} · ${man.orbita.antiguedad_dias} d · ${man.orbita.estado}` : 'null'}</dd></div>
              <div><dt className="label-caps">Tramas usadas</dt><dd className="text-xs">{man.fuente_telemetria.tramas.length}</dd></div>
              <div><dt className="label-caps">Commit</dt><dd className="font-mono text-xs">{man.aplicacion.commit ?? 'null'}{man.aplicacion.cambios_sin_confirmar ? ' + cambios sin confirmar' : ''}</dd></div>
            </dl>
            <h4 className="mt-4 label-caps">Manifest completo</h4>
            <Json valor={man} />
          </Card>
          <Card>
            <CardHeader title="Verificar un manifest" description="Repite la reconstrucción con las entradas del manifest y compara la huella de los resultados." />
            <input type="file" accept="application/json,.json" onChange={(e) => subir(e.target.files?.[0])}
              className="text-sm text-ink-soft file:mr-3 file:rounded-lg file:border file:border-line file:bg-panel file:px-3 file:py-1.5 file:text-navy" />
            {errVerif && <p className="mt-3 text-sm text-danger">{errVerif}</p>}
            {verif && <div className="mt-4"><TablaResultados resultados={verif.resultados} /></div>}
          </Card>
          <Card>
            <CardHeader title="Sincronización de esta reconstrucción" />
            <TablaResultados resultados={data.sincronizacion} />
          </Card>
        </div>
      )}
    </Cargando>
  )
}

/* ── H · Informes ─────────────────────────────────────────────────────────── */

function Informes({ t }: { t: string }) {
  const enlace = 'inline-flex items-center rounded-lg border px-4 py-2 text-sm font-medium'
  return (
    <Card>
      <CardHeader title={`Informe técnico de la reconstrucción en ${t}Z`}
        description="14 apartados: identificación, fuentes, procedencia, TLE, metodología SGP4, resultados orbitales, coordenadas, telemetría, sincronización, diagnósticos, pruebas, limitaciones y conclusiones. Cada valor indica si es medido, calculado, derivado o estimado." />
      <div className="flex flex-wrap gap-3">
        <a className={`${enlace} border-navy bg-navy text-on-accent`} href={api.valUrl('informe', `${t}Z`, '&formato=pdf')}>Descargar PDF</a>
        <a className={`${enlace} border-navy text-navy hover:bg-blue-light`} href={api.valUrl('informe', `${t}Z`, '&formato=json')}>Descargar JSON</a>
      </div>
      <p className="mt-3 text-xs text-ink-soft">La generación ejecuta la reconstrucción y todas las pruebas de servidor: puede tardar unos segundos.</p>
    </Card>
  )
}

/* ── Página ───────────────────────────────────────────────────────────────── */

/** Estado inicial desde la URL (?seccion=orbital&t=2025-06-01T00:00:00): enlaces compartibles. */
function deUrl(): { pestana: Pestana; t: string } {
  const q = new URLSearchParams(window.location.search)
  const sec = q.get('seccion') as Pestana | null
  const t = q.get('t')
  return {
    pestana: sec && PESTANAS.some((p) => p.valor === sec) ? sec : 'resumen',
    t: t && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(t) ? t : INSTANTE_INICIAL,
  }
}

export function ValidacionCientifica() {
  const inicial = useState(deUrl)[0]
  const [pestana, setPestanaEstado] = useState<Pestana>(inicial.pestana)
  const [borrador, setBorrador] = useState(inicial.t)
  const [t, setTEstado] = useState(inicial.t)
  const reflejar = (p: Pestana, instante: string) =>
    window.history.replaceState(null, '', `?seccion=${p}&t=${instante}`)
  const setPestana = (p: Pestana) => { setPestanaEstado(p); reflejar(p, t) }
  const setT = (instante: string) => { setTEstado(instante); reflejar(pestana, instante) }
  const usaInstante = ['orbital', 'temporal', 'reproducibilidad', 'informes'].includes(pestana)
  return (
    <Section
      title="Validación científica"
      description="Scientific Validation · Procedencia, validación orbital y de telemetría, sincronización temporal, diagnósticos y reconstrucciones reproducibles de STRaND-1. Un resultado que no puede demostrarse no se presenta como validado."
    >
      <div className="mb-5 space-y-4">
        <Tabs opciones={PESTANAS} valor={pestana} onChange={setPestana} />
        {usaInstante && (
          <div className="flex flex-wrap items-center gap-2">
            <label className="label-caps" htmlFor="instante">Instante (UTC)</label>
            <input id="instante" type="datetime-local" step="1" value={borrador}
              onChange={(e) => setBorrador(e.target.value.length === 16 ? `${e.target.value}:00` : e.target.value)}
              className="rounded-lg border border-line bg-panel px-3 py-2 font-mono text-sm text-ink" />
            <span className="text-xs text-ink-soft">UTC</span>
            <Button onClick={() => setT(borrador)} disabled={!borrador || borrador === t}>Reconstruir</Button>
          </div>
        )}
      </div>
      {pestana === 'resumen' && <Resumen />}
      {pestana === 'procedencia' && <Procedencia />}
      {pestana === 'orbital' && <Orbital t={`${t}Z`} />}
      {pestana === 'telemetria' && <Telemetria />}
      {pestana === 'temporal' && <Temporal t={t} />}
      {pestana === 'diagnosticos' && <Diagnosticos />}
      {pestana === 'reproducibilidad' && <Reproducibilidad t={t} />}
      {pestana === 'informes' && <Informes t={t} />}
    </Section>
  )
}
