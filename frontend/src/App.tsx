import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import Courses from "./pages/Courses";
import Dashboard from "./pages/Dashboard";
import Deadlines from "./pages/Deadlines";
import GraphVisualizer from "./pages/GraphVisualizer";
import Login from "./pages/Login";
import Notes from "./pages/Notes";
import Register from "./pages/Register";
import Visualizer from "./pages/Visualizer";

// 路由表。
//
// /login、/register 是公开页；其余页面统一套在 RequireAuth + Layout 里：
// RequireAuth 负责「没登录就踢到 /login」，Layout 负责顶部导航和 <Outlet />。
// 两级都写成无 path 的父路由，真正的路径挂在里面的子路由上，这样外层逻辑只写一遍。
//
// 兜底路由把任何没匹配上的路径都重定向回 "/"，避免出现白屏的 404 页面；
// "/" 本身又受 RequireAuth 保护，所以未登录时最终会落到 /login。
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/courses" element={<Courses />} />
          <Route path="/deadlines" element={<Deadlines />} />
          <Route path="/notes" element={<Notes />} />
          <Route path="/visualizer" element={<Visualizer />} />
          <Route path="/graph" element={<GraphVisualizer />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
