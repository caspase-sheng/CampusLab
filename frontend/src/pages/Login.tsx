import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

// 登录页。契约见 docs/CONTRACT.md §4.1。
// 提交期间按钮禁用；后端抛错时把消息显示在表单上方；成功后 user 被更新，
// 页首的 <Navigate> 会把用户带回首页（RequireAuth 那边也会兜底）。
export default function Login() {
  const { user, loading, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // loading 为 true 时 AuthProvider 还在拿 localStorage 里的 token 调 me() 恢复登录态，
  // 这期间 user 是 null。如果直接往下走，已登录用户一刷新就会先看到登录表单闪一下，
  // 等 me() 回来才跳走，所以这里先显示和 RequireAuth 一致的加载态。
  // 注意：这段必须放在所有 useState 之后，hooks 的调用顺序才不会被提前 return 打乱。
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        加载中…
      </div>
    );
  }

  // 已登录还访问 /login 就直接回首页
  if (user !== null) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8">
        <h1 className="mb-6 text-xl font-semibold text-slate-900">登录 CampusLab</h1>

        {error !== null && (
          <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-600">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-slate-600" htmlFor="username">
              用户名
            </label>
            <input
              id="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-600" htmlFor="password">
              密码
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded bg-slate-900 py-2 text-sm text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "登录中…" : "登录"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-slate-500">
          还没有账号？
          <Link to="/register" className="ml-1 text-slate-900 underline">
            去注册
          </Link>
        </p>
      </div>
    </div>
  );
}
