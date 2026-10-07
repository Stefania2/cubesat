import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'

export default function SpectrumChart({ spectrum }) {
  if (!spectrum || !spectrum.disponible) {
    return (
      <section className="panel">
        <h2 className="panel-titulo">Espectro (FFT Welch · tap IQ real)</h2>
        <div className="vacio">{spectrum?.nota || 'Sin datos de espectro todavía.'}</div>
      </section>
    )
  }
  const datos = spectrum.datos || []
  const paso = Math.max(1, Math.floor(datos.length / 600))
  const sub = datos.filter((_, i) => i % paso === 0)

  return (
    <section className="panel">
      <h2 className="panel-titulo">Espectro (FFT Welch · tap IQ real)</h2>
      <div className="fuente">{spectrum.fuente}</div>
      <div className="grafico">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={sub} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1f2b3a" strokeDasharray="3 3" />
            <XAxis
              dataKey="freq_hz"
              tick={{ fill: '#8aa4c0', fontSize: 11 }}
              tickFormatter={(v) => `${(v / 1000).toFixed(1)} kHz`}
              domain={['dataMin', 'dataMax']}
              tickCount={9}
            />
            <YAxis
              tick={{ fill: '#8aa4c0', fontSize: 11 }}
              tickFormatter={(v) => `${v.toFixed(0)} dB`}
              domain={['dataMin - 4', 'dataMax + 2']}
              width={54}
            />
            <Tooltip
              contentStyle={{ background: '#0d1520', border: '1px solid #22313f' }}
              labelStyle={{ color: '#d7e3f0' }}
              formatter={(v) => [`${v.toFixed(2)} dB`, 'Potencia']}
              labelFormatter={(v) => `${(v / 1000).toFixed(2)} kHz`}
            />
            <ReferenceLine x={0} stroke="#3a6ea5" strokeDasharray="4 4" />
            <ReferenceLine
              x={-spectrum.ancho_banda_hz / 2}
              stroke="#5a4a8a"
              strokeDasharray="4 4"
            />
            <ReferenceLine x={spectrum.ancho_banda_hz / 2} stroke="#5a4a8a" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="power_db"
              stroke="#3fb950"
              dot={false}
              strokeWidth={1.4}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="nota-banda">
        BW de análisis {spectrum.ancho_banda_hz / 1000} kHz · señal baseband centrada en 0 Hz
      </div>
    </section>
  )
}