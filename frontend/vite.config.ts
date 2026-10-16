import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Vite 配置。契约见 docs/CONTRACT.md §1.1、§6。
//
// 关于代理：这里把 "/api" 和 "/kv" 转发到后端 127.0.0.1:8000。
// 配了代理之后，浏览器只跟开发服务器（5173）打交道，请求由 Vite 在服务端转发给 8000，
// 于是浏览器视角里前后端同源，跨域（CORS）问题根本不会发生 —— 后端因此不需要加任何
// CORS 中间件。如果哪天绕开代理直接用 http://127.0.0.1:8000 请求，就会立刻撞上跨域，
// 那时候要么把代理配回来，要么在后端补 CORS，别两边都改。
//
// Tailwind 4 通过 @tailwindcss/vite 插件接入，不需要 tailwind.config.js，
// 也不需要 postcss.config.js —— 这两个文件是 Tailwind 3 的产物，建了反而会干扰。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 契约 §1.1：前端开发地址固定 5173
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/kv": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
