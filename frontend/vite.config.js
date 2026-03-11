import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../dist',   // ← output to project root/dist instead of frontend/dist
    emptyOutDir: true,
  }
})
