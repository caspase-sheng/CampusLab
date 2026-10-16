// 站点级配置：导航、作者信息、社交链接都集中在这里。
// 布局和页面统一从这里读，改文案不用翻组件。

export interface NavItem {
  label: string;
  href: string;
}

export interface SocialLink {
  label: string;
  href: string;
}

export interface SiteConfig {
  /** 站点标题，用于 <title> 和页脚 */
  title: string;
  /** 一句话站点描述，用于 meta description 和首页 */
  description: string;
  /** 作者信息 */
  author: {
    name: string;
    role: string;
    bio: string;
    email: string;
  };
  /** 顶部导航项，顺序即展示顺序 */
  nav: NavItem[];
  /** 关于页展示的社交链接 */
  socials: SocialLink[];
  /** 关于页展示的技能列表 */
  skills: string[];
}

export const site: SiteConfig = {
  title: 'CampusLab 个人站',
  description:
    'CampusLab 后端开发者，记录全栈校园学习平台的设计、实现与踩坑。',
  author: {
    name: 'caspase-sheng',
    role: 'student',
    bio: '在做一个叫 CampusLab 的本地全栈校园学习平台：自研的 KV 存储引擎、课程表与 DDL 管理、算法可视化都塞在里面。平时习惯把实现里的取舍和踩过的坑写下来，也顺手记一些零散笔记。',
    email: 'thfu_ao@163.com',
  },
  nav: [
    { label: '首页', href: '/' },
    { label: '项目', href: '/projects' },
    { label: '博客', href: '/blog' },
    { label: '笔记', href: '/notes' },
    { label: '实验室', href: '/lab' },
    { label: '关于', href: '/about' },
  ],
  socials: [
    { label: 'GitHub', href: 'https://github.com/caspase-sheng/' },
    { label: 'Email', href: 'mailto:thfu_ao@163.com' },
  ],
  skills: [
    'Python / FastAPI / SQLAlchemy',
    'SQLite · 自研 Bitcask 风格 KV 存储',
    'TypeScript / React 19 / Vite',
    'Tailwind 4 · Astro',
    '追加写段文件与崩溃恢复、LRU 读缓存',
  ],
};

/** 每页给 <title> 加点前缀，避免所有页面标题都一样 */
export function pageTitle(page?: string): string {
  return page ? `${page} · ${site.title}` : site.title;
}
