/** Utilidades de formato. Todo se muestra en UTC: es la convención de SatNOGS. */

/** Zona horaria explícita al final de la cadena: `Z`, `+HH:MM` o `-HH:MM`. */
const CON_ZONA = /(?:Z|[+-]\d{2}:?\d{2})$/

/**
 * Convierte una marca de tiempo de la API a `Date`.
 *
 * Solo añade la `Z` cuando la cadena viene sin zona horaria. Comprobar
 * únicamente `+` dejaba fuera los desfases negativos y producía cadenas como
 * `2026-02-20T22:20:49-05:00Z`, que dan `Invalid Date`.
 */
function aDate(iso: string): Date {
  return new Date(CON_ZONA.test(iso) ? iso : `${iso}Z`)
}

export function fechaUTC(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = aDate(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toISOString().slice(0, 10)
}

export function horaUTC(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = aDate(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.toISOString().slice(11, 19)} UTC`
}

export function fechaHoraUTC(iso: string | null | undefined): string {
  if (!iso) return '—'
  return `${fechaUTC(iso)} ${horaUTC(iso)}`
}

/** Agrupa el hexadecimal en pares separados por espacio, como un volcado. */
export function hexLegible(hex: string, porLinea = 0): string {
  const pares = hex.toUpperCase().match(/.{1,2}/g) ?? []
  if (porLinea <= 0) return pares.join(' ')
  const lineas: string[] = []
  for (let i = 0; i < pares.length; i += porLinea) {
    lineas.push(pares.slice(i, i + porLinea).join(' '))
  }
  return lineas.join('\n')
}

export function truncarHex(hex: string, maxBytes = 8): string {
  const pares = hex.toUpperCase().match(/.{1,2}/g) ?? []
  if (pares.length <= maxBytes) return pares.join(' ')
  return `${pares.slice(0, maxBytes).join(' ')} …`
}

export function numero(n: number | null | undefined, decimales = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toLocaleString('es-ES', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })
}

/**
 * Magnitud medida, con cifras significativas en lugar de decimales fijos.
 *
 * Las ecuaciones de calibración de AMSAT-UK devuelven el float completo
 * (`6.308999999999999`, `-0.17226880700002312`), que en una tabla de resultados
 * es ruido de coma flotante, no precisión: la cuenta ADC de origen tiene 10 bits.
 * Se recortan a cuatro cifras significativas, que ya cubren de sobra esa
 * resolución, y los enteros grandes se dejan intactos porque son cuentas crudas.
 */
export function magnitud(n: number | null | undefined, significativas = 4): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  if (Number.isInteger(n)) return n.toLocaleString('es-ES')
  const abs = Math.abs(n)
  // Decimales necesarios para dejar `significativas` cifras, acotado a [0, 6].
  const decimales = Math.min(6, Math.max(0, significativas - 1 - Math.floor(Math.log10(abs))))
  return Number(n.toFixed(decimales)).toLocaleString('es-ES', {
    maximumFractionDigits: decimales,
  })
}

export function frecuenciaMHz(hz: number | null | undefined): string {
  if (!hz) return '—'
  return `${(hz / 1e6).toFixed(4)} MHz`
}

/** Etiqueta legible para el eje X según la granularidad del backend. */
export function etiquetaBucket(bucket: string, granularidad: string): string {
  if (granularidad === 'hora') return `${bucket.slice(11, 13)}:00`
  if (granularidad === 'dia') return bucket.slice(5)
  return bucket
}
