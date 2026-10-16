// auth 接口。契约见 docs/CONTRACT.md §4.1。
// 三个函数都走 client.ts 的封装，这里只负责拼路径和请求体。

import { get, post } from "./client";
import type { TokenOut, User } from "./types";

/** POST /api/auth/register —— 注册，返回创建好的用户。 */
export function register(
  username: string,
  email: string,
  password: string
): Promise<User> {
  return post<User>("/api/auth/register", { username, email, password });
}

/**
 * POST /api/auth/login —— 登录，返回 token。
 *
 * 传 skipAuthRedirect: true：登录失败（用户名或密码错误）后端返回 401，
 * 那是表单层面的正常报错，不能让 client 把用户从登录页弹走。
 */
export function login(username: string, password: string): Promise<TokenOut> {
  return post<TokenOut>(
    "/api/auth/login",
    { username, password },
    { skipAuthRedirect: true }
  );
}

/** GET /api/auth/me —— 取当前登录用户，未登录时 client 会按 401 处理。 */
export function me(): Promise<User> {
  return get<User>("/api/auth/me");
}
