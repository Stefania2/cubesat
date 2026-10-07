export default function Metrica({ etiqueta, valor, unidad, nota, tono = 'ok' }) {
  return (
    <div className={`tarjeta metrica tono-${tono}`}>
      <div className="metrica-etiqueta">{etiqueta}</div>
      <div className="metrica-valor">
        {valor === null || valor === undefined ? '—' : valor}
        {unidad != null && <span className="metrica-unidad">{unidad}</span>}
      </div>
      {nota && <div className="metrica-nota">{nota}</div>}
    </div>
  )
}

export function formatearNumero(v, decimales = 4) {
  if (v === null || v === undefined) return null
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return v.toLocaleString('es-CO')
    return v.toFixed(decimales)
  }
  return v
}