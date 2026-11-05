/**
 * Supervisión de salud de STRaND-1 (HMTA · Health Monitoring & Telemetry Analysis).
 *
 * Dos niveles de lectura en cada pantalla: el básico explica qué se mide y qué
 * significa; el técnico añade referencia, estadísticas, validación y la serie.
 *
 * Reglas que esta página no se salta:
 *  - cada dato lleva su procedencia (REAL, SIMULADO, ESTIMADO, DOCUMENTADO,
 *    NO DISPONIBLE) en una insignia visible, no solo en un tooltip;
 *  - la falta de datos se dice («no disponible»), nunca se rellena;
 *  - un escenario simulado pinta una franja permanente que lo identifica.
 *
 * Es solo supervisión: no hay ningún control que envíe órdenes al satélite.
 */

import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ComposedChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Badge, Card, CardHeader, EmptyState, ErrorState, MetricCard, Nota, Skeleton, Tabs } from '../components/ui'
import { api, useApi } from '../lib/api'
import type {
  AlertaSalud,
  EstadoSalud,
  IndicadorSalud,
  InformeSalud,
  NoDisponibleSalud,
  Procedencia,
  SubsistemaSalud,
} from '../lib/api'
import { fechaHoraUTC, fechaUTC, magnitud } from '../lib/format'

/* ── Vocabulario común ────────────────────────────────────────────────────── */

const TONO_ESTADO: Record<EstadoSalud, string> = {
  NORMAL: 'normal',
  ADVERTENCIA: 'warning',
  CRITICO: 'critical',
  DESCONOCIDO: 'not_available',
}
const TEXTO_ESTADO: Record<EstadoSalud, string> = {
  NORMAL: 'Normal',
  ADVERTENCIA: 'Advertencia',
  CRITICO: 'Crítico',
  DESCONOCIDO: 'Desconocido',
}
const AYUDA_ESTADO: Record<EstadoSalud, string> = {
  NORMAL: 'Comportamiento dentro de los parámetros conocidos.',
  ADVERTENCIA: 'Desviación que requiere seguimiento. No significa avería.',
  CRITICO: 'Supera un límite crítico documentado (con fuente).',
  DESCONOCIDO: 'No hay información suficiente para determinar el estado.',
}

const TONO_PROC: Record<Procedencia, string> = {
  REAL: 'decoded',
  SIMULADO: 'warning',
  ESTIMADO: 'measured',
  DOCUMENTADO: 'info',
  NO_DISPONIBLE: 'not_available',
}
const AYUDA_PROC: Record<Procedencia, string> = {
  REAL: 'Medición obtenida de una fuente real verificable (balizas recibidas por SatNOGS).',
  SIMULADO: 'Dato generado por una simulación o un escenario de prueba.',
  ESTIMADO: 'Resultado calculado a partir de un modelo o de otros datos.',
  DOCUMENTADO: 'Información procedente de documentación técnica.',
  NO_DISPONIBLE: 'La fuente consultada no tiene este dato.',
}

function EstadoBadge({ estado }: { estado: EstadoSalud }) {
  return (
    <span title={AYUDA_ESTADO[estado]}>
      <Badge tono={TONO_ESTADO[estado]}>{TEXTO_ESTADO[estado]}</Badge>
    </span>
  )
}

function ProcBadge({ p }: { p: Procedencia }) {
  return (
    <span title={AYUDA_PROC[p]}>
      <Badge tono={TONO_PROC[p]} conPunto={false}>
        {p === 'NO_DISPONIBLE' ? 'NO DISPONIBLE' : p}
      </Badge>
    </span>
  )
}

/** Ayuda desplegable: la explicación sencilla de un término técnico. */
function Ayuda({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <details className="group text-sm">
      <summary className="cursor-pointer select-none text-xs font-medium text-navy hover:underline">
        {titulo}
      </summary>
      <div className="mt-1.5 text-ink-soft">{children}</div>
    </details>
  )
}

function Explicacion({ children }: { children: ReactNode }) {
  return (
    <div className="mb-6 rounded-lg border border-blue/20 bg-blue-light px-4 py-3">
      <div className="label-caps mb-1">Para empezar</div>
      <p className="text-sm text-ink">{children}</p>
    </div>
  )
}

function valorTexto(v: IndicadorSalud['valor'], decimales = 3): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return magnitud(v, decimales + 1)
  return String(v)
}

/* ── Gráfica de una serie con lecturas inválidas marcadas ─────────────────── */

const EJE = { stroke: '#22324A', tick: { fill: '#93A4B8', fontSize: 11 } }

