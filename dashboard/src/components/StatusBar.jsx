export default function StatusBar({ status, config, conectado, ocupado, simular }) {
  const link = status?.link_status || 'OFFLINE'
  const sim = status?.sim_status || 'IDLE'
  const enMarcha = sim === 'RUNNING'

  const claseLink = link === 'ACTIVE' ? 'verde' : 'rojo'
  const claseSim = enMarcha ? 'ambar' : sim === 'STOPPED' ? 'verde' : 'gris'

  return (
    <header className="barra-superior">
      <div className="marca">
        <div className="marca-titulo">
          STRAND-1 <span className="marca-sub">Ground Station · NORAD 39090</span>
        </div>
        <div className="marca-sub2">Monitoreo del enlace RF simulado (GNU Radio → FastAPI → WebSocket)</div>
      </div>

      <div className="estado-chips">
        <span className={`chip chip-${claseLink}`}>
          <span className="dot" /> Enlace: {link}
        </span>
        <span className={`chip chip-${claseSim}`}>
          <span className="dot" /> Simulación: {sim}
        </span>
        <span className={`chip ${conectado ? 'chip-verde' : 'chip-rojo'}`}>
          <span className="dot" /> WebSocket: {conectado ? 'conectado' : 'desconectado'}
        </span>
      </div>

      <div className="controles">
        <button
          className="btn btn-primario"
          disabled={enMarcha || ocupado}
          onClick={() => simular('start')}
        >
          ▶ Iniciar simulación
        </button>
        <button className="btn" disabled={!enMarcha || ocupado} onClick={() => simular('stop')}>
          ■ Detener
        </button>
        <button className="btn" disabled={ocupado} onClick={() => simular('reset')}>
          ↺ Reset
        </button>
        {config && (
          <span className="config-ref">
            {config.modulacion} · {config.frecuencia_hz / 1e6} MHz ·{' '}
            {(config.tasa_bits_bps / 1000).toFixed(1)} kbps · SNR {config.snr_min_db}–
            {config.snr_max_db} dB
          </span>
        )}
      </div>
    </header>
  )
}