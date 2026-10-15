/** Gráficas sobre el tema oscuro. Las series repiten los tokens
 *  --color-series-* de index.css (cian / violeta / verde, todas por encima de
 *  6,5:1 sobre el panel); la serie intermedia va además discontinua, así que
 *  no depende solo del color. */

import {
  Area,
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ReactNode } from 'react'

export const SERIES = {
  recibidos: '#38BDF8',
  procesados: '#A78BFA',
  decodificados: '#34D399',
} as const

const EJE = { stroke: '#22324A', tick: { fill: '#93A4B8', fontSize: 11 } }

/* ── Tooltip común ────────────────────────────────────────────────────────── */

function CajaTooltip({ titulo, filas }: { titulo: string; filas: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-panel px-3 py-2 shadow-lg shadow-black/40">
      <div className="mb-1.5 text-xs font-semibold text-navy-dark">{titulo}</div>
      <div className="space-y-1">{filas}</div>
    </div>
  )
}

function FilaTooltip({ color, nombre, valor }: { color: string; nombre: string; valor: ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="size-2 shrink-0 rounded-[2px]" style={{ background: color }} aria-hidden />
      <span className="text-ink-soft">{nombre}</span>
      <span className="ml-auto pl-3 font-semibold tnum text-ink">{valor}</span>
    </div>
  )
}

/* ── Leyenda ──────────────────────────────────────────────────────────────── */

export function Leyenda({
  items,
}: {
  items: { color: string; label: string; discontinua?: boolean }[]
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      {items.map((i) => (
        <div key={i.label} className="flex items-center gap-2">
          <svg width="18" height="4" aria-hidden className="shrink-0">
            <line
              x1="0"
              y1="2"
              x2="18"
              y2="2"
              stroke={i.color}
              strokeWidth="2"
              strokeDasharray={i.discontinua ? '5 3' : undefined}
            />
          </svg>
          <span className="text-xs font-medium text-ink-soft">{i.label}</span>
        </div>
      ))}
    </div>
  )
}

/* ── Serie temporal de frames ─────────────────────────────────────────────── */

export interface PuntoSerie {
  etiqueta: string
  recibidos: number
  procesados: number
  decodificados: number
}

/** Serie de frames. `zoom` añade una barra para acotar el intervalo visible,
 *  útil en el histórico (más de cien meses en un solo eje). */
