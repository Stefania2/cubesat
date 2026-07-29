import { Card, LinkButton, Nota, Section } from '../components/ui'

/* ── Página del proyecto de simulación RF ──────────────────────────────────
 *
 * Resume el trabajo publicado en https://stefania2.github.io/cubesat/ — la
 * caracterización por simulación del enlace de comunicaciones del CubeSat.
 * Es el complemento natural de esta plataforma: allí se modela el enlace, aquí
 * se procesa la telemetría que ese mismo satélite emite.
 *
 * Todas las cifras proceden de `cubesat/resultados_simulacion/`, generadas por
 * el pipeline de scripts, y del informe técnico. No hay ningún valor escrito a
 * mano que no salga de una corrida real.                                     */

const REPO = 'https://github.com/Stefania2/cubesat'
const WEB = 'https://stefania2.github.io/cubesat/'

const METRICAS = [
  { valor: '7,1 – 18,0 dB', etiqueta: 'Margen de enlace descendente', nota: '5° a 90° de elevación' },
  { valor: '23,3 – 34,2 dB', etiqueta: 'Margen de enlace ascendente', nota: '10 W a 435 MHz, 1200 bps' },
  { valor: '5,9×', etiqueta: 'Reducción de ancho de banda', nota: 'conformado RRC, sin coste en BER' },
  { valor: '~4 dB', etiqueta: 'Ganancia de codificación', nota: 'convolucional r=1/2, K=7 + Viterbi' },
]

const HALLAZGOS = [
  {
    titulo: 'BPSK supera a FSK en canal AWGN',
    texto:
      'A 0 dB de SNR, BPSK da BER 5,3·10⁻⁵ frente a 5,3·10⁻² de FSK: tres órdenes de magnitud. ' +
      'Consistente con la teoría de modulaciones binarias, y coherente con que 9600 bps BPSK sea ' +
      'el estándar de facto en CubeSats UHF.',
  },
  {
    titulo: 'El conformado RRC mete la señal en el canal de 25 kHz',
    texto:
      'El ancho de banda ocupado al 99 % baja de 66,1 kHz a 11,2 kHz al aplicar filtro de coseno ' +
      'realzado en raíz (α = 0,35) en transmisión y recepción, sin penalización en BER.',
  },
  {
    titulo: 'La tolerancia al Doppler residual es de décimas de hercio',
    texto:
      'Sin recuperación de portadora, un error de 0,2 Hz tras la precompensación por TLE produce un ' +
      'suelo irreducible de BER sobre el registro de 1,96 s. Cuantifica por qué un receptor real ' +
      'necesita un lazo de Costas.',
  },
  {
    titulo: 'El límite del rotor es tolerable con haz ancho',
    texto:
      'En la culminación de un paso casi cenital el satélite exige 8,23 °/s en azimut y el rotor da ' +
      '5 °/s. El retraso llega a 20° de azimut, pero a 82,5° de elevación eso son 2,62° reales fuera ' +
      'de boresight: 0,09 dB de pérdida con un haz de 30°.',
  },
]

const MODELOS = [
  {
    nombre: 'Modelo básico',
    script: 'simular_enlace_rf_fsk_bpsk.py',
    descripcion:
      'Telemetría real → bits → BPSK/FSK a 8 muestras por símbolo → canal AWGN (SNR de −2 a 12 dB) ' +
      '→ demodulación coherente (BPSK) o por correlación (FSK) → BER. Sincronización ideal.',
  },
  {
    nombre: 'Modelo avanzado',
    script: 'simular_enlace_rf_bpsk_avanzado.py',
    descripcion:
      'Añade conformado RRC, desvanecimiento Rice con perfil de Jakes, error residual de Doppler, ' +
      'codificación convolucional con Viterbi y tramas AX.25 verificadas con FCS CRC-16/X-25. ' +
      '18 configuraciones × 8 puntos de SNR = 144 corridas.',
  },
  {
    nombre: 'Link budget y estación terrena',
    script: 'calcular_link_budget.py · modelo_estacion_terrena.py',
    descripcion:
      'Balance de potencia descendente y ascendente en UHF sobre órbita real de 775 km, y un paso ' +
      'orbital completo con seguimiento automático desde Bogotá, con error de apuntamiento y ' +
      'pérdida asociada.',
  },
  {
    nombre: 'Flujogramas GNU Radio',
    script: 'simulacion_visualizar_iq.grc · simulacion_cadena_completa.grc',
    descripcion:
      'Visualización IQ con control interactivo de AWGN, y cadena BPSK completa desde los bytes de ' +
      'telemetría hasta la demodulación. GNU Radio 3.10 con PyQt5.',
  },
]

