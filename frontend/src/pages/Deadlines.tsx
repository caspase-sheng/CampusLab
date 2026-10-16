// DDL 页：列表 + 增删改查。契约见 docs/CONTRACT.md §4.3。
//
// 页面加载时同时拉 DDL 列表和课程列表：DDL 列表决定页面成败，课程列表只用来把
// course_id 翻成课程名。所以课程列表请求单独 catch 掉，失败了也不影响 DDL 显示，
// 关联课程那一列退回「未关联」。

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { listCourses } from "../api/courses";
import {
  createDeadline,
  deleteDeadline,
  listDeadlines,
  updateDeadline,
} from "../api/deadlines";
import type { Course, Deadline, DeadlineCreate } from "../api/types";
import { formatDateTime } from "../utils/datetime";

/** DDL 状态只有这两种取值（契约 §5.3）。 */
type DeadlineStatus = "pending" | "done";

/** 状态的中文文案。 */
const STATUS_LABELS: Record<string, string> = {
  pending: "待办",
  done: "已完成",
};

export default function Deadlines() {
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // editing 为 null 表示新建，非 null 表示正在编辑这条 DDL；showForm 控制面板显隐。
  const [editing, setEditing] = useState<Deadline | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 表单字段。course_id 用空串表示「不关联」，提交时再转成 null（见 handleSubmit）。
  const [title, setTitle] = useState("");
  const [dueTime, setDueTime] = useState("");
  const [courseId, setCourseId] = useState("");
  const [status, setStatus] = useState<DeadlineStatus>("pending");

  // course.id → course.name 的查表，列表里把 course_id 翻成课程名用。
  const courseNameMap = useMemo(
    () => new Map(courses.map((course) => [course.id, course.name])),
    [courses]
  );

  /** 拉一次 DDL 列表；顺带刷新课程列表（失败也不影响 DDL 显示）。 */
  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [list, courseList] = await Promise.all([
        listDeadlines(),
        // 课程只用来显示名字，挂了就退化成空列表，让 course_id 兜底显示「未关联」，
        // 不把整个页面的加载判成失败。
        listCourses().catch(() => [] as Course[]),
      ]);
      setDeadlines(list);
      setCourses(courseList);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "加载 DDL 失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** 打开新建表单：字段回到默认值。 */
  function openCreate() {
    setEditing(null);
    setFormError(null);
    setTitle("");
    setDueTime("");
    setCourseId("");
    setStatus("pending");
    setShowForm(true);
  }

  /** 打开编辑表单：用这条 DDL 的现有值预填。 */
  function openEdit(deadline: Deadline) {
    setEditing(deadline);
    setFormError(null);
    setTitle(deadline.title);
    // 后端返回的是带秒的串（如 "2026-10-20T23:59:00"），而 datetime-local 的 value
    // 只认分钟精度 "YYYY-MM-DDTHH:mm"。直接塞带秒的串，浏览器会判成非法值并把输入框
    // 清空，用户看到的就是「截止时间莫名其妙没了」。统一截到分钟再填。
    setDueTime(deadline.due_time.slice(0, 16));
    setCourseId(deadline.course_id === null ? "" : String(deadline.course_id));
    setStatus(deadline.status === "done" ? "done" : "pending");
    setShowForm(true);
  }

  /** 关闭表单并清掉编辑态。 */
  function closeForm() {
    setShowForm(false);
    setEditing(null);
    setFormError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const trimmedTitle = title.trim();
    if (trimmedTitle === "") {
      setFormError("标题不能为空");
      return;
    }
    if (dueTime === "") {
      setFormError("请选择截止时间");
      return;
    }

    // due_time 直接发 datetime-local 产出的 "YYYY-MM-DDTHH:mm"，不加 "Z" 也不加时区
    // 偏移：后端存的是 naive 时间（契约 §1.4），带上时区后语义就变了（会被当成某个
    // UTC 时刻，落库/显示都会平移）。原样发，前端显示的和后端存的才对得上。
    //
    // course_id 选「不关联」时显式传 null，不是空串也不是省略字段：契约里它是可空外键，
    // 传 null 才是「解除关联」；传空串会被后端当成无效的 int 直接 422。
    const payload: DeadlineCreate = {
      title: trimmedTitle,
      due_time: dueTime,
      course_id: courseId === "" ? null : Number(courseId),
      status,
    };

    setSubmitting(true);
    try {
      if (editing !== null) {
        await updateDeadline(editing.id, payload);
      } else {
        await createDeadline(payload);
      }
      closeForm();
      // 保存成功后重新拉列表最省事，不用在本地手动拼一份新的 deadlines。
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "保存失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (editing === null) {
      return;
    }
    if (!window.confirm("确定删除这条 DDL？")) {
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await deleteDeadline(editing.id);
      closeForm();
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "删除失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  /** 点一下快速切换状态：pending ↔ done，只发 status 这一个字段。 */
  async function toggleStatus(deadline: Deadline) {
    const next: DeadlineStatus = deadline.status === "done" ? "pending" : "done";
    try {
      const updated = await updateDeadline(deadline.id, { status: next });
      // 只替换这一行，不整表重拉，避免整个列表闪一下加载态。
      setDeadlines((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "更新状态失败");
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">DDL</h1>
        <button
          type="button"
          onClick={openCreate}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white transition-colors hover:bg-slate-700"
        >
          新建 DDL
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-lg border border-slate-200 bg-white p-5"
        >
          <h2 className="text-lg font-medium text-slate-900">
            {editing !== null ? "编辑 DDL" : "新建 DDL"}
          </h2>

          {formError !== null && (
            <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
              {formError}
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1 block text-sm text-slate-600" htmlFor="ddl-title">
                标题
              </label>
              <input
                id="ddl-title"
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="ddl-due">
                截止时间
              </label>
              <input
                id="ddl-due"
                type="datetime-local"
                required
                value={dueTime}
                onChange={(e) => setDueTime(e.target.value)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="ddl-course">
                关联课程
              </label>
              <select
                id="ddl-course"
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              >
                <option value="">不关联</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="ddl-status">
                状态
              </label>
              <select
                id="ddl-status"
                value={status}
                onChange={(e) => setStatus(e.target.value as DeadlineStatus)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              >
                <option value="pending">待办</option>
                <option value="done">已完成</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "保存中…" : "保存"}
            </button>
            <button
              type="button"
              onClick={closeForm}
              disabled={submitting}
              className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              取消
            </button>

            {editing !== null && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={submitting}
                className="ml-auto rounded bg-red-600 px-4 py-2 text-sm text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                删除
              </button>
            )}
          </div>

          <p className="text-xs text-slate-500">
            删除 DDL 不会影响关联的课程。
          </p>
        </form>
      )}

      {loading ? (
        <p className="text-slate-500">加载中…</p>
      ) : loadError !== null ? (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
          {loadError}
        </p>
      ) : deadlines.length === 0 ? (
        <p className="text-sm text-slate-500">还没有 DDL，点右上角新建一条</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {deadlines.map((deadline) => {
            const isDone = deadline.status === "done";
            return (
              <li
                key={deadline.id}
                onClick={() => openEdit(deadline)}
                className="flex cursor-pointer items-center gap-4 px-4 py-3 transition-colors hover:bg-slate-50"
              >
                <div className="min-w-0 flex-1">
                  <div
                    className={
                      isDone
                        ? "truncate font-medium text-slate-400 line-through"
                        : "truncate font-medium text-slate-900"
                    }
                  >
                    {deadline.title}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                    <span>{formatDateTime(deadline.due_time)}</span>
                    <span>
                      {deadline.course_id === null
                        ? "未关联"
                        : courseNameMap.get(deadline.course_id) ?? "未关联"}
                    </span>
                  </div>
                </div>

                <span
                  className={
                    isDone
                      ? "shrink-0 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-400"
                      : "shrink-0 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700"
                  }
                >
                  {STATUS_LABELS[deadline.status] ?? deadline.status}
                </span>

                <button
                  type="button"
                  onClick={(e) => {
                    // 行点击是「进编辑」，这个按钮是「切状态」，别让事件冒泡上去也打开表单。
                    e.stopPropagation();
                    void toggleStatus(deadline);
                  }}
                  className="shrink-0 rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 transition-colors hover:border-slate-900 hover:bg-slate-100"
                >
                  {isDone ? "标记待办" : "标记完成"}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
