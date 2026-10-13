/**
 * Pestañas documentales del gemelo: subsistemas, estructura y procedencia.
 *
 * Todo lo que muestran estas pestañas es REFERENCIA DOCUMENTAL (lo que dicen
 * los documentos técnicos) salvo las lecturas de telemetría, que llegan por
 * `lecturas` desde la API y se rotulan como histórico real. Ningún valor de
 * referencia se usa para rellenar una lectura que falte.
 */

import type { LecturaGemelo } from '../../lib/api'
import {
  CLASE,
  COMPONENTES,
  DISCREPANCIAS,
  ESTRUCTURA_1U,
  FUENTE_ESTRUCTURA_1U,
  FUENTE_MISION,
  FUENTE_TELEMETRIA,
  MASA_KG,
  MASA_TOTALES,
  NO_DISPONIBLES,
  POTENCIA_PICO_W,
  POTENCIA_TOTALES,
  SUBSISTEMAS,
} from '../../data/referenciaStrand1'
import type { ClaseDato } from '../../data/referenciaStrand1'
import { FilaLectura, Sello } from './comunes'

const es = (v: number, d = 1) =>
  v.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d })

/* ── Subsistemas ──────────────────────────────────────────────────────────── */

export function PanelSubsistemas({
  lecturas, onVerEnModelo,
}: {
  lecturas: Map<string, LecturaGemelo>
  onVerEnModelo: (id: string) => void
}) {
  return (
    <div className="gd-grid">
      <div className="gd-nota">
        La descripción y los valores de diseño proceden del documento de la misión
        (<strong>{FUENTE_MISION.clave}</strong>). {FUENTE_MISION.aviso} Las lecturas son las del
        instante que marca el cursor de reproducción.
      </div>
      <div className="gd-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))' }}>
        {SUBSISTEMAS.map((s, i) => {
          const comps = COMPONENTES.filter((c) => c.subsistema === s.id)
          const campos = comps.flatMap((c) => c.campos)
          const presentes = campos.map((c) => lecturas.get(c)).filter(Boolean) as LecturaGemelo[]
          return (
            <section key={s.id} className="gd-panel" aria-labelledby={`sub-${s.id}`}>
              <h3 id={`sub-${s.id}`} className="gd-panel-titulo">
                <span>{i + 1}. {s.titulo}</span>
                <small>{comps.length} componente{comps.length === 1 ? '' : 's'} en el modelo</small>
              </h3>
              <p style={{ fontSize: 13 }}>{s.descripcion}</p>

              <div style={{ marginTop: 10 }}>
                <Sello clase="referencia" />
                <dl className="gd-dl" style={{ marginTop: 6 }}>
                  {s.referencia.map((r) => (
                    <div key={r.magnitud} style={{ display: 'contents' }}>
                      <dt>{r.magnitud}</dt>
                      <dd>{r.valor}</dd>
                    </div>
                  ))}
                </dl>
              </div>

              <div style={{ marginTop: 12 }}>
                <Sello clase={presentes.length ? 'historico' : 'no_disponible'} />
                <p className="gd-tarjeta-pie" style={{ fontSize: 12 }}>{s.telemetria}</p>
                {presentes.length > 0 && (
                  <div className="gd-tabla-scroll" style={{ marginTop: 6 }}>
                    <table className="gd-tabla">
                      <tbody>
                        {presentes.map((l) => <FilaLectura key={l.campo} l={l} />)}
                      </tbody>
                    </table>
                  </div>
                )}
                {campos.length > 0 && presentes.length === 0 && (
                  <p className="gd-vacio" style={{ fontSize: 12, marginTop: 6 }}>
                    Sin datos en este instante
                  </p>
                )}
              </div>

              <div className="gd-lista-comp" style={{ marginTop: 12 }}>
                {comps.map((c) => (
                  <button key={c.id} type="button" className="gd-comp" onClick={() => onVerEnModelo(c.id)}>
                    Ver en el modelo: {c.nombre}
                  </button>
                ))}
              </div>
            </section>
          )
        })}
      </div>

      <div className="gd-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))' }}>
        <section className="gd-panel">
          <h3 className="gd-panel-titulo">
            <span>Presupuesto de masa</span><small>tabla II del documento · kg con 10 % de margen</small>
          </h3>
          <table className="gd-tabla">
            <tbody>
              {MASA_KG.map((m) => (
                <tr key={m.subsistema}><td>{m.subsistema}</td><td className="num">{es(m.masa)}</td></tr>
              ))}
              <tr><td><strong>Masa seca</strong></td><td className="num">{es(MASA_TOTALES.seca)}</td></tr>
              <tr><td>Propelente</td><td className="num">{es(MASA_TOTALES.propelente)}</td></tr>
              <tr><td><strong>Masa de lanzamiento</strong></td><td className="num">{es(MASA_TOTALES.lanzamiento)}</td></tr>
            </tbody>
          </table>
          <p className="gd-tarjeta-pie"><Sello clase="referencia" /> Valores de diseño; la masa de vuelo no consta en el proyecto.</p>
        </section>
        <section className="gd-panel">
          <h3 className="gd-panel-titulo">
            <span>Demanda de potencia de pico</span><small>tabla III del documento · W</small>
          </h3>
          <table className="gd-tabla">
            <tbody>
              {POTENCIA_PICO_W.map((p) => (
                <tr key={p.componente}><td>{p.componente}</td><td className="num">{es(p.potencia)}</td></tr>
              ))}
              <tr><td>Margen</td><td className="num">{es(POTENCIA_TOTALES.margen)}</td></tr>
              <tr><td><strong>Pico total</strong></td><td className="num">{es(POTENCIA_TOTALES.pico)}</td></tr>
            </tbody>
          </table>
          <p className="gd-tarjeta-pie">
            <Sello clase="referencia" /> Consumo máximo previsto de cada equipo, no consumo medido. La
            baliza no permite calcular la potencia real.
          </p>
        </section>
      </div>
    </div>
  )
}

