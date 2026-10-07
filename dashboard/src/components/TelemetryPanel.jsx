import Metrica, { formatearNumero } from './Metrica.jsx'

function tonoPara(param) {
  if (!param.disponible) return 'gris'
  if (param.status === 'ALERTA') return 'rojo'
  if (param.status === 'NORMAL' || param.status === 'OK') return 'ok'
  return 'gris'
}

export default function TelemetryPanel({ telemetry }) {
  const t = telemetry || {}
  const parametros = t.parametros || []

  return (
    <section className="panel">
      <h2 className="panel-titulo">
        Telemetría decodificada{' '}
        <span className="etiqueta-ref">{t.total_frames ?? 0} balizas AMSAT</span>
      </h2>
      {t.nota && <div className="fuente">{t.nota}</div>}
      <div className="malla-metricas">
        {parametros.map((p) => (
          <Metrica
            key={p.key}
            etiqueta={p.label}
            valor={formatearNumero(p.value, 3)}
            unidad={p.unit}
            tono={tonoPara(p)}
          />
        ))}
      </div>
      <h3 className="sub-titulo">Últimas balizas recibidas</h3>
      <div className="tabla-scroll">
        <table className="tabla">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Estación</th>
              <th>Bytes</th>
              <th>Payload</th>
              <th>Decodificada</th>
            </tr>
          </thead>
          <tbody>
            {(t.frames || []).slice(0, 10).map((f, idx) => (
              <tr key={idx}>
                <td>{f.timestamp || '—'}</td>
                <td>{f.observer || '—'}</td>
                <td>{f.tamano_bytes ?? '—'}</td>
                <td className="mono">{f.hex || '—'}</td>
                <td>{f.decodificado ? 'sí' : 'no'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}