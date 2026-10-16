// notes 接口。契约见 docs/CONTRACT.md §4.4。
// 四个函数都走 client.ts 的封装，这里只负责拼路径和请求体，不碰 fetch / 信封。

import { del, get, post, put } from "./client";
import type { Note, NoteCreate, NoteUpdate } from "./types";

/** GET /api/notes —— 当前用户全部笔记。 */
export function listNotes(): Promise<Note[]> {
  return get<Note[]>("/api/notes");
}

/** POST /api/notes —— 新建笔记，返回创建好的笔记。 */
export function createNote(payload: NoteCreate): Promise<Note> {
  return post<Note>("/api/notes", payload);
}

/** PUT /api/notes/{id} —— 部分更新，只更新 payload 里出现的字段。 */
export function updateNote(id: number, payload: NoteUpdate): Promise<Note> {
  return put<Note>(`/api/notes/${id}`, payload);
}

/**
 * DELETE /api/notes/{id} —— 删除笔记。
 *
 * 契约 §4.4 里删除的响应固定是 {"code": 0, "message": "ok", "data": null}，
 * data 恒为 null，拿不到被删的对象。所以返回类型是 void 而不是 Note。
 */
export function deleteNote(id: number): Promise<void> {
  return del<void>(`/api/notes/${id}`);
}
