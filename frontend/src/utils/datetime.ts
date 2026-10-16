// 时间格式化的公共小工具，DDL 页和笔记页共用，避免两处各写一份。

/**
 * 把后端返回的 ISO 串格式化成 "YYYY-MM-DD HH:mm"。
 *
 * 为什么不用 ``toLocaleString``：它输出什么格式取决于浏览器 / 系统语言和区域
 * 设置，同一份代码在 Chrome 和 Firefox、在中文和英文环境下显示的串都不一样，
 * 手点验收时对不上。这里手工拼字段，输出恒定。
 *
 * 为什么按本地时间取字段：后端存的是 naive 时间（不带时区，如
 * "2026-10-20T23:59:00"，契约 §1.4），JS 的 ``new Date("2026-10-20T23:59:00")``
 * 按规范会把这种不带时区的串当成**本地时间**解析，于是 getFullYear / getMonth
 * 这一组本地取值读出来就等于后端存的那个字面值，前后端对得上，不会整段平移。
 */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}
