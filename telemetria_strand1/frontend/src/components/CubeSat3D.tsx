/**
 * FASE 6 --- Modelo 3D simplificado de STRaND-1, y FASE 7 --- su enlace a los datos.
 *
 * El modelo es un 3U (10 x 10 x 30 cm) a escala, con cuerpo, cuatro paneles
 * solares desplegados, dos antenas de latiguillo UHF y unos testigos por
 * subsistema. No pretende ser fiel al satelite real: pretende que cada cosa
 * que cambia de color en pantalla corresponda a un dato que existe.
 *
 * De ahi la regla que gobierna todo este archivo: **ningun elemento visual se
 * mueve si no hay una lectura que lo mueva**. Un panel sin corriente medida se
 * pinta en gris de «sin dato», no en verde. Una lectura vieja se atenua en
 * proporcion a su edad. Es lo que separa un gemelo digital de una animacion
 * bonita: el gris tiene que ser visible, porque la mayor parte del tiempo el
 * satelite no esta diciendo nada.
 *
 * La rotacion es el unico elemento SINTETICO, y esta rotulado como tal en la
 * interfaz: la telemetria de STRaND-1 no incluye actitud. Los magnetometros
 * dan la direccion del campo en ejes cuerpo --- dato real --- pero eso fija
 * dos grados de libertad, no tres, asi que se usa para inclinar el modelo y el
 * giro restante es un barrido constante.
 */

import { Canvas, useFrame } from '@react-three/fiber'
import { Html, OrbitControls, Stars } from '@react-three/drei'
import { useMemo, useRef } from 'react'
import type { Group } from 'three'
import type { EstadoCubeSat, LecturaGemelo } from '../lib/api'

/** Color del cuerpo segun el diagnostico vigente. */
const COLOR_ESTADO: Record<EstadoCubeSat, string> = {
  NOMINAL: '#22c55e',
  ADVERTENCIA: '#f59e0b',
  CRITICO: '#ef4444',
  INSTRUMENTACION_PERDIDA: '#a855f7',
  SIN_REFERENCIA: '#64748b',
}

/** Gris reservado a «no hay dato». Nunca se usa para un valor real. */
const SIN_DATO = '#3f4654'

/** Corriente de panel, en mA, que se considera plena iluminacion. */
const CORRIENTE_PLENA = 520

/** Los seis paneles que STRaND-1 si emite, con su sitio en el modelo. */
const PANELES = [
  { campo: 'adc1_py_array_current', pos: [0, 0.9, 0], rot: [0, 0, 0], eje: '+Y' },
  { campo: 'adc4_my_array_current', pos: [0, -0.9, 0], rot: [0, 0, Math.PI], eje: '-Y' },
  { campo: 'adc7_mx_array_current', pos: [-0.9, 0, 0], rot: [0, 0, Math.PI / 2], eje: '-X' },
  { campo: 'adc13_px_array_current', pos: [0.9, 0, 0], rot: [0, 0, -Math.PI / 2], eje: '+X' },
] as const

interface Props {
  estado: EstadoCubeSat
  lecturas: LecturaGemelo[]
  girando: boolean
}

/** Indexa las lecturas por campo para no recorrer el array en cada malla. */
function usarIndice(lecturas: LecturaGemelo[]) {
  return useMemo(() => {
    const m = new Map<string, LecturaGemelo>()
    lecturas.forEach((l) => m.set(l.campo, l))
    return m
  }, [lecturas])
}

/** Opacidad que corresponde a la edad de una lectura: lo viejo se desvanece. */
function opacidadPorEdad(l: LecturaGemelo | undefined): number {
  if (!l) return 0.25
  if (l.frescura === 'fresca') return 1
  if (l.frescura === 'vieja') return 0.6
  return 0.3
}

function Panel({ lectura, pos, rot }: {
  lectura: LecturaGemelo | undefined
  pos: readonly [number, number, number]
  rot: readonly [number, number, number]
}) {
  // La corriente medida gobierna el brillo: es el dato real mas directo que
  // tenemos de que un panel esta iluminado.
  const fraccion = lectura ? Math.min(1, Math.max(0, lectura.valor / CORRIENTE_PLENA)) : 0
  const color = lectura ? '#1e3a8a' : SIN_DATO
  const emision = lectura ? fraccion * 0.9 : 0

  return (
    <mesh position={pos as unknown as [number, number, number]}
          rotation={rot as unknown as [number, number, number]}>
      <boxGeometry args={[1.4, 0.04, 2.6]} />
      <meshStandardMaterial
        color={color}
        emissive="#60a5fa"
        emissiveIntensity={emision}
        transparent
        opacity={opacidadPorEdad(lectura)}
        metalness={0.4}
        roughness={0.3}
      />
    </mesh>
  )
}