/* ── Estructura ───────────────────────────────────────────────────────────── */

export function PanelEstructura() {
  const estructura = SUBSISTEMAS.find((s) => s.id === 'estructura')!
  return (
    <div className="gd-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 400px), 1fr))' }}>
      <section className="gd-panel">
        <h3 className="gd-panel-titulo">
          <span>Estructura de STRaND-1</span><small>CubeSat 3U</small>
        </h3>
        <p style={{ fontSize: 13 }}>{estructura.descripcion}</p>
        <dl className="gd-dl" style={{ marginTop: 10 }}>
          {estructura.referencia.map((r) => (
            <div key={r.magnitud} style={{ display: 'contents' }}><dt>{r.magnitud}</dt><dd>{r.valor}</dd></div>
          ))}
        </dl>
        <p className="gd-tarjeta-pie"><Sello clase="referencia" /> {FUENTE_MISION.cita}</p>

        <div className="gd-nota gd-nota-ambar" style={{ marginTop: 12 }}>
          <strong>Análisis estructural propio: no existe.</strong> El proyecto no dispone de un modelo
          de elementos finitos de STRaND-1 ni de resultados de ensayo. Este módulo es documental; el
          análisis queda pendiente de validación.
        </div>
        <h4 className="gd-panel-titulo" style={{ marginTop: 14 }}><span>Verificaciones pendientes</span></h4>
        <ul style={{ fontSize: 12.5, paddingLeft: 18, listStyle: 'disc', color: 'var(--g-suave)' }}>
          {ESTRUCTURA_1U.pendienteStrand1.map((p) => <li key={p}>{p}</li>)}
        </ul>
      </section>

      <section className="gd-panel" style={{ borderStyle: 'dashed' }}>
        <h3 className="gd-panel-titulo">
          <span>{ESTRUCTURA_1U.titulo}</span><small>otro satélite · solo comparación</small>
        </h3>
        <div className="gd-nota gd-nota-rojo">
          <strong>No es STRaND-1.</strong> {ESTRUCTURA_1U.aviso}
        </div>
        <div className="gd-tabla-scroll" style={{ marginTop: 10 }}>
          <table className="gd-tabla">
            <thead><tr><th>Magnitud (estructura 1U)</th><th style={{ textAlign: 'right' }}>Valor publicado</th></tr></thead>
            <tbody>
              {ESTRUCTURA_1U.valores.map((v) => (
                <tr key={v.magnitud}>
                  <td>{v.magnitud}</td>
                  <td className="num">{v.valor}{v.unidad && ` ${v.unidad}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h4 className="gd-panel-titulo" style={{ marginTop: 14 }}><span>Limitaciones del estudio</span></h4>
        <ul style={{ fontSize: 12.5, paddingLeft: 18, listStyle: 'disc', color: 'var(--g-suave)' }}>
          {ESTRUCTURA_1U.limitaciones.map((l) => <li key={l}>{l}</li>)}
        </ul>
        <p className="gd-tarjeta-pie" style={{ marginTop: 10 }}>
          <Sello clase="referencia" /> {FUENTE_ESTRUCTURA_1U.cita}
        </p>
      </section>
    </div>
  )
}

/* ── Procedencia y discrepancias ──────────────────────────────────────────── */

export function PanelProcedencia({ fuente, fuenteCalibracion }: { fuente?: string; fuenteCalibracion?: string }) {
  return (
    <div className="gd-grid">
      <section className="gd-panel">
        <h3 className="gd-panel-titulo"><span>Clases de dato</span><small>cada valor de la página lleva una</small></h3>
        <div className="gd-tabla-scroll">
          <table className="gd-tabla">
            <tbody>
              {(Object.keys(CLASE) as ClaseDato[]).map((k) => (
                <tr key={k}>
                  <td style={{ whiteSpace: 'nowrap' }}><Sello clase={k} /></td>
                  <td>{CLASE[k].descripcion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="gd-tarjeta-pie" style={{ marginTop: 8 }}>
          Esta página no contiene datos simulados: no hay ningún modelo que genere telemetría. Las
          simulaciones del enlace están en «Simulación RF» y «Enlace RF», rotuladas allí.
        </p>
      </section>

      <section className="gd-panel">
        <h3 className="gd-panel-titulo"><span>Fuentes</span></h3>
        <dl className="gd-dl" style={{ gridTemplateColumns: 'minmax(8rem, auto) 1fr' }}>
          <dt>Telemetría</dt><dd style={{ textAlign: 'left' }}>{fuente ?? FUENTE_TELEMETRIA}</dd>
          <dt>Calibración</dt><dd style={{ textAlign: 'left' }}>{fuenteCalibracion ?? '—'}</dd>
          <dt>Satélite (3U)</dt><dd style={{ textAlign: 'left' }}>{FUENTE_MISION.cita} {FUENTE_MISION.aviso}</dd>
          <dt>Estructura 1U</dt><dd style={{ textAlign: 'left' }}>{FUENTE_ESTRUCTURA_1U.cita}</dd>
        </dl>
      </section>

      <section className="gd-panel">
        <h3 className="gd-panel-titulo">
          <span>Discrepancias detectadas</span><small>se conservan ambos valores, con su origen</small>
        </h3>
        <div className="gd-tabla-scroll">
          <table className="gd-tabla" style={{ minWidth: 760 }}>
            <thead>
              <tr><th>Asunto</th><th>En la aplicación</th><th>En el documento</th><th>Tratamiento</th></tr>
            </thead>
            <tbody>
              {DISCREPANCIAS.map((d) => (
                <tr key={d.asunto}>
                  <td><strong>{d.asunto}</strong></td><td>{d.aplicacion}</td><td>{d.documento}</td>
                  <td style={{ color: 'var(--g-suave)' }}>{d.tratamiento}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="gd-panel">
        <h3 className="gd-panel-titulo"><span>Parámetros no disponibles</span><small>y por qué</small></h3>
        <div className="gd-tabla-scroll">
          <table className="gd-tabla">
            <tbody>
              {NO_DISPONIBLES.map((n) => (
                <tr key={n.magnitud}>
                  <td>{n.magnitud}</td>
                  <td style={{ whiteSpace: 'nowrap' }} className="gd-t-gris"><span className="gd-sello">{n.estado}</span></td>
                  <td style={{ color: 'var(--g-suave)' }}>{n.motivo}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="gd-panel">
        <h3 className="gd-panel-titulo"><span>Monitorización, no control</span></h3>
        <p style={{ fontSize: 13, color: 'var(--g-suave)' }}>
          Esta página solo lee. No envía comandos al satélite ni a ningún equipo, no modifica la base
          de datos y no ejecuta maniobras. Los controles del modelo (plegar paneles, vista explotada,
          giro) cambian únicamente la representación en pantalla.
        </p>
      </section>
    </div>
  )
}
