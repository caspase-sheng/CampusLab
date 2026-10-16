// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';

// 说明：这里是 Tailwind 4 的接法。
// Tailwind 4 把「配置」搬进了 CSS（@import "tailwindcss"），所以：
//   1. 不再需要 @astrojs/tailwind 集成（那是 Tailwind 3 时代的产物）；
//   2. 也不再需要 tailwind.config.js / postcss.config.js；
//   3. 只要把官方的 Vite 插件挂到 vite.plugins 上，Astro 的构建就走 Tailwind 了。
//
// react() 是给 /lab 页那个排序演示组件用的：Astro 本身不认 .tsx，
// 挂上这个集成后 .tsx 会走 React 的编译流程，页面里才能写 <SortingDemo />。
// 注意这两个是不同的东西：react 是 Astro 集成（进 integrations），
// tailwindcss 是 Vite 插件（进 vite.plugins），位置不能混。
export default defineConfig({
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
  },
});
