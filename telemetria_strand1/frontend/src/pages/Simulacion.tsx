import { Badge, Card, LinkButton, Nota, Section } from '../components/ui'
import resumen from '../data/resumen_simulacion.json'

/* ── Página del proyecto de simulación RF ──────────────────────────────────
 *
 * Ninguna cifra de esta página está escrita aquí. Todas salen de
 * `src/data/resumen_simulacion.json`, que genera `generar_resumen_web.py` a
 * partir de `cubesat/resultados_simulacion/`. Antes los números vivían en este
 * archivo y se quedaron atrás respecto de los resultados (el seguimiento del
 * rotor mostraba 2,62° y 0,09 dB cuando la corrida vigente daba 0,77° y
 * 0,01 dB). `tests/test_coherencia_resultados.py` falla si el JSON publicado
 * no coincide con los resultados actuales.                                   */

const REPO = 'https://github.com/Stefania2/cubesat'
const WEB = 'https://stefania2.github.io/cubesat/'

const r = resumen
const lb = r.link_budget
const paso = r.paso_sgp4
const avz = r.modelo_avanzado
const est = r.estacion_terrena
const rec = r.recepcion

/* ── Formato ──────────────────────────────────────────────────────────────── */

const es = (v: number, dec = 1) =>
  v.toLocaleString('es-CO', { minimumFractionDigits: dec, maximumFractionDigits: dec })

const db = (v: number | null | undefined, dec = 1) =>
  v === null || v === undefined ? 'N/A' : `${es(v, dec)} dB`

/** Tasa de error en notación científica; nunca un cero sin su cota. */
function tasa(v: number | null | undefined, cotaSup?: number | null): string {
  if (v === null || v === undefined) return 'N/A'
  if (v === 0) return cotaSup ? `0 (< ${cotaSup.toExponential(1)})` : '0'
  return v >= 0.01 ? es(v, 3) : v.toExponential(1)
}

const fechaUTC = (iso: string) => iso.slice(0, 16).replace('T', ' ') + ' UTC'

type Tipo = 'simulado' | 'teorico' | 'derivado' | 'documentado' | 'supuesto' | 'deducido'

const TONO: Record<Tipo, string> = {
  simulado: 'warning',
  teorico: 'unclassified',
  derivado: 'normal',
  documentado: 'normal',
  deducido: 'normal',
  supuesto: 'warning',
}

const ETIQUETA: Record<Tipo, string> = {
  simulado: 'Simulado',
  teorico: 'Teórico',
  derivado: 'Derivado de datos reales',
  documentado: 'Documentado',
  deducido: 'Deducido de datos',
  supuesto: 'Supuesto de diseño',
}

function EtiquetaTipo({ tipo }: { tipo: Tipo }) {
  return <Badge tono={TONO[tipo]}>{ETIQUETA[tipo]}</Badge>
}

/* ── Datos derivados del resumen (solo selección y formato) ───────────────── */

const curva = (esquema: string, canal: string) =>
  avz.curvas.filter((c) => c.esquema === esquema && c.canal === canal)

const gBer = avz.ganancia_codificacion_ber
const gFer = avz.ganancia_codificacion_fer
const mc = paso.montecarlo
const residual = (dt: number) => paso.residual.find((x) => x.error_tiempo_s === dt)

const METRICAS: { valor: string; etiqueta: string; nota: string; tipo: Tipo }[] = [
  {
    valor: `${es(lb.margen_fsk_min_db)} – ${es(lb.margen_fsk_max_db)} dB`,
    etiqueta: 'Margen descendente, FSK',
    nota: `5° a 90°, umbral teórico FSK no coherente a BER ${lb.ber_objetivo.toExponential(0)}`,
    tipo: 'teorico',
  },
  {
    valor: `${es(paso.margen_fsk.margen_min_db)} – ${es(paso.margen_fsk.margen_max_db)} dB`,
    etiqueta: 'Margen en un paso SGP4',
    nota: `culminación a ${es(paso.elev_max_deg, 0)}°; ${es(
      paso.margen_fsk.porcentaje_tiempo_margen_positivo,
      0,
    )} % del tiempo con margen positivo`,
    tipo: 'simulado',
  },
  {
    valor: `${es(avz.reduccion_ancho_banda)}×`,
    etiqueta: 'Reducción de ancho de banda',
    nota: `RRC α=${es(avz.rrc_rolloff, 2)}: ${es(avz.ancho_banda_nrz_hz / 1000)} → ${es(
      avz.ancho_banda_rrc_hz / 1000,
    )} kHz (99 %)`,
    tipo: 'simulado',
  },
  {
    valor: db(gBer.ganancia_db),
    etiqueta: 'Ganancia de codificación',
    nota: `a BER ${gBer.ber_objetivo}, AWGN, igual Eb/N0; resolución ±${es(
      gBer.resolucion_db,
    )} dB`,
    tipo: 'simulado',
  },
]

