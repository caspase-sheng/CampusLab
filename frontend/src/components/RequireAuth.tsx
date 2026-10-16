import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

// 路由守卫。
//
// 分三种情况，顺序不能反：
// 1. loading 为 true（还在用 token 恢复登录态）时先显示加载态，
//    免得把已登录的用户错误地弹去登录页；
// 2. 恢复失败、但还留着 token 时给一个能重试的提示页。这里**不能**直接踢去登录页：
//    多半只是后端没起 / 断网，用户手里的 token 其实还是好的，后端一恢复点下重试就能回来；
//    真把他踢去登录页，等于因为一次临时网络抖动就逼他重新输账号密码。
// 3. 确实没登录（没有 token，或 token 被服务器明确判为 401 无效）才去登录页。
export default function RequireAuth() {
  const { user, loading, restoreError, retryRestore } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        加载中…
      </div>
    );
  }

  if (restoreError !== null && user === null) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
        <p className="text-slate-600">{restoreError}</p>
        <p className="text-sm text-slate-500">
          如果是在本地开发，确认后端已经启动（backend 目录下 uvicorn）。
        </p>
        <button
          type="button"
          onClick={retryRestore}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-700"
        >
          重试
        </button>
      </div>
    );
  }

  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
