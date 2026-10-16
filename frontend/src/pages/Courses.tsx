// 课程页：周视图 + 增删改查。契约见 docs/CONTRACT.md §4.2。
//
// 周视图用 CSS Grid 手搭：行是 30 分钟一格，从 08:00 到 22:00 共 28 格；
// 列是时间轴 + 周一..周日。行数是算出来的，Tailwind 类名写不出动态行数，
// 所以 grid-template-columns / rows 用 inline style 写死，其余用 Tailwind。
//
// 已知限制（本次不做）：
// - 同一时段、同一天的课程会叠在一起，不做避让；谁排在数组后面谁盖在上面。
// - week_range（如 "1-16"）只在表单里编辑、在卡片上展示，不参与渲染计算 ——
//   没有「当前是第几周」这个概念，没法把「第 3 周的课」限制在某几周里显示。

import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  createCourse,
  deleteCourse,
  listCourses,
  updateCourse,
} from "../api/courses";
import type { Course, CourseCreate } from "../api/types";

// 时间轴范围：08:00 - 22:00，每格 30 分钟。
const START_MINUTES = 8 * 60; // 08:00
const END_MINUTES = 22 * 60; // 22:00
const SLOT_MINUTES = 30;
const SLOT_COUNT = (END_MINUTES - START_MINUTES) / SLOT_MINUTES; // 28 格

// 表头文案，下标 0 对应 day_of_week === 1（周一）。
const DAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

/**
 * 把 "HH:MM" 解析成「从 00:00 起的分钟数」。解析不了（格式不对、时分越界）返回 null。
 * 用它来判断开始/结束时间能不能落到时间轴上。
 */
function parseTime(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value);
  if (match === null) {
    return null;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) {
    return null;
  }
  return hours * 60 + minutes;
}

