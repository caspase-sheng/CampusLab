---
title: tsc -b 和 --noEmit 不能一起用
date: 2026-10-18
tags:
  - TypeScript
  - 构建
  - Vite
draft: false
---

frontend/package.json 里的 typecheck 脚本，原来写的是 `"tsc -b --noEmit"`，跑不起来。后来改成了 `"tsc -b"`。

报错是这个：

```
TS6310: Referenced project '...tsconfig.node.json' may not disable emit.
```

原因在 `-b` 这个开关。`tsc -b` 是构建模式，它不是只检查当前这个文件，而是会顺着 tsconfig.json 里的 `references` 去构建被引用的项目。frontend/tsconfig.node.json 是 `composite: true`，而 composite 项目不允许禁用 emit——`--noEmit` 一传，就撞上这条规则。

其实也不需要传。根 tsconfig.json 自己已经写了 `noEmit: true`：

```json
"noEmit": true,
"tsBuildInfoFile": "./node_modules/.tmp/tsconfig.tsbuildinfo",
```

所以 `tsc -b` 对根项目本来就是只检查不输出，`--noEmit` 是多余的。去掉之后类型检查照跑，`"tsc -b && vite build"` 里第一步也顺了。

至于 tsconfig.node.json 那边，既然 composite 必须 emit，就把产物丢到一个没人看的地方：

```json
"outDir": "./node_modules/.tmp/tsconfig.node",
```

反正只是过一遍类型检查，生成的文件没人用。根项目的增量缓存也一并指到 node_modules 里（`tsBuildInfoFile`），免得仓库根目录冒出一个 tsconfig.tsbuildinfo。
