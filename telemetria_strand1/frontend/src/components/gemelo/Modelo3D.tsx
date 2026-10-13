/**
 * Modelo 3D de STRaND-1 (CubeSat 3U) para el gemelo digital.
 *
 * Qué es: una representación a escala de la configuración general que describe
 * el documento de la misión (Kenyon, Bridges et al., 2011): chasis 3U, dos
 * paneles solares de 30 × 10 cm abisagrados en las aristas largas, dos
 * monopolos que salen por el costado y la pila de tarjetas PC104.
 *
 * Qué no es: un modelo CAD ni de fabricación. La forma y el orden de las
 * tarjetas en la pila son ESQUEMÁTICOS —el documento no los fija— y así se
 * rotula en la interfaz.
 *
 * Reglas que gobiernan este archivo:
 *   1. Ningún color de estado sin un dato que lo respalde. Un componente sin
 *      telemetría se pinta en neutro; nunca en verde.
 *   2. El modelo no adopta ninguna orientación derivada de datos: STRaND-1 no
 *      transmite actitud. El giro opcional es de presentación.
 *   3. El despliegue de paneles y antenas es una animación conceptual: la
 *      baliza no informa del estado de despliegue.
 *
 * Escala: 1 unidad = 10 cm. Ejes del modelo: Y es el eje largo del 3U. La
 * correspondencia con los ejes cuerpo del documento no está documentada con
 * precisión suficiente y no se afirma.
 */

import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { GizmoHelper, GizmoViewport, Html, OrbitControls } from '@react-three/drei'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Group, Mesh } from 'three'
import { MathUtils } from 'three'
import type { LecturaGemelo } from '../../lib/api'
import { COMPONENTES } from '../../data/referenciaStrand1'

export type ModoVista = 'exterior' | 'interior' | 'explotada'
export type Camara = 'isometrica' | 'frontal' | 'lateral' | 'superior'

/** Estado visual de un componente, deducido solo de sus lecturas. */
export type EstadoComponente = 'sin_telemetria' | 'sin_lectura' | 'con_lectura' | 'sin_medida'

interface Props {
  lecturas: LecturaGemelo[]
  modo: ModoVista
  camara: Camara
  desplegado: boolean
  giro: boolean
  etiquetas: boolean
  seleccion: string | null
  onSeleccion: (id: string | null) => void
}

/* ── Paleta: neutra por omisión, color solo con dato ──────────────────────── */

const COLOR = {
  chasis: '#8793a4',
  tarjeta: '#1f5a4c',
  celda: '#1f3f8f',
  metal: '#aeb9c7',
  seleccion: '#22d3ee',
  sin_telemetria: '#566173',
  sin_lectura: '#566173',
  con_lectura: '#38bdf8',
  sin_medida: '#f59e0b',
} as const

export function estadoDeComponente(id: string, lecturas: Map<string, LecturaGemelo>): EstadoComponente {
  const comp = COMPONENTES.find((c) => c.id === id)
  if (!comp || comp.campos.length === 0) return 'sin_telemetria'
  const presentes = comp.campos.map((c) => lecturas.get(c)).filter(Boolean) as LecturaGemelo[]
  if (presentes.length === 0) return 'sin_lectura'
  // Calibrables: si todas las que tienen recta valen su ordenada, no hay medida.
  const calibrables = presentes.filter(
    (l) => ['calibrado', 'canal_sin_medida', 'pendiente_de_validacion'].includes(l.validacion?.estado ?? ''),
  )
  if (calibrables.length > 0 && calibrables.every((l) => l.validacion?.estado === 'canal_sin_medida'))
    return 'sin_medida'
  return 'con_lectura'
}

/** Lo reciente se ve pleno; lo viejo, atenuado. */
function intensidad(id: string, lecturas: Map<string, LecturaGemelo>): number {
  const comp = COMPONENTES.find((c) => c.id === id)
  const presentes = (comp?.campos ?? []).map((c) => lecturas.get(c)).filter(Boolean) as LecturaGemelo[]
  if (presentes.length === 0) return 0
  const mejor = presentes.reduce((a, b) => (a.edad_s <= b.edad_s ? a : b))
  return mejor.frescura === 'fresca' ? 1 : mejor.frescura === 'vieja' ? 0.55 : 0.25
}

