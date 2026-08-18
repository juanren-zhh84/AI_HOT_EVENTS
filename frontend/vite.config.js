// frontend/vite.config.js
// Vite 构建配置。
import { defineConfig } from 'vite' // Vite 配置函数。
import vue from '@vitejs/plugin-vue' // Vue 单文件组件插件。

export default defineConfig({
  plugins: [vue()], // 启用 Vue 插件。
  base: './', // 构建产物使用相对路径，保证由 FastAPI 的 /admin 托管时资源能正确加载。
  server: {
    port: 5173, // 开发服务器端口。
    proxy: {
      '/api': 'http://127.0.0.1:8000', // 开发时把 /api 请求代理到本地后端，避免跨域。
    },
  },
  build: {
    outDir: 'dist', // 构建产物目录，FastAPI 会托管这个目录。
  },
})
