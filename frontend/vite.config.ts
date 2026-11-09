import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/api':     'http://localhost:5001',
      '/chat':    'http://localhost:5001',
      '/refresh': 'http://localhost:5001',
      '/status':  'http://localhost:5001',
      '/rules':   'http://localhost:5001',
      '/label':   'http://localhost:5001',
    },
  },
  build: {
    outDir: '../data/dashboard/app',
    emptyOutDir: true,
  },
})
