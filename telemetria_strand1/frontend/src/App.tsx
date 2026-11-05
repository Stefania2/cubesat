import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Header } from './components/Header'
import { Dashboard } from './pages/Dashboard'
import { Observations } from './pages/Observations'
import { Telemetry } from './pages/Telemetry'
import { EnlaceRF } from './pages/EnlaceRF'
import { Simulacion } from './pages/Simulacion'
import { Analytics } from './pages/Analytics'
import { Advanced } from './pages/Advanced'
import { Docs } from './pages/Docs'
import { api, useApi } from './lib/api'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Error capturado en una pagina:', error, info.componentStack)
  }
  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-2xl rounded-lg border border-line bg-panel p-8 text-center">
          <h2 className="mb-2 text-xl font-semibold text-ink">Algo salió mal en esta página</h2>
          <p className="mb-4 text-sm text-ink-soft">
            Recarga con Ctrl+Shift+R. Si persiste, el error fue:
          </p>
          <pre className="overflow-auto rounded bg-blue-lighter p-3 text-left text-xs text-danger">
            {String(this.state.error?.message || this.state.error)}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}

/** /salud?seccion=eps lleva al inicio conservando la sección elegida. */
function RedirigirSalud() {
  const { search } = useLocation()
  return <Navigate to={{ pathname: '/', search, hash: '#salud' }} replace />
}

function Footer() {
  return (
    <footer className="mt-12 border-t border-line bg-panel">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-5 text-xs text-ink-soft sm:px-6">
        <span>
          STRaND-1 · Telemetría · Datos de la red SatNOGS · NORAD 39090
        </span>
        <span>
          Cuando un dato no existe, la plataforma lo dice: nunca se inventa.
        </span>
      </div>
    </footer>
  )
}

export default function App() {
  const { data: status } = useApi(() => api.status(), [])

  return (
    <BrowserRouter>
      <div className="flex min-h-screen flex-col">
        <Header status={status} />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-6 sm:py-10">
          <Routes>
            <Route path="/" element={<Dashboard status={status} />} />
            <Route path="/observations" element={<Observations />} />
            <Route path="/telemetry" element={<Telemetry />} />
            <Route path="/enlace" element={<ErrorBoundary><EnlaceRF /></ErrorBoundary>} />
            <Route path="/simulacion" element={<Simulacion />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/advanced" element={<Advanced />} />
            {/* El gemelo y la salud viven ahora en el inicio; los enlaces antiguos siguen valiendo. */}
            <Route path="/gemelo" element={<Navigate to={{ pathname: '/', hash: '#gemelo' }} replace />} />
            <Route path="/salud" element={<RedirigirSalud />} />
            <Route path="/docs" element={<Docs />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}