function Antena({ x }: { x: number }) {
  return (
    <mesh position={[x, -1.7, 0]} rotation={[0, 0, x > 0 ? -0.25 : 0.25]}>
      <cylinderGeometry args={[0.02, 0.02, 1.3, 8]} />
      <meshStandardMaterial color="#cbd5e1" metalness={0.9} roughness={0.2} />
    </mesh>
  )
}

/** Testigo de un subsistema: encendido solo si hay lectura que lo encienda. */
function Testigo({ lectura, pos }: {
  lectura: LecturaGemelo | undefined
  pos: [number, number, number]
}) {
  const encendido = lectura !== undefined && lectura.valor > 0
  return (
    <mesh position={pos}>
      <sphereGeometry args={[0.09, 16, 16]} />
      <meshStandardMaterial
        color={encendido ? '#22c55e' : SIN_DATO}
        emissive={encendido ? '#22c55e' : '#000000'}
        emissiveIntensity={encendido ? opacidadPorEdad(lectura) : 0}
      />
    </mesh>
  )
}

function Satelite({ estado, lecturas, girando }: Props) {
  const grupo = useRef<Group>(null)
  const indice = usarIndice(lecturas)

  // Inclinacion a partir de los magnetometros --- dato REAL --- y giro
  // constante para el grado de libertad que la telemetria no fija.
  const mx = indice.get('magnetometer_x')?.valor ?? 0
  const mz = indice.get('magnetometer_z')?.valor ?? 0
  const escala = 800000
  const inclinacion = Math.atan2(mz / escala, mx / escala || 1)

  useFrame((_, dt) => {
    if (grupo.current && girando) grupo.current.rotation.y += dt * 0.25
  })

  const color = COLOR_ESTADO[estado] ?? SIN_DATO
  const critico = estado === 'CRITICO' || estado === 'INSTRUMENTACION_PERDIDA'

  return (
    <group ref={grupo} rotation={[inclinacion * 0.35, 0, 0]}>
      {/* Cuerpo 3U: 1 x 1 x 3 unidades = 10 x 10 x 30 cm a escala */}
      <mesh>
        <boxGeometry args={[1, 3, 1]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={critico ? 0.55 : 0.18}
          metalness={0.6}
          roughness={0.35}
        />
      </mesh>

      {PANELES.map((p) => (
        <Panel key={p.campo} lectura={indice.get(p.campo)} pos={p.pos} rot={p.rot} />
      ))}

      <Antena x={0.35} />
      <Antena x={-0.35} />

      {/* Testigos de subsistemas conmutables, en la cara +Z */}
      <Testigo lectura={indice.get('switch_1_ppt_1_2_corriente')} pos={[0.3, 1.2, 0.55]} />
      <Testigo lectura={indice.get('switch_5_digi_wi9c_corriente')} pos={[0, 1.2, 0.55]} />
      <Testigo lectura={indice.get('switch_7_reaction_wheels_corriente')} pos={[-0.3, 1.2, 0.55]} />

      {critico && (
        <Html center position={[0, 2.2, 0]}>
          <div className="rounded bg-red-600/90 px-2 py-1 text-xs font-semibold whitespace-nowrap text-white">
            {estado.replace(/_/g, ' ')}
          </div>
        </Html>
      )}
    </group>
  )
}

export function CubeSat3D({ estado, lecturas, girando }: Props) {
  return (
    <Canvas camera={{ position: [5, 2.5, 5], fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={['#070b14']} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[6, 5, 4]} intensity={1.6} />
      <directionalLight position={[-5, -3, -4]} intensity={0.3} color="#60a5fa" />
      <Stars radius={60} depth={30} count={1200} factor={3} fade />
      <Satelite estado={estado} lecturas={lecturas} girando={girando} />
      <OrbitControls enablePan={false} minDistance={3.5} maxDistance={14} />
    </Canvas>
  )
}
