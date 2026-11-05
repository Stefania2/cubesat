/**
 * Globo terrestre con un pase de STRaND-1 sobre una estación de SatNOGS.
 *
 * Escala: el radio de la Tierra vale 1 (6371 km). Los 775 km de altura de la
 * órbita quedan en 1,12: se ve a simple vista lo cerca que pasa el satélite.
 * Ejes de three.js con Y hacia arriba (polo norte).
 */

import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import tierra from '../../data/tierra_110m.json'

const RADIO_KM = 6371

export interface PuntoPaso {
  t: string
  lat: number
  lon: number
  alt_km: number
  az: number
  el: number
  dist_km: number
  doppler_hz: number
  en_ventana: boolean
}

export function aXYZ(lat: number, lon: number, altKm = 0): [number, number, number] {
  const r = 1 + altKm / RADIO_KM
  const f = (lat * Math.PI) / 180
  const l = (lon * Math.PI) / 180
  return [r * Math.cos(f) * Math.cos(l), r * Math.sin(f), -r * Math.cos(f) * Math.sin(l)]
}

/** Corta una polilínea donde cruza el antimeridiano para no trazar una cuerda. */
function tramos(puntos: { lat: number; lon: number; alt_km?: number }[], elevar = 0.003) {
  const salida: [number, number, number][][] = []
  let actual: [number, number, number][] = []
  puntos.forEach((p, i) => {
    if (i > 0 && Math.abs(p.lon - puntos[i - 1].lon) > 180) {
      if (actual.length > 1) salida.push(actual)
      actual = []
    }
    actual.push(aXYZ(p.lat, p.lon, (p.alt_km ?? 0) + elevar * RADIO_KM))
  })
  if (actual.length > 1) salida.push(actual)
  return salida
}

function Tierra() {
  const contornos = useMemo(
    () =>
      (tierra.anillos as number[][][]).flatMap((anillo) =>
        tramos(anillo.map(([lon, lat]) => ({ lat, lon })), 0.001),
      ),
    [],
  )
  const reticula = useMemo(() => {
    const lineas: [number, number, number][][] = []
    for (let lat = -60; lat <= 60; lat += 30) {
      lineas.push(Array.from({ length: 73 }, (_, i) => aXYZ(lat, -180 + i * 5, 2)))
    }
    for (let lon = -180; lon < 180; lon += 30) {
      lineas.push(Array.from({ length: 37 }, (_, i) => aXYZ(-90 + i * 5, lon, 2)))
    }
    return lineas
  }, [])
  return (
    <group>
      <mesh>
        <sphereGeometry args={[1, 64, 64]} />
        <meshStandardMaterial color="#0b2a44" roughness={0.9} metalness={0.05} />
      </mesh>
      {reticula.map((l, i) => (
        <Line key={`r${i}`} points={l} color="#1d3b57" lineWidth={0.6} transparent opacity={0.6} />
      ))}
      {contornos.map((l, i) => (
        <Line key={`c${i}`} points={l} color="#5fb3a1" lineWidth={1.1} />
      ))}
    </group>
  )
}

function Satelite({ posicion, oye }: { posicion: [number, number, number]; oye: boolean }) {
  const ref = useRef<THREE.Mesh>(null)
  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.8
  })
  return (
    <group position={posicion}>
      <mesh ref={ref}>
        <boxGeometry args={[0.018, 0.018, 0.05]} />
        <meshStandardMaterial color={oye ? '#FBBF24' : '#E3EAF3'} emissive={oye ? '#a16207' : '#334155'} />
      </mesh>
      <Html center style={{ pointerEvents: 'none' }}>
        <div className="-mt-6 whitespace-nowrap rounded bg-black/70 px-1.5 py-0.5 text-[11px] font-semibold text-warn">
          STRaND-1
        </div>
      </Html>
    </group>
  )
}

export function Globo3D({
  puntos,
  orbita,
  estacion,
  indice,
  tramasIdx,
}: {
  puntos: PuntoPaso[]
  orbita: { lat: number; lon: number; alt_km: number }[]
  estacion: { nombre: string; lat: number; lng: number; alt_m: number }
  indice: number
  /** Índices de `puntos` donde llegó una trama. */
  tramasIdx: number[]
}) {
  const pEst = useMemo(() => aXYZ(estacion.lat, estacion.lng, 0.004 * RADIO_KM), [estacion])
  const lineaOrbita = useMemo(() => tramos(orbita, 0), [orbita])
  const lineaPase = useMemo(() => tramos(puntos.filter((p) => p.en_ventana), 0), [puntos])
  const huella = useMemo(
    () => tramos(puntos.filter((p) => p.en_ventana).map((p) => ({ lat: p.lat, lon: p.lon })), 0.002),
    [puntos],
  )
  const i = Math.min(Math.max(0, Math.floor(indice)), puntos.length - 1)
  const actual = puntos[i]
  const pSat = aXYZ(actual.lat, actual.lon, actual.alt_km)
  const oye = actual.el > 0 && actual.en_ventana
  const recibidas = tramasIdx.filter((k) => k <= i)

  // Cámara de partida: sobre la estación, algo alejada.
  const camara = useMemo(() => {
    const [x, y, z] = aXYZ(estacion.lat, estacion.lng, 0)
    return [x * 3.2, y * 3.2 + 0.4, z * 3.2] as [number, number, number]
  }, [estacion])

  return (
    <Canvas camera={{ position: camara, fov: 40, near: 0.01, far: 100 }} dpr={[1, 2]}>
      <color attach="background" args={['#05080f']} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[5, 3, 5]} intensity={1.1} />
      <Tierra />
      {lineaOrbita.map((l, k) => (
        <Line key={`o${k}`} points={l} color="#475569" lineWidth={1} dashed dashSize={0.02} gapSize={0.015} />
      ))}
      {huella.map((l, k) => (
        <Line key={`h${k}`} points={l} color="#A78BFA" lineWidth={1.2} transparent opacity={0.7} />
      ))}
      {lineaPase.map((l, k) => (
        <Line key={`p${k}`} points={l} color="#22D3EE" lineWidth={2.4} />
      ))}
      {recibidas.map((k) => (
        <mesh key={`t${k}`} position={aXYZ(puntos[k].lat, puntos[k].lon, puntos[k].alt_km)}>
          <sphereGeometry args={[0.006, 10, 10]} />
          <meshBasicMaterial color="#34D399" />
        </mesh>
      ))}
      <mesh position={pEst}>
        <coneGeometry args={[0.012, 0.035, 12]} />
        <meshStandardMaterial color="#F87171" emissive="#7f1d1d" />
      </mesh>
      <Html position={pEst} center style={{ pointerEvents: 'none' }}>
        <div className="mt-6 whitespace-nowrap rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-semibold text-danger">
          Estación {estacion.nombre}
        </div>
      </Html>
      <Line
        points={[pEst, pSat]}
        color={oye ? '#34D399' : '#64748b'}
        lineWidth={oye ? 2 : 1}
        dashed={!oye}
        dashSize={0.02}
        gapSize={0.02}
      />
      <Satelite posicion={pSat} oye={oye} />
      <OrbitControls enablePan={false} minDistance={1.3} maxDistance={8} makeDefault />
    </Canvas>
  )
}