/* ── Pila de tarjetas: orden ESQUEMÁTICO ──────────────────────────────────── */

interface Tarjeta {
  id: string
  y: number
  alto: number
  /** Componentes que no son una tarjeta PC104 llevan otra forma. */
  forma?: 'tarjeta' | 'telefono' | 'deposito' | 'ruedas'
}

const PILA: Tarjeta[] = [
  { id: 'radio', y: 1.28, alto: 0.07 },
  { id: 'obc', y: 1.08, alto: 0.07 },
  { id: 'eps', y: 0.84, alto: 0.2 },
  { id: 'cubesense', y: 0.58, alto: 0.07 },
  { id: 'ruedas', y: 0.36, alto: 0.2, forma: 'ruedas' },
  { id: 'gps', y: 0.13, alto: 0.07 },
  { id: 'hpc', y: -0.07, alto: 0.07 },
  { id: 'telefono', y: -0.42, alto: 0.5, forma: 'telefono' },
  { id: 'ppt', y: -0.92, alto: 0.3 },
  { id: 'resistojet', y: -1.3, alto: 0.21, forma: 'deposito' },
]

const SEPARACION_EXPLOTADA = 2.1

/* ── Piezas ───────────────────────────────────────────────────────────────── */

function useSeleccionable(id: string, onSeleccion: (id: string | null) => void) {
  const [encima, setEncima] = useState(false)
  useEffect(() => {
    document.body.style.cursor = encima ? 'pointer' : 'auto'
    return () => {
      document.body.style.cursor = 'auto'
    }
  }, [encima])
  return {
    encima,
    eventos: {
      onClick: (e: { stopPropagation: () => void }) => {
        e.stopPropagation()
        onSeleccion(id)
      },
      onPointerOver: (e: { stopPropagation: () => void }) => {
        e.stopPropagation()
        setEncima(true)
      },
      onPointerOut: () => setEncima(false),
    },
  }
}

function Etiqueta({ id, visible }: { id: string; visible: boolean }) {
  if (!visible) return null
  const comp = COMPONENTES.find((c) => c.id === id)
  return (
    <Html center style={{ pointerEvents: 'none' }} zIndexRange={[5, 0]}>
      <div className="gd-etiqueta3d">
        {comp?.nombre ?? id}
        {comp?.geometria === 'aproximada' && <span> · esquemático</span>}
      </div>
    </Html>
  )
}

