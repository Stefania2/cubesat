import { useDash } from './ws.js'
import StatusBar from './components/StatusBar.jsx'
import MetricsPanel from './components/MetricsPanel.jsx'
import BitIntegrityPanel from './components/BitIntegrityPanel.jsx'
import SpectrumChart from './components/SpectrumChart.jsx'
import ConstellationChart from './components/ConstellationChart.jsx'
import HistoryChart from './components/HistoryChart.jsx'
import TelemetryPanel from './components/TelemetryPanel.jsx'
import LogPanel from './components/LogPanel.jsx'

export default function App() {
  const { state, error, ocupado, simular } = useDash()
  const { status, metrics, integrity, telemetry, spectrum, constellation, config, history, logs, conectado } = state

  return (
    <div className="app">
      <StatusBar
        status={status}
        config={config}
        conectado={conectado}
        ocupado={ocupado}
        simular={simular}
      />

      {error && <div className="banner-error">{error}</div>}

      <main className="contenido">
        <section className="fila">
          <MetricsPanel metrics={metrics} status={status} />
        </section>
        <section className="fila">
          <BitIntegrityPanel integridad={integrity} />
        </section>
        <section className="fila dos-columnas">
          <SpectrumChart spectrum={spectrum} />
          <ConstellationChart constellation={constellation} />
        </section>
        <section className="fila">
          <HistoryChart history={history} config={config} />
        </section>
        <section className="fila">
          <TelemetryPanel telemetry={telemetry} />
        </section>
        <section className="fila dos-columnas">
          <LogPanel logs={logs} mensaje={status?.mensaje} />
        </section>
      </main>

      <footer className="pie">
        STRAND-1 Ground Station · Enlace RF simulado en GNU Radio 3.10 · Los valores son
        resultado real de la cadena y del decodificador AMSAT (nada se inventa; RSSI/FER se
        muestran como N/A porque el modelo es baseband-equivalente).
      </footer>
    </div>
  )
}