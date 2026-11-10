import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const backend = process.env.VITE_BACKEND ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': backend,
      '/uploads': backend,
    },
  },
})
