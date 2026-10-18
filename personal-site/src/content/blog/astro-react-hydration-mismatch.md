---
title: Astro 里嵌 React，初始数据不能是随机的
description: /lab 页里的排序演示组件，初始数组本来想用 randomArray 生成。可带 client 指令的 React 组件会先 SSR 再 hydrate，Math.random() 两端算出来不一样，React 直接报 hydration mismatch。最后把初始数组写死了。
date: 2026-10-18
tags:
  - Astro
  - React
  - 前端
draft: false
---

个人站是 Astro 的，/lab 页面里嵌了一个 React 组件 SortingDemo.tsx，挂载写法是 `<SortingDemo client:visible />`。这组件是个排序过程回放，柱状图的初始高度本该是随机数组。第一版我写的是 `randomArray(24)`，本地点着没看出问题，控制台在刷 hydration mismatch。

## 为什么随机就出问题

带 client 指令的 React 组件，Astro 会先在服务端把它渲染一遍（SSR），再把 HTML 送到浏览器，然后用同一份初始状态在浏览器里 hydrate。这两次渲染必须算出一模一样的结果，hydrate 才对得上。

`randomArray` 内部用的是 `Math.random()`。服务端那一次算出的一组数，和客户端那一次算出的另一组数，只要有一个位置不一样，两次的 DOM 就对不上。React 发现服务端给的标记和客户端算的不一致，报 hydration mismatch，严重时它会把这块整个重渲染。

根子不在随机本身，在于「同一份初始状态要在两个地方各算一次」。只要这个值是随机的，这两次就不可能相等，跟随机数的实现没关系。

## 改法：初始数组写死

初始数组改成写死的一组 24 个数，取值都在 5 到 100 之间。写死之后，服务端和客户端读的是同一个字面量，首屏两边算出来完全一致，没有 mismatch。

只有用户点「重置」或者拖数组大小时，才允许调 `randomArray`。这两个动作都发生在 hydrate 之后，是纯浏览器的交互，服务端这时候早就不参与了，也就无所谓两端一致不一致。

## 为什么用 client:visible 而不是 client:only

`client:only` 会让组件完全跳过 SSR，只在浏览器里渲染，那样确实绕开了 mismatch，代价是没有 JS 就什么都看不到。

初始数组写死之后这个代价就不必要了，所以这里用 `client:visible`：SSR 出来的首屏是稳定的，没有 mismatch，而且就算没加载到 JS，页面上也能看到一排柱子，只是按钮点不动。`client:visible` 的意思还有一层——组件进入视口时才 hydrate。演示组件不一定每次都被划到，晚点加载比首屏就拖一个组件下来合适。

## 排序逻辑是拷过来的一份

组件调的 `sorting.ts`，是从 frontend/src/lib/sorting.ts 复制过来的，两份内容一样。个人站不依赖 frontend 那个包，也没打算把两个项目耦合起来，所以只能拷一份，改的时候记得两边都要顾到。

## 定时器这块

组件里有两个 useEffect，分工不一样。一个负责按速度推进 index，每帧走一步；另一个负责在到达最后一帧时自动把播放停掉。两个都读 index，但关心的边界不同，所以拆开写，没合并成一个。

定时器只依赖 playing / speed 这两个值，index 那边用的是函数式更新。这样 index 每帧都在变，也不会把定时器反复重建——否则每推进一帧就重建一次 interval，播放起来会一顿一顿的。
