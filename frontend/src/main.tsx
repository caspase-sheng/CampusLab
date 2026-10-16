import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import "./index.css";

// 应用入口。React 19 的 createRoot 写法。
// 外层套 BrowserRouter（路由）和 AuthProvider（登录态），顺序上 AuthProvider 在里层，
// 这样路由和页面组件都能通过 useAuth() 拿到当前用户。
const container = document.getElementById("root");
if (container === null) {
  throw new Error("找不到 #root 挂载点，检查 index.html");
}

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>
);
