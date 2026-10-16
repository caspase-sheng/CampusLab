// 后端请求的 fetch 封装。契约见 docs/CONTRACT.md §1.2、§1.3、§6。
//
// 这个文件负责三件事：
// 1. 自动带上 Authorization 头（token 从 localStorage 读）；
// 2. 自动拆信封：/api 返回的 {code, message, data}，code === 0 时返回 data，
//    否则抛带 message 的 Error；
// 3. 401 时清 token 并跳登录页 —— 但登录/注册接口例外（见 skipAuthRedirect）。
//
// 不引 axios 之类的请求库，浏览器原生 fetch 够用，也少一层依赖。

import type { ApiResponse } from "./types";

/** localStorage 里存 token 的键名，固定不变。 */
const TOKEN_KEY = "campuslab_token";

/** 从 localStorage 取出 token；没有则返回 null。 */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/** 把 token 写入 localStorage。 */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/** 清掉 localStorage 里的 token（登出、401 时用）。 */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * 带 HTTP 状态码的请求错误，让调用方能区分失败原因。
 *
 * status 为 0 是一个约定值，表示**压根没连上服务器**（fetch 在网络层就 reject 了：
 * 后端没起、断网、请求被拒），而不是服务器返回的某个状态码。调用方据此把
 * 「网络不通」和「服务器明确说不行（比如 401 表示 token 无效）」分开处理。
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** request() 的选项。 */
export interface RequestOptions {
  /** HTTP 方法，默认 GET。 */
  method?: string;
  /** 请求体，会被 JSON.stringify；不需要体的接口不传。 */
  body?: unknown;
  /**
   * 命中 401 时是否跳过「清 token + 跳登录页」这套默认动作。
   * 登录、注册接口要传 true：登录失败（用户名或密码错误）也是 401，
   * 那是正常的表单错误，不该把用户从登录页弹走。
   */
  skipAuthRedirect?: boolean;
}

/** 从任意错误体里尽量抠出可读的 message。 */
function extractMessage(payload: unknown): string | null {
  if (payload !== null && typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    if (typeof obj.message === "string" && obj.message.length > 0) {
      return obj.message;
    }
    // /kv 的错误体是 {"detail": "..."}，顺手兼容一下
    if (typeof obj.detail === "string" && obj.detail.length > 0) {
      return obj.detail;
    }
  }
  return null;
}

/** 判断一个已解析的 body 是不是 {code, message, data} 信封。 */
function isEnvelope(payload: unknown): payload is ApiResponse<unknown> {
  if (payload === null || typeof payload !== "object") {
    return false;
  }
  return typeof (payload as Record<string, unknown>).code === "number";
}

/** 401 时把浏览器导航到登录页；已经在登录页就不动，免得多一次整页刷新。 */
function redirectToLogin(): void {
  if (window.location.pathname !== "/login") {
    window.location.assign("/login");
  }
}

/**
 * 核心请求方法：发一个 JSON 请求，成功返回拆好的 data，失败抛 Error。
 *
 * 泛型 T 是对应接口 data 的类型，调用方自己指定（比如 request<User>("/api/auth/me")）。
 */
export async function request<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, skipAuthRedirect = false } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token !== null) {
    headers.Authorization = `Bearer ${token}`;
  }

  const init: RequestInit = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    // fetch 只有网络层失败才会 reject；拿到 4xx/5xx 也会正常 resolve。
    // 统一包成 status = 0 的 ApiError，调用方靠 status 区分
    // 「压根没连上服务器」和「服务器明确返回了某个错误」。
    throw new ApiError("无法连接服务器，请检查网络或确认后端已启动", 0);
  }

  // 先读文本再尝试 JSON.parse：既避免「空 body 上 JSON.parse 报错」，
  // 也避免「非 2xx 但 body 不是 JSON」时拿不到状态码兜底。
  const text = await response.text();
  let payload: unknown = null;
  if (text.length > 0) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    // 非 2xx：后端错误也是信封，尽力取 message，取不到就用状态码兜底。
    const message =
      extractMessage(payload) ?? `请求失败（HTTP ${response.status}）`;

    if (response.status === 401 && !skipAuthRedirect) {
      clearToken();
      redirectToLogin();
    }
    throw new ApiError(message, response.status);
  }

  // 2xx：拆信封。理论上 /api 全部是信封，非信封的情况兜底直接返回。
  if (isEnvelope(payload)) {
    if (payload.code === 0) {
      return payload.data as T;
    }
    throw new Error(payload.message || `请求失败（code ${payload.code}）`);
  }
  return payload as T;
}

/** GET 便捷方法。 */
export function get<T>(
  path: string,
  options: Omit<RequestOptions, "method" | "body"> = {}
): Promise<T> {
  return request<T>(path, { ...options, method: "GET" });
}

/** POST 便捷方法。 */
export function post<T>(
  path: string,
  body?: unknown,
  options: Omit<RequestOptions, "method" | "body"> = {}
): Promise<T> {
  return request<T>(path, { ...options, method: "POST", body });
}

/** PUT 便捷方法。 */
export function put<T>(
  path: string,
  body?: unknown,
  options: Omit<RequestOptions, "method" | "body"> = {}
): Promise<T> {
  return request<T>(path, { ...options, method: "PUT", body });
}

/** DELETE 便捷方法。 */
export function del<T>(
  path: string,
  options: Omit<RequestOptions, "method" | "body"> = {}
): Promise<T> {
  return request<T>(path, { ...options, method: "DELETE" });
}
