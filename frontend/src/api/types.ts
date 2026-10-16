// 与后端 API 对应的 TypeScript 类型，字段以 docs/CONTRACT.md §4 为准。
//
// 时间字段（created_at / updated_at / due_time）后端返回 ISO 8601 字符串
// （契约 §1.4），这里就按 string 收着，等真要用（比如格式化成「还剩几小时」）
// 再在页面里 new Date(...) 解析。

/** 用户对外暴露的字段（契约 §4.1），对应后端 UserOut。 */
export interface User {
  id: number;
  username: string;
  email: string;
}

/** 登录成功后的 token（契约 §4.1），对应后端 TokenOut。 */
export interface TokenOut {
  access_token: string;
  token_type: string;
}

/** 课程（契约 §4.2）。teacher / location / week_range 后端可空。 */
export interface Course {
  id: number;
  name: string;
  teacher: string | null;
  location: string | null;
  day_of_week: number; // 1 = 周一 ... 7 = 周日（契约 §1.4）
  start_time: string; // "HH:MM"
  end_time: string; // "HH:MM"
  week_range: string | null; // 如 "1-16"
  created_at: string;
}

/**
 * 新建课程的请求体（契约 §4.2 的 POST）。teacher / location / week_range 可选，
 * 不填就不传。
 */
export interface CourseCreate {
  name: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  teacher?: string | null;
  location?: string | null;
  week_range?: string | null;
}

/**
 * 更新课程的请求体（契约 §4.2 的 PUT），字段全部可选，只更新传入的字段。
 *
 * name / day_of_week / start_time / end_time 这四个写成 ``?: string`` 而不是
 * ``?: string | null``，是特意把后端的约束搬到类型上：它们在 courses 表里是
 * NOT NULL（契约 §5.2），后端 CourseUpdate 里有个校验器会对「显式传 null」
 * 直接抛 422。类型上禁掉 null，调用方就写不出会被拒的请求，省得运行时才发现。
 * teacher / location / week_range 可空，显式传 null 表示清空该字段，所以留了 null。
 */
export interface CourseUpdate {
  name?: string;
  day_of_week?: number;
  start_time?: string;
  end_time?: string;
  teacher?: string | null;
  location?: string | null;
  week_range?: string | null;
}

/** DDL（契约 §4.3）。course_id 可选，可能为 null。 */
export interface Deadline {
  id: number;
  title: string;
  course_id: number | null;
  due_time: string; // ISO 8601
  status: string; // pending / done
  created_at: string;
}

/**
 * 新建 DDL 的请求体（契约 §4.3 的 POST）。course_id / status 可选，
 * status 不传时后端按默认值 "pending" 落库。
 *
 * due_time 用 "YYYY-MM-DDTHH:mm"（datetime-local 的原生格式）直接发即可：
 * 后端 pydantic 的 datetime 能解析不带时区、不带秒的串，库里存的也是 naive 时间。
 */
export interface DeadlineCreate {
  title: string;
  due_time: string;
  course_id?: number | null;
  status?: "pending" | "done";
}

/**
 * 更新 DDL 的请求体（契约 §4.3 的 PUT），字段全部可选，只更新传入的字段。
 *
 * title / due_time / status 只写 ``?: string`` / ``?: "pending" | "done"`` 而不带
 * ``| null``，是把后端的约束搬到类型上：它们在 deadlines 表里是 NOT NULL
 * （契约 §5.3），后端 DeadlineUpdate 里的校验器对「显式传 null」直接抛 422。
 * 类型上禁掉 null，调用方就写不出会被拒的请求。
 *
 * course_id 可空：它在库里是可空外键，显式传 null 表示解除与课程的关联，是合法更新。
 */
export interface DeadlineUpdate {
  title?: string;
  due_time?: string;
  status?: "pending" | "done";
  course_id?: number | null;
}

/** 笔记（契约 §4.4）。tags 是逗号分隔字符串，后端可空。 */
export interface Note {
  id: number;
  title: string;
  content_md: string;
  tags: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * 新建笔记的请求体（契约 §4.4 的 POST）。tags 可选、可空。
 *
 * content_md 是 Markdown 源文，本次按纯文本处理，不引渲染库。
 */
export interface NoteCreate {
  title: string;
  content_md: string;
  tags?: string | null;
}

/**
 * 更新笔记的请求体（契约 §4.4 的 PUT），字段全部可选，只更新传入的字段。
 *
 * title / content_md 只写 ``?: string`` 不带 ``| null``：它们在 notes 表里是
 * NOT NULL（契约 §5.4），后端 NoteUpdate 的校验器拒绝显式传 null，会返 422。
 * tags 可空，显式传 null 表示清空标签，是合法更新。
 */
export interface NoteUpdate {
  title?: string;
  content_md?: string;
  tags?: string | null;
}

/**
 * 统一响应信封（契约 §1.2）。/api 下所有接口都套这个壳。
 *
 * data 显式写成 ``T | null``：契约规定失败时 data 是 null，client 拆信封时
 * 也要按「可能没有数据」来处理，类型上不该假装它一定存在。
 */
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T | null;
}
