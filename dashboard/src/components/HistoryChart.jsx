import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

export default function HistoryChart({ history, config }) {
  const datos = (history || []).slice()
  if (!datos.length) {
    return (
      <section className="panel">
        <h2 className="panel-titulo">BER medido vs SNR (historial de la sesión)</h2>
        <div className="vacio">
          Sin puntos todavía. Ejecuta una simulación para registrar BER medido por SNR.
        </div>
      </section>
    )
  }

  return (
    <section className="panel">
      <h2 className="panel-titulo">BER medido vs SNR (historial de la sesión)</h2>
      <div className="grafico">
        <ResponsiveContainer width="100%" height={220}>
          <ScatterChart margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1f2b3a" strokeDasharray="3 3" />
            <XAxis
              type="number"
              dataKey="snr_db"
              name="SNR"
              unit=" dB"
              tick={{ fill: '#8aa4c0', fontSize: 11 }}
              domain={[config?.snr_min_db ?? 'dataMin', config?.snr_max_db ?? 'dataMax']}
              tickCount={8}
            />
            <YAxis
              type="number"
              dataKey="ber"
              name="BER"
              scale="log"
              domain={[1e-6, 1]}
              allowDataOverflow
              tick={{ fill: '#8aa4c0', fontSize: 11 }}
              tickFormatter={(v) => (v === 0 ? '0' : v.toExponential(0))}
              width={54}
            />
            <Tooltip
              contentStyle={{ background: '#0d1520', border: '1px solid #22313f' }}
              labelStyle={{ color: '#d7e3f0' }}
              formatter={(v, nombre) => {
                if (nombre === 'ber')
                  return [v === 0 ? 0 : v.toExponential(3), 'BER medido']
                return [v, 'SNR']
              }}
              labelFormatter={() => ''}
            />
            <Scatter data={datos} fill="#d29922" isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}