const HALLAZGOS: { titulo: string; texto: string; tipo: Tipo }[] = [
  {
    titulo: 'La baliza real es FSK; BPSK es un modelo comparativo',
    texto:
      `La modulación documentada de STRaND-1 es ${r.modulacion.documentada} (${r.modulacion.fuentes}). ` +
      `El modelo de banda base usa BPSK coherente para estudiar conformado, sincronización y ` +
      `codificación. A BER ${lb.ber_objetivo.toExponential(0)} la FSK no coherente necesita ` +
      `${es(r.modulacion.esquemas.fsk_no_coherente.eb_n0_teorica_db, 2)} dB de Eb/N0 y la BPSK ` +
      `${es(r.modulacion.esquemas.bpsk_coherente.eb_n0_teorica_db, 2)} dB: esa diferencia es la que ` +
      `separa los dos márgenes de enlace. El umbral de un receptor FSK real no está documentado.`,
    tipo: 'documentado',
  },
  {
    titulo: 'El conformado RRC mete la señal en el canal de 25 kHz',
    texto:
      `El ancho de banda ocupado al 99 % baja de ${es(avz.ancho_banda_nrz_hz / 1000)} kHz a ` +
      `${es(avz.ancho_banda_rrc_hz / 1000)} kHz. Con sincronización real (Costas + Gardner) la ` +
      `BPSK con RRC sigue la curva teórica desde 3 dB de Eb/N0; sin filtro adaptado los lazos no ` +
      `se sostienen.`,
    tipo: 'simulado',
  },
  {
    titulo: 'El FEC gana menos de lo que se decía',
    texto:
      `Comparado a igual Eb/N0 por bit de información, el código convolucional r=1/2 K=7 con ` +
      `Viterbi de decisión dura gana ${db(gBer.ganancia_db)} a BER ${gBer.ber_objetivo} y ` +
      `${db(gFer.ganancia_db)} en el umbral de FER ${es(gFer.fer_objetivo * 100, 0)} % de tramas ` +
      `AX.25. La cifra publicada antes era mayor porque comparaba a igual SNR por muestra, lo que ` +
      `da al código el doble de energía por bit de información. ` +
      `Con desvanecimiento Rice: ${avz.ganancia_codificacion_rice.estado}.`,
    tipo: 'simulado',
  },
  {
    titulo: 'El Doppler orbital es de ±10 kHz; lo que importa es el residual',
    texto:
      `En el paso analizado el Doppler recorre de ${es(paso.doppler_max_hz / 1000, 2)} a ` +
      `${es(paso.doppler_min_hz / 1000, 2)} kHz y cambia hasta ${es(paso.tasa_doppler_max_hz_s)} Hz/s. ` +
      `Un error de tiempo de 0,5 s en la predicción deja un residual de hasta ` +
      `${es(residual(0.5)?.residual_max_abs_hz ?? 0, 0)} Hz. El lazo de Costas del modelo absorbe 50 Hz ` +
      `sin pérdida apreciable y empieza a perder el enganche a 100 Hz.`,
    tipo: 'simulado',
  },
  {
    titulo: 'El rotor no limita el enlace',
    texto:
      `En un paso con culminación a ${es(est.elev_culminacion_deg, 0)}° el error máximo de ` +
      `apuntamiento es ${es(est.error_apuntamiento_max_deg, 2)}° y la pérdida asociada ` +
      `${es(est.perdida_apuntamiento_max_db, 2)} dB con un haz de 30°.`,
    tipo: 'simulado',
  },
  {
    titulo: 'El margen depende de supuestos, no de medidas',
    texto:
      `Variando a la vez los parámetros supuestos dentro de sus rangos (${mc.corridas.toLocaleString(
        'es-CO',
      )} corridas), el margen mínimo del paso queda entre ${es(mc.margen_min_db.p5)} y ` +
      `${es(mc.margen_min_db.p95)} dB (percentiles 5–95) y es positivo en el ` +
      `${es(mc.probabilidad_margen_min_positivo * 100, 0)} % de los casos. Un margen positivo aquí ` +
      `es una predicción del modelo: no hay medición del enlace que la confirme.`,
    tipo: 'simulado',
  },
  {
    titulo: 'Varias estaciones oyen la misma emisión',
    texto:
      `De ${rec.diversidad.emisiones_distintas_recibidas.toLocaleString('es-CO')} emisiones ` +
      `distintas recibidas, ${rec.diversidad.emisiones_multiestacion.toLocaleString('es-CO')} llegaron ` +
      `a dos o más estaciones. En las ventanas con varias estaciones, combinarlas recupera ` +
      `×${es(rec.diversidad.ganancia_por_combinacion ?? 0, 2)} respecto de la mejor estación sola. ` +
      `Es un resultado observacional, no una prueba de diversidad física del canal.`,
    tipo: 'derivado',
  },
  {
    titulo: 'Pérdida de paquetes medida con el contador de secuencia',
    texto:
      `Dentro de las ráfagas recibidas faltan el ` +
      `${es((rec.perdida_por_secuencia.global.perdida ?? 0) * 100, 1)} % de los paquetes ` +
      `(${rec.perdida_por_secuencia.global.paquetes_recibidos.toLocaleString('es-CO')} recibidos de ` +
      `${rec.perdida_por_secuencia.global.paquetes_emitidos_estimados.toLocaleString(
        'es-CO',
      )} estimados), bajo la hipótesis de que el contador sube uno por paquete emitido. ` +
      `${rec.perdida_por_secuencia.alcance}`,
    tipo: 'derivado',
  },
]

