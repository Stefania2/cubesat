/**
 * FASE 5 --- Panel de telemetria, y FASE 7 --- enlace de los datos con el 3D.
 *
 * Reune las tres vistas del mismo instante: el modelo 3D, el panel de valores
 * y la grafica temporal. Las tres se alimentan del mismo cursor, de modo que
 * el pico se ve simultaneamente en la curva y en el satelite.
 *
 * Sobre el transporte: el cursor avanza por **indice de evento**, no por el eje
 * virtual comprimido. El eje comprimido vive en el motor de Python
 * (`gemelo_digital/reproduccion.py`) y es lo que gobernara el bucle inmersivo
 * de la fase 8; aqui la velocidad se rotula en eventos por segundo para no dar
 * a entender que el navegador respeta la cadencia real de las balizas.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { CubeSat3D, xrStore } from '../components/CubeSat3D'
import { Badge, Button, Card, CardHeader, ErrorState, Nota, Section, Skeleton } from '../components/ui'
import { api, useApi } from '../lib/api'
import type { EstadoGemelo, EtiquetaAnomalia } from '../lib/api'

const VELOCIDADES = [1, 2, 5, 10, 25, 60]

const TONO: Record<EtiquetaAnomalia, string> = {
  normal: 'normal',
  advertencia: 'warning',
  anomalia: 'error',
  canal_enrielado: 'error',
  sin_referencia: 'muted',
}

const COLOR_ETIQUETA: Record<EtiquetaAnomalia, string> = {
  normal: '#22c55e',
  advertencia: '#f59e0b',
  anomalia: '#ef4444',
  canal_enrielado: '#a855f7',
  sin_referencia: '#64748b',
}

function edadLegible(s: number): string {
  if (s < 90) return `${s.toFixed(0)} s`
  if (s < 5400) return `${(s / 60).toFixed(0)} min`
  if (s < 172800) return `${(s / 3600).toFixed(1)} h`
  return `${(s / 86400).toFixed(1)} d`
}

export function GemeloDigital() {
  const { data: resumen, error, loading } = useApi(() => api.gemeloResumen(), [])
  const [campo, setCampo] = useState('battery_voltage')
  const [indice, setIndice] = useState(0)
  const [reproduciendo, setReproduciendo] = useState(false)
  const [velocidad, setVelocidad] = useState(10)
  const [estado, setEstado] = useState<EstadoGemelo | null>(null)
  const [soportaVR, setSoportaVR] = useState(false)
  const [guion, setGuion] = useState<string | null>(null)
  const enVuelo = useRef(false)

  // WebXR solo existe en contexto seguro (https o localhost) y con visor.
  // Se comprueba una vez: sin esto el boton prometeria algo que no puede dar.
  useEffect(() => {
    const xr = (navigator as Navigator & { xr?: { isSessionSupported(m: string): Promise<boolean> } }).xr
    xr?.isSessionSupported('immersive-vr').then(setSoportaVR).catch(() => setSoportaVR(false))
  }, [])

  const { data: serie } = useApi(() => api.gemeloSerie(campo), [campo])
  const { data: eventos } = useApi(() => api.gemeloEventos(campo), [campo])

  // Una peticion de estado a la vez: si la anterior no ha vuelto, se salta el
  // cuadro. Evita encolar cientos de peticiones al reproducir deprisa.
  useEffect(() => {
    if (enVuelo.current) return
    enVuelo.current = true
    api.gemeloEstado(indice, campo)
      .then(setEstado)
      .catch(() => undefined)
      .finally(() => { enVuelo.current = false })
  }, [indice, campo])

  useEffect(() => {
    if (!reproduciendo || !resumen) return
    const id = window.setInterval(() => {
      setIndice((i) => (i + 1 >= resumen.eventos ? (setReproduciendo(false), i) : i + 1))
    }, 1000 / velocidad)
    return () => window.clearInterval(id)
  }, [reproduciendo, velocidad, resumen])

  /**
   * FASE 9 --- Demostracion guiada del fallo.
   *
   * Coloca el cursor unos eventos antes del suceso y lo reproduce despacio, de
   * modo que se vea la transicion y no solo el estado final: primero el canal
   * midiendo, luego el salto al extremo de escala, y el cuerpo del modelo
   * cambiando de color a la vez que la curva.
   */
  const demostrar = useCallback((ev: typeof evento) => {
    if (!ev || !serie || !resumen) return
    const j = serie.puntos.findIndex((p) => p.t >= ev.inicio)
    if (j < 0) return
    const centro = Math.round((j / serie.puntos.length) * resumen.eventos)
    setIndice(Math.max(0, centro - 40))
    setVelocidad(2)
    setReproduciendo(true)
    setGuion(ev.inicio)
  }, [serie, resumen])

  const saltarA = useCallback((iso: string) => {
    if (!serie) return
    const j = serie.puntos.findIndex((p) => p.t >= iso)
    if (j >= 0 && resumen) {
      setIndice(Math.round((j / serie.puntos.length) * resumen.eventos))
    }
  }, [serie, resumen])

  if (loading) return <Skeleton className="h-96" />
  if (error) return <ErrorState mensaje={error} />
  if (!resumen) return null

  const anomalos = serie?.puntos.filter((p) => p.etiqueta !== 'normal' && p.valor !== null) ?? []
  const evento = eventos?.eventos[0]

  return (
    <Section
      title="Gemelo digital"
      description={`${resumen.eventos.toLocaleString('es')} eventos, ${resumen.pases} pases de recepción, ${resumen.duracion_real_dias} días`}
    >
      <Nota tono="info">
        La rotación del modelo es <strong>sintética</strong>: STRaND-1 no transmite actitud. La
        inclinación sí procede de los magnetómetros, que fijan dos de los tres grados de libertad.
        Los elementos en gris no tienen lectura asociada, y las lecturas viejas se atenúan según su
        edad.
      </Nota>

      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        {/* --- Modelo 3D ------------------------------------------------ */}
        <Card className="relative min-h-[26rem] overflow-hidden p-0">
          <div className="absolute top-3 right-3 z-10 flex gap-2">
            <Button
              variante={soportaVR ? 'primary' : 'secondary'}
              disabled={!soportaVR}
              title={soportaVR ? 'Entrar en realidad virtual' : 'Este navegador o equipo no expone un visor WebXR'}
              onClick={() => xrStore.enterVR()}
            >
              🥽 {soportaVR ? 'Entrar en VR' : 'VR no disponible'}
            </Button>
          </div>
          <div className="h-[26rem] w-full">
            <CubeSat3D
              estado={estado?.estado_cubesat ?? 'SIN_REFERENCIA'}
              lecturas={estado?.lecturas ?? []}
              girando={reproduciendo}
              momento={estado?.momento ?? ''}
            />
          </div>
        </Card>

        {/* --- Panel de telemetria -------------------------------------- */}
        <Card>
          <CardHeader
            title="Panel de telemetría"
            actions={<Badge tono={TONO[estado?.etiqueta ?? 'sin_referencia']}>
              {estado?.estado_cubesat.replace(/_/g, ' ') ?? '—'}
            </Badge>}
          />
          <dl className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-slate-400">Satélite</dt><dd>STRaND-1 (39090)</dd>
            <dt className="text-slate-400">Instante</dt>
            <dd className="font-mono text-xs">{estado?.momento.replace('T', ' ').slice(0, 19) ?? '—'}</dd>
            <dt className="text-slate-400">Pase</dt><dd>#{estado?.pase ?? '—'}</dd>
            <dt className="text-slate-400">Evento</dt>
            <dd>{indice.toLocaleString('es')} / {resumen.eventos.toLocaleString('es')}</dd>
          </dl>

          <div className="max-h-56 overflow-y-auto rounded border border-slate-700">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-800 text-slate-300">
                <tr><th className="p-1.5">Variable</th><th className="p-1.5 text-right">Valor</th><th className="p-1.5 text-right">Edad</th></tr>
              </thead>
              <tbody>
                {(estado?.lecturas ?? []).map((l) => (
                  <tr key={l.campo}
                      className={`border-t border-slate-800 ${l.frescura === 'obsoleta' ? 'opacity-40' : l.frescura === 'vieja' ? 'opacity-70' : ''}`}>
                    <td className="p-1.5 font-mono">{l.campo}</td>
                    <td className="p-1.5 text-right tabular-nums">
                      {l.valor.toFixed(2)} <span className="text-slate-500">{l.unidad}</span>
                    </td>
                    <td className="p-1.5 text-right tabular-nums text-slate-400">{edadLegible(l.edad_s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* --- Transporte --------------------------------------------------- */}
      <Card className="mt-4">
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setReproduciendo((r) => !r)}>
            {reproduciendo ? '⏸ Pausar' : '▶ Reproducir'}
          </Button>
          <Button onClick={() => setIndice((i) => Math.max(0, i - 10))}>◀◀</Button>
          <Button onClick={() => setIndice((i) => Math.min(resumen.eventos - 1, i + 10))}>▶▶</Button>
          <select
            className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
            value={velocidad}
            onChange={(e) => setVelocidad(Number(e.target.value))}
          >
            {VELOCIDADES.map((v) => <option key={v} value={v}>{v} eventos/s</option>)}
          </select>
          <select
            className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
            value={campo}
            onChange={(e) => setCampo(e.target.value)}
          >
            {resumen.magnitudes.map((m) => (
              <option key={m.campo} value={m.campo}>{m.campo} {m.unidad && `(${m.unidad})`}</option>
            ))}
          </select>
          <input
            type="range" min={0} max={resumen.eventos - 1} value={indice}
            onChange={(e) => setIndice(Number(e.target.value))}
            className="ml-auto w-full max-w-md"
          />
        </div>
      </Card>

      {/* --- Grafica ------------------------------------------------------ */}
      <Card className="mt-4">
        <CardHeader
          title={`${campo} ${serie?.unidad ? `(${serie.unidad})` : ''}`}
          actions={serie && <span className="text-xs text-slate-400">
            {serie.n_total.toLocaleString('es')} lecturas · media {serie.estadisticas.media} · rango {serie.estadisticas.minimo}–{serie.estadisticas.maximo}
          </span>}
        />
        {serie ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={serie.puntos}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="t" tickFormatter={(t: string) => t.slice(0, 7)}
                     minTickGap={40} stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 12 }}
                labelFormatter={(t) => String(t).replace('T', ' ').slice(0, 19)}
              />
              {/* Comportamiento normal: la mediana movil que sirve de referencia */}
              <Line type="monotone" dataKey="mediana" stroke="#38bdf8" dot={false}
                    strokeDasharray="4 3" strokeWidth={1} name="normal esperado" isAnimationActive={false} />
              <Line type="monotone" dataKey="valor" stroke="#e2e8f0" dot={false}
                    strokeWidth={1.2} name="observado" isAnimationActive={false} />
              {estado && <ReferenceLine x={estado.momento} stroke="#facc15" strokeWidth={1.5} />}
              {evento && <ReferenceLine x={evento.inicio} stroke="#a855f7" strokeDasharray="5 3" />}
            </LineChart>
          </ResponsiveContainer>
        ) : <Skeleton className="h-64" />}
        <p className="mt-1 text-xs text-slate-500">
          Línea amarilla: instante reproducido. Línea morada: inicio del evento más largo.
          {anomalos.length > 0 && ` ${anomalos.length.toLocaleString('es')} lecturas no normales.`}
        </p>
      </Card>

      {/* --- Alerta del evento -------------------------------------------- */}
      {evento && (
        <Card className="mt-4">
          <div className="mb-3 h-1 rounded"
               style={{ background: COLOR_ETIQUETA[evento.etiqueta] }} />
          <CardHeader
            title={`Evento detectado — ${evento.etiqueta.replace(/_/g, ' ')}`}
            actions={
              <div className="flex gap-2">
                <Button variante="secondary" onClick={() => saltarA(evento.inicio)}>Ir al evento</Button>
                <Button onClick={() => demostrar(evento)}>▶ Reproducir el evento</Button>
              </div>
            }
          />
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-4">
            <dt className="text-slate-400">Variable</dt><dd className="font-mono text-xs">{evento.campo}</dd>
            <dt className="text-slate-400">Inicio</dt>
            <dd className="font-mono text-xs">{evento.inicio.replace('T', ' ').slice(0, 19)}</dd>
            <dt className="text-slate-400">Duración</dt><dd>{(evento.duracion_s / 86400).toFixed(1)} d ({evento.n_lecturas} lecturas)</dd>
            <dt className="text-slate-400">Estado</dt><dd>{evento.estado_cubesat.replace(/_/g, ' ')}</dd>
            <dt className="text-slate-400">Valor esperado</dt><dd>{evento.valor_esperado} {eventos?.unidad}</dd>
            <dt className="text-slate-400">Valor registrado</dt><dd>{evento.valor_registrado} {eventos?.unidad}</dd>
            <dt className="text-slate-400">Diferencia</dt>
            <dd className={evento.diferencia >= 0 ? 'text-amber-400' : 'text-sky-400'}>
              {evento.diferencia > 0 ? '+' : ''}{evento.diferencia} {eventos?.unidad}
            </dd>
            <dt className="text-slate-400">|z| máximo</dt><dd>{Number.isFinite(evento.z_max) ? evento.z_max : '—'}</dd>
          </dl>
        </Card>
      )}
    </Section>
  )
}
