import { useNavigate } from 'react-router-dom'
import { Button, StatusDot } from './ui'
import { frecuenciaMHz } from '../lib/format'
import type { Status } from '../lib/api'

/** Ilustración minimalista de un CubeSat 3U con paneles desplegados. */
function CubeSatIcon() {
  return (
    <svg viewBox="0 0 120 80" className="h-16 w-auto" role="img" aria-label="CubeSat 3U">
      <g fill="none" stroke="#1B5C8F" strokeWidth="1.6" strokeLinejoin="round">
        <rect x="48" y="24" width="24" height="32" rx="2" fill="#EAF3F8" />
        <path d="M48 32h24M48 40h24M48 48h24" strokeWidth="1" stroke="#9FBDD4" />
        <path d="M48 30 L18 22 L18 44 L48 52" fill="#F4F8FB" />
        <path d="M72 30 L102 22 L102 44 L72 52" fill="#F4F8FB" />
        <path d="M24 26v16M32 28v14M40 30v12" strokeWidth="0.9" stroke="#9FBDD4" />
        <path d="M96 26v16M88 28v14M80 30v12" strokeWidth="0.9" stroke="#9FBDD4" />
        <path d="M60 24V12" strokeLinecap="round" />
        <circle cx="60" cy="10" r="2.5" fill="#178A52" stroke="#178A52" />
      </g>
    </svg>
  )
}

function Dato({ etiqueta, valor, tono }: { etiqueta: string; valor: string; tono?: string }) {
  return (
    <div className="border-t border-line py-2.5 first:border-t-0 first:pt-0">
      <div className="label-caps">{etiqueta}</div>
      <div
        className={`mt-0.5 flex items-center gap-1.5 text-sm font-semibold tnum ${
          tono === 'ok' ? 'text-ok' : 'text-navy-dark'
        }`}
      >
        {tono === 'ok' && <StatusDot tono="normal" />}
        {valor}
      </div>
    </div>
  )
}

export function Hero({ status }: { status: Status | null }) {
  const navigate = useNavigate()

  return (
    <section className="mb-10 grid gap-6 lg:grid-cols-[1.35fr_1fr] lg:gap-10">
      <div className="flex flex-col justify-center">
        <span className="mb-4 inline-flex w-fit items-center gap-2 rounded-full border border-line bg-white px-3 py-1 text-[11px] font-semibold tracking-wide text-navy">
          STRAND-1 • NORAD {status?.norad_id ?? 39090}
        </span>
        <h1 className="text-3xl font-bold leading-[1.15] tracking-tight text-navy-dark sm:text-4xl lg:text-[2.75rem]">
          Telemetría y análisis de datos de STRAND-1
        </h1>
        <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
          Plataforma para la recopilación, procesamiento, decodificación y análisis histórico
          de telemetría obtenida mediante observaciones de la red SatNOGS.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Button onClick={() => navigate('/telemetry')}>Explorar telemetría</Button>
          <Button variante="secondary" onClick={() => navigate('/observations')}>
            Ver observaciones
          </Button>
        </div>
      </div>

      <div className="card p-6">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-navy-dark">STRAND-1</h2>
            <p className="mt-0.5 text-xs text-ink-soft">
              Surrey Training, Research and Nanosatellite Demonstrator
            </p>
          </div>
          <CubeSatIcon />
        </div>
        <div className="grid gap-0 sm:grid-cols-2 sm:gap-x-6">
          <Dato etiqueta="NORAD ID" valor={String(status?.norad_id ?? 39090)} />
          <Dato etiqueta="Transmitter" valor="UHF 9k6 FSK TLM" />
          <Dato etiqueta="Frequency" valor={frecuenciaMHz(437_568_000)} />
          <Dato etiqueta="Mode" valor="FSK 9600" />
          <Dato etiqueta="Status" valor="ACTIVE" tono="ok" />
          <Dato
            etiqueta="Frames en base"
            valor={status ? status.frames.toLocaleString('es-ES') : '—'}
          />
        </div>
      </div>
    </section>
  )
}