const MODELOS = [
  {
    nombre: 'Modelo básico',
    script: 'simular_enlace_rf_fsk_bpsk.py',
    descripcion:
      'Telemetría real → bits → BPSK/FSK a 8 muestras por símbolo → AWGN → demodulación con ' +
      'sincronización ideal → BER. Compara dos modelos de banda base; su FSK no es la forma de ' +
      'onda del satélite.',
  },
  {
    nombre: 'Modelo avanzado',
    script: 'simular_enlace_rf_bpsk_avanzado.py',
    descripcion:
      `RRC, Costas + Gardner, desvanecimiento Rice, Doppler residual, FEC convolucional y tramas ` +
      `AX.25. ${avz.configuraciones} configuraciones × ${avz.puntos_ebn0} valores de Eb/N0 × ` +
      `${r.procedencia.ensayos_por_punto} ensayos, sobre el mismo canal y las mismas semillas.`,
  },
  {
    nombre: 'Presupuesto de enlace y paso SGP4',
    script: 'calcular_link_budget.py · margen_paso_sgp4.py · modelo_estacion_terrena.py',
    descripcion:
      'Balance de potencia por elevación y a lo largo de un paso propagado con SGP4 desde el TLE ' +
      'versionado: margen, Doppler, seguimiento del rotor y sensibilidad a los supuestos.',
  },
  {
    nombre: 'Estimación de SNR y recepción real',
    script: 'estimar_snr_iq.py · tools/analizar_recepcion.py',
    descripcion:
      'Estimador M2M4 de Es/N0 sobre las muestras IQ, contrastado con la SNR conocida, y análisis ' +
      'observacional de las tramas recibidas por la red SatNOGS.',
  },
]

/* ── Tablas ───────────────────────────────────────────────────────────────── */

