import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import * as authApi from "../api/auth";
import { ApiError, clearToken, getToken, setToken } from "../api/client";
import type { User } from "../api/types";

// 全局登录态。
//
// 初始化的逻辑：进页面时先看 localStorage 里有没有 token，有就调一次 /api/auth/me
// 把用户信息恢复出来（刷新页面不丢登录态靠的就是这一步）。这期间 loading 为 true，
// RequireAuth 会先显示加载态，避免出现「明明已登录却闪一下登录页」。
//
// 恢复失败要分两种情况，不能一刀切：
//   - 服务器明确返回 401：token 过期或无效 → 清掉本地 token，按未登录处理，回登录页；
//   - 网络层失败（后端没起、断网、超时，status 0，或经代理变成 5xx）→ token 本身
//     是好的，必须保留，只把错误信息暴露给 RequireAuth，让用户点「重试」。
// 旧实现把两者混为一谈、失败一律 clearToken()，导致后端重启那几秒刷新一下就被登出。

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  /** 恢复登录态失败时的错误信息；null 表示没有错误。 */
  restoreError: string | null;
  /** 出错后重新走一遍恢复流程（给「重试」按钮用）。 */
  retryRestore: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  const restore = useCallback(async () => {
    if (getToken() === null) {
      setLoading(false);
      return;
    }
    try {
      const current = await authApi.me();
      setUser(current);
      setRestoreError(null);
    } catch (err) {
      // 只有服务器明确说 token 不行（401）才清 token。
      // 网络错误 / 后端没起（status 0，或经代理变成了 5xx）都不能清：
      // token 本身没问题，清了会让用户在后端重启那几秒刷新一下就被登出。
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        setUser(null);
        setRestoreError(null);
      } else {
        setUser(null);
        setRestoreError(
          err instanceof Error ? err.message : "恢复登录态失败，请稍后重试"
        );
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // 启动时恢复登录态。
  //
  // 这里没有像旧实现那样加 cancelled 标志防止卸载后 setState：AuthProvider 从挂载到
  // 应用退出一直存在，基本不会卸载；而且 React 18 起对「卸载后 setState」已经不再警告。
  // 保留它反而会让 restore 没法被下面的重试逻辑复用——重试时组件显然还活着，标志位只会碍事。
  useEffect(() => {
    void restore();
  }, [restore]);

  /** 出错后用户点「重试」时调用：重新走一遍恢复流程。 */
  const retryRestore = useCallback(() => {
    setRestoreError(null);
    setLoading(true);
    void restore();
  }, [restore]);

  const login = useCallback(async (username: string, password: string) => {
    const token = await authApi.login(username, password);
    setToken(token.access_token);
    // 存下 token 后再拉一次用户信息，拿到 id / email，页面右上角要显示用户名
    const current = await authApi.me();
    setUser(current);
    // 登录成功，把之前可能残留的连接错误清掉，别让它在界面上留着
    setRestoreError(null);
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
      // 同 login：注册成功也把可能残留的连接错误清掉
      setRestoreError(null);
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
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, restoreError, retryRestore }}
    >
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
