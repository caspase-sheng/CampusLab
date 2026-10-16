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

/**
 * GET /api/auth/me —— 取当前登录用户。
 *
 * 传 skipAuthRedirect: true：me() 只在恢复登录态时被调用，401（token 过期或无效）
 * 该由 AuthContext 自己判断怎么处理，不要让 client 直接 window.location.assign
 * 硬跳转——那是整页刷新，会白闪一下；交给 RequireAuth 走 React 路由的软跳转更顺。
 */
export function me(): Promise<User> {
  return get<User>("/api/auth/me", { skipAuthRedirect: true });
}