function GraficaSerie({ ind }: { ind: IndicadorSalud }) {
  // Un hueco de más de un día corta la línea: unir con una recta dos pases
  // separados por semanas dibujaría una evolución que nadie midió.
  const datos = useMemo(() => {
    const fuera: { t: number; valida: number | null; invalida: number | null }[] = []
    let previo: number | null = null
    for (const p of ind.serie) {
      const t = new Date(p.t).getTime()
      if (previo !== null && t - previo > 86_400_000) {
        fuera.push({ t: previo + 1, valida: null, invalida: null })
      }
      fuera.push({
        t,
        valida: p.valida ? p.v : null,
        invalida: !p.valida && p.v !== null ? p.v : null,
      })
      previo = t
    }
    return fuera
  }, [ind.serie])
  if (datos.length === 0) return null
  const hayInvalidas = datos.some((d) => d.invalida !== null)
  return (
    <div className="w-full">
      <div className="h-48 w-full">
      <ResponsiveContainer>
        <ComposedChart data={datos} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#22324A" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            scale="time"
            tickFormatter={(t) => fechaUTC(new Date(t).toISOString())}
            {...EJE}
          />
          <YAxis width={56} {...EJE} tickFormatter={(v) => magnitud(v, 3)} />
          <Tooltip
            contentStyle={{ background: '#0b121c', border: '1px solid #22324A', fontSize: 12 }}
            labelFormatter={(t) => fechaHoraUTC(new Date(Number(t)).toISOString())}
            formatter={(v, nombre) => [
              `${magnitud(Number(v), 4)} ${ind.unidad ?? ''}`,
              nombre === 'valida' ? 'Lectura válida' : 'No es una medida',
            ]}
          />
          <Line
            dataKey="valida"
            stroke="#38BDF8"
            dot={datos.length < 80}
            strokeWidth={1.5}
            connectNulls={false}
            isAnimationActive={false}
          />
          {hayInvalidas && (
            <Scatter dataKey="invalida" fill="#F87171" shape="cross" isAnimationActive={false} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
      </div>
      {hayInvalidas && (
        <p className="mt-1 text-xs text-ink-soft">
          <span className="font-semibold text-danger">✕</span> Lecturas que no son medidas
          (canal sin medida, saturado o enrielado). Se muestran, pero no se usan en el análisis.
        </p>
      )}
    </div>
  )
}

/* ── Tarjeta de indicador ─────────────────────────────────────────────────── */

function TarjetaIndicador({ ind, tecnico }: { ind: IndicadorSalud; tecnico: boolean }) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-navy-dark">{ind.nombre}</h4>
        <div className="flex flex-wrap gap-1.5">
          <ProcBadge p={ind.procedencia} />
          <EstadoBadge estado={ind.estado} />
        </div>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-semibold tnum text-navy-dark">{valorTexto(ind.valor)}</span>
        {ind.unidad && ind.valor !== null && (
          <span className="text-sm text-ink-soft">{ind.unidad}</span>
        )}
      </div>
      {ind.valor_fecha && (
        <div className="text-xs text-ink-soft">Última lectura válida: {fechaHoraUTC(ind.valor_fecha)}</div>
      )}
      <p className="text-sm text-ink">{ind.estado_motivo}</p>
      <Ayuda titulo="¿Qué significa?">{ind.que_es}</Ayuda>
      <Ayuda titulo="¿Por qué es importante?">{ind.por_que_importa}</Ayuda>
      {ind.notas.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-xs text-ink-soft">
          {ind.notas.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {tecnico && (
        <div className="space-y-2 border-t border-line pt-3 text-xs text-ink-soft">
          <div>
            <span className="font-semibold text-ink">Referencia: </span>
            {ind.referencia || '—'}
          </div>
          {Object.keys(ind.estadisticas).length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 tnum">
              {Object.entries(ind.estadisticas)
                .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
                .map(([k, v]) => (
                  <span key={k}>
                    {k.replaceAll('_', ' ')}: <span className="text-ink">{typeof v === 'number' ? magnitud(v, 5) : v}</span>
                  </span>
                ))}
            </div>
          )}
          {ind.validacion?.lecturas !== undefined && (
            <div className="tnum">
              Lecturas en el periodo: <span className="text-ink">{ind.validacion.lecturas}</span> ·
              válidas: <span className="text-ink">{ind.validacion.validas}</span>
              {ind.validacion.fraccion_valida !== null &&
                ` (${(ind.validacion.fraccion_valida * 100).toFixed(1)} %)`}
            </div>
          )}
          {ind.hallazgos.length > 0 && (
            <ul className="space-y-1">
              {ind.hallazgos.map((h) => (
                <li key={h.tipo}>
                  <Badge tono="warning">{h.tipo.replaceAll('_', ' ')}</Badge>{' '}
                  {h.lecturas} lecturas — {h.explicacion}
                </li>
              ))}
            </ul>
          )}
          {ind.tendencia && (
            <div className="tnum">
              Tendencia: {magnitud(ind.tendencia.pendiente_por_dia, 3)} {ind.unidad}/día en{' '}
              {magnitud(ind.tendencia.dias, 3)} días (|t| = {magnitud(ind.tendencia.t, 3)},{' '}
              {ind.tendencia.significativa ? 'significativa' : 'no significativa'})
            </div>
          )}
        </div>
      )}
      {ind.serie.length > 0 && <GraficaSerie ind={ind} />}
    </Card>
  )
}

function ListaNoDisponibles({ items }: { items: NoDisponibleSalud[] }) {
  if (items.length === 0) return null
  return (
    <Card>
      <CardHeader
        title="Información no disponible"
        description="Variables que esta fuente no contiene. No es lo mismo que un fallo del satélite."
      />
      <ul className="divide-y divide-line">
        {items.map((d) => (
          <li key={d.clave} className="py-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-ink">{d.nombre}</span>
              {d.unidad && <span className="text-xs text-ink-soft">({d.unidad})</span>}
              <ProcBadge p="NO_DISPONIBLE" />
            </div>
            <p className="mt-1 text-sm text-ink-soft">{d.motivo}</p>
            <Ayuda titulo="¿Qué mediría?">
              {d.que_es} {d.por_que_importa}
              {d.nodo_canal && <span className="block text-xs">Canal AMSAT-UK: {d.nodo_canal}</span>}
            </Ayuda>
            {d.notas.map((n) => (
              <p key={n} className="mt-1 text-xs text-ink-soft">
                {n}
              </p>
            ))}
          </li>
        ))}
      </ul>
    </Card>
  )
}

/* ── Alerta con las siete preguntas ───────────────────────────────────────── */

function TarjetaAlerta({ a }: { a: AlertaSalud }) {
  const u = a.unidad ? ` ${a.unidad}` : ''
  return (
    <details className="card group p-4">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
        <EstadoBadge estado={a.nivel} />
        <ProcBadge p={a.procedencia} />
        <Badge tono="info" conPunto={false}>
          {a.mecanismo}
        </Badge>
        <span className="min-w-0 flex-1 text-sm text-ink">
          <span className="font-semibold">{a.componente}:</span> {a.que_ocurrio}
        </span>
        <span className="text-xs text-ink-soft">
          {a.inicio.includes('T') ? fechaHoraUTC(a.inicio) : a.inicio}
        </span>
      </summary>
      <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[14rem_1fr]">
        <dt className="text-ink-soft">1. ¿Qué ocurrió?</dt>
        <dd className="text-ink">{a.que_ocurrio}</dd>
        <dt className="text-ink-soft">2. ¿En qué componente?</dt>
        <dd className="text-ink">{a.componente}</dd>
        <dt className="text-ink-soft">3. ¿Qué variable?</dt>
        <dd className="font-mono text-xs text-ink">{a.variable}</dd>
        <dt className="text-ink-soft">4. ¿Qué valor se registró?</dt>
        <dd className="tnum text-ink">
          {typeof a.valor_registrado === 'number' ? magnitud(a.valor_registrado, 5) : String(a.valor_registrado)}
          {typeof a.valor_registrado === 'number' ? u : ''}
        </dd>
        <dt className="text-ink-soft">5. ¿Cuál es la referencia?</dt>
        <dd className="text-ink">
          <span className="tnum">
            {typeof a.valor_referencia === 'number' ? magnitud(a.valor_referencia, 5) + u : String(a.valor_referencia)}
          </span>
          <span className="block text-xs text-ink-soft">{a.referencia}</span>
        </dd>
        <dt className="text-ink-soft">6. ¿Por qué puede importar?</dt>
        <dd className="text-ink">{a.por_que_importa}</dd>
        <dt className="text-ink-soft">7. ¿Qué falta para investigarlo?</dt>
        <dd className="text-ink">{a.informacion_adicional}</dd>
        <dt className="text-ink-soft">Periodo</dt>
        <dd className="text-xs text-ink-soft">
          {a.inicio} → {a.fin} · {a.lecturas} lecturas
        </dd>
      </dl>
    </details>
  )
}

function ListaAlertas({ alertas, vacio }: { alertas: AlertaSalud[]; vacio: string }) {
  const [todas, setTodas] = useState(false)
  if (alertas.length === 0) return <EmptyState titulo="Sin alertas" descripcion={vacio} />
  const visibles = todas ? alertas : alertas.slice(0, 15)
  return (
    <div className="space-y-2">
      {visibles.map((a) => (
        <TarjetaAlerta key={a.id} a={a} />
      ))}
      {alertas.length > 15 && (
        <button className="text-sm text-navy hover:underline" onClick={() => setTodas(!todas)}>
          {todas ? 'Mostrar menos' : `Mostrar las ${alertas.length} alertas`}
        </button>
      )}
    </div>
  )
}

/* ── Sección de subsistema ────────────────────────────────────────────────── */

function SeccionSubsistema({
  s,
  tecnico,
  extra,
}: {
  s: SubsistemaSalud
  tecnico: boolean
  extra?: ReactNode
}) {
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold text-navy-dark sm:text-2xl">{s.nombre}</h2>
        <EstadoBadge estado={s.estado} />
        {s.procedencias.map((p) => (
          <ProcBadge key={p} p={p} />
        ))}
      </div>
      <Explicacion>{s.explicacion}</Explicacion>
      <p className="mb-4 text-sm text-ink">{s.resumen}</p>
      {s.notas.map((n) => (
        <div key={n} className="mb-4">
          <Nota tono="warning">{n}</Nota>
        </div>
      ))}
      {s.indicadores.length > 0 && (
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          {s.indicadores.map((i) => (
            <TarjetaIndicador key={i.clave} ind={i} tecnico={tecnico} />
          ))}
        </div>
      )}
      {extra}
      {s.alertas.length > 0 && (
        <div className="mb-6">
          <h3 className="mb-3 text-base font-semibold text-navy-dark">Alertas de este subsistema</h3>
          <ListaAlertas alertas={s.alertas} vacio="" />
        </div>
      )}
      <ListaNoDisponibles items={s.no_disponibles} />
    </div>
  )
}

