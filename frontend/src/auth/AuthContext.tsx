import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import * as authApi from "../api/auth";
import { clearToken, getToken, setToken } from "../api/client";
import type { User } from "../api/types";

// 全局登录态。
//
// 初始化的逻辑：进页面时先看 localStorage 里有没有 token，有就调一次 /api/auth/me
// 把用户信息恢复出来（刷新页面不丢登录态靠的就是这一步）。这期间 loading 为 true，
// RequireAuth 会先显示加载态，避免出现「明明已登录却闪一下登录页」。
//
// 没有 token，或 me() 失败（token 过期/无效，后端返回 401），就清掉本地 token，
// user 保持 null，等 RequireAuth 把用户送去 /login。

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // 启动时恢复登录态，只跑一次。
  useEffect(() => {
    let cancelled = false;

    async function restore() {
      if (getToken() === null) {
        setLoading(false);
        return;
      }
      try {
        const current = await authApi.me();
        if (!cancelled) {
          setUser(current);
        }
      } catch {
        // token 无效（401 已被 client 清掉）或网络问题，都当未登录处理
        clearToken();
        if (!cancelled) {
          setUser(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const token = await authApi.login(username, password);
    setToken(token.access_token);
    // 存下 token 后再拉一次用户信息，拿到 id / email，页面右上角要显示用户名
    const current = await authApi.me();
    setUser(current);
  }, []);

  const register = useCallback(
    async (username: string, email: string, password: string) => {
      // register 的响应本身就是 UserOut（id / username / email），跟 me() 返回的是同一个形状，
      // 所以直接拿注册返回的用户对象就行，这里不再调 me()——比登录少一次往返。
      // （login() 不行：它只返回 token，必须再调一次 me() 才拿得到用户信息。）
      const created = await authApi.register(username, email, password);
      // 注册成功后直接登录，省得让用户再去登录页手动输一遍
      const token = await authApi.login(username, password);
      setToken(token.access_token);
      setUser(created);
    },
    []
  );

  const logout = useCallback(() => {
    // 后端目前没有 logout 接口（契约 §1.3 提的 JWT 黑名单还没实现），
    // 所以这里只是清掉本地 token 和内存里的用户，刷新页面即视为登出。
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/** 取当前登录态。必须在 AuthProvider 内部调用。 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth 必须在 <AuthProvider> 内部使用");
  }
  return ctx;
}
