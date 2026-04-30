import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 55343,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:55342',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:55342',
        ws: true,
      },
    },
  },
})
