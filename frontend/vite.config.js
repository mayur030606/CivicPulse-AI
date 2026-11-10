import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Read .env from the repository root so backend and frontend share one file.
  envDir: '..',
  server: {
    port: 5173,
    proxy: {
      // Dev proxy: avoids CORS while keeping the frontend origin clean.
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
})
