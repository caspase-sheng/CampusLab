---
title: node:test 跑 .ts 测试时，相对导入必须带扩展名
date: 2026-10-18
tags:
  - 前端
  - 测试
  - Node
draft: false
---

frontend 用 Node 内置的 node:test 跑测试，package.json 里的脚本是 `"test": "node --test \"tests/*.test.ts\""`。写第一个测试文件时，导入项目模块我按平时的习惯写成了不带扩展名的 `../src/lib/sorting`，跑起来直接报找不到模块。

## 要写全扩展名

Node 的类型剥离模式要求相对导入写全扩展名，所以 tests 里的导入是 `../src/lib/sorting.ts` 和 `../src/lib/graph.ts`，`.ts` 不能省。

对比一下就明显了：src 下的代码互相 import 是不带扩展名的，那是交给 Vite 解析的，Vite 自己会补全。测试这边跑在 Node 上，不走 Vite，就得按 Node 的规矩来。两套解析规则不一样，同一个相对路径在两处的写法就不一样。

## 测试为什么不能放 src 下

最省事的想法是把测试文件直接放 src 里，跟源文件挨着。但 frontend/tsconfig.json 的 `include` 只有 `["src"]`，放进 src 的测试会被 tsc 一起检查。tsc 的模块解析规则和 Node 对扩展名的要求正好打架——给 Node 写的带 `.ts` 的导入，到了 tsc 那边是另一套逻辑。两边都要照顾，写起来拧巴。

所以测试统一放在 frontend/tests/，这个目录不在 include 里，tsc 不管它。测试文件里的导入带 `.ts`，给 Node 的类型剥离模式用，两边各守自己的规矩，互不干扰。