export function Simulacion() {
  return (
    <>
      <Section
        title="Simulación del enlace RF del CubeSat"
        description="Caracterización por simulación del subsistema de comunicaciones de STRaND-1, con herramientas de software libre."
        actions={
          <div className="flex gap-2">
            <LinkButton href={WEB}>Ver sitio del proyecto</LinkButton>
            <LinkButton href={REPO}>Repositorio</LinkButton>
          </div>
        }
      >
        <div className="space-y-5">
          <Nota>
            Este proyecto y la plataforma de telemetría son las dos mitades del mismo trabajo: aquí se
            <strong className="font-semibold"> modela el enlace</strong> que haría falta para hablar con
            el satélite, y en el resto de la aplicación se{' '}
            <strong className="font-semibold">procesa lo que ese satélite emite de verdad</strong>. Las
            tramas reales descargadas de SatNOGS son la fuente de bits que alimenta las simulaciones.
          </Nota>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {METRICAS.map((m) => (
              <Card key={m.etiqueta} className="min-w-0">
                <div className="text-2xl font-bold leading-none text-navy-dark tnum">{m.valor}</div>
                <div className="label-caps mt-2">{m.etiqueta}</div>
                <p className="mt-1 text-xs text-ink-soft">{m.nota}</p>
              </Card>
            ))}
          </div>
        </div>
      </Section>

      <Section
        title="Modelos implementados"
        description="Cada uno es un script independiente que escribe sus resultados a disco: JSON de configuración, CSV de resultados y gráficas."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {MODELOS.map((m) => (
            <Card key={m.nombre}>
              <div className="label-caps">{m.nombre}</div>
              <p className="mt-2 text-sm leading-relaxed text-ink">{m.descripcion}</p>
              <p className="mt-3 font-mono text-[11px] text-ink-soft">{m.script}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section
        title="Hallazgos principales"
        description="Resultados que salen de las corridas, no de la literatura."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {HALLAZGOS.map((h) => (
            <Card key={h.titulo}>
              <div className="font-semibold text-navy-dark">{h.titulo}</div>
              <p className="mt-2 text-sm leading-relaxed text-ink">{h.texto}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section
        title="Parámetros del enlace"
        description="Valores del satélite y de la estación terrena usados en el balance de potencia."
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-line text-left label-caps">
                <th className="py-2 pr-3">Parámetro</th>
                <th className="py-2 pr-3 text-right">Valor</th>
                <th className="py-2">Nota</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Frecuencia descendente', '437,568 MHz', 'UHF, banda de radioaficionado'],
                ['Tasa de símbolo', '9600 bps', 'BPSK coherente'],
                ['Altura orbital', '775 km', 'del TLE real, órbita heliosíncrona'],
                ['Potencia del satélite', '1 W (30 dBm)', 'monopolo λ/4, 0 dBi'],
                ['Antena de estación', '15 dBi', 'Yagi UHF de 11–13 elementos'],
                ['Temperatura de sistema', '371 K', 'incluye ruido del cable hasta el LNA'],
                ['Eb/N0 requerida', '10 dB', 'para BER objetivo de 10⁻⁵'],
              ].map(([p, v, n]) => (
                <tr key={p} className="border-b border-line/60">
                  <td className="py-2 pr-3">{p}</td>
                  <td className="py-2 pr-3 text-right tnum font-medium">{v}</td>
                  <td className="py-2 text-ink-soft">{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        title="Documentación técnica"
        description="El informe recoge la metodología completa, los resultados y sus limitaciones."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            {
              titulo: 'Informe técnico final',
              texto: 'Metodología, resultados, discusión y conclusiones. Sus tablas se regeneran desde los datos.',
              href: `${REPO}/blob/main/docs/INFORME_TECNICO_FINAL.md`,
            },
            {
              titulo: 'Diseño del modelo RF',
              texto: 'Decisiones de diseño de la cadena de simulación y su justificación.',
              href: `${REPO}/blob/main/docs/DISENO_MODELO_SIMULACION_ENLACE_RF.md`,
            },
            {
              titulo: 'Caracterización de componentes',
              texto: 'Antena, transceptor, módem y TT&C del subsistema de comunicaciones.',
              href: `${REPO}/blob/main/docs/CARACTERIZACION_COMPONENTES_COMMS.md`,
            },
          ].map((d) => (
            <Card key={d.titulo}>
              <div className="font-semibold text-navy-dark">{d.titulo}</div>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">{d.texto}</p>
              <div className="mt-3">
                <LinkButton href={d.href}>Abrir</LinkButton>
              </div>
            </Card>
          ))}
        </div>
      </Section>
    </>
  )
}