function PiezaPila({
  t, lecturas, modo, seleccion, etiquetas, onSeleccion,
}: {
  t: Tarjeta
  lecturas: Map<string, LecturaGemelo>
  modo: ModoVista
  seleccion: string | null
  etiquetas: boolean
  onSeleccion: (id: string | null) => void
}) {
  const ref = useRef<Group>(null)
  const { encima, eventos } = useSeleccionable(t.id, onSeleccion)
  const estado = estadoDeComponente(t.id, lecturas)
  const elegido = seleccion === t.id
  const destino = modo === 'explotada' ? t.y * SEPARACION_EXPLOTADA : t.y

  useFrame((_, dt) => {
    if (ref.current) ref.current.position.y = MathUtils.damp(ref.current.position.y, destino, 6, dt)
  })

  const borde = elegido ? COLOR.seleccion : COLOR[estado]
  const brillo = elegido ? 0.9 : estado === 'con_lectura' || estado === 'sin_medida'
    ? 0.25 + 0.55 * intensidad(t.id, lecturas)
    : 0

  return (
    <group ref={ref} position={[0, t.y, 0]} {...eventos}>
      {t.forma === 'telefono' ? (
        <>
          {/* Bandeja y teléfono: 119 × 60 × 11,5 mm aprox., de canto */}
          <mesh position={[0, 0, -0.12]}>
            <boxGeometry args={[0.6, 1.15, 0.12]} />
            <meshStandardMaterial color="#0c1016" metalness={0.5} roughness={0.35} />
          </mesh>
          <mesh position={[0, 0, -0.055]}>
            <boxGeometry args={[0.52, 0.98, 0.012]} />
            <meshStandardMaterial color="#0b1220" emissive={borde} emissiveIntensity={brillo * 0.5} />
          </mesh>
        </>
      ) : t.forma === 'deposito' ? (
        <mesh>
          <boxGeometry args={[0.75, t.alto, 0.75]} />
          <meshStandardMaterial color="#9aa5b4" metalness={0.4} roughness={0.5} />
        </mesh>
      ) : t.forma === 'ruedas' ? (
        <>
          <mesh>
            <boxGeometry args={[0.86, 0.05, 0.86]} />
            <meshStandardMaterial color={COLOR.tarjeta} roughness={0.7} />
          </mesh>
          {[[0.2, 0.07, 0.2, 0], [-0.2, 0.07, 0.2, 1], [0, 0.07, -0.22, 2]].map(([x, y, z, eje]) => (
            <mesh key={eje} position={[x, y, z]}
                  rotation={eje === 0 ? [0, 0, 0] : eje === 1 ? [Math.PI / 2, 0, 0] : [0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.13, 0.13, 0.07, 24]} />
              <meshStandardMaterial color={COLOR.metal} metalness={0.4} roughness={0.45} />
            </mesh>
          ))}
        </>
      ) : (
        <mesh>
          <boxGeometry args={[0.88, t.alto, 0.88]} />
          <meshStandardMaterial color={COLOR.tarjeta} roughness={0.7} metalness={0.1} />
        </mesh>
      )}

      {/* Marco de estado: el único elemento que cambia con la telemetría */}
      <mesh>
        <boxGeometry args={[0.93, Math.max(0.02, t.forma === 'telefono' ? 0.02 : t.alto * 0.25), 0.93]} />
        <meshStandardMaterial
          color={borde}
          emissive={borde}
          emissiveIntensity={brillo}
          transparent
          opacity={encima || elegido ? 0.95 : 0.6}
        />
      </mesh>
      <group position={[0.95, 0, 0.5]}>
        <Etiqueta id={t.id} visible={elegido || (etiquetas && modo === 'explotada')} />
      </group>
    </group>
  )
}

function PanelAla({
  id, lado, desplegado, modo, seleccion, etiquetas, onSeleccion,
}: {
  id: string
  lado: 1 | -1
  desplegado: boolean
  modo: ModoVista
  seleccion: string | null
  etiquetas: boolean
  onSeleccion: (id: string | null) => void
}) {
  const bisagra = useRef<Group>(null)
  const { encima, eventos } = useSeleccionable(id, onSeleccion)
  const elegido = seleccion === id
  // Plegado: el panel descansa sobre la cara lateral. Desplegado: coplanario
  // con la cara frontal, como «alas».
  const angulo = desplegado ? 0 : (lado * Math.PI) / 2
  const fuera = modo === 'explotada' ? 0.35 : 0

  useFrame((_, dt) => {
    if (!bisagra.current) return
    bisagra.current.rotation.y = MathUtils.damp(bisagra.current.rotation.y, angulo, 4, dt)
    bisagra.current.position.x = MathUtils.damp(bisagra.current.position.x, lado * (0.5 + fuera), 6, dt)
  })

  return (
    <group ref={bisagra} position={[lado * 0.5, 0, 0.52]} {...eventos}>
      <group position={[lado * 0.5, 0, 0]}>
        <mesh>
          <boxGeometry args={[1, 3, 0.03]} />
          <meshStandardMaterial
            color={elegido ? '#1e3a6e' : COLOR.celda}
            emissive={elegido || encima ? COLOR.seleccion : '#000000'}
            emissiveIntensity={elegido ? 0.35 : encima ? 0.15 : 0}
            metalness={0.3}
            roughness={0.5}
          />
        </mesh>
        {/* Seis celdas de 4 × 7 cm por panel, según el documento */}
        {[-1.1, -0.66, -0.22, 0.22, 0.66, 1.1].map((y) => (
          <mesh key={y} position={[0, y, 0.017]}>
            <planeGeometry args={[0.7, 0.4]} />
            <meshStandardMaterial color="#12275f" metalness={0.35} roughness={0.45} />
          </mesh>
        ))}
        <Etiqueta id={id} visible={elegido || (etiquetas && modo === 'explotada')} />
      </group>
    </group>
  )
}

