/**
 * Pagina «Enlace RF»: monitoreo en tiempo real del enlace RF simulado.
 *
 * Lanza la cadena GNU Radio del proyecto (subproceso), verifica la integridad
 * de los 18.776 bits y muestra BER, espectro y constelacion del tap IQ de la
 * simulacion, ademas de la telemetria AMSAT re-decodificada. Nada se inventa:
 * los valores vienen de GNU Radio o del decodificador; RSSI/FER salen como N/A.
 *
 * Dos clases de dato conviven aqui y se rotulan por separado: lo SIMULADO
 * (cadena BPSK de banda base, modelo comparativo) y lo HISTORICO REAL (balizas
 * de SatNOGS). El resultado de integridad solo se muestra si consta la corrida
 * que lo produjo, con su SNR y su fecha.
 */
import { useEffect, useReducer, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  LineChart,
  Line,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

/* ── Tipos ────────────────────────────────────────────────────────────────── */

type Estado = {
  link_status?: string
  sim_status?: string
  timestamp?: string
  frames_received?: number | null
  frames_valid?: number | null
  frames_error?: number | null
  mensaje?: string | null
}
type Metricas = Record<string, any> | null
type Integridad = {
  valido?: boolean | null
  bits_entrada?: number
  bits_recuperados?: number | null
  diferencia?: number | null
  sha256_entrada?: string | null
  sha256_recuperado?: string | null
  frames_esperados?: number
  mensaje?: string | null
  procedencia?: 'sin_corrida' | 'archivo_sin_registro' | 'sesion_actual' | 'corrida_anterior'
  corrida_utc?: string | null
  snr_db?: number | null
} | null

/* ── Estado del hook ──────────────────────────────────────────────────────── */

const vacio = {
  status: null as Estado | null,
  metrics: null as Metricas,
  integrity: null as Integridad,
  telemetry: null as Record<string, any> | null,
  spectrum: null as Record<string, any> | null,
  constellation: null as Record<string, any> | null,
  config: null as Record<string, any> | null,
  history: [] as any[],
  logs: [] as any[],
  conectado: false,
}

type Accion =
  | { tipo: 'ws'; valor: boolean }
  | { tipo: 'set'; clave: keyof typeof vacio; valor: any }

function reducer(s: typeof vacio, a: Accion): typeof vacio {
  if (a.tipo === 'ws') return { ...s, conectado: a.valor }
  if (a.tipo === 'set') return { ...s, [a.clave]: a.valor }
  return s
}

function useEnlace() {
  const [state, dispatch] = useReducer(reducer, vacio)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let vivo = true
    const cargar = async () => {
      try {
        const [status, metrics, integrity, telemetry, spectrum, constellation, config, history, logs] =
          await Promise.all([
            fetch('/api/enlace/status').then((r) => r.json()),
            fetch('/api/enlace/metrics').then((r) => r.json()),
            fetch('/api/enlace/integrity').then((r) => r.json()),
            fetch('/api/enlace/telemetry').then((r) => r.json()),
            fetch('/api/enlace/spectrum').then((r) => r.json()),
            fetch('/api/enlace/constellation').then((r) => r.json()),
            fetch('/api/enlace/config').then((r) => r.json()),
            fetch('/api/enlace/history').then((r) => r.json()),
            fetch('/api/enlace/log').then((r) => r.json()),
          ])
        if (!vivo) return
        for (const [k, v] of Object.entries({
          status, metrics, integrity, telemetry, spectrum, constellation, config, history, logs,
        }) as [keyof typeof vacio, any][]) {
          dispatch({ tipo: 'set', clave: k, valor: v })
        }
      } catch (e) {
        if (vivo) setError(String(e))
      }
    }
    cargar()

    // WebSocket con auto-reconexion. Requisitos que resuelven los fallos vistos:
    //  - StrictMode (solo dev) monta el efecto dos veces: cada invocacion tiene su
    //    bandera `vivo`, asi el onclose/onerror del primer socket se ignora y no
    //    pinta "desconectado"/error sobre el segundo, que es el que funciona.
    //  - Si la conexion se cae (reinicio de vite, corte breve), se reconecta sola
    //    con espera progresiva y sin dejar un banner de error permanente.
    let ws: WebSocket | null = null
    let reintentos = 0
    const conectar = () => {
      if (!vivo) return
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const candidato = new WebSocket(`${proto}://${window.location.host}/ws/enlace`)
      ws = candidato
      wsRef.current = candidato

      candidato.onopen = () => {
        if (!vivo || ws !== candidato) return
        reintentos = 0
        setError(null)
        dispatch({ tipo: 'ws', valor: true })
      }
      candidato.onmessage = (ev) => {
        if (!vivo || ws !== candidato) return
        try {
          const msg = JSON.parse(ev.data)
          if (!msg?.type) return
          const mapeo: Record<string, keyof typeof vacio> = {
            status_update: 'status',
            metrics_update: 'metrics',
            integrity_update: 'integrity',
            telemetry_update: 'telemetry',
            spectrum_ready: 'spectrum',
            constellation_ready: 'constellation',
          }
          const clave = mapeo[msg.type]
          if (clave) dispatch({ tipo: 'set', clave, valor: msg.payload })
          else if (msg.type === 'log_batch') dispatch({ tipo: 'set', clave: 'logs', valor: msg.payload })
        } catch {
          /* mensaje malformado */
        }
      }
      candidato.onclose = () => {
        if (!vivo || ws !== candidato) return
        dispatch({ tipo: 'ws', valor: false })
        reintentos += 1
        const espera = Math.min(1000 * 2 ** reintentos, 15000)
        window.setTimeout(conectar, espera)
      }
      candidato.onerror = () => {
        /* onclose sigue y dispara la reconexion; no se muestra banner por cortes transitorios */
      }
    }
    conectar()

    return () => {
      vivo = false
      ws?.close()
      wsRef.current = null
    }
  }, [])

  const simular = async (action: string, snr?: number | undefined) => {
    setOcupado(true)
    setError(null)
    try {
      const r = await fetch('/api/enlace/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, snr_db: snr }),
      })
      // Algunas respuestas (proxy, red) llegan con cuerpo vacio; leerlas como JSON
      // crashea con un SyntaxError poco util. Se lee el texto crudo y se parsea con
      // cuidado, mostrando el status real si algo falla.
      let cuerpo = ''
      try { cuerpo = await r.text() } catch { cuerpo = '' }
      let json: Record<string, any> | null = null
      if (cuerpo) {
        try { json = JSON.parse(cuerpo) } catch { json = null }
      }
      if (!r.ok) throw new Error(json?.detail || `${r.status} ${r.statusText}`.trim())
      dispatch({ tipo: 'set', clave: 'status', valor: json })
    } catch (e) {
      setError(String(e))
    } finally {
      setOcupado(false)
    }
  }

  return { state, error, ocupado, simular }
}

