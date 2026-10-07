export default function LogPanel({ logs, mensaje }) {
  const entradas = [...(logs || [])].reverse()

  return (
    <section className="panel">
      <h2 className="panel-titulo">Log de la simulación</h2>
      {mensaje && <div className="mensaje">{mensaje}</div>}
      <div className="tabla-scroll">
        <table className="tabla">
          <thead>
            <tr>
              <th>Tiempo</th>
              <th>Nivel</th>
              <th>Mensaje</th>
            </tr>
          </thead>
          <tbody>
            {(entradas.length ? entradas : [{ timestamp: null, nivel: '—', mensaje: 'Sin eventos todavía.' }]).map(
              (e, idx) => (
                <tr key={idx}>
                  <td>{e.timestamp || '—'}</td>
                  <td>{e.nivel || '—'}</td>
                  <td className="mono">{e.mensaje || '—'}</td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}