function Antena({
  lado, largo, y, desplegado,
}: { lado: 1 | -1; largo: number; y: number; desplegado: boolean }) {
  const ref = useRef<Mesh>(null)
  // Recogida en su caja o extendida. Animación conceptual.
  const escala = desplegado ? 1 : 0.04
  useFrame((_, dt) => {
    if (!ref.current) return
    ref.current.scale.x = MathUtils.damp(ref.current.scale.x, escala, 4, dt)
    ref.current.position.x = lado * (0.5 + (largo * ref.current.scale.x) / 2)
  })
  return (
    <mesh ref={ref} position={[lado * 0.5, y, -0.45]}>
      <boxGeometry args={[largo, 0.06, 0.008]} />
      <meshStandardMaterial color={COLOR.metal} metalness={0.4} roughness={0.45} />
    </mesh>
  )
}

function Chasis({
  modo, seleccion, etiquetas, onSeleccion, desplegado,
}: {
  modo: ModoVista
  seleccion: string | null
  etiquetas: boolean
  desplegado: boolean
  onSeleccion: (id: string | null) => void
}) {
  const { eventos } = useSeleccionable('chasis', onSeleccion)
  const antenas = useSeleccionable('antenas', onSeleccion)
  const elegido = seleccion === 'chasis'
  const abierto = modo !== 'exterior'
  return (
    <group>
      <mesh {...(abierto ? {} : eventos)}>
        <boxGeometry args={[1, 3, 1]} />
        <meshStandardMaterial
          color={COLOR.chasis}
          emissive={elegido ? COLOR.seleccion : '#000000'}
          emissiveIntensity={elegido ? 0.25 : 0}
          metalness={0.35}
          roughness={0.55}
          transparent
          opacity={abierto ? 0.07 : 1}
          depthWrite={!abierto}
        />
      </mesh>
      {/* Rieles del estándar CubeSat en las cuatro aristas largas */}
      {[[0.48, 0.48], [-0.48, 0.48], [0.48, -0.48], [-0.48, -0.48]].map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 0, z]} {...eventos}>
          <boxGeometry args={[0.085, 3.14, 0.085]} />
          <meshStandardMaterial color="#b4bfcd" metalness={0.4} roughness={0.5} />
        </mesh>
      ))}
      {/* Paneles menores montados en el cuerpo: dorsal y hacia la Tierra.
          El documento los menciona sin dar medidas: tamaño aproximado. */}
      {!abierto && (
        <>
          <mesh position={[0, 0.2, -0.508]}>
            <planeGeometry args={[0.8, 1.6]} />
            <meshStandardMaterial color={COLOR.celda} metalness={0.6} roughness={0.3} side={2} />
          </mesh>
          <mesh position={[0, -1.508, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <planeGeometry args={[0.8, 0.8]} />
            <meshStandardMaterial color={COLOR.celda} metalness={0.6} roughness={0.3} side={2} />
          </mesh>
        </>
      )}
      {/* Cajas modulares de antena y monopolos: λ/4 de 70 cm ≈ 17 cm y de 2 m ≈ 51 cm */}
      <group {...antenas.eventos}>
        <mesh position={[0, 1.42, -0.42]}>
          <boxGeometry args={[0.9, 0.1, 0.14]} />
          <meshStandardMaterial
            color="#2a3140"
            emissive={seleccion === 'antenas' ? COLOR.seleccion : '#000000'}
            emissiveIntensity={seleccion === 'antenas' ? 0.5 : 0}
          />
        </mesh>
        <Antena lado={1} largo={1.7} y={1.42} desplegado={desplegado} />
        <Antena lado={-1} largo={5.1} y={1.42} desplegado={desplegado} />
        <group position={[0, 1.6, -0.42]}>
          <Etiqueta id="antenas" visible={seleccion === 'antenas' || (etiquetas && modo === 'explotada')} />
        </group>
      </group>
      <group position={[0, -1.75, 0]}>
        <Etiqueta id="chasis" visible={elegido} />
      </group>
    </group>
  )
}

