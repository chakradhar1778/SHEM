import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Dev server forwards /api (REST + WebSocket) to the SHEM backend,
  // so the app can use same-origin URLs and no CORS setup is needed.
  const backend = env.SHEM_BACKEND_URL || 'http://127.0.0.1:8000'
  const proxy = { '/api': { target: backend, changeOrigin: true, ws: true } }
  // Optional HTTPS (e.g. mkcert certs) so phones on the LAN get a secure
  // context: needed for installing the PWA and for the microphone.
  const https = env.SHEM_HTTPS_CERT && env.SHEM_HTTPS_KEY
    ? { cert: readFileSync(env.SHEM_HTTPS_CERT), key: readFileSync(env.SHEM_HTTPS_KEY) }
    : undefined
  // host: true → listen on all interfaces so other devices on the Wi-Fi can connect.
  return {
    plugins: [react()],
    server: { host: true, https, proxy },
    preview: { host: true, https, proxy },
  }
})
