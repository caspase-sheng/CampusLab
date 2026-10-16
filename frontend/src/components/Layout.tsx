import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

// 登录后页面的外框：顶部导航 + 内容区。
// 内容由子路由通过 <Outlet /> 渲染，导航项用 NavLink，会自动给当前页加高亮样式。

const navItems = [
  { to: "/", label: "概览" },
  { to: "/courses", label: "课程" },
  { to: "/deadlines", label: "DDL" },
  { to: "/notes", label: "笔记" },
  { to: "/visualizer", label: "可视化" },
  { to: "/graph", label: "图遍历" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    // 退出后回登录页；RequireAuth 也会兜底，这里主动跳一下体验更顺
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-8">
            <span className="text-lg font-semibold text-slate-900">CampusLab</span>
            <nav className="flex items-center gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    [
                      "rounded px-3 py-1.5 text-sm transition-colors",
                      isActive
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:bg-slate-100",
                    ].join(" ")
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-500">{user?.username}</span>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-100"
            >
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
