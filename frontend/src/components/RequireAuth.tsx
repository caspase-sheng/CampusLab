import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

// 路由守卫。
//
// loading 为 true（还在用 token 恢复登录态）时先显示一个简单的加载态，
// 免得把已登录的用户错误地弹去登录页；恢复完成后再判断有没有 user。
export default function RequireAuth() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        加载中…
      </div>
    );
  }

  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
