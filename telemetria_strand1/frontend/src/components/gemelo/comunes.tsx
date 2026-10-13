/** Piezas compartidas por los paneles del gemelo: formato, sellos y filas. */

import type { LecturaGemelo, ValidacionLectura } from '../../lib/api'
import { CLASE } from '../../data/referenciaStrand1'
import type { ClaseDato } from '../../data/referenciaStrand1'

/* ── Nombres legibles de los campos de la baliza ──────────────────────────── */

const EJE: Record<string, string> = { px: '+X', mx: '−X', py: '+Y', my: '−Y', pz: '+Z', mz: '−Z' }

const NOMBRES: Record<string, string> = {
  battery_voltage: 'Tensión de batería (0 y 1)',
  battery_0_voltage: 'Tensión de batería 0',
  battery_1_voltage: 'Tensión de batería 1',
  obc_uptime: 'OBC: tiempo desde el arranque',
  obc_unix_time: 'OBC: reloj (campo original)',
  magnetometer_x: 'Magnetómetro X',
  magnetometer_y: 'Magnetómetro Y',
  magnetometer_z: 'Magnetómetro Z',
}

const INTERRUPTORES: Record<string, string> = {
  switch_0_ppt_power_supply: 'Alimentación de los PPT',
  switch_1_ppt_1_2: 'PPT 1 y 2',
  switch_2_phone_5v_webcam: 'Teléfono (5 V) y cámara',
  switch_3_warp_valve: 'Válvula del resistojet',
  switch_4_warp_heater: 'Calefactor del resistojet',
  switch_5_digi_wi9c: 'Computador Digi-Wi9C',
  switch_6_sgr05: 'GPS SGR-05',
  switch_7_reaction_wheels: 'Ruedas de reacción',
}

/** Nombre legible de un campo; el identificador original se conserva aparte. */
export function etiquetaCampo(campo: string): string {
  if (NOMBRES[campo]) return NOMBRES[campo]
  const panel = campo.match(/^adc\d+_([pm][xyz])_array_current(_adc)?$/)
  if (panel) return `Corriente de panel ${EJE[panel[1]]}${panel[2] ? ' (cuenta ADC)' : ''}`
  const sw = campo.match(/^(switch_\d_[a-z0-9_]+?)_(corriente|tension)$/)
  if (sw && INTERRUPTORES[sw[1]])
    return `${INTERRUPTORES[sw[1]]}: ${sw[2] === 'corriente' ? 'corriente' : 'tensión'}`
  if (campo.endsWith('_adc')) return `${etiquetaCampo(campo.slice(0, -4))} (cuenta ADC)`
  return campo
}

export function edadLegible(s: number): string {
  if (s < 90) return `${s.toFixed(0)} s`
  if (s < 5400) return `${(s / 60).toFixed(0)} min`
  if (s < 172800) return `${(s / 3600).toFixed(1)} h`
  if (s < 86400 * 730) return `${(s / 86400).toFixed(1)} d`
  return `${(s / (86400 * 365.25)).toFixed(1)} años`
}

/** Valor con los decimales que su unidad admite; las cuentas son enteras. */
export function valorLegible(valor: number, unidad: string): string {
  if (!Number.isFinite(valor)) return '—'
  if (unidad === 'cuenta' || unidad === 's' || unidad === '') return valor.toLocaleString('es-CO', { maximumFractionDigits: 0 })
  if (unidad === 'V') return valor.toLocaleString('es-CO', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
  return valor.toLocaleString('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}

export const fechaUTC = (iso: string | undefined | null) =>
  iso ? `${iso.replace('T', ' ').slice(0, 19)} UTC` : '—'

/* ── Sellos ───────────────────────────────────────────────────────────────── */

const TONO_CLASE: Record<ClaseDato, string> = {
  historico: 'gd-t-cian',
  referencia: 'gd-t-gris',
  derivado: 'gd-t-gris',
  conceptual: 'gd-t-ambar',
  no_disponible: 'gd-t-gris',
}

export function Sello({ clase }: { clase: ClaseDato }) {
  return (
    <span className={`gd-sello ${TONO_CLASE[clase]}`} title={CLASE[clase].descripcion}>
      {CLASE[clase].etiqueta}
    </span>
  )
}

const VALIDACION: Record<ValidacionLectura['estado'], { texto: string; tono: string }> = {
  calibrado: { texto: 'Calibrado', tono: 'gd-t-cian' },
  decodificado: { texto: 'Decodificado', tono: 'gd-t-cian' },
  canal_sin_medida: { texto: 'Sin medida', tono: 'gd-t-ambar' },
  pendiente_de_validacion: { texto: 'Por validar', tono: 'gd-t-ambar' },
  sin_calibrar: { texto: 'Sin calibrar', tono: 'gd-t-gris' },
  dato_crudo: { texto: 'Dato crudo', tono: 'gd-t-gris' },
}

export function SelloValidacion({ v }: { v: ValidacionLectura | undefined }) {
  if (!v) return null
  const { texto, tono } = VALIDACION[v.estado] ?? { texto: v.estado, tono: 'gd-t-gris' }
  return <span className={`gd-sello ${tono}`} title={v.detalle}>{texto}</span>
}

/** Fila de tabla con una lectura: nombre, valor, antigüedad y validación. */
export function FilaLectura({ l }: { l: LecturaGemelo }) {
  return (
    <tr style={{ opacity: l.frescura === 'obsoleta' ? 0.55 : l.frescura === 'vieja' ? 0.8 : 1 }}>
      <td>
        {etiquetaCampo(l.campo)}
        <div className="gd-mono" style={{ color: 'var(--g-tenue)', fontSize: 10.5 }}>{l.campo}</div>
      </td>
      <td className="num">
        {valorLegible(l.valor, l.unidad)} <span style={{ color: 'var(--g-suave)' }}>{l.unidad}</span>
      </td>
      <td className="num" title={`Medida el ${fechaUTC(l.medida_en)}`}>hace {edadLegible(l.edad_s)}</td>
      <td style={{ whiteSpace: 'nowrap' }}><SelloValidacion v={l.validacion} /></td>
    </tr>
  )
}