/* ── Cámara y escena ──────────────────────────────────────────────────────── */

const POSICIONES: Record<Camara, [number, number, number]> = {
  isometrica: [4.2, 2.6, 6.4],
  frontal: [0, 0, 8.5],
  lateral: [8.5, 0, 0],
  superior: [0, 8.5, 0.001],
}

function ControlCamara({ camara }: { camara: Camara }) {
  const { camera } = useThree()
  // Solo al cambiar de vista: no pisa lo que el usuario haya orbitado después.
  useEffect(() => {
    const [x, y, z] = POSICIONES[camara]
    camera.position.set(x, y, z)
    camera.lookAt(0, 0, 0)
  }, [camara, camera])
  return null
}

function Satelite(p: Props) {
  const grupo = useRef<Group>(null)
  const indice = useMemo(() => {
    const m = new Map<string, LecturaGemelo>()
    p.lecturas.forEach((l) => m.set(l.campo, l))
    return m
  }, [p.lecturas])

  useFrame((_, dt) => {
    if (grupo.current && p.giro) grupo.current.rotation.y += dt * 0.2
  })

  return (
    <group ref={grupo}>
      <Chasis modo={p.modo} seleccion={p.seleccion} etiquetas={p.etiquetas}
              desplegado={p.desplegado} onSeleccion={p.onSeleccion} />
      <PanelAla id="panel_ala_a" lado={1} desplegado={p.desplegado} modo={p.modo}
                seleccion={p.seleccion} etiquetas={p.etiquetas} onSeleccion={p.onSeleccion} />
      <PanelAla id="panel_ala_b" lado={-1} desplegado={p.desplegado} modo={p.modo}
                seleccion={p.seleccion} etiquetas={p.etiquetas} onSeleccion={p.onSeleccion} />
      {p.modo !== 'exterior' &&
        PILA.map((t) => (
          <PiezaPila key={t.id} t={t} lecturas={indice} modo={p.modo} seleccion={p.seleccion}
                     etiquetas={p.etiquetas} onSeleccion={p.onSeleccion} />
        ))}
    </group>
  )
}

export function Modelo3D(props: Props) {
  return (
    <Canvas
      camera={{ position: POSICIONES.isometrica, fov: 42 }}
      dpr={[1, 2]}
      onPointerMissed={() => props.onSeleccion(null)}
      aria-label="Modelo tridimensional esquemático de STRaND-1"
    >
      <color attach="background" args={['#060b14']} />
      {/*
        Nada de esta escena carga recursos externos: son mallas y luces
        generadas en el cliente, así que no hace falta frontera de suspensión.
        Si se añade algo que sí cargue (un glTF, una fuente), hay que envolverlo
        en su propio `Suspense` o React ocultará la página entera al esperar.
      */}
      {/* Sin mapa de entorno, un metal muy pulido se ve negro: los materiales
          son poco metálicos y la luz es sobre todo difusa. */}
      <ambientLight intensity={1.1} />
      <hemisphereLight args={['#dbeafe', '#0b1220', 0.9]} />
      <directionalLight position={[6, 7, 8]} intensity={2.4} />
      <directionalLight position={[-7, 3, 6]} intensity={1.1} />
      <directionalLight position={[-4, -3, -6]} intensity={0.7} color="#7dd3fc" />
      <ControlCamara camara={props.camara} />
      <Satelite {...props} />
      <OrbitControls enablePan minDistance={3} maxDistance={22} makeDefault />
      <GizmoHelper alignment="bottom-left" margin={[58, 58]}>
        <GizmoViewport axisColors={['#f87171', '#4ade80', '#60a5fa']} labelColor="#0b1220" />
      </GizmoHelper>
    </Canvas>
  )
}
