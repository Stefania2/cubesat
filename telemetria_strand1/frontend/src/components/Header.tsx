import { NavLink } from 'react-router-dom'
import { useState } from 'react'
import { StatusDot } from './ui'
import type { Status } from '../lib/api'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/observations', label: 'Observations' },
  { to: '/telemetry', label: 'Telemetry' },
  { to: '/simulacion', label: 'Simulación RF' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/advanced', label: 'Advanced' },
  { to: '/gemelo', label: 'Gemelo digital' },
  { to: '/docs', label: 'Docs' },
]

function Logo() {
  return (
    <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-navy text-[13px] font-bold tracking-tight text-white">
      RF
    </div>
  )
}

export function Header({ status }: { status: Status | null }) {
  const [abierto, setAbierto] = useState(false)
  const activo = status !== null

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-white">
      <div className="mx-auto flex max-w-[1400px] items-center gap-4 px-4 py-3 sm:px-6">
        <NavLink to="/" className="flex items-center gap-3" onClick={() => setAbierto(false)}>
          <Logo />
          <div className="leading-tight">
            <div className="text-[15px] font-bold tracking-tight text-navy-dark">
              STRAND-1 TELEMETRY
            </div>
            <div className="hidden text-[11px] text-ink-soft sm:block">
              Satellite Telemetry Analysis &amp; Monitoring
            </div>
          </div>
        </NavLink>

        <nav className="ml-auto hidden items-center gap-0.5 lg:flex">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-navy text-white'
                    : 'text-ink-soft hover:bg-blue-light hover:text-navy'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3 lg:ml-4">
          <div className="hidden items-center gap-1.5 sm:flex">
            <StatusDot tono={activo ? 'normal' : 'critical'} />
            <span
              className={`text-[11px] font-semibold tracking-wide ${
                activo ? 'text-ok' : 'text-danger'
              }`}
            >
              {activo ? 'SYSTEM ACTIVE' : 'API OFFLINE'}
            </span>
          </div>
          <div className="hidden rounded-md border border-line bg-blue-lighter px-2.5 py-1 text-[11px] font-semibold text-navy md:block">
            NORAD {status?.norad_id ?? 39090}
          </div>

          <button
            className="rounded-md border border-line p-2 lg:hidden"
            onClick={() => setAbierto((v) => !v)}
            aria-label="Abrir navegación"
            aria-expanded={abierto}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      </div>

      {abierto && (
        <nav className="border-t border-line bg-white px-4 py-2 lg:hidden">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setAbierto(false)}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium ${
                  isActive ? 'bg-navy text-white' : 'text-ink-soft'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  )
}
