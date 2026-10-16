// deadlines 接口。契约见 docs/CONTRACT.md §4.3。
// 四个函数都走 client.ts 的封装，这里只负责拼路径和请求体，不碰 fetch / 信封。

import { del, get, post, put } from "./client";
import type { Deadline, DeadlineCreate, DeadlineUpdate } from "./types";

/** GET /api/deadlines —— 当前用户全部 DDL。 */
export function listDeadlines(): Promise<Deadline[]> {
  return get<Deadline[]>("/api/deadlines");
}

/** POST /api/deadlines —— 新建 DDL，返回创建好的 DDL。 */
export function createDeadline(payload: DeadlineCreate): Promise<Deadline> {
  return post<Deadline>("/api/deadlines", payload);
}

/** PUT /api/deadlines/{id} —— 部分更新，只更新 payload 里出现的字段。 */
export function updateDeadline(
  id: number,
  payload: DeadlineUpdate
): Promise<Deadline> {
  return put<Deadline>(`/api/deadlines/${id}`, payload);
}

/**
 * DELETE /api/deadlines/{id} —— 删除 DDL。
 *
 * 契约 §4.3 里删除的响应固定是 {"code": 0, "message": "ok", "data": null}，
 * data 恒为 null，拿不到被删的对象。所以返回类型是 void 而不是 Deadline，
 * 别让调用方以为还能读到返回值。
 */
export function deleteDeadline(id: number): Promise<void> {
  return del<void>(`/api/deadlines/${id}`);
}
