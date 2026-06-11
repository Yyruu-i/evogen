import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': '/src' },
  },
  server: {
    port: 5174,
    proxy: {
      '/api': 'http://localhost:8100',
      '/api/v1/ws': { target: 'ws://localhost:8100', ws: true },
    },
  },
})
