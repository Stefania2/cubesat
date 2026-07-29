import { Card, CardHeader, Nota, Section } from '../components/ui'
import { api, useApi } from '../lib/api'

function Capa({
  nombre,
  color,
  descripcion,
  ejemplo,
}: {
  nombre: string
  color: string
  descripcion: string
  ejemplo: string
}) {
  return (
    <div className="rounded-lg border border-line p-4">
      <div className="flex items-center gap-2">
        <span className="size-2.5 rounded-sm" style={{ background: color }} aria-hidden />
        <h4 className="text-sm font-bold tracking-wide text-navy-dark">{nombre}</h4>
      </div>
      <p className="mt-2 text-sm text-ink-soft">{descripcion}</p>
      <code className="mt-2.5 block rounded border border-line bg-blue-lighter px-2.5 py-1.5 font-mono text-[11px] text-ink">
        {ejemplo}
      </code>
    </div>
  )
}

export function Docs() {
  const protocolos = useApi(() => fetch('/api/telemetry/protocolos').then((r) => r.json()), [])
  const estado = useApi(() => api.status(), [])

  return (
    <>
      <Section
        title="Documentación"
        description="Cómo trata esta plataforma los datos de telemetría y por qué."
      >
        <div className="space-y-5">
          <Nota tono="warning">
            <strong className="font-semibold">Principio rector.</strong> La aplicación nunca
            interpreta ni inventa el significado de una trama HEX si el protocolo no ha sido
            validado. Un parámetro sin definición validada se muestra como «Not decoded», nunca con
            un número plausible.
          </Nota>

          <Card>
            <CardHeader
              title="Separación de capas de datos"
              description="Cada dato sabe de qué capa procede y no se mezcla con las demás, ni en la interfaz ni en las exportaciones."
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Capa
                nombre="RAW DATA"
                color="#123B63"
                descripcion="El hexadecimal tal como lo entregó SatNOGS. No se altera nunca."
                ejemplo="raw_hex: 502D7A711E04F8"
              />
              <Capa
                nombre="PROCESSED DATA"
                color="#5BA9D6"
                descripcion="Métricas calculadas sobre los bytes. Ciertas sin conocer el protocolo."
                ejemplo="byte_count: 7 · entropy: 2.81 bits/byte"
              />
              <Capa
                nombre="DECODED TELEMETRY"
                color="#178A52"
                descripcion="Valores físicos. Solo existen si una definición de protocolo validada dice cómo extraerlos."
                ejemplo="(vacío: decodificador cargado, ninguna baliza recibida)"
              />
              <Capa
                nombre="UNKNOWN DATA"
                color="#607080"
                descripcion="El estado por defecto. Un frame sin estructura reconocida se queda aquí."
                ejemplo="status: unclassified · protocol: null"
              />
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Por qué la telemetría aparece sin decodificar"
              description="No es una carencia de la aplicación, sino el estado real del conocimiento sobre este satélite."
            />
            <ul className="space-y-2.5 text-sm text-ink-soft">
              <li className="flex gap-2.5">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-navy" />
                <span>
                  STRaND-1 no publica una especificación validada de su formato de telemetría de
                  baliza que permita mapear bytes a magnitudes físicas.
                </span>
              </li>
              <li className="flex gap-2.5">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-navy" />
                <span>
                  El propio SatNOGS DB entrega estos frames con el campo{' '}
                  <code className="font-mono text-xs">decoded</code> vacío, lo que es consistente con
                  la ausencia de un decodificador validado en la red.
                </span>
              </li>
              <li className="flex gap-2.5">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-navy" />
                <span>
                  Los frames del conjunto van de 1 a 64 bytes, con longitudes muy dispares. Sin
                  cabecera identificada no hay forma fiable de alinear campos.
                </span>
              </li>
            </ul>
            <p className="mt-4 text-sm text-ink-soft">
              Para habilitar la decodificación, registra una fila en{' '}
              <code className="font-mono text-xs">protocol_definitions</code> con{' '}
              <code className="font-mono text-xs">validated = true</code> y su{' '}
              <code className="font-mono text-xs">field_spec</code>. Solo entonces la aplicación
              rellenará los parámetros y las gráficas de Analytics.
            </p>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader title="Protocolos registrados" />
              {protocolos.data ? (
                protocolos.data.total === 0 ? (
                  <p className="text-sm text-ink-soft">
                    Ninguna definición registrada. Es el estado esperado para STRaND-1.
                  </p>
                ) : (
                  <ul className="space-y-2 text-sm">
                    {protocolos.data.items.map((p: any) => (
                      <li key={p.name} className="flex items-center justify-between gap-3">
                        <span className="font-medium">{p.name}</span>
                        <span className="text-xs text-ink-soft">
                          {p.validated ? 'validado' : 'sin validar'} · {p.campos} campos
                        </span>
                      </li>
                    ))}
                  </ul>
                )
              ) : (
                <p className="text-sm text-ink-soft">Cargando…</p>
              )}
              {protocolos.data?.nota && (
                <p className="mt-3 border-t border-line pt-3 text-xs text-ink-soft">
                  {protocolos.data.nota}
                </p>
              )}
            </Card>

            <Card>
              <CardHeader title="Origen de los datos" />
              <dl className="space-y-2.5 text-sm">
                {[
                  ['Satélite', 'STRaND-1 (Surrey Space Centre, 2013)'],
                  ['NORAD ID', String(estado.data?.norad_id ?? 39090)],
                  ['Fuente', 'SatNOGS DB · endpoint /api/telemetry'],
                  ['Frecuencia de referencia', '437.5680 MHz (UHF)'],
                  ['Modo', 'FSK 9600'],
                  ['Frames almacenados', String(estado.data?.frames ?? '—')],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-start justify-between gap-3">
                    <dt className="shrink-0 text-ink-soft">{k}</dt>
                    <dd className="text-right font-medium text-ink">{v}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="API"
              description="El backend expone su documentación interactiva en /docs (OpenAPI)."
            />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead>
                  <tr className="border-b border-line">
                    <th className="label-caps py-2 text-left">Endpoint</th>
                    <th className="label-caps py-2 text-left">Devuelve</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-xs">
                  {[
                    ['GET /api/frames', 'Listado paginado con filtros'],
                    ['GET /api/frames/kpis', 'Métricas del dashboard'],
                    ['GET /api/frames/series', 'Serie temporal por rango'],
                    ['GET /api/observations', 'Observaciones y sus metadatos'],
                    ['POST /api/observations/sync', 'Completa metadatos desde SatNOGS Network'],
                    ['GET /api/telemetry', 'Parámetros y su estado de decodificación'],
                    ['POST /api/decoder', 'Analiza una trama HEX'],
                    ['GET /api/anomalies', 'Informe de anomalías y reglas'],
                    ['GET /api/export/{set}.{csv|json}', 'Exportación por capa'],
                  ].map(([e, d]) => (
                    <tr key={e} className="border-b border-line last:border-0">
                      <td className="py-2 pr-4 text-navy">{e}</td>
                      <td className="py-2 font-sans text-ink-soft">{d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </Section>
    </>
  )
}
