import Metrica, { formatearNumero } from './Metrica.jsx'

export default function MetricsPanel({ metrics, status }) {
  const m = metrics || {}
  const tonoBer =
    m.ber === null ? 'gris'
    : m.ber === 0 ? 'ok'
    : m.ber < 1e-2 ? 'ok'
    : m.ber < 1e-1 ? 'ambar'
    : 'rojo'

  return (
    <section className="panel">
      <h2 className="panel-titulo">Métricas del enlace RF</h2>
      <div className="malla-metricas">
        <Metrica etiqueta="SNR configurada" valor={formatearNumero(m.snr_db, 1)} unidad="dB" />
        <Metrica
          etiqueta="BER medido (empírico)"
          valor={formatearNumero(m.ber, 6)}
          tono={tonoBer}
        />
        <Metrica
          etiqueta="RSSI"
          valor={formatearNumero(m.rssi_dbm, 1)}
          unidad="dBm"
          nota={m.nota_rssi}
          tono="gris"
        />
        <Metrica
          etiqueta="FER"
          valor={formatearNumero(m.fer)}
          nota={m.nota_fer}
          tono="gris"
        />
        <Metrica
          etiqueta="Potencia relativa (tap IQ)"
          valor={formatearNumero(m.potencia_relativa_dbfs, 1)}
          unidad="dBFs"
          nota="Media de |I+jQ|² del canal tras AWGN"
        />
        <Metrica
          etiqueta="Ruido fuera de banda (Welch)"
          valor={formatearNumero(m.ruido_estimado, 1)}
          unidad="dB"
          nota="Potencia media de ruido fuera de la banda RRC"
        />
      </div>
      <div className="notas-config">
        <span title={m.nota_frecuencia}>{m.nota_frecuencia}</span>
        <span title={m.nota_ancho_banda}>{m.nota_ancho_banda}</span>
        <span>
          Tramas: recibidas {status?.frames_received ?? '—'} · válidas{' '}
          {status?.frames_valid ?? '—'} · error {status?.frames_error ?? '—'}
        </span>
      </div>
    </section>
  )
}