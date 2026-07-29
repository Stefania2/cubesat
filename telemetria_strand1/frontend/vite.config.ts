import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import basicSsl from '@vitejs/plugin-basic-ssl'

/**
 * Modo visor: `VR=1 npm run dev -- --host`.
 *
 * WebXR solo se expone en **contexto seguro**. `localhost` cuenta como tal, asi
 * que en el equipo de desarrollo basta con HTTP; pero un visor conectado por la
 * red local abre `http://<ip>:5173`, que no lo es, y entonces `navigator.xr`
 * simplemente no existe --- el boton de entrar en VR se deshabilita y no hay
 * nada que depurar en el codigo, porque el navegador ni siquiera ofrece la API.
 *
 * Con VR=1 se sirve por HTTPS con un certificado autofirmado. El navegador del
 * visor avisara de que no es de confianza: hay que aceptarlo una vez. No se
 * activa por defecto porque `--host` publica el servidor en la red local y eso
 * debe ser una decision explicita, no un efecto secundario.
 *
 * La alternativa sin certificados es un tunel USB, que en un Quest se monta con
 * `adb reverse tcp:5173 tcp:5173`: el visor ve `localhost:5173`, que si es
 * contexto seguro. Requiere adb instalado, que en este equipo no lo esta.
 */
const modoVisor = process.env.VR === '1'

/**
 * Reparto de dependencias en chunks.
 *
 * El criterio no es el tamano sino **quien las necesita**. Three.js y la pila
 * de XR solo hacen falta en la pagina del gemelo digital; recharts, solo donde
 * hay graficas. Separandolas, quien entra al panel de tramas no descarga el
 * motor 3D, que es la mitad del peso.
 *
 * El reparto por si solo no basta: hace falta ademas que la pagina del gemelo
 * se cargue de forma diferida (`lazy` en App.tsx). Sin eso, el chunk de three
 * sigue siendo dependencia directa del arranque y el navegador lo pide igual,
 * solo que en dos peticiones en vez de una.
 */
function repartir(id: string): string | undefined {
  // El ayudante `__vitePreload` es un modulo virtual compartido. Si se deja al
  // criterio de Rollup acaba dentro del primer chunk con nombre que lo use ---
  // `three` --- y entonces el entry lo importa de forma **estatica** para
  // obtenerlo, arrastrando los dos megas de Three.js a todas las paginas y
  // anulando la carga diferida. Se ancla al chunk que siempre esta presente.
  if (id.includes('vite/preload-helper')) return 'react'

  if (!id.includes('node_modules')) return undefined

  // Las salas del emulador de XR llegan por `import()` dinamico y Rollup ya las
  // deja en chunks propios que el navegador solo pide si el emulador arranca
  // --- nunca en produccion, con `emulate: false`. Asignarlas a un chunk con
  // nombre las convertiria en carga obligatoria: son cinco megas.
  if (/[\\/]@pmndrs[\\/]xr[\\/].*(room|emulate)/.test(id)) return undefined

  if (/[\\/]node_modules[\\/](three|@react-three|@pmndrs)[\\/]/.test(id)) return 'three'
  if (/[\\/]node_modules[\\/](recharts|d3-|internmap|delaunator|robust-predicates)/.test(id)) return 'charts'
  if (/[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(id)) return 'react'

  // El resto se deja a Rollup. Un cajon de sastre `vendor` obliga a descargar
  // de golpe dependencias que solo usa una pagina, y ademas crea ciclos entre
  // chunks cuando ese cajon depende de uno de los nombrados.
  return undefined
}

export default defineConfig({
  plugins: [react(), tailwindcss(), ...(modoVisor ? [basicSsl()] : [])],
  build: {
    rollupOptions: { output: { manualChunks: repartir } },
    // Con el reparto hecho, el aviso por defecto de 500 kB solo delata el
    // chunk de three, que no se puede partir mas sin trocear la biblioteca.
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    proxy: {
      // El frontend habla siempre con rutas /api relativas; el proxy las
      // redirige al backend en desarrollo y evita configurar CORS por entorno.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
