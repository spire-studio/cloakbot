import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const gatewayUrl = process.env.CLOAKBOT_WEBUI_GATEWAY_URL ?? 'http://127.0.0.1:18790'
const gatewayWsUrl = gatewayUrl.replace(/^http/, 'ws')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: gatewayUrl,
        changeOrigin: true,
      },
      '/ws': {
        target: gatewayWsUrl,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
