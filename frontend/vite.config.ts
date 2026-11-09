import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Dev server forwards /api (REST + WebSocket) to the SHEM backend,
  // so the app can use same-origin URLs and no CORS setup is needed.
  const backend = env.SHEM_BACKEND_URL || 'http://127.0.0.1:8000'
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': { target: backend, changeOrigin: true, ws: true },
      },
    },
    preview: {
      proxy: {
        '/api': { target: backend, changeOrigin: true, ws: true },
      },
    },
  }
})
