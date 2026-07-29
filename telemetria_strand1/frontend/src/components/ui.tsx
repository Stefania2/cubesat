/** Componentes base del sistema de diseño. */

import type { ReactNode } from 'react'

/* ── Tarjeta ──────────────────────────────────────────────────────────────── */

export function Card({
  children,
  className = '',
  padding = true,
}: {
  children: ReactNode
  className?: string
  padding?: boolean
}) {
  return (
    <div className={`card ${padding ? 'p-5 sm:p-6' : ''} ${className}`}>{children}</div>
  )
}

export function CardHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="text-base font-semibold text-navy-dark">{title}</h3>
        {description && <p className="mt-1 text-sm text-ink-soft">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

/* ── Sección de página ────────────────────────────────────────────────────── */

export function Section({
  title,
  description,
  children,
  actions,
}: {
  title: string
  description?: string
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <section className="mb-10">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-navy-dark sm:text-2xl">
            {title}
          </h2>
          {description && (
            <p className="mt-1.5 max-w-3xl text-sm text-ink-soft">{description}</p>
          )}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  )
}

/* ── Badges de estado ─────────────────────────────────────────────────────── */

const ESTILOS_BADGE: Record<string, string> = {
  decoded: 'bg-ok-bg text-ok border-ok/25',
  // «Medido» no es un grado menor de «decodificado»: es otra capa. Un valor
  // medido sale de los bytes recibidos sin suponer ningún formato, así que se
  // distingue en color de los que dependen de un protocolo validado.
  measured: 'bg-blue-light text-blue border-blue/20',
  partially_decoded: 'bg-warn-bg text-warn border-warn/25',
  unclassified: 'bg-slate-100 text-slate-600 border-slate-300',
  not_decoded: 'bg-slate-100 text-slate-600 border-slate-300',
  not_available: 'bg-slate-100 text-slate-600 border-slate-300',
  error: 'bg-danger-bg text-danger border-danger/25',
  critical: 'bg-danger-bg text-danger border-danger/25',
  warning: 'bg-warn-bg text-warn border-warn/25',
  normal: 'bg-ok-bg text-ok border-ok/25',
  info: 'bg-blue-light text-blue border-blue/20',
}

const ETIQUETAS: Record<string, string> = {
  decoded: 'Decoded',
  measured: 'Medido',
  partially_decoded: 'Partially Decoded',
  unclassified: 'Unclassified',
  not_decoded: 'Not decoded',
  not_available: 'Not available',
  error: 'Error',
  critical: 'Critical',
  warning: 'Warning',
  normal: 'Normal',
}

export function Badge({
  tono = 'info',
  children,
  icono,
}: {
  tono?: keyof typeof ESTILOS_BADGE | string
  children?: ReactNode
  icono?: ReactNode
}) {
  const estilo = ESTILOS_BADGE[tono] ?? ESTILOS_BADGE.info
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium ${estilo}`}
    >
      {icono}
      {children ?? ETIQUETAS[tono] ?? tono}
    </span>
  )
}

/** Punto de estado. Nunca va solo: siempre acompañado de su etiqueta de texto,
 *  de modo que el estado no dependa únicamente del color. */
export function StatusDot({ tono = 'normal' }: { tono?: string }) {
  const color =
    tono === 'critical' || tono === 'error'
      ? 'bg-danger'
      : tono === 'warning'
        ? 'bg-warn'
        : tono === 'muted'
          ? 'bg-slate-400'
          : 'bg-ok'
  return <span className={`inline-block size-2 shrink-0 rounded-full ${color}`} aria-hidden />
}

/* ── Botones ──────────────────────────────────────────────────────────────── */

type VarianteBoton = 'primary' | 'secondary' | 'ghost'

const ESTILOS_BOTON: Record<VarianteBoton, string> = {
  primary:
    'bg-navy text-white border-navy hover:bg-navy-dark hover:border-navy-dark',
  secondary:
    'bg-white text-navy border-navy hover:bg-blue-light',
  ghost:
    'bg-white text-ink-soft border-line hover:border-navy hover:text-navy',
}

export function Button({
  variante = 'primary',
  children,
  className = '',
  ...props
}: {
  variante?: VarianteBoton
  children: ReactNode
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${ESTILOS_BOTON[variante]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function LinkButton({
  variante = 'ghost',
  children,
  className = '',
  ...props
}: {
  variante?: VarianteBoton
  children: ReactNode
} & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      className={`inline-flex items-center justify-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${ESTILOS_BOTON[variante]} ${className}`}
      {...props}
    >
      {children}
    </a>
  )
}

/* ── Pestañas ─────────────────────────────────────────────────────────────── */

export function Tabs<T extends string>({
  opciones,
  valor,
  onChange,
}: {
  opciones: { valor: T; etiqueta: string }[]
  valor: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist">
      {opciones.map((o) => {
        const activo = o.valor === valor
        return (
          <button
            key={o.valor}
            role="tab"
            aria-selected={activo}
            onClick={() => onChange(o.valor)}
            className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
              activo
                ? 'border-navy bg-navy text-white'
                : 'border-line bg-white text-navy hover:border-navy'
            }`}
          >
            {o.etiqueta}
          </button>
        )
      })}
    </div>
  )
}

/* ── Estados de carga, error y vacío ──────────────────────────────────────── */

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

export function ErrorState({ mensaje, onReintentar }: { mensaje: string; onReintentar?: () => void }) {
  return (
    <div className="rounded-lg border border-danger/25 bg-danger-bg p-5">
      <div className="flex items-start gap-3">
        <StatusDot tono="critical" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-danger">No se pudieron cargar los datos</p>
          <p className="mt-1 break-words text-sm text-ink-soft">{mensaje}</p>
          <p className="mt-2 text-xs text-ink-soft">
            Comprueba que el backend esté en marcha:{' '}
            <code className="font-mono">uvicorn app.main:app --reload</code>
          </p>
        </div>
        {onReintentar && (
          <Button variante="secondary" onClick={onReintentar}>
            Reintentar
          </Button>
        )}
      </div>
    </div>
  )
}

export function EmptyState({ titulo, descripcion }: { titulo: string; descripcion?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-blue-lighter px-6 py-10 text-center">
      <p className="text-sm font-semibold text-navy-dark">{titulo}</p>
      {descripcion && (
        <p className="mx-auto mt-1.5 max-w-md text-sm text-ink-soft">{descripcion}</p>
      )}
    </div>
  )
}

/** Aviso metodológico. Se usa allí donde la aplicación deja de tener datos y
 *  debe decirlo en lugar de rellenar el hueco. */
export function Nota({ children, tono = 'info' }: { children: ReactNode; tono?: string }) {
  const estilos =
    tono === 'warning'
      ? 'border-warn/25 bg-warn-bg'
      : 'border-blue/20 bg-blue-light'
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm text-ink ${estilos}`}>
      {children}
    </div>
  )
}