/** 把「从 00:00 起的分钟数」还原成 "HH:MM"，用于时间轴刻度文字。 */
function formatMinutes(total: number): string {
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export default function Courses() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // editing 为 null 表示新建，非 null 表示正在编辑这门课；showForm 控制面板显隐。
  const [editing, setEditing] = useState<Course | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 表单字段。teacher / location / week_range 用空字符串表示「没填」，
  // 提交时再转成 null（见 handleSubmit），这样受控 input 好写。
  const [name, setName] = useState("");
  const [dayOfWeek, setDayOfWeek] = useState(1);
  const [startTime, setStartTime] = useState("08:00");
  const [endTime, setEndTime] = useState("09:40");
  const [teacher, setTeacher] = useState("");
  const [location, setLocation] = useState("");
  const [weekRange, setWeekRange] = useState("");

  /** 拉一次课程列表。页面对增删改后的刷新都复用它。 */
  const load = useCallback(async () => {
    setLoadingCourses(true);
    setLoadError(null);
    try {
      const list = await listCourses();
      setCourses(list);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "加载课程失败");
    } finally {
      setLoadingCourses(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** 打开新建表单：字段全部回到默认值。 */
  function openCreate() {
    setEditing(null);
    setFormError(null);
    setName("");
    setDayOfWeek(1);
    setStartTime("08:00");
    setEndTime("09:40");
    setTeacher("");
    setLocation("");
    setWeekRange("");
    setShowForm(true);
  }

  /** 打开编辑表单：用这门课的现有值预填，可空字段为 null 时填成空串。 */
  function openEdit(course: Course) {
    setEditing(course);
    setFormError(null);
    setName(course.name);
    setDayOfWeek(course.day_of_week);
    setStartTime(course.start_time);
    setEndTime(course.end_time);
    setTeacher(course.teacher ?? "");
    setLocation(course.location ?? "");
    setWeekRange(course.week_range ?? "");
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

    const trimmedName = name.trim();
    if (trimmedName === "") {
      setFormError("课程名不能为空");
      return;
    }

    // 本地先拦一道时间顺序，省一次必然失败的请求。type="time" 且 required
    // 基本不会给到空串，但 parseTime 仍可能返回 null，兜一下。
    const startMin = parseTime(startTime);
    const endMin = parseTime(endTime);
    if (startMin === null || endMin === null) {
      setFormError("请填写有效的开始和结束时间");
      return;
    }
    if (startMin >= endMin) {
      setFormError("结束时间必须晚于开始时间");
      return;
    }

    // 可选字段：空字符串一律转成 null 再发。传 "" 会在库里存个空串，
    // 编辑时清空地点后读回来就成了 ""，而不是「这个字段没有值」；
    // 传 null 才是真正的「清空」。
    const payload: CourseCreate = {
      name: trimmedName,
      day_of_week: dayOfWeek,
      start_time: startTime,
      end_time: endTime,
      teacher: teacher.trim() === "" ? null : teacher.trim(),
      location: location.trim() === "" ? null : location.trim(),
      week_range: weekRange.trim() === "" ? null : weekRange.trim(),
    };

    setSubmitting(true);
    try {
      if (editing !== null) {
        await updateCourse(editing.id, payload);
      } else {
        await createCourse(payload);
      }
      closeForm();
      // 保存成功后重新拉列表最省事，不用在本地手动拼一份新的 courses。
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
    if (!window.confirm("确定删除这门课程？")) {
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await deleteCourse(editing.id);
      closeForm();
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "删除失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  // 按能否落到时间轴上分成两组。
  const scheduled: { course: Course; startMin: number; endMin: number }[] = [];
  const unscheduled: Course[] = [];
  for (const course of courses) {
    const startMin = parseTime(course.start_time);
    const endMin = parseTime(course.end_time);
    if (startMin === null || endMin === null) {
      unscheduled.push(course);
      continue;
    }
    // 两端各自 clamp 到时间轴范围内，超出 22:00 的课会被截到 22:00。
    const clampedStart = Math.min(Math.max(startMin, START_MINUTES), END_MINUTES);
    const clampedEnd = Math.min(Math.max(endMin, START_MINUTES), END_MINUTES);
    if (clampedEnd <= clampedStart) {
      // 整段都在时间轴外（比如 06:00-07:00 或 22:30-23:30），单独列出。
      unscheduled.push(course);
      continue;
    }
    scheduled.push({ course, startMin: clampedStart, endMin: clampedEnd });
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">课程</h1>
        <button
          type="button"
          onClick={openCreate}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white transition-colors hover:bg-slate-700"
        >
          新建课程
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-lg border border-slate-200 bg-white p-5"
        >
          <h2 className="text-lg font-medium text-slate-900">
            {editing !== null ? "编辑课程" : "新建课程"}
          </h2>

          {formError !== null && (
            <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
              {formError}
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="course-name">
                课程名
              </label>
              <input
                id="course-name"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="course-dow">
                星期
              </label>
              <select
                id="course-dow"
                value={dayOfWeek}
                onChange={(e) => setDayOfWeek(Number(e.target.value))}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              >
                {DAY_LABELS.map((label, index) => (
                  <option key={label} value={index + 1}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="course-start">
                开始时间
              </label>
              <input
                id="course-start"
                type="time"
                required
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="course-end">
                结束时间
              </label>
              <input
                id="course-end"
                type="time"
                required
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="course-teacher">
                教师
              </label>
              <input
                id="course-teacher"
                type="text"
                value={teacher}
                onChange={(e) => setTeacher(e.target.value)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="course-location">
                地点
              </label>
              <input
                id="course-location"
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm text-slate-600" htmlFor="course-weeks">
                周次
              </label>
              <input
                id="course-weeks"
                type="text"
                value={weekRange}
                onChange={(e) => setWeekRange(e.target.value)}
                placeholder="如 1-16"
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
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

          {editing !== null && (
            <p className="text-xs text-slate-500">
              删除课程不会删掉挂在上面的 DDL，DDL 的 course_id 会变成 null，记录保留。
            </p>
          )}
        </form>
      )}

      {loadingCourses ? (
        <p className="text-slate-500">加载中…</p>
      ) : loadError !== null ? (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-600">
          {loadError}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <div
            className="grid min-w-[900px]"
            style={{
              gridTemplateColumns: "64px repeat(7, minmax(0, 1fr))",
              gridTemplateRows: `40px repeat(${SLOT_COUNT}, 28px)`,
            }}
          >
            {/* 表头：第 1 行第 1 列留空，其余是周一到周日 */}
            <div
              className="border-b border-r border-slate-200"
              style={{ gridColumn: 1, gridRow: 1 }}
            />
            {DAY_LABELS.map((label, index) => (
              <div
                key={label}
                className="flex items-center justify-center border-b border-r border-slate-200 text-xs font-medium text-slate-500"
                style={{ gridColumn: index + 2, gridRow: 1 }}
              >
                {label}
              </div>
            ))}

            {/* 时间轴：第 1 列、第 2..29 行，每格都有边框，但只有整点行显示文字 */}
            {Array.from({ length: SLOT_COUNT }, (_, slot) => (
              <div
                key={`axis-${slot}`}
                className="border-b border-r border-slate-200 pr-1 text-right text-[10px] leading-none text-slate-400"
                style={{ gridColumn: 1, gridRow: slot + 2 }}
              >
                {slot % 2 === 0
                  ? formatMinutes(START_MINUTES + slot * SLOT_MINUTES)
                  : ""}
              </div>
            ))}

            {/* 背景格：7 天 × 28 格，只为了画出格子线；课程卡片随后覆盖在上面 */}
            {Array.from({ length: SLOT_COUNT }, (_, slot) =>
              DAY_LABELS.map((_label, day) => (
                <div
                  key={`bg-${slot}-${day}`}
                  className="border-b border-r border-slate-100"
                  style={{ gridColumn: day + 2, gridRow: slot + 2 }}
                />
              ))
            )}

            {/* 课程卡片：用 gridRow 跨行表示时长，画在背景格之上 */}
            {scheduled.map(({ course, startMin, endMin }) => {
              const rowStart =
                2 + Math.floor((startMin - START_MINUTES) / SLOT_MINUTES);
              const rowSpan = Math.max(
                1,
                Math.ceil((endMin - startMin) / SLOT_MINUTES)
              );
              return (
                <button
                  key={course.id}
                  type="button"
                  onClick={() => openEdit(course)}
                  className="m-px overflow-hidden rounded border border-slate-300 bg-slate-100 px-1.5 py-1 text-left text-xs transition-colors hover:border-slate-900 hover:bg-white"
                  style={{
                    gridColumn: course.day_of_week + 1,
                    gridRow: `${rowStart} / span ${rowSpan}`,
                    zIndex: 1,
                  }}
                >
                  <div className="truncate font-semibold text-slate-900">
                    {course.name}
                  </div>
                  <div className="truncate text-slate-500">
                    {course.start_time}-{course.end_time}
                  </div>
                  {course.location !== null && (
                    <div className="truncate text-slate-500">{course.location}</div>
                  )}
                  {course.week_range !== null && (
                    <div className="truncate text-slate-400">
                      {course.week_range}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {!loadingCourses && loadError === null && courses.length === 0 && (
        <p className="text-sm text-slate-500">还没有课程，点右上角新建一门</p>
      )}

      {/* 时间轴外的课程：解析失败，或 clamp 后整段落在 08:00-22:00 之外 */}
      {unscheduled.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="mb-2 text-sm text-slate-500">
            以下课程的时间不在 08:00-22:00 范围内，没画在周视图上：
          </p>
          <ul className="flex flex-wrap gap-2">
            {unscheduled.map((course) => (
              <li key={course.id}>
                <button
                  type="button"
                  onClick={() => openEdit(course)}
                  className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-700 transition-colors hover:border-slate-900 hover:bg-slate-100"
                >
                  {course.name}（{DAY_LABELS[course.day_of_week - 1]}{" "}
                  {course.start_time}-{course.end_time}）
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
