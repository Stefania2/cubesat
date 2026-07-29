import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Header } from './components/Header'
import { Dashboard } from './pages/Dashboard'
import { Observations } from './pages/Observations'
import { Telemetry } from './pages/Telemetry'
import { Simulacion } from './pages/Simulacion'
import { Analytics } from './pages/Analytics'
import { Advanced } from './pages/Advanced'
import { Docs } from './pages/Docs'
import { api, useApi } from './lib/api'

function Footer() {
  return (
    <footer className="mt-12 border-t border-line bg-white">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-5 text-xs text-ink-soft sm:px-6">
        <span>
          STRAND-1 Telemetry · Datos de la red SatNOGS · NORAD 39090
        </span>
        <span>
          Los parámetros sin protocolo validado se muestran como «Not decoded», nunca estimados.
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
            <Route path="/simulacion" element={<Simulacion />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/advanced" element={<Advanced />} />
            <Route path="/docs" element={<Docs />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}