function TablaCurvas() {
  const filas = curva('rrc', 'awgn')
  const fec = curva('rrc_fec', 'awgn')
  const ax = curva('ax25', 'awgn')
  const axFec = curva('ax25_fec', 'awgn')
  const rice = curva('ax25', 'rice')
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] text-sm">
        <thead>
          <tr className="border-b border-line text-left label-caps">
            <th className="py-2 pr-3 text-right">Eb/N0</th>
            <th className="py-2 pr-3 text-right">BER teórica</th>
            <th className="py-2 pr-3 text-right">BER sin código</th>
            <th className="py-2 pr-3 text-right">BER con FEC</th>
            <th className="py-2 pr-3 text-right">FER AX.25</th>
            <th className="py-2 pr-3 text-right">FER AX.25 + FEC</th>
            <th className="py-2 text-right">FER AX.25, Rice</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((f, i) => (
            <tr key={f.ebn0_db} className="border-b border-line/60">
              <td className="py-2 pr-3 text-right tnum font-medium">{es(f.ebn0_db)} dB</td>
              <td className="py-2 pr-3 text-right tnum text-ink-soft">
                {tasa(f.ber_teorica_bpsk)}
              </td>
              <td className="py-2 pr-3 text-right tnum">{tasa(f.ber, f.ber_ic95_sup)}</td>
              <td className="py-2 pr-3 text-right tnum">{tasa(fec[i]?.ber, fec[i]?.ber_ic95_sup)}</td>
              <td className="py-2 pr-3 text-right tnum">
                {tasa(ax[i]?.fer)}{' '}
                <span className="text-xs text-ink-soft">
                  ({ax[i]?.ax25_frames_validos}/{ax[i]?.ax25_frames_tx})
                </span>
              </td>
              <td className="py-2 pr-3 text-right tnum">{tasa(axFec[i]?.fer)}</td>
              <td className="py-2 text-right tnum">{tasa(rice[i]?.fer)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TablaParametros() {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-line text-left label-caps">
            <th className="py-2 pr-3">Parámetro</th>
            <th className="py-2 pr-3 text-right">Valor</th>
            <th className="py-2 pr-3">Procedencia</th>
            <th className="py-2">Fuente</th>
          </tr>
        </thead>
        <tbody>
          {lb.parametros.map((p) => (
            <tr key={p.clave} className="border-b border-line/60 align-top">
              <td className="py-2 pr-3 font-mono text-xs">{p.clave}</td>
              <td className="py-2 pr-3 text-right tnum font-medium whitespace-nowrap">
                {p.valor.toLocaleString('es-CO')} {p.unidad}
              </td>
              <td className="py-2 pr-3">
                <EtiquetaTipo tipo={p.procedencia as Tipo} />
              </td>
              <td className="py-2 text-xs text-ink-soft">{p.fuente}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── Página ───────────────────────────────────────────────────────────────── */

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
            <strong className="font-semibold"> modela el enlace</strong>, y en el resto de la
            aplicación se{' '}
            <strong className="font-semibold">procesa lo que el satélite emitió de verdad</strong>.
            Las cifras de esta página son{' '}
            <strong className="font-semibold">resultados de modelo</strong>, no mediciones del
            enlace: cada una lleva su etiqueta. Corrida del modelo avanzado:{' '}
            {fechaUTC(r.procedencia.simulacion_avanzada_utc)} · código{' '}
            <span className="font-mono">{r.procedencia.commit_resultados}</span> · semilla{' '}
            {r.procedencia.semilla_base} · {r.procedencia.ensayos_por_punto} ensayos de{' '}
            {r.procedencia.bits_por_ensayo.toLocaleString('es-CO')} bits por punto.
          </Nota>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {METRICAS.map((m) => (
              <Card key={m.etiqueta} className="min-w-0">
                <div className="text-2xl font-bold leading-none text-navy-dark tnum">{m.valor}</div>
                <div className="label-caps mt-2">{m.etiqueta}</div>
                <p className="mt-1 text-xs text-ink-soft">{m.nota}</p>
                <div className="mt-2">
                  <EtiquetaTipo tipo={m.tipo} />
                </div>
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
        description="Cada texto se compone con los valores de la corrida vigente."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {HALLAZGOS.map((h) => (
            <Card key={h.titulo}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="font-semibold text-navy-dark">{h.titulo}</div>
                <EtiquetaTipo tipo={h.tipo} />
              </div>
              <p className="mt-2 text-sm leading-relaxed text-ink">{h.texto}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section
        title="BER y FER del modelo avanzado"
        description="Canal AWGN salvo la última columna. Eb/N0 por bit de información; receptor con Costas + Gardner."
      >
        <div className="space-y-4">
          <TablaCurvas />
          <p className="text-xs leading-snug text-ink-soft">
            «0 (&lt; x)» significa cero errores observados y x como cota superior al 95 % (Wilson):
            la muestra no permite afirmar una tasa menor. FER = tramas con FCS inválido o no
            recuperadas / tramas transmitidas; entre paréntesis, tramas válidas sobre transmitidas.
            Canal Rice: K = {avz.canal_rice.k_db} dB, dispersión Doppler{' '}
            {avz.canal_rice.dispersion_doppler_hz} Hz — {avz.canal_rice.respaldo}.
          </p>
        </div>
      </Section>

      <Section
        title="Parámetros del enlace y su procedencia"
        description="Qué valores están documentados para STRaND-1 y cuáles son supuestos de diseño de una estación hipotética."
      >
        <TablaParametros />
      </Section>

      <Section title="Limitaciones del modelo" description="Lo que estos resultados no cubren.">
        <Card>
          <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink">
            {avz.limitaciones.map((l) => (
              <li key={l}>{l}</li>
            ))}
            <li>{r.uplink.nota}.</li>
            <li>{paso.estacion}.</li>
          </ul>
        </Card>
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
              titulo: 'Auditoría del gemelo RF',
              texto: 'Hallazgos, causas raíz, cambios, matriz de trazabilidad y pendientes.',
              href: `${REPO}/blob/main/docs/AUDITORIA_GEMELO_RF.md`,
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
