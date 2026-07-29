import { useState } from 'react'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorState,
  Nota,
  Section,
  StatusDot,
} from '../components/ui'
import { api, type DecodeResult } from '../lib/api'
import { numero } from '../lib/format'

const EJEMPLO = '50 2D 7A 71 1E 04 F8'

/* ── Flujo horizontal del decodificador ───────────────────────────────────── */

function Pipeline({ pasos }: { pasos: DecodeResult['pipeline'] }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2">
      {pasos.map((p, i) => (
        <div key={p.paso} className="flex items-stretch gap-2">
          <div
            className={`min-w-[130px] rounded-lg border px-3 py-2.5 ${
              p.estado === 'ok'
                ? 'border-ok/25 bg-ok-bg'
                : 'border-line bg-white'
            }`}
          >
            <div className="flex items-center gap-1.5">
              <StatusDot tono={p.estado === 'ok' ? 'normal' : 'muted'} />
              <span className="text-[10px] font-semibold tracking-wide text-navy-dark">
                {p.paso}
              </span>
            </div>
            <div className="mt-1 font-mono text-xs text-ink-soft">{p.detalle}</div>
          </div>
          {i < pasos.length - 1 && (
            <div className="flex items-center text-line" aria-hidden>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path
                  d="M4 8h8m0 0-3-3m3 3-3 3"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/* ── Volcado de bytes ─────────────────────────────────────────────────────── */

function VolcadoBytes({ bytes }: { bytes: string[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-blue-lighter p-3">
      <div className="flex flex-wrap gap-1">
        {bytes.map((b, i) => (
          <div key={i} className="flex flex-col items-center">
            <span className="rounded border border-line bg-white px-1.5 py-1 font-mono text-xs font-medium text-navy-dark">
              {b}
            </span>
            <span className="mt-0.5 font-mono text-[9px] tnum text-slate-400">{i}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Resultado({ etiqueta, valor, tono }: { etiqueta: string; valor: string; tono?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line py-2.5 last:border-0">
      <span className="label-caps">{etiqueta}</span>
      <span
        className={`text-sm font-semibold tnum ${
          tono === 'muted' ? 'text-slate-400' : 'text-navy-dark'
        }`}
      >
        {valor}
      </span>
    </div>
  )
}

export function Decoder() {
  const [hex, setHex] = useState(EJEMPLO)
  const [resultado, setResultado] = useState<DecodeResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(false)

  async function decodificar() {
    setCargando(true)
    setError(null)
    try {
      setResultado(await api.decode(hex))
    } catch (e) {
      setError((e as Error).message)
      setResultado(null)
    } finally {
      setCargando(false)
    }
  }

  const ax25 = resultado?.analysis?.ax25

  return (
    <Section
      title="Telemetry Decoder"
      description="Analiza una trama hexadecimal y muestra qué se puede afirmar sobre ella y qué no."
    >
      <div className="space-y-5">
        <Card>
          <CardHeader title="Flujo de decodificación" />
          <Pipeline
            pasos={
              resultado?.pipeline ?? [
                { paso: 'RAW HEX', estado: 'pendiente', detalle: 'Introduce una trama' },
                { paso: 'BYTES', estado: 'pendiente', detalle: '—' },
                { paso: 'FRAME IDENTIFICATION', estado: 'pendiente', detalle: '—' },
                { paso: 'PROTOCOL', estado: 'pendiente', detalle: '—' },
                { paso: 'PAYLOAD', estado: 'pendiente', detalle: '—' },
                { paso: 'DECODED TELEMETRY', estado: 'pendiente', detalle: '—' },
              ]
            }
          />
        </Card>

        <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
          <Card>
            <CardHeader
              title="Entrada HEX"
              description="Admite espacios, saltos de línea y prefijos 0x."
              actions={
                <Button variante="ghost" onClick={() => setHex(EJEMPLO)}>
                  Cargar ejemplo
                </Button>
              }
            />
            <textarea
              value={hex}
              onChange={(e) => setHex(e.target.value)}
              rows={5}
              spellCheck={false}
              className="w-full resize-y rounded-lg border border-line bg-blue-lighter p-3 font-mono text-sm text-ink focus:border-blue focus:bg-white focus:outline-none"
              placeholder="50 2D 7A 71 1E 04 F8"
            />
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button onClick={decodificar} disabled={cargando || !hex.trim()}>
                {cargando ? 'Analizando…' : 'Analizar trama'}
              </Button>
              <span className="text-xs text-ink-soft">
                {hex.replace(/\s/g, '').length / 2 || 0} bytes
              </span>
            </div>

            {error && (
              <div className="mt-4">
                <ErrorState mensaje={error} />
              </div>
            )}

            {resultado && (
              <div className="mt-5 space-y-4">
                <div>
                  <div className="label-caps mb-2">Bytes</div>
                  <VolcadoBytes bytes={resultado.bytes} />
                </div>
              </div>
            )}
          </Card>

          <div className="space-y-5">
            <Card>
              <CardHeader title="Resultado" />
              {resultado ? (
                <>
                  <Resultado etiqueta="Bytes" valor={String(resultado.byte_count)} />
                  <Resultado
                    etiqueta="Protocol"
                    valor={resultado.protocol ?? 'Unknown'}
                    tono={resultado.protocol ? undefined : 'muted'}
                  />
                  <Resultado etiqueta="Frame Type" valor={resultado.frame_type} />
                  <Resultado
                    etiqueta="Decoded"
                    valor={resultado.decoded ? 'Sí' : 'No'}
                    tono={resultado.decoded ? undefined : 'muted'}
                  />
                  <Resultado
                    etiqueta="Entropía"
                    valor={`${numero(resultado.entropy_bits_per_byte, 2)} bits/byte`}
                  />
                  <Resultado
                    etiqueta="Bytes distintos"
                    valor={String(resultado.distinct_bytes)}
                  />
                  <div className="mt-3 flex items-center gap-2">
                    <Badge tono={resultado.status} />
                  </div>
                </>
              ) : (
                <p className="text-sm text-ink-soft">
                  Introduce una trama y pulsa «Analizar» para ver el resultado.
                </p>
              )}
            </Card>

            {resultado && (
              <Card>
                <CardHeader title="Estructura buscada" />
                <div className="space-y-2.5 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-ink-soft">Banderas AX.25 (0x7E)</span>
                    <span className="font-semibold tnum">{ax25?.flags_encontradas ?? 0}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-ink-soft">Campo de direcciones</span>
                    <Badge tono={ax25?.campo_direcciones_plausible ? 'normal' : 'unclassified'}>
                      {ax25?.campo_direcciones_plausible ? 'Plausible' : 'No encaja'}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-ink-soft">FCS</span>
                    <Badge
                      tono={
                        ax25?.fcs_valido === true
                          ? 'normal'
                          : ax25?.fcs_valido === false
                            ? 'error'
                            : 'unclassified'
                      }
                    >
                      {ax25?.fcs_valido === true
                        ? 'Válido'
                        : ax25?.fcs_valido === false
                          ? 'No cuadra'
                          : 'No evaluado'}
                    </Badge>
                  </div>
                  {ax25?.origen && (
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-ink-soft">Indicativos</span>
                      <span className="font-mono text-xs font-semibold">
                        {ax25.origen} → {ax25.destino}
                      </span>
                    </div>
                  )}
                </div>
              </Card>
            )}
          </div>
        </div>

        {resultado && (
          <Nota tono={resultado.decoded ? 'info' : 'warning'}>
            <strong className="font-semibold">Interpretación: </strong>
            {resultado.mensaje}
          </Nota>
        )}

        <Nota>
          <strong className="font-semibold">Cómo leer esta pantalla.</strong> El decodificador
          informa de dos cosas: métricas objetivas de los bytes (longitud, entropía, bytes
          distintos), que son ciertas sin conocer el protocolo, y evidencia estructural — busca una
          estructura conocida y dice si aparece. Nunca traduce un byte a una magnitud física sin una
          definición de protocolo validada. Por eso el último paso del flujo permanece pendiente.
        </Nota>
      </div>
    </Section>
  )
}
