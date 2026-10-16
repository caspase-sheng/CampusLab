// 概览页：顶部一句问候 + 三块卡片（今日课程 / 临近 DDL / 最近笔记）。
//
// 数据全部来自已有的三个列表接口（courses / deadlines / notes），不新增后端接口，
// 也不改 backend/。三块卡片各自独立取数、独立降级，见下方 useEffect 里的注释。
//
// 一个必须先说清楚的时间坑：JS 的 new Date().getDay() 是 0=周日..6=周六，而契约
// §1.4 里 Course.day_of_week 是 1=周一..7=周日，两边差一位。直接拿 getDay() 去和
// day_of_week 比，会把整周的课静默错位一天（周一那天显示周日的课、周日显示周六的课），
// 而且不报任何错，只有肉眼点开才看得出来。所以底部所有「今天有没有这门课」的判断
// 统一走 todayDayOfWeek()，不直接用 getDay()。

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { listCourses } from "../api/courses";
import { listDeadlines } from "../api/deadlines";
import { listNotes } from "../api/notes";
import type { Course, Deadline, Note } from "../api/types";
import { formatDateTime } from "../utils/datetime";

/** 今天的 day_of_week：1=周一 ... 7=周日，和 Course.day_of_week 对齐。
 *  new Date().getDay() 是 0=周日，所以要先把 0 映射成 7，其余不变。 */
function todayDayOfWeek(): number {
  const jsDay = new Date().getDay();
  return jsDay === 0 ? 7 : jsDay;
}

/** 把 "HH:MM" 解析成「从 00:00 起的分钟数」；格式不对或时分越界返回 null。 */
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

/** 取某个 Date 当天的 00:00，把时分秒抹掉，只留「哪一天」。 */
function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/** 顶部问候语：按当前小时数分早上 / 下午 / 晚上，一句话。 */
function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) {
    return "早上好";
  }
  if (hour < 18) {
    return "下午好";
  }
  return "晚上好";
}

/** DDL 相对时间的展示结果。 */
interface DeadlineRelative {
  /** 展示文案：「已过期」/「今天截止」/「明天」/「还有 N 天」。 */
  label: string;
  /** 已经过了当前时间，整行标红。 */
  expired: boolean;
  /** 今天之内到期，文案用橙色强调。 */
  urgent: boolean;
}

/**
 * 算一条 DDL 相对当前时间的文案。
 *
 * 天数差要先把两个时间都抹到当天 00:00 再算，不能直接拿毫秒数相减除一天：
 * 「今天 23:00」和「明天 01:00」实际只差两小时，直接除以 86400000 会得到 0，
 * 显示成「今天截止」，但它明明已经是明天了。抹掉时分秒后，两者分别落在
 * 10-17 和 10-18 的两个零点，天数差稳稳是 1，显示「明天」才对。
 *
 * 而过期判断反过来，要用完整时刻比：过了 due_time 那一刻才算过期，不能只看日期，
 * 否则今天早上 09:00 的 DDL 在今天 15:00 会算成「今天截止」而不是「已过期」。
 */
function relativeDeadline(dueTime: string, now: Date): DeadlineRelative {
  const due = new Date(dueTime);
  if (due.getTime() < now.getTime()) {
    return { label: "已过期", expired: true, urgent: false };
  }
  // 两个零点相差是整数天，用 round 收掉可能的浮点误差（本地时区没有夏令时，误差很小）。
  const diffDays = Math.round(
    (startOfDay(due).getTime() - startOfDay(now).getTime()) / 86400000
  );
  if (diffDays === 0) {
    return { label: "今天截止", expired: false, urgent: true };
  }
  if (diffDays === 1) {
    return { label: "明天", expired: false, urgent: false };
  }
  return { label: `还有 ${diffDays} 天`, expired: false, urgent: false };
}

/** 三块卡片共用的外框：标题 + 右上角「查看全部 →」+ 内容区。 */
function CardSection({
  title,
  to,
  children,
}: {
  title: string;
  to: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        <Link
          to={to}
          className="text-sm text-slate-500 transition-colors hover:text-slate-900"
        >
          查看全部 →
        </Link>
      </div>
      {children}
    </div>
  );
}

/** 卡片内容区统一的空状态 / 失败态文案。 */
function CardMessage({ text, error }: { text: string; error?: boolean }) {
  if (error === true) {
    return <p className="text-sm text-red-600">加载失败</p>;
  }
  return <p className="text-sm text-slate-500">{text}</p>;
}