/* ── Pequeños componentes de presentacion ────────────────────────────────── */

function fmt(v: unknown, dec = 4): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return v.toLocaleString('es-CO')
    return v.toFixed(dec)
  }
  return String(v)
}

function Chip({ label, tono }: { label: string; tono: 'verde' | 'rojo' | 'ambar' | 'gris' }) {
  return (
    <span className={`enlace-chip enlace-chip-${tono}`}>
      <span className="enlace-dot" /> {label}
    </span>
  )
}

function Metrica({ etiqueta, valor, unidad, nota, tono = 'gris' }: {
  etiqueta: string
  valor: unknown
  unidad?: string | null
  nota?: string
  tono?: 'ok' | 'ambar' | 'rojo' | 'gris'
}) {
  return (
    <div className={`enlace-tarjeta enlace-tono-${tono}`}>
      <div className="enlace-etiqueta">{etiqueta}</div>
      <div className="enlace-valor">
        {fmt(valor, tono === 'ok' ? 6 : 3)}
        {unidad ? <span className="enlace-unidad">{unidad}</span> : null}
      </div>
      {nota ? <div className="enlace-nota">{nota}</div> : null}
    </div>
  )
}

function Paso({ etiqueta, valor, tono }: { etiqueta: string; valor: unknown; tono: string }) {
  return (
    <div className="enlace-paso">
      <div className={`enlace-paso-valor ${tono}`}>{fmt(valor)}</div>
      <div className="enlace-paso-etiqueta">{etiqueta}</div>
    </div>
  )
}

/* ── Pagina ───────────────────────────────────────────────────────────────── */

