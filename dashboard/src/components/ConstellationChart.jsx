import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

export default function ConstellationChart({ constellation }) {
  if (!constellation || !constellation.disponible) {
    return (
      <section className="panel">
        <h2 className="panel-titulo">Constelación BPSK (tap a tasa de símbolo)</h2>
        <div className="vacio">{constellation?.nota || 'Sin constelación todavía.'}</div>
      </section>
    )
  }
  const datos = constellation.puntos || []

  return (
    <section className="panel">
      <h2 className="panel-titulo">Constelación BPSK (tap a tasa de símbolo)</h2>
      <div className="fuente">{constellation.fuente}</div>
      <div className="grafico">
        <ResponsiveContainer width="100%" height={220}>
          <ScatterChart margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1f2b3a" strokeDasharray="3 3" />
            <XAxis
              type="number"
              dataKey="i"
              domain={['dataMin - 0.15', 'dataMax + 0.15']}
              tickCount={7}
              tick={{ fill: '#8aa4c0', fontSize: 11 }}
              label={{ value: 'I', position: 'insideBottom', fill: '#d7e3f0', offset: -2 }}
            />
            <YAxis
              type="number"
              dataKey="q"
              domain={['dataMin - 0.15', 'dataMax + 0.15']}
              tickCount={7}
              tick={{ fill: '#8aa4c0', fontSize: 11 }}
              width={48}
              label={{ value: 'Q', angle: -90, position: 'insideLeft', fill: '#d7e3f0', offset: 8 }}
            />
            <Tooltip
              contentStyle={{ background: '#0d1520', border: '1px solid #22313f' }}
              labelStyle={{ color: '#d7e3f0' }}
              formatter={(v) => [v.toFixed(4), '']}
            />
            <ReferenceLine x={0} stroke="#3a6ea5" strokeDasharray="4 4" />
            <ReferenceLine y={0} stroke="#3a6ea5" strokeDasharray="4 4" />
            <Scatter
              data={datos}
              fill="#3fb950"
              fillOpacity={0.55}
              stroke="none"
              isAnimationActive={false}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}