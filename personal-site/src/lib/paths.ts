/**
 * 把站内绝对路径拼上部署 base。
 *
 * 部署在 GitHub Pages 子路径（/CampusLab/）时，href="/lab" 会指向域名根、
 * 而不是仓库子路径，必须拼上前缀；本地开发时 base 是 '/'，拼完还是原样。
 *
 * 用 import.meta.env.BASE_URL 而不是读 process.env：前者是 Astro 在构建时
 * 注入的常量，开发/生产两边都正确，也不需要把环境变量暴露到客户端。
 */
export function withBase(path: string): string {
  // BASE_URL 形如 '/CampusLab/' 或 '/'，末尾一定带斜杠，先去掉再拼
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  // path 一定是 '/' 开头的站内路径
  return `${base}${path}`;
}
