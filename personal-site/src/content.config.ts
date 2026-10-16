// 内容集合定义（Astro 5 Content Layer API）。
//
// 为什么用 Content Layer 而不是老的 src/content/config.ts 写法？
//   1. 老写法要求目录结构和集合名绑死（src/content/blog 只能叫 blog），
//      Content Layer 用 glob() 显式声明 pattern + base，目录可以自由挪。
//   2. glob loader 在构建时把 md 文件读进数据仓库，页面用 getCollection 取就行，
//      所以「新增一个 .md 文件就自动出现在对应列表里，不用改任何代码」——
//      页面从来不是写死清单，而是运行时遍历集合的结果，这就是本站的核心设计。
//   3. schema 校验在构建期完成，frontmatter 写错字段会直接 build 失败，而不是静默漏掉。
//
// 注意：这个文件在 src/ 下，不是 src/content/ 下。Astro 5 规定集合配置放在 src/content.config.ts。

import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// 三个集合共用的字段，抽出来避免重复。
// draft 默认 false：不写 draft 的文章视为已发布。
// 为什么要有 draft 过滤？写作中或不想公开的稿子标 draft: true，
// 列表页和详情页都会把它过滤掉，等于「文件还在，但站点上看不到」。

const baseFields = {
  title: z.string(),
  date: z.coerce.date(),
  tags: z.array(z.string()).default([]),
  draft: z.boolean().default(false),
};

// 项目：多了 description / repo / demo 三个可选展示字段
const projects = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/projects' }),
  schema: z.object({
    ...baseFields,
    description: z.string(),
    repo: z.string().url().optional(),
    demo: z.string().url().optional(),
  }),
});

// 博客：description 用于列表页摘要
const blog = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/blog' }),
  schema: z.object({
    ...baseFields,
    description: z.string(),
  }),
});

// 笔记：偏碎片记录，不强制 description
const notes = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/notes' }),
  schema: z.object({
    ...baseFields,
  }),
});

export const collections = { projects, blog, notes };
