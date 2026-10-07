import { formatearNumero } from './Metrica.jsx'

export default function BitIntegrityPanel({ integridad }) {
  const i = integridad || {}
  const valido = i.valido === true
  const tono = valido ? 'green' : 'red'

  return (
    <section className="panel">
      <h2 className="panel-titulo">
        Integridad de bits{' '}
        <span className={`etiqueta-estado etiqueta-${tono}`}>
          {valido ? 'IDENTICOS' : 'DISCREPANCIA'}
        </span>
      </h2>
      <div className="integridad-grid">
        <div className="stat">
          <div className="stat-valor">{formatearNumero(i.bits_entrada)}</div>
          <div className="stat-etiqueta">bits de entrada</div>
        </div>
        <div className="stat">
          <div className="stat-valor">{formatearNumero(i.bits_recuperados)}</div>
          <div className="stat-etiqueta">bits recuperados</div>
        </div>
        <div className="stat">
          <div className={`stat-valor ${i.diferencia === 0 ? '' : 'stat-alerta'}`}>
            {i.diferencia ?? '—'}
          </div>
          <div className="stat-etiqueta">diferencia por bit</div>
        </div>
        <div className="stat">
          <div className="stat-valor">{i.frames_esperados ?? '—'}</div>
          <div className="stat-etiqueta">tramas esperadas (100 × 2347 B)</div>
        </div>
      </div>
      <div className="mono">
        <div>SHA-256 entrada: {i.sha256_entrada}</div>
        <div>SHA-256 salida:  {i.sha256_recuperado}</div>
      </div>
      {i.mensaje && <div className="mensaje">{i.mensaje}</div>}
    </section>
  )
}