export function GraficaFrames({
  datos,
  alto = 300,
  zoom = false,
}: {
  datos: PuntoSerie[]
  alto?: number
  zoom?: boolean
}) {
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <ComposedChart data={datos} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
        <defs>
          <linearGradient id="relleno-recibidos" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES.recibidos} stopOpacity={0.28} />
            <stop offset="100%" stopColor={SERIES.recibidos} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} strokeDasharray="0" />
        <XAxis
          dataKey="etiqueta"
          axisLine={{ stroke: EJE.stroke }}
          tickLine={false}
          tick={EJE.tick}
          minTickGap={24}
        />
        <YAxis
          axisLine={false}
          tickLine={false}
          tick={EJE.tick}
          allowDecimals={false}
          width={60}
          label={{
            value: 'Frames',
            angle: -90,
            position: 'insideLeft',
            offset: 14,
            style: { fill: '#93A4B8', fontSize: 11 },
          }}
        />
        <Tooltip
          cursor={{ stroke: '#93A4B8', strokeWidth: 1, strokeDasharray: '3 3' }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null
            return (
              <CajaTooltip
                titulo={String(label)}
                filas={payload.map((p) => (
                  <FilaTooltip
                    key={String(p.dataKey)}
                    color={p.color as string}
                    nombre={String(p.name)}
                    valor={p.value as number}
                  />
                ))}
              />
            )
          }}
        />
        {/* El área solo da peso visual a la serie principal; las otras dos
            quedan como líneas para no tapar la diferencia entre ellas. */}
        <Area
          type="monotone"
          dataKey="recibidos"
          name="Recibidos"
          stroke={SERIES.recibidos}
          strokeWidth={2}
          fill="url(#relleno-recibidos)"
          dot={false}
          isAnimationActive={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: '#0B121C' }}
        />
        {/* Trazo discontinuo como codificación secundaria: "procesados" coincide
            exactamente con "recibidos" siempre que todos los frames tengan bytes
            analizables, y una línea sólida encima de otra ocultaría la de abajo. */}
        <Line
          type="monotone"
          dataKey="procesados"
          name="Procesados"
          stroke={SERIES.procesados}
          strokeWidth={2}
          strokeDasharray="6 4"
          dot={false}
          isAnimationActive={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: '#0B121C' }}
        />
        <Line
          type="monotone"
          dataKey="decodificados"
          name="Decodificados"
          stroke={SERIES.decodificados}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: '#0B121C' }}
        />
        {zoom && datos.length > 12 && (
          <Brush
            dataKey="etiqueta"
            height={18}
            travellerWidth={6}
            stroke="#2E5A78"
            fill="#0B121C"
            tickFormatter={() => ''}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/* ── Barras genéricas ─────────────────────────────────────────────────────── */

export function GraficaBarras({
  datos,
  claveX,
  claveY,
  etiquetaX,
  etiquetaY,
  color = SERIES.recibidos,
  alto = 260,
  colores,
  sufijoTooltip = '',
  escalaLog = false,
}: {
  datos: Record<string, any>[]
  claveX: string
  claveY: string
  etiquetaX?: string
  etiquetaY?: string
  color?: string
  alto?: number
  colores?: string[]
  sufijoTooltip?: string
  /** Eje Y logarítmico. Los ceros no existen en log: esas barras se omiten. */
  escalaLog?: boolean
}) {
  const filas = escalaLog
    ? datos.map((d) => ({ ...d, [claveY]: d[claveY] > 0 ? d[claveY] : null }))
    : datos
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <BarChart data={filas} margin={{ top: 8, right: 12, bottom: etiquetaX ? 20 : 4, left: -8 }}>
        <CartesianGrid vertical={false} strokeDasharray="0" />
        <XAxis
          dataKey={claveX}
          axisLine={{ stroke: EJE.stroke }}
          tickLine={false}
          tick={EJE.tick}
          minTickGap={12}
          label={
            etiquetaX
              ? { value: etiquetaX, position: 'insideBottom', offset: -12, style: { fill: '#93A4B8', fontSize: 11 } }
              : undefined
          }
        />
        <YAxis
          axisLine={false}
          tickLine={false}
          tick={EJE.tick}
          allowDecimals={false}
          width={etiquetaY ? (escalaLog ? 72 : 60) : 44}
          scale={escalaLog ? 'log' : 'auto'}
          ticks={escalaLog ? [1, 10, 100, 1000, 10000, 100000] : undefined}
          domain={escalaLog ? [1, (max: number) => 10 ** Math.ceil(Math.log10(Math.max(max, 10)))] : [0, 'auto']}
          allowDataOverflow={escalaLog}
          label={
            etiquetaY
              ? { value: etiquetaY, angle: -90, position: 'insideLeft', offset: 14, style: { fill: '#93A4B8', fontSize: 11 } }
              : undefined
          }
        />
        <Tooltip
          cursor={{ fill: '#0E2233' }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null
            return (
              <CajaTooltip
                titulo={`${label}${sufijoTooltip}`}
                filas={
                  <FilaTooltip
                    color={(payload[0].payload?.__color as string) ?? color}
                    nombre={String(payload[0].name)}
                    valor={payload[0].value as number}
                  />
                }
              />
            )
          }}
        />
        {/* Radio 4px en el extremo de dato, anclado a la línea base. */}
        <Bar
          dataKey={claveY}
          name="Frames"
          fill={color}
          radius={[4, 4, 0, 0]}
          maxBarSize={38}
          isAnimationActive={false}
        >
          {colores &&
            filas.map((_, i) => <Cell key={i} fill={colores[i % colores.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ── Barras horizontales (ranking) ────────────────────────────────────────── */

export function GraficaRanking({
  datos,
  claveNombre,
  claveValor,
  alto,
  detalle,
}: {
  datos: Record<string, any>[]
  claveNombre: string
  claveValor: string
  alto?: number
  /** Línea extra del tooltip (por ejemplo, la fecha del último frame). */
  detalle?: (fila: Record<string, any>) => string
}) {
  return (
    <ResponsiveContainer width="100%" height={alto ?? datos.length * 26 + 16}>
      <BarChart data={datos} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey={claveNombre}
          axisLine={false}
          tickLine={false}
          tick={{ ...EJE.tick, fontFamily: 'JetBrains Mono, monospace', fontSize: 10.5 }}
          width={118}
        />
        <Tooltip
          cursor={{ fill: '#0E2233' }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const fila = payload[0].payload as Record<string, any>
            return (
              <CajaTooltip
                titulo={String(fila[claveNombre])}
                filas={
                  <>
                    <FilaTooltip color={SERIES.recibidos} nombre="Frames" valor={fila[claveValor]} />
                    {detalle && <div className="text-xs text-ink-soft">{detalle(fila)}</div>}
                  </>
                }
              />
            )
          }}
        />
        <Bar
          dataKey={claveValor}
          fill={SERIES.recibidos}
          radius={[0, 4, 4, 0]}
          barSize={14}
          isAnimationActive={false}
          label={{ position: 'right', fill: '#93A4B8', fontSize: 11 }}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ── Minigráfica para tarjetas de parámetro ───────────────────────────────── */

export function Sparkline({ datos }: { datos: { value: number }[] }) {
  if (datos.length < 2) return null
  return (
    <ResponsiveContainer width="100%" height={40}>
      <LineChart data={datos} margin={{ top: 4, right: 2, bottom: 2, left: 2 }}>
        <Line
          type="monotone"
          dataKey="value"
          stroke={SERIES.recibidos}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
