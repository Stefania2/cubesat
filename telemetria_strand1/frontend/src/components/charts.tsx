/** Gráficas. Paleta validada con el comprobador de la guía de visualización:
 *  #1B5C8F / #5BA9D6 / #178A52 superan banda de luminosidad, suelo de croma,
 *  separación CVD, piso de visión normal y contraste sobre blanco. */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ReactNode } from 'react'

export const SERIES = {
  recibidos: '#1B5C8F',
  procesados: '#5BA9D6',
  decodificados: '#178A52',
} as const

const EJE = { stroke: '#D8E0E7', tick: { fill: '#607080', fontSize: 11 } }

/* ── Tooltip común ────────────────────────────────────────────────────────── */

function CajaTooltip({ titulo, filas }: { titulo: string; filas: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 shadow-lg">
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

export function GraficaFrames({ datos, alto = 300 }: { datos: PuntoSerie[]; alto?: number }) {
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <LineChart data={datos} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
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
          width={44}
          label={{
            value: 'Frames',
            angle: -90,
            position: 'insideLeft',
            offset: 16,
            style: { fill: '#607080', fontSize: 11 },
          }}
        />
        <Tooltip
          cursor={{ stroke: '#607080', strokeWidth: 1, strokeDasharray: '3 3' }}
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
        <Line
          type="monotone"
          dataKey="recibidos"
          name="Recibidos"
          stroke={SERIES.recibidos}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }}
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
          activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }}
        />
        <Line
          type="monotone"
          dataKey="decodificados"
          name="Decodificados"
          stroke={SERIES.decodificados}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }}
        />
      </LineChart>
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
}) {
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <BarChart data={datos} margin={{ top: 8, right: 12, bottom: etiquetaX ? 20 : 4, left: -8 }}>
        <CartesianGrid vertical={false} strokeDasharray="0" />
        <XAxis
          dataKey={claveX}
          axisLine={{ stroke: EJE.stroke }}
          tickLine={false}
          tick={EJE.tick}
          minTickGap={12}
          label={
            etiquetaX
              ? { value: etiquetaX, position: 'insideBottom', offset: -12, style: { fill: '#607080', fontSize: 11 } }
              : undefined
          }
        />
        <YAxis
          axisLine={false}
          tickLine={false}
          tick={EJE.tick}
          allowDecimals={false}
          width={44}
          label={
            etiquetaY
              ? { value: etiquetaY, angle: -90, position: 'insideLeft', offset: 16, style: { fill: '#607080', fontSize: 11 } }
              : undefined
          }
        />
        <Tooltip
          cursor={{ fill: '#EAF3F8' }}
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
            datos.map((_, i) => <Cell key={i} fill={colores[i % colores.length]} />)}
        </Bar>
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