/* ── Extras de comunicaciones: lo simulado aparte de lo recibido ──────────── */

function ExtraComunicaciones({ s }: { s: SubsistemaSalud }) {
  const ber = s.extra.simulacion_ber as
    | { puntos: { snr_db: number; ber_empirica: number; ber_teorica: number }[]; fuente: string; nota: string }
    | null
  const margen = s.extra.margen_enlace as
    | { por_elevacion: { elevacion_deg: number; margen_db: number }[]; fuente: string; nota: string; esquema: string }
    | null
  return (
    <div className="mb-6 grid gap-4 lg:grid-cols-2">
      {ber && (
        <Card>
          <CardHeader title="BER de la cadena GNU Radio" description={ber.nota} actions={<ProcBadge p="SIMULADO" />} />
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={ber.puntos.map((p) => ({ ...p, emp: Math.max(p.ber_empirica, 1e-6) }))}>
                <CartesianGrid stroke="#22324A" strokeDasharray="3 3" />
                <XAxis dataKey="snr_db" unit=" dB" {...EJE} />
                <YAxis scale="log" domain={[1e-6, 1]} allowDataOverflow width={56} {...EJE}
                  tickFormatter={(v) => Number(v).toExponential(0)} />
                <Tooltip contentStyle={{ background: '#0b121c', border: '1px solid #22324A', fontSize: 12 }}
                  formatter={(v) => Number(v).toExponential(2)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line dataKey="emp" name="BER simulada" stroke="#FBBF24" isAnimationActive={false} />
                <Line dataKey="ber_teorica" name="BER teórica" stroke="#93A4B8" strokeDasharray="4 3" dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-ink-soft">{ber.fuente}</p>
        </Card>
      )}
      {margen && (
        <Card>
          <CardHeader title="Margen del enlace según la elevación" description={margen.nota} actions={<ProcBadge p="ESTIMADO" />} />
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={margen.por_elevacion}>
                <CartesianGrid stroke="#22324A" strokeDasharray="3 3" />
                <XAxis dataKey="elevacion_deg" unit="°" {...EJE} />
                <YAxis unit=" dB" width={56} {...EJE} />
                <ReferenceLine y={0} stroke="#F87171" strokeDasharray="4 3" />
                <Tooltip contentStyle={{ background: '#0b121c', border: '1px solid #22324A', fontSize: 12 }} />
                <Line dataKey="margen_db" name="Margen (dB)" stroke="#A78BFA" isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-ink-soft">{margen.esquema} · {margen.fuente}</p>
        </Card>
      )}
      <div className="lg:col-span-2">
        <Nota>
          <strong>Tipo de señal:</strong> {s.extra.tipo_de_senal} La BER y el margen de arriba son
          simulación y estimación: no prueban comunicación real con STRaND-1.
        </Nota>
      </div>
    </div>
  )
}

/* ── Inicio ───────────────────────────────────────────────────────────────── */

const ORDEN_SUBSISTEMAS = ['eps', 'termico', 'comunicaciones', 'obc', 'adcs'] as const

function Inicio({ inf, ir }: { inf: InformeSalud; ir: (s: Pestana) => void }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          etiqueta="Estado general de supervisión"
          valor={TEXTO_ESTADO[inf.estado_general]}
          tono={{ NORMAL: 'ok', ADVERTENCIA: 'warning', CRITICO: 'critical', DESCONOCIDO: 'muted' }[inf.estado_general] as any}
          detalle={inf.estado_general_texto}
        />
        <MetricCard
          etiqueta="Última telemetría"
          valor={inf.ultima_actualizacion ? fechaUTC(inf.ultima_actualizacion) : '—'}
          tono="muted"
          detalle={inf.antiguedad_dias !== null && !inf.simulado ? `Hace ${Math.round(inf.antiguedad_dias)} días` : 'Escenario simulado'}
        />
        <MetricCard
          etiqueta="Periodo evaluado"
          valor={inf.periodo.ventana_dias ? `${inf.periodo.ventana_dias} días` : 'Completo'}
          tono="info"
          detalle={
            inf.periodo.desde
              ? `${fechaUTC(inf.periodo.desde)} → ${fechaUTC(inf.periodo.hasta)}`
              : `Hasta ${fechaUTC(inf.periodo.hasta)}`
          }
        />
      </div>
      <Nota tono={inf.simulado ? 'warning' : 'info'}>
        <strong>Vigencia:</strong> {inf.vigencia}
      </Nota>

      <div>
        <h3 className="mb-3 text-base font-semibold text-navy-dark">Estado de los seis subsistemas</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ORDEN_SUBSISTEMAS.map((k) => {
            const s = inf.subsistemas[k]
            return (
              <button key={k} onClick={() => ir(k)} className="card p-4 text-left transition-colors hover:border-navy">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-navy-dark">{s.nombre}</span>
                  <EstadoBadge estado={s.estado} />
                </div>
                <p className="text-xs text-ink-soft">{s.resumen}</p>
                <p className="mt-2 text-xs text-ink-soft">
                  {s.indicadores.length} indicadores · {s.no_disponibles.length} no disponibles
                </p>
              </button>
            )
          })}
          <button onClick={() => ir('anomalias')} className="card p-4 text-left transition-colors hover:border-navy">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-navy-dark">{inf.anomalias.nombre}</span>
              <EstadoBadge estado={inf.anomalias.estado} />
            </div>
            <p className="text-xs text-ink-soft">{inf.anomalias.resumen.total} alertas en el periodo.</p>
          </button>
        </div>
      </div>

      <Card>
        <CardHeader
          title="Procedencia de la información"
          description="Cuántos indicadores salen de cada tipo de fuente."
        />
        <div className="flex flex-wrap gap-3">
          {Object.entries(inf.indicadores_por_procedencia).map(([p, n]) => (
            <span key={p} className="flex items-center gap-2 text-sm">
              <ProcBadge p={p as Procedencia} /> <span className="tnum text-ink">{n}</span>
            </span>
          ))}
        </div>
        <p className="mt-3 text-xs text-ink-soft">
          Fuente: {inf.fuente}. {inf.descripcion_fuente}
        </p>
      </Card>

      <div>
        <h3 className="mb-3 text-base font-semibold text-navy-dark">Alertas recientes</h3>
        <ListaAlertas alertas={inf.alertas_recientes} vacio="No se detectó ninguna desviación en el periodo." />
      </div>
    </div>
  )
}