export function EnlaceRF() {
  const { state, error, ocupado, simular } = useEnlace()
  const { status, metrics, integrity, telemetry, spectrum, constellation, config, history, conectado } = state

  const enMarcha = status?.sim_status === 'RUNNING'
  // undefined mientras carga la configuracion: no se habilita ni se niega nada.
  const simulable = config ? config.simulacion_disponible !== false : false
  const tonoLink = status?.link_status === 'ACTIVE' ? 'verde' : 'rojo'
  const tonoSim = enMarcha ? 'ambar' : status?.sim_status === 'STOPPED' ? 'verde' : 'gris'

  return (
    <div className="enlace-rf">
      <header className="enlace-cabecera">
        <div className="enlace-titulo">
          STRAND-1 Ground Station{' '}
          <span className="enlace-sub">RF Communication Link Monitoring</span>
          <div className="enlace-sub2">
            GNU Radio → FastAPI → WebSocket · {fmt(config?.frecuencia_hz, 0)} Hz ·{' '}
            {((config?.tasa_bits_bps ?? 0) / 1000).toFixed(1)} kbps BPSK (modelo) · 18.776 bits
          </div>
          <div className="enlace-sub2">
            Simulación de banda base. {config?.modulacion_nota ?? ''}
          </div>
        </div>
        <div className="enlace-chips">
          <Chip label={`Enlace: ${status?.link_status ?? 'OFFLINE'}`} tono={tonoLink} />
          <Chip label={`Simulación: ${status?.sim_status ?? 'IDLE'}`} tono={tonoSim} />
          <Chip label={`WebSocket: ${conectado ? 'conectado' : 'desconectado'}`} tono={conectado ? 'verde' : 'rojo'} />
        </div>
        <div className="enlace-controles">
          <button className="enlace-btn enlace-btn-primario" disabled={enMarcha || ocupado || !simulable}
            title={config?.simulacion_no_disponible_motivo ?? undefined}
            onClick={() => simular('start', config?.snr_default_db)}>
            ▶ Iniciar simulación
          </button>
          <button className="enlace-btn" disabled={!enMarcha || ocupado} onClick={() => simular('stop')}>
            ■ Detener
          </button>
          <button className="enlace-btn" disabled={ocupado} onClick={() => simular('reset')}>
            ↺ Reset
          </button>
          <span className="enlace-config">
            SNR {fmt(config?.snr_min_db, 0)}–{fmt(config?.snr_max_db, 0)} dB · RRC α={config?.rolloff}
          </span>
        </div>
      </header>

      {error && <div className="enlace-banner">{error}</div>}
      {config?.simulacion_disponible === false && (
        <div className="enlace-banner">
          Simulación no disponible en esta instancia: {config.simulacion_no_disponible_motivo} Los
          paneles de simulación quedan vacíos; la telemetría decodificada de abajo es histórica y sí
          está disponible.
        </div>
      )}

      <section className="enlace-grid enlace-grid-metricas">
        <Metrica etiqueta="Eb/N0 configurada" valor={fmt(metrics?.snr_db, 1)} unidad="dB"
          nota="Valor impuesto a la simulación, no estimado de la señal" />
        <Metrica etiqueta="BER medido (empírico)" valor={metrics?.ber} tono="ok"
          nota={berNota(metrics?.ber as number | null)} />
        <Metrica etiqueta="RSSI" valor={null} unidad="dBm" nota={metrics?.nota_rssi} />
        <Metrica etiqueta="FER" valor={null} nota={metrics?.nota_fer} />
        <Metrica etiqueta="Potencia relativa (tap IQ)" valor={fmt(metrics?.potencia_relativa_dbfs, 1)} unidad="dBFs"
          nota="Media de |I+jQ|² del canal tras AWGN" />
        <Metrica etiqueta="Ruido fuera de banda (Welch)" valor={fmt(metrics?.ruido_estimado, 1)} unidad="dB"
          nota="Potencia media de ruido fuera de la banda RRC" />
      </section>

      <section className="enlace-grid enlace-grid-integridad">
        <div className="enlace-panel">
          <h3 className="enlace-panel-titulo">
            Integridad de bits{' '}
            <span className={`enlace-veredicto ${integrity?.valido ? 'enlace-ok' : 'enlace-mal'}`}>
              {integrity?.valido
                ? 'IDENTICOS'
                : integrity?.valido === false
                  ? `${fmt(integrity?.diferencia)} BIT(S) ERRÓNEO(S)`
                  : 'SIN CORRIDA'}
            </span>
          </h3>
          <div className="enlace-grid enlace-grid-cuatro">
            <Paso etiqueta="bits de entrada" valor={integrity?.bits_entrada} tono="enlace-mono" />
            <Paso etiqueta="bits recuperados" valor={integrity?.bits_recuperados} tono="enlace-mono" />
            <Paso etiqueta="bits erróneos"
              valor={fmt(integrity?.diferencia)} tono={integrity?.diferencia === 0 ? 'enlace-ok' : 'enlace-mal'} />
            <Paso etiqueta="tramas esperadas" valor={integrity?.frames_esperados} tono="enlace-mono" />
          </div>
          <div className="enlace-mono">
            <div>SHA-256 TX:  {integrity?.sha256_entrada}</div>
            <div>SHA-256 RX:  {integrity?.sha256_recuperado}</div>
          </div>
          {integrity?.corrida_utc && (
            <div className="enlace-fuente">
              Resultado simulado · corrida del {integrity.corrida_utc} · SNR {fmt(integrity.snr_db, 1)} dB
              {integrity.procedencia === 'corrida_anterior' ? ' · anterior a esta sesión' : ''}
            </div>
          )}
          {integrity?.mensaje && <div className="enlace-msg">{integrity.mensaje}</div>}
          {status?.mensaje ? <div className="enlace-msg">{status.mensaje}</div> : null}
        </div>
      </section>

      <section className="enlace-grid enlace-grid-dos">
        <div className="enlace-panel">
          <h3 className="enlace-panel-titulo">Espectro (FFT Welch · tap IQ real)</h3>
          {grafica(spectrum, (s) => {
            const datos = (s.datos || []).filter((_: any, i: number) => i % Math.max(1, Math.floor(s.datos.length / 600)) === 0)
            return (
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={datos} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#1f2b3a" strokeDasharray="3 3" />
                  <XAxis dataKey="freq_hz" tick={{ fill: '#8aa4c0', fontSize: 11 }}
                    tickFormatter={(v: number) => `${(v / 1000).toFixed(1)} kHz`}
                    domain={['dataMin', 'dataMax']} tickCount={9} />
                  <YAxis tick={{ fill: '#8aa4c0', fontSize: 11 }}
                    tickFormatter={(v: number) => `${v.toFixed(0)} dB`}
                    domain={['dataMin - 4', 'dataMax + 2']} width={54} />
                  <Tooltip contentStyle={{ background: '#0d1520', border: '1px solid #22313f' }}
                    labelStyle={{ color: '#d7e3f0' }} formatter={(v: any) => [`${v.toFixed(2)} dB`, 'Potencia']} />
                  <ReferenceLine x={0} stroke="#3a6ea5" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="power_db" stroke="#3fb950" dot={false}
                    strokeWidth={1.4} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            )
          }, 'FFT data unavailable — ejecuta la simulacion (POST /api/enlace/simulate)')}
        </div>

        <div className="enlace-panel">
          <h3 className="enlace-panel-titulo">Constelación BPSK (tap a tasa de símbolo)</h3>
          {grafica(constellation, (s) => (
            <ResponsiveContainer width="100%" height={230}>
              <ScatterChart margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#1f2b3a" strokeDasharray="3 3" />
                <XAxis type="number" dataKey="i" domain={['dataMin - 0.15', 'dataMax + 0.15']}
                  tickCount={7} tick={{ fill: '#8aa4c0', fontSize: 11 }} />
                <YAxis type="number" dataKey="q" domain={['dataMin - 0.15', 'dataMax + 0.15']}
                  tickCount={7} tick={{ fill: '#8aa4c0', fontSize: 11 }} width={48} />
                <Tooltip contentStyle={{ background: '#0d1520', border: '1px solid #22313f' }}
                  formatter={(v: any) => [v.toFixed(4), '']} />
                <ReferenceLine x={0} stroke="#3a6ea5" strokeDasharray="4 4" />
                <ReferenceLine y={0} stroke="#3a6ea5" strokeDasharray="4 4" />
                <Scatter data={s.puntos || []} fill="#3fb950" fillOpacity={0.55}
                  stroke="none" isAnimationActive={false} />
              </ScatterChart>
            </ResponsiveContainer>
          ), 'Constelacion no disponible — ejecuta la simulacion primero')}
        </div>
      </section>

      <section className="enlace-grid">
        <div className="enlace-panel">
          <h3 className="enlace-panel-titulo">BER medido vs SNR (historial de la sesión)</h3>
          {history.length ? (
            <ResponsiveContainer width="100%" height={200}>
              <ScatterChart margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#1f2b3a" strokeDasharray="3 3" />
                <XAxis type="number" dataKey="snr_db" name="SNR" unit=" dB"
                  tick={{ fill: '#8aa4c0', fontSize: 11 }}
                  domain={[config?.snr_min_db ?? 'dataMin', config?.snr_max_db ?? 'dataMax']}
                  tickCount={8} />
                <YAxis type="number" dataKey="ber" name="BER" scale="log" domain={[1e-6, 1]}
                  allowDataOverflow tick={{ fill: '#8aa4c0', fontSize: 11 }}
                  tickFormatter={(v: number) => (v === 0 ? '0' : v.toExponential(0))} width={54} />
                <Tooltip contentStyle={{ background: '#0d1520', border: '1px solid #22313f' }}
                  formatter={(v: any, n: any) =>
                    n === 'ber' ? [v === 0 ? 0 : v.toExponential(3), 'BER medido'] : [v, 'SNR']} />
                <Scatter data={history} fill="#d29922" isAnimationActive={false} />
              </ScatterChart>
            </ResponsiveContainer>
          ) : (
            <div className="enlace-vacio">
              Sin puntos todavia. Ejecuta una simulacion para registrar BER medido por SNR.
            </div>
          )}
        </div>
      </section>

      <section className="enlace-grid">
        <div className="enlace-panel">
          <h3 className="enlace-panel-titulo">
            Telemetría decodificada (histórica real){' '}
            <span className="enlace-ref">{fmt(telemetry?.total_frames)} balizas AMSAT</span>
          </h3>
          {telemetry?.nota && <div className="enlace-fuente">{telemetry.nota}</div>}
          <div className="enlace-grid enlace-grid-metricas">
            {(telemetry?.parametros || []).slice(0, 18).map((p: any) => (
              <Metrica key={p.key} etiqueta={p.label} valor={p.value} unidad={p.unit}
                nota={p.nota ?? undefined}
                tono={p.status === 'SIN_MEDIDA' ? 'ambar' : 'ok'} />
            ))}
          </div>
          <h4 className="enlace-subtitulo">Últimas balizas recibidas</h4>
          <div className="enlace-tabla-scroll">
            <table className="enlace-tabla">
              <thead>
                <tr>
                  <th>Timestamp</th><th>Estación</th><th>Bytes</th><th>Payload</th><th>Dec.</th>
                </tr>
              </thead>
              <tbody>
                {(telemetry?.frames || []).slice(0, 8).map((f: any, i: number) => (
                  <tr key={i}>
                    <td>{f.timestamp || '—'}</td>
                    <td>{f.observer || '—'}</td>
                    <td>{f.tamano_bytes ?? '—'}</td>
                    <td className="enlace-mono">{f.hex || '—'}</td>
                    <td>{f.decodificado ? 'sí' : 'no'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <footer className="enlace-pie">
        Enlace RF simulado en GNU Radio 3.10 (BPSK de banda base, modelo comparativo; la baliza
        real es FSK 9600). BER, espectro y constelación son salidas de esa simulación; la telemetría
        es histórica real, re-decodificada. RSSI y FER se muestran como N/A porque esta cadena no
        tiene potencia RF ni tramas AX.25/FEC; la FER del modelo avanzado está en «Simulación RF».
      </footer>
    </div>
  )
}

function grafica(obj: Record<string, any> | null, render: (s: any) => ReactNode, fallback: string) {
  if (!obj || !obj.disponible) {
    return <div className="enlace-vacio">{obj?.nota || fallback}</div>
  }
  return render(obj)
}

function berNota(ber: number | null | undefined): string {
  if (ber === null || ber === undefined) return 'Aun sin medicion (ejecuta la simulacion)'
  if (ber === 0) return '0 errores sobre los 18.776 bits'
  const errores = Math.max(1, Math.round(ber * 18_776))
  return `${ber.toExponential(3)} (${errores} ${errores === 1 ? 'error' : 'errores'} / 18.776 bits)`
}