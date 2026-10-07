import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dashboard STRAND-1: el frontend habla con /api y /ws relativos; el proxy los
// envia al backend FastAPI en desarrollo (puerto por defecto 8150).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8150', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8150', ws: true, changeOrigin: true },
    },
  },
  preview: {
    port: 4175,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8150', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8150', ws: true, changeOrigin: true },
    },
  },
})