/* ── Anomalías ────────────────────────────────────────────────────────────── */

function Anomalias({ inf }: { inf: InformeSalud }) {
  const a = inf.anomalias
  const cm = a.comparacion_modelo
  const datosModelo = useMemo(
    () => (cm ? cm.referencia.map((r, i) => ({ t: r.t, ref: r.y, med: cm.medida[i]?.y })) : []),
    [cm],
  )
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold text-navy-dark sm:text-2xl">{a.nombre}</h2>
        <EstadoBadge estado={a.estado} />
      </div>
      <Explicacion>{a.explicacion}</Explicacion>
      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="Cómo se detectan" />
          <ul className="space-y-2 text-sm">
            {Object.entries(a.mecanismos).map(([k, v]) => (
              <li key={k}>
                <span className="font-semibold text-ink">{k}</span>{' '}
                <span className="text-ink-soft">— {v}</span>
                {a.resumen.por_mecanismo[k] ? (
                  <span className="ml-1 tnum text-warn">({a.resumen.por_mecanismo[k]})</span>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Clasificación" />
          <ul className="space-y-2 text-sm">
            {(['NORMAL', 'ADVERTENCIA', 'CRITICO', 'DESCONOCIDO'] as EstadoSalud[]).map((e) => (
              <li key={e} className="flex items-start gap-2">
                <EstadoBadge estado={e} />
                <span className="text-ink-soft">
                  {AYUDA_ESTADO[e]} <span className="tnum text-ink">{a.resumen.por_nivel[e] ?? 0}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-ink-soft">
            Para STRaND-1 no hay límites de operación publicados, así que sobre los datos reales
            ninguna alerta puede llegar a «Crítico».
          </p>
        </Card>
      </div>
      {cm && (
        <Card className="mb-6">
          <CardHeader
            title={`Comparación con el modelo ${cm.planta} · ${cm.controlador}`}
            description={`Residuo RMS ${cm.rms_residuo_normalizado} (tolerancia ${cm.tolerancia}). Sobrepaso medido ${cm.sobrepaso_medido_pct} % frente a ${cm.sobrepaso_modelo_pct} % del modelo.`}
            actions={
              <>
                <ProcBadge p={cm.procedencia_medida} />
                <Badge tono={cm.fuera_de_tolerancia ? 'warning' : 'normal'}>
                  {cm.fuera_de_tolerancia ? 'Fuera de tolerancia' : 'Dentro de tolerancia'}
                </Badge>
              </>
            }
          />
          <div className="h-64">
            <ResponsiveContainer>
              <LineChart data={datosModelo}>
                <CartesianGrid stroke="#22324A" strokeDasharray="3 3" />
                <XAxis dataKey="t" type="number" unit=" s" {...EJE} />
                <YAxis width={48} {...EJE} />
                <Tooltip contentStyle={{ background: '#0b121c', border: '1px solid #22324A', fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line dataKey="ref" name="Modelo (ESTIMADO)" stroke="#93A4B8" strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                <Line dataKey="med" name={`Medida (${cm.procedencia_medida})`} stroke="#FBBF24" dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-ink-soft">
            Una discrepancia indica que la respuesta no es la del modelo, no que haya una avería. G1
            y G2 no están identificados con ningún subsistema de STRaND-1.
          </p>
        </Card>
      )}
      <h3 className="mb-3 text-base font-semibold text-navy-dark">Registro de eventos del periodo</h3>
      <ListaAlertas alertas={a.alertas} vacio="No se detectó ninguna desviación en el periodo evaluado." />
    </div>
  )
}

/* ── Modelos PID ──────────────────────────────────────────────────────────── */

const COLOR_CTRL = { P: '#38BDF8', PI: '#A78BFA', PID: '#34D399' } as const

function ModelosPid({ tecnico }: { tecnico: boolean }) {
  const [ts, setTs] = useState(0.01)
  const { data, error, loading, recargar } = useApi(() => api.saludPid(ts), [ts])
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold text-navy-dark sm:text-2xl">Modelos de referencia P, PI y PID</h2>
        <ProcBadge p="ESTIMADO" />
      </div>
      <Explicacion>
        Un controlador PID ajusta una acción para que un sistema llegue a un valor deseado: la parte
        P reacciona al error actual, la I al error acumulado y la D a lo rápido que cambia. Aquí se
        estudian dos modelos matemáticos del trabajo de Teoría de Control, sintonizados con el
        método de Ziegler–Nichols, para comparar respuestas esperadas con respuestas medidas. Son
        resultados matemáticos: no controlan nada del satélite.
      </Explicacion>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <label htmlFor="ts" className="text-ink-soft">
          Periodo de muestreo
        </label>
        <select
          id="ts"
          value={ts}
          onChange={(e) => setTs(Number(e.target.value))}
          className="rounded-md border border-line bg-panel px-2 py-1 text-ink"
        >
          {[0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.25].map((v) => (
            <option key={v} value={v}>
              {v} s
            </option>
          ))}
        </select>
        <span className="text-xs text-ink-soft">
          Con muestreos lentos algún lazo discreto se vuelve inestable: se indica, no se oculta.
        </span>
      </div>
      {loading && <Skeleton className="h-96" />}
      {error && <ErrorState mensaje={error} onReintentar={recargar} />}
      {data && (
        <div className="space-y-6">
          <Nota tono="warning">
            <ul className="list-disc space-y-1 pl-5">
              {data.limitaciones.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </Nota>
          {data.modelos.map((m) => {
            const filas = m.controladores[0].respuesta.map((p, i) => {
              const fila: Record<string, number> = { t: p.t }
              m.controladores.forEach((c) => {
                const y = c.respuesta[i]?.y
                if (y !== undefined && Math.abs(y) < 5) fila[c.controlador] = y
              })
              return fila
            })
            return (
              <Card key={m.planta}>
                <CardHeader
                  title={`${m.planta}(s) = ${m.expresion}`}
                  description={`${m.descripcion} Ku = ${magnitud(m.ganancia_ultima.Ku, 5)}, Pu = ${magnitud(m.ganancia_ultima.Pu_s, 4)} s.`}
                />
                <div className="h-72">
                  <ResponsiveContainer>
                    <LineChart data={filas}>
                      <CartesianGrid stroke="#22324A" strokeDasharray="3 3" />
                      <XAxis dataKey="t" type="number" unit=" s" {...EJE} />
                      <YAxis width={44} domain={[0, 'auto']} {...EJE} />
                      <ReferenceLine y={1} stroke="#6B7D92" strokeDasharray="4 3" />
                      <Tooltip contentStyle={{ background: '#0b121c', border: '1px solid #22324A', fontSize: 12 }}
                        formatter={(v) => Number(v).toFixed(4)} labelFormatter={(t) => `t = ${t} s`} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      {m.controladores.map((c) => (
                        <Line key={c.controlador} dataKey={c.controlador} stroke={COLOR_CTRL[c.controlador]}
                          strokeDasharray={c.controlador === 'PI' ? '5 3' : undefined}
                          dot={false} isAnimationActive={false} />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm tnum">
                    <thead className="text-left text-xs text-ink-soft">
                      <tr>
                        <th className="py-1 pr-3">Control</th>
                        <th className="pr-3">Kp</th>
                        <th className="pr-3">Ti (s)</th>
                        <th className="pr-3">Td (s)</th>
                        <th className="pr-3" title="Cuánto se pasa la respuesta del valor final">Sobrepaso</th>
                        <th className="pr-3" title="Del 10 % al 90 % del valor final">T. subida</th>
                        <th className="pr-3" title="Hasta quedar dentro de ±2 %">T. asentamiento</th>
                        <th className="pr-3" title="1 − valor final">Error estac.</th>
                        <th className="pr-3">Estabilidad</th>
                        {tecnico && <th className="pr-3">máx |z|</th>}
                        {tecnico && <th className="pr-3">MG / MF</th>}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {m.controladores.map((c) => {
                        const k = c.metricas
                        return (
                          <tr key={c.controlador}>
                            <td className="py-1.5 pr-3 font-semibold" style={{ color: COLOR_CTRL[c.controlador] }}>{c.controlador}</td>
                            <td className="pr-3">{magnitud(c.sintonia.Kp, 5)}</td>
                            <td className="pr-3">{c.sintonia.Ti !== null ? magnitud(c.sintonia.Ti, 4) : '—'}</td>
                            <td className="pr-3">{c.sintonia.Td !== null ? magnitud(c.sintonia.Td, 4) : '—'}</td>
                            <td className="pr-3">{k.sobrepaso_pct !== null ? `${k.sobrepaso_pct} %` : '—'}</td>
                            <td className="pr-3">{k.tiempo_subida_s !== null ? `${k.tiempo_subida_s} s` : '—'}</td>
                            <td className="pr-3">
                              {k.tiempo_asentamiento_s !== null ? `${k.tiempo_asentamiento_s} s` : k.estable_discreto ? '> 20 s' : '—'}
                            </td>
                            <td className="pr-3">{k.error_estacionario !== null ? magnitud(k.error_estacionario, 3) : '—'}</td>
                            <td className="pr-3">
                              <Badge tono={k.estable_discreto ? 'normal' : 'critical'}>
                                {k.estable_discreto ? 'Estable' : 'Inestable'}
                              </Badge>
                            </td>
                            {tecnico && <td className="pr-3">{k.max_modulo_polo_z.toFixed(5)}</td>}
                            {tecnico && (
                              <td className="pr-3">
                                {c.margenes.margen_ganancia_db ?? '—'} dB / {c.margenes.margen_fase_deg ?? '—'}°
                              </td>
                            )}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            )
          })}
          <p className="text-xs text-ink-soft">
            {data.discretizacion} Filtro derivativo N = {data.n_filtro_derivativo}. Entrada: {data.entrada}.
            Ts = {data.ts_s} s. Validado contra scipy.signal y MATLAB (health_monitor/validacion_matlab).
          </p>
        </div>
      )}
    </div>
  )
}

/* ── Historial ────────────────────────────────────────────────────────────── */

function Historial({ simulado }: { simulado: boolean }) {
  const hist = useApi(() => api.saludHistorial(), [])
  const ev = useApi(() => api.saludEventos(), [])
  const filas = (hist.data?.meses ?? []).filter((m) => m.variable === 'battery_0_voltage')
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold text-navy-dark sm:text-2xl">Historial</h2>
        <ProcBadge p="REAL" />
      </div>
      <Explicacion>
        Cuántas lecturas del voltaje de la batería llegaron cada mes y cuántas eran medidas de
        verdad. Así se ve cuándo dejó de medir el convertidor del sistema de energía: la batería
        no «se puso en 9,75 V», el sensor dejó de leer.
      </Explicacion>
      {simulado && (
        <Nota>El historial siempre muestra el archivo real, aunque arriba esté seleccionado un escenario.</Nota>
      )}
      {hist.loading && <Skeleton className="h-64" />}
      {hist.error && <ErrorState mensaje={hist.error} onReintentar={hist.recargar} />}
      {filas.length > 0 && (
        <Card>
          <CardHeader title="Fracción de lecturas válidas por mes · batería 0" />
          <div className="h-64">
            <ResponsiveContainer>
              <ComposedChart data={filas.map((m) => ({ ...m, pct: m.fraccion_valida * 100 }))}>
                <CartesianGrid stroke="#22324A" strokeDasharray="3 3" />
                <XAxis dataKey="mes" {...EJE} />
                <YAxis yAxisId="a" unit=" %" domain={[0, 100]} width={52} {...EJE} />
                <YAxis yAxisId="b" orientation="right" unit=" V" width={52} {...EJE} />
                <Tooltip contentStyle={{ background: '#0b121c', border: '1px solid #22324A', fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line yAxisId="a" dataKey="pct" name="% válidas" stroke="#34D399" isAnimationActive={false} />
                <Line yAxisId="b" dataKey="mediana_valida" name="Mediana válida (V)" stroke="#38BDF8"
                  strokeDasharray="4 3" connectNulls={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
      <Card>
        <CardHeader
          title="Eventos registrados"
          description={ev.data?.nota ?? 'Alertas guardadas por las evaluaciones hechas en esta instalación.'}
        />
        {ev.data && (
          <ListaAlertas alertas={ev.data.eventos} vacio="Todavía no se ha registrado ninguna alerta." />
        )}
      </Card>
    </div>
  )
}

/* ── Página ───────────────────────────────────────────────────────────────── */

type Pestana =
  | 'inicio' | 'eps' | 'termico' | 'comunicaciones' | 'obc' | 'adcs' | 'anomalias' | 'pid' | 'historial'

const PESTANAS: { valor: Pestana; etiqueta: string }[] = [
  { valor: 'inicio', etiqueta: 'Inicio' },
  { valor: 'eps', etiqueta: 'Sistema energético' },
  { valor: 'termico', etiqueta: 'Estado térmico' },
  { valor: 'comunicaciones', etiqueta: 'Comunicaciones' },
  { valor: 'obc', etiqueta: 'Computador de a bordo' },
  { valor: 'adcs', etiqueta: 'Orientación' },
  { valor: 'anomalias', etiqueta: 'Anomalías' },
  { valor: 'pid', etiqueta: 'Modelos PID' },
  { valor: 'historial', etiqueta: 'Historial' },
]

const PERIODOS = [
  { id: 'ultimo', etiqueta: 'Último registro (30 días)', hasta: undefined, dias: 30 },
  { id: 'sana', etiqueta: 'Fase sana (2019-11 a 2020-10)', hasta: '2020-10-31', dias: 365 },
  { id: 'transicion', etiqueta: 'Fallo del ADC (2020-11 a 2021-02)', hasta: '2021-02-28', dias: 120 },
  { id: 'todo', etiqueta: 'Todo el archivo', hasta: undefined, dias: 4000 },
] as const

/** Sección, fuente, periodo y nivel viven en la URL para poder enlazar una vista
 *  concreta (?seccion=eps&fuente=caida_voltaje&nivel=tecnico). */
function leerUrl() {
  const q = new URLSearchParams(window.location.search)
  const seccion = q.get('seccion') as Pestana | null
  const periodo = q.get('periodo')
  return {
    pestana: PESTANAS.some((t) => t.valor === seccion) ? (seccion as Pestana) : 'inicio',
    tecnico: q.get('nivel') === 'tecnico',
    fuente: q.get('fuente') || 'real',
    periodo: (PERIODOS.some((x) => x.id === periodo) ? periodo : 'ultimo') as (typeof PERIODOS)[number]['id'],
  }
}

export function Salud({ embebido = false }: { embebido?: boolean }) {
  const inicial = useMemo(leerUrl, [])
  const [pestana, setPestana] = useState<Pestana>(inicial.pestana)
  const [tecnico, setTecnico] = useState(inicial.tecnico)
  const [fuente, setFuente] = useState<string>(inicial.fuente)
  const [periodo, setPeriodo] = useState<(typeof PERIODOS)[number]['id']>(inicial.periodo)
  useEffect(() => {
    const q = new URLSearchParams()
    if (pestana !== 'inicio') q.set('seccion', pestana)
    if (fuente !== 'real') q.set('fuente', fuente)
    if (periodo !== 'ultimo') q.set('periodo', periodo)
    if (tecnico) q.set('nivel', 'tecnico')
    const cola = q.toString()
    window.history.replaceState(null, '', `${window.location.pathname}${cola ? `?${cola}` : ''}${window.location.hash}`)
  }, [pestana, fuente, periodo, tecnico])
  const escenarios = useApi(() => api.saludEscenarios(), [])
  const p = PERIODOS.find((x) => x.id === periodo)!
  const { data: inf, error, loading, recargar } = useApi(
    () => (fuente === 'real' ? api.saludResumen(p.hasta, p.dias) : api.saludEscenario(fuente)),
    [fuente, periodo],
  )

  const contenido = (): ReactNode => {
    if (pestana === 'pid') return <ModelosPid tecnico={tecnico} />
    if (pestana === 'historial') return <Historial simulado={fuente !== 'real'} />
    if (loading) return <Skeleton className="h-96" />
    if (error) return <ErrorState mensaje={error} onReintentar={recargar} />
    if (!inf) return null
    if (pestana === 'inicio') return <Inicio inf={inf} ir={setPestana} />
    if (pestana === 'anomalias') return <Anomalias inf={inf} />
    const s = inf.subsistemas[pestana]
    return (
      <SeccionSubsistema
        s={s}
        tecnico={tecnico}
        extra={pestana === 'comunicaciones' ? <ExtraComunicaciones s={s} /> : undefined}
      />
    )
  }

  return (
    <div>
      {inf?.simulado && fuente !== 'real' && (
        <div className="sticky top-16 z-20 mb-4 rounded-lg border border-warn/40 bg-warn-bg px-4 py-2 text-sm font-semibold text-warn">
          ESCENARIO SIMULADO · «{inf.escenario}» — estos datos no son de STRaND-1
        </div>
      )}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className={embebido ? 'hidden' : ''}>
          <div className="label-caps">STRaND-1 · NORAD 39090 · HMTA</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-navy-dark sm:text-3xl">
            Supervisión de salud del satélite
          </h1>
          <p className="mt-1.5 max-w-3xl text-sm text-ink-soft">
            Convierte la telemetría en información comprensible sobre el estado de cada
            subsistema. Es solo supervisión: no envía órdenes al satélite. Cada dato indica de
            dónde sale.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-ink-soft">Fuente</span>
            <select
              value={fuente}
              onChange={(e) => setFuente(e.target.value)}
              className="rounded-md border border-line bg-panel px-2 py-1 text-ink"
            >
              <option value="real">Archivo real (SatNOGS)</option>
              {escenarios.data?.escenarios.map((e) => (
                <option key={e.nombre} value={e.nombre}>
                  Simulado: {e.nombre.replaceAll('_', ' ')}
                </option>
              ))}
            </select>
          </label>
          {fuente === 'real' && (
            <label className="flex items-center gap-2">
              <span className="text-ink-soft">Periodo</span>
              <select
                value={periodo}
                onChange={(e) => setPeriodo(e.target.value as typeof periodo)}
                className="rounded-md border border-line bg-panel px-2 py-1 text-ink"
              >
                {PERIODOS.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.etiqueta}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Tabs
            opciones={[
              { valor: 'basico', etiqueta: 'Básico' },
              { valor: 'tecnico', etiqueta: 'Técnico' },
            ]}
            valor={tecnico ? 'tecnico' : 'basico'}
            onChange={(v) => setTecnico(v === 'tecnico')}
          />
        </div>
      </div>
      {fuente !== 'real' && escenarios.data && (
        <div className="mb-4">
          <Nota tono="warning">
            {escenarios.data.escenarios.find((e) => e.nombre === fuente)?.descripcion}{' '}
            {escenarios.data.nota}
          </Nota>
        </div>
      )}
      <nav className="mb-6 flex flex-wrap gap-1.5" aria-label="Secciones de salud">
        {PESTANAS.map((t) => {
          const estado = t.valor === 'anomalias' ? inf?.anomalias.estado : inf?.subsistemas[t.valor]?.estado
          return (
            <button
              key={t.valor}
              onClick={() => setPestana(t.valor)}
              aria-current={pestana === t.valor}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                pestana === t.valor
                  ? 'border-navy bg-navy text-on-accent'
                  : 'border-line bg-panel text-navy hover:border-navy'
              }`}
            >
              {t.etiqueta}
              {estado && estado !== 'NORMAL' && estado !== 'DESCONOCIDO' && (
                <span className={`size-1.5 rounded-full ${estado === 'CRITICO' ? 'bg-danger' : 'bg-warn'}`} aria-label={TEXTO_ESTADO[estado]} />
              )}
            </button>
          )
        })}
      </nav>
      {contenido()}
    </div>
  )
}
