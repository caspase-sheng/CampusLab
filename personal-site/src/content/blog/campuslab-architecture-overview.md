---
title: CampusLab 整体架构：三个独立子项目怎么拼成一个平台
description: 这个仓库为什么拆成 backend、frontend 和个人站三个子项目，它们靠什么联系，又有哪些东西刻意没有共享。
date: 2026-10-18
tags:
  - 架构
  - 项目结构
  - Astro
draft: false
---

这个仓库第一眼看上去有点散。根目录下并排躺着 backend、frontend、personal-site 三个子目录，谁也不住在谁的工程里。单点的技术笔记写多了，容易漏掉「它们整体是怎么拼起来的」，所以这篇专门回答为什么这么拆、彼此靠什么联系、哪些东西明明能共享却故意没共享。

## 三个子项目，各管各的

backend/ 是 FastAPI 应用，frontend/ 是 React 单页应用，personal-site/ 是 Astro 静态站，另外还有一个只放契约文档的 docs/。三者之间没有任何代码依赖：个人站不 import 前端的东西，前端不 import 后端的 Python，后端压根不知道前端存在。依赖清单也是分开的——backend/requirements.txt、frontend/package.json、personal-site/package.json 各记各的，某一边加个库不会把另外两边拖下水。

根目录上另有一批跨子项目的东西：README.md、dev.bat、dev.ps1、放三个启动子脚本的 scripts/，以及 .github/workflows/ 下的流水线。这些算是「共用」，但共用的只是流程，不是代码。

三边的技术栈也各成一派。后端是 FastAPI 0.115 + SQLAlchemy 2.0 + SQLite，迁移用 Alembic，鉴权用 python-jose 签 HS256 JWT、bcrypt 存密码。前端是 React 19 + TypeScript + Vite 7 + Tailwind 4，路由用 react-router。个人站是 Astro 5 + Tailwind 4，内容走 Astro 的内容集合，纯静态输出。

## 为什么必须在自己目录里启动

这是路径写死的结果，不是习惯问题。backend/app/core/config.py 里 DATABASE_URL 默认是 sqlite:///./campuslab.db，KV_DATA_DIR 默认是 data/kv，两个都是相对当前工作目录的路径。要是从仓库根带路径去起后端，程序会在仓库根建出一个 campuslab.db 和一份 data/kv，而不是落在 backend/ 里面。库和段文件就这么换了地方，肉眼一时半会儿还看不出来。所以后端、前端、个人站都各自 cd 进自己的目录再启动。

## 后端里有两条不搭界的链路

/api 这条走的是 FastAPI 路由 → SQLAlchemy ORM → SQLite，数据落在 campuslab.db。另有一条 /kv，走 FastAPI 路由 → 自研 KV 引擎 → 磁盘段文件，引擎代码就在 backend/app/kv/。两条链路不共享任何存储，backend/app/api/ 下的业务代码从来不调用 KV 引擎。

契约里本来打算把 JWT 黑名单塞进 KV，但没实现，现在退出登录只是把本地 token 清掉。KV 引擎是 Bitcask 风格的：段文件追加写，内存里维护一份 KeyDir 索引，外面套一层 LRU 读缓存，启动时按段文件编号升序重放一遍把状态恢复回来。

接口约定集中在 docs/CONTRACT.md，路由、请求响应结构、错误码、时间格式、鉴权、数据库表都在那。/api 下所有接口套同一个信封 {code, message, data}，code 为 0 才算成功。异常处理集中在一个文件里——backend/app/core/errors.py，按 request.url.path 分流：/api 下校验失败返回 422 信封，/kv 下返回 400，body 里只有 {"detail": "..."}。两条链路的错误形状不一样，是刻意的。

/api 这一侧的数据是分用户的。courses、deadlines、notes 三张表都带 user_id，查询一律拼 WHERE user_id = ?，这个值从 JWT 里解出来，请求体里没有 user_id 字段。按 id 取单条时同时带 id 和 user_id，查不到统一返回 404，不区分「这条不存在」还是「这条是别人的」，免得从状态码就能探出别人数据的存亡。

## 前端不直接连后端

开发时前端跑在 Vite dev server 的 5173 端口，后端在 8000。frontend/vite.config.ts 里配了 server.proxy，把 /api 和 /kv 都转发到 http://127.0.0.1:8000。浏览器全程只跟 5173 讲话，转发是 Vite 在服务端做的，所以浏览器视角里前后端同源，后端就不用加 CORS。这个代理只在 npm run dev 时存在，npm run build 出来的静态文件里没有它。

## 个人站为什么坚持独立

personal-site 是个纯静态的 Astro 站点，不连任何后端，也不调任何接口。它那个排序可视化用到的 sorting.ts，是从 frontend/src/lib/sorting.ts 复制过来的，两边各存一份，没有做成共享包。为了一两个组件去引入 monorepo 或 workspace 不划算，复制一份、改的时候手动对齐，在目前这个规模里更省事。

## CI、部署和测试规模

CI 在 .github/workflows/ci.yml，三个 job 并行跑：backend 跑 pytest，frontend 跑 build 加 node:test，personal-site 跑 build。个人站部署在 GitHub Pages 上，挂在仓库名对应的 /CampusLab 子路径下。因为带着这层子路径，站内所有绝对路径链接都得把前缀拼上去，代码里用一个 withBase() 统一处理，没有到处手写。后端和前端目前只在本地跑，没有部署。

测试上，后端 pytest 有 117 个用例；前端用 Node 自带的 node:test 写了 14 个，覆盖 src/lib/ 下的排序和图算法两个纯函数模块。个人站没有自动化测试。