export default function Dashboard() {
  // 三块数据各存一份，null 表示这一块接口失败了（区别于「成功但空列表」的 []）。
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [deadlines, setDeadlines] = useState<Deadline[] | null>(null);
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      // 概览页是登录后的入口页，一块数据挂了不该把整个首页拖垮。所以三个请求并发
      // 发出、各自收结果：用 allSettled 而不是 all —— all 只要有一个 reject 就整体
      // reject，三块数据全都拿不到，页面只剩一行错误、另外两块也白屏了。
      // allSettled 下每块各判各的，失败的那块显示「加载失败」，其余两块照常渲染。
      const [coursesResult, deadlinesResult, notesResult] = await Promise.allSettled([
        listCourses(),
        listDeadlines(),
        listNotes(),
      ]);
      if (cancelled) {
        return;
      }
      setCourses(coursesResult.status === "fulfilled" ? coursesResult.value : null);
      setDeadlines(
        deadlinesResult.status === "fulfilled" ? deadlinesResult.value : null
      );
      setNotes(notesResult.status === "fulfilled" ? notesResult.value : null);
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const now = new Date();
  // 「今天有课」的判断基准。注意这里用的是 todayDayOfWeek()，不是 now.getDay()。
  const todayDow = todayDayOfWeek();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();

  // 今日课程：筛出 day_of_week 等于今天的，按 start_time 升序（"HH:MM" 定长零填充，
  // 直接字符串比大小就等于比时间先后，不用先解析）。
  const todayCourses =
    courses === null
      ? []
      : courses
          .filter((course) => course.day_of_week === todayDow)
          .sort((a, b) =>
            a.start_time < b.start_time ? -1 : a.start_time > b.start_time ? 1 : 0
          );

  // 临近 DDL：只留待办，按截止时间升序取前 5 条。
  const upcomingDeadlines =
    deadlines === null
      ? []
      : deadlines
          .filter((deadline) => deadline.status === "pending")
          .sort((a, b) =>
            a.due_time < b.due_time ? -1 : a.due_time > b.due_time ? 1 : 0
          )
          .slice(0, 5);

  // 最近笔记：按 updated_at 倒序取前 5 条。先复制一份再排，别把 state 里的数组原地排乱。
  const recentNotes =
    notes === null
      ? []
      : [...notes]
          .sort((a, b) =>
            a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0
          )
          .slice(0, 5);

  return (
    <section className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">{greeting()}</h1>

      <div className="grid gap-4 lg:grid-cols-3">
        <CardSection title="今日课程" to="/courses">
          {loading ? (
            <CardMessage text="加载中…" />
          ) : courses === null ? (
            <CardMessage text="加载失败" error />
          ) : todayCourses.length === 0 ? (
            <CardMessage text="今天没有课" />
          ) : (
            <ul className="space-y-2 text-sm">
              {todayCourses.map((course) => {
                const startMin = parseTime(course.start_time);
                const endMin = parseTime(course.end_time);
                // 解析不出分钟数（格式异常）时就按普通课显示，不误判进行中 / 已过。
                const finished = endMin !== null && nowMinutes >= endMin;
                const ongoing =
                  startMin !== null &&
                  endMin !== null &&
                  nowMinutes >= startMin &&
                  nowMinutes < endMin;
                return (
                  <li
                    key={course.id}
                    className={[
                      "flex items-baseline gap-3",
                      finished ? "text-slate-400" : "",
                      ongoing ? "font-semibold text-slate-900" : "",
                    ]
                      .filter((cls) => cls !== "")
                      .join(" ")}
                  >
                    <span className="shrink-0 tabular-nums">
                      {course.start_time}-{course.end_time}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{course.name}</span>
                    {course.location !== null && course.location !== "" && (
                      <span className="shrink-0 text-xs">{course.location}</span>
                    )}
                    {ongoing && (
                      <span className="shrink-0 rounded bg-slate-900 px-2 py-0.5 text-xs font-normal text-white">
                        进行中
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardSection>

        <CardSection title="临近 DDL" to="/deadlines">
          {loading ? (
            <CardMessage text="加载中…" />
          ) : deadlines === null ? (
            <CardMessage text="加载失败" error />
          ) : upcomingDeadlines.length === 0 ? (
            <CardMessage text="没有待办的 DDL" />
          ) : (
            <ul className="space-y-2 text-sm">
              {upcomingDeadlines.map((deadline) => {
                const rel = relativeDeadline(deadline.due_time, now);
                return (
                  <li
                    key={deadline.id}
                    className={`flex items-baseline gap-3 ${
                      rel.expired ? "text-red-600" : "text-slate-900"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate">{deadline.title}</span>
                    <span
                      className={`shrink-0 text-xs tabular-nums ${
                        rel.expired ? "" : "text-slate-500"
                      }`}
                    >
                      {formatDateTime(deadline.due_time)}
                    </span>
                    <span
                      className={`shrink-0 text-xs ${
                        rel.expired
                          ? ""
                          : rel.urgent
                            ? "text-amber-600"
                            : "text-slate-500"
                      }`}
                    >
                      {rel.label}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </CardSection>

        <CardSection title="最近笔记" to="/notes">
          {loading ? (
            <CardMessage text="加载中…" />
          ) : notes === null ? (
            <CardMessage text="加载失败" error />
          ) : recentNotes.length === 0 ? (
            <CardMessage text="还没有笔记" />
          ) : (
            <ul className="space-y-2 text-sm">
              {recentNotes.map((note) => (
                <li key={note.id}>
                  {/* 笔记页自己会打开列表，这里每行点进去直接跳 /notes，不做详情页。 */}
                  <Link
                    to="/notes"
                    className="flex items-baseline gap-3 transition-colors hover:underline"
                  >
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {note.title}
                    </span>
                    <span className="shrink-0 text-xs text-slate-400">
                      更新于 {formatDateTime(note.updated_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardSection>
      </div>
    </section>
  );
}
