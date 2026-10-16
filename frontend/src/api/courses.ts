// courses 接口。契约见 docs/CONTRACT.md §4.2。
// 四个函数都走 client.ts 的封装，这里只负责拼路径和请求体，不碰 fetch / 信封。

import { del, get, post, put } from "./client";
import type { Course, CourseCreate, CourseUpdate } from "./types";

/** GET /api/courses —— 当前用户全部课程。 */
export function listCourses(): Promise<Course[]> {
  return get<Course[]>("/api/courses");
}

/** POST /api/courses —— 新建课程，返回创建好的课程。 */
export function createCourse(payload: CourseCreate): Promise<Course> {
  return post<Course>("/api/courses", payload);
}

/** PUT /api/courses/{id} —— 部分更新，只更新 payload 里出现的字段。 */
export function updateCourse(
  id: number,
  payload: CourseUpdate
): Promise<Course> {
  return put<Course>(`/api/courses/${id}`, payload);
}

/**
 * DELETE /api/courses/{id} —— 删除课程。
 *
 * 契约 §4.2 里删除的响应固定是 {"code": 0, "message": "ok", "data": null}，
 * data 恒为 null，拿不到被删的对象。所以返回类型是 void 而不是 Course，
 * 别让调用方以为还能读到返回值。
 */
export function deleteCourse(id: number): Promise<void> {
  return del<void>(`/api/courses/${id}`);
}
