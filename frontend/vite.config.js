import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // 前端用同源路径(/api、/ws),这样生产环境由 FastAPI 一起 serve、
  // 走 network.dorafmon.com 时不会去找浏览器自己的 localhost。
  // dev 时 Vite 在 5173,这里把这两条代理到 8000 的后端,保住原来的开发流程。
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
