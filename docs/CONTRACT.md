# CampusLab API 契约

版本：v1.0  
日期：2026-10-16  
状态：定稿，后续开发以此为准

---

## 1. 通用约定

### 1.1 服务地址
- 后端 API base：`http://127.0.0.1:8000/api`
- KV API base：`http://127.0.0.1:8000/kv`
- 前端开发地址：`http://127.0.0.1:5173`
- 前端通过 Vite 代理 `/api` 和 `/kv` 到 `http://127.0.0.1:8000`

### 1.2 后端 API 响应格式
除 KV API 外，所有后端接口统一返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

- `code`：业务码，`0` 表示成功，非 `0` 表示错误
- `message`：人类可读信息
- `data`：业务数据，失败时为 `null`

HTTP 状态码与 `code` 对应关系：

| HTTP | code | 含义 |
|------|------|------|
| 200  | 0    | 成功 |
| 401  | 401  | 未登录或 token 无效 |
| 403  | 403  | 无权限 |
| 404  | 404  | 资源不存在 |
| 422  | 422  | 参数校验失败 |
| 500  | 500  | 服务器内部错误 |

### 1.3 鉴权
- 除 `/api/auth/register`、`/api/auth/login`、`/health` 外，所有后端接口需要 JWT
- 请求头：`Authorization: Bearer <access_token>`
- token 有效期：24 小时
- JWT 黑名单存自研 KV，key 为 `jwt:blacklist:<token>`，TTL 与 token 剩余有效期一致

### 1.4 时间与格式
- 日期时间：ISO 8601 字符串，如 `2026-10-16T12:00:00`
- 日期：`YYYY-MM-DD`
- 时间：`HH:MM`，24 小时制
- `day_of_week`：整数，`1` = 周一，`7` = 周日
- `tags`：逗号分隔字符串，如 `"算法,KV,后端"`

---

## 2. 探活

### GET /health
- 无鉴权
- 响应：`{"status": "ok"}`
- 用途：本地启动检查

---

## 3. KV API

### 3.1 通用说明
- base：`http://127.0.0.1:8000/kv`
- 无鉴权，本地内部服务
- **不套** `{code, message, data}` 信封，直接返回数据
- 错误时返回 `{"detail": "错误信息"}`，HTTP 状态码表示错误类型

### 3.2 接口列表

#### POST /kv/set
- 请求：
```json
{
  "key": "user:1:session",
  "value": "abc123",
  "ttl": 3600
}
```
- `ttl` 可选，单位秒；不传表示永不过期
- 响应：
```json
{"ok": true}
```

#### GET /kv/get/{key}
- 响应 200：
```json
{
  "key": "user:1:session",
  "value": "abc123",
  "ttl": 3599
}
```
- 响应 404：
```json
{"detail": "key not found"}
```

#### DELETE /kv/del/{key}
- 响应：
```json
{"ok": true}
```

#### GET /kv/keys
- 响应：
```json
{"keys": ["k1", "k2", "k3"]}
```

#### GET /kv/stats
- 响应：
```json
{
  "hits": 100,
  "misses": 5,
  "hit_rate": 0.95,
  "keys": 20,
  "wal_size": 1024,
  "files": 3
}
```

#### POST /kv/compact
- 响应：
```json
{
  "ok": true,
  "files_before": 5,
  "files_after": 2
}
```

### 3.3 错误码
- `400`：参数错误
- `404`：键不存在
- `500`：内部错误

---

## 4. 后端 API

### 4.1 Auth

#### POST /api/auth/register
- 请求：
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "secret123"
}
```
- 响应：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com"
  }
}
```

#### POST /api/auth/login
- 请求：
```json
{
  "username": "alice",
  "password": "secret123"
}
```
- 响应：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer"
  }
}
```

#### GET /api/auth/me
- 需要鉴权
- 响应：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com"
  }
}
```

### 4.2 Courses

#### GET /api/courses
- 需要鉴权
- 返回当前用户所有课程
- 响应：
```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "id": 1,
      "name": "数据结构",
      "teacher": "张老师",
      "location": "教三-201",
      "day_of_week": 1,
      "start_time": "08:00",
      "end_time": "09:40",
      "week_range": "1-16",
      "created_at": "2026-10-16T12:00:00"
    }
  ]
}
```

#### POST /api/courses
- 需要鉴权
- 请求：
```json
{
  "name": "数据结构",
  "teacher": "张老师",
  "location": "教三-201",
  "day_of_week": 1,
  "start_time": "08:00",
  "end_time": "09:40",
  "week_range": "1-16"
}
```
- `teacher`、`location`、`week_range` 可选
- 响应：同 GET 单个课程

#### GET /api/courses/{id}
- 需要鉴权
- 响应：同上单个课程

#### PUT /api/courses/{id}
- 需要鉴权
- 请求体同 POST，字段可选，只更新传入字段
- 响应：更新后的课程

#### DELETE /api/courses/{id}
- 需要鉴权
- 响应：
```json
{"code": 0, "message": "ok", "data": null}
```

### 4.3 Deadlines

#### GET /api/deadlines
- 需要鉴权
- 返回当前用户所有 DDL
- 响应：
```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "id": 1,
      "title": "数据结构作业3",
      "course_id": 1,
      "due_time": "2026-10-20T23:59:00",
      "status": "pending",
      "created_at": "2026-10-16T12:00:00"
    }
  ]
}
```

#### POST /api/deadlines
- 需要鉴权
- 请求：
```json
{
  "title": "数据结构作业3",
  "course_id": 1,
  "due_time": "2026-10-20T23:59:00",
  "status": "pending"
}
```
- `course_id` 可选，`status` 可选，默认 `"pending"`
- 响应：同 GET 单个 DDL

#### GET /api/deadlines/{id}
- 需要鉴权
- 响应：同上单个 DDL

#### PUT /api/deadlines/{id}
- 需要鉴权
- 请求体同 POST，字段可选
- 响应：更新后的 DDL

#### DELETE /api/deadlines/{id}
- 需要鉴权
- 响应：
```json
{"code": 0, "message": "ok", "data": null}
```

### 4.4 Notes

#### GET /api/notes
- 需要鉴权
- 返回当前用户所有笔记
- 响应：
```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "id": 1,
      "title": "KV 学习笔记",
      "content_md": "# WAL\n...",
      "tags": "KV,存储",
      "created_at": "2026-10-16T12:00:00",
      "updated_at": "2026-10-16T12:00:00"
    }
  ]
}
```

#### POST /api/notes
- 需要鉴权
- 请求：
```json
{
  "title": "KV 学习笔记",
  "content_md": "# WAL\n...",
  "tags": "KV,存储"
}
```
- `tags` 可选
- 响应：同 GET 单个笔记

#### GET /api/notes/{id}
- 需要鉴权
- 响应：同上单个笔记

#### PUT /api/notes/{id}
- 需要鉴权
- 请求体同 POST，字段可选
- 响应：更新后的笔记

#### DELETE /api/notes/{id}
- 需要鉴权
- 响应：
```json
{"code": 0, "message": "ok", "data": null}
```

---

## 5. 数据库表

开发期使用 SQLite，部署可切换 MySQL。字段类型使用 SQLAlchemy 通用类型，不写数据库特有语法。

### 5.1 users
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, autoincrement | |
| username | String(50) | unique, not null | |
| email | String(255) | unique, not null | |
| hashed_password | String(255) | not null | |
| created_at | DateTime | default now | |

### 5.2 courses
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, autoincrement | |
| user_id | Integer | FK → users.id, not null, ondelete CASCADE | |
| name | String(100) | not null | |
| teacher | String(50) | nullable | |
| location | String(100) | nullable | |
| day_of_week | Integer | not null | 1-7，1=周一 |
| start_time | String(5) | not null | "HH:MM" |
| end_time | String(5) | not null | "HH:MM" |
| week_range | String(50) | nullable | "1-16" |
| created_at | DateTime | default now | |

### 5.3 deadlines
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, autoincrement | |
| user_id | Integer | FK → users.id, not null, ondelete CASCADE | |
| title | String(200) | not null | |
| course_id | Integer | FK → courses.id, nullable, ondelete SET NULL | |
| due_time | DateTime | not null | |
| status | String(20) | not null, default "pending" | pending/done |
| created_at | DateTime | default now | |

### 5.4 notes
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, autoincrement | |
| user_id | Integer | FK → users.id, not null, ondelete CASCADE | |
| title | String(200) | not null | |
| content_md | Text | not null | Markdown 源文 |
| tags | String(255) | nullable | 逗号分隔 |
| created_at | DateTime | default now | |
| updated_at | DateTime | default now, onupdate now | |

---

## 6. 前端调用说明

- 前端 base：`http://127.0.0.1:5173`
- Vite 代理配置：
  - `/api` → `http://127.0.0.1:8000`
  - `/kv` → `http://127.0.0.1:8000`
- 请求后端 API 时自动带 `Authorization: Bearer <token>`
- 统一处理后端响应信封：`code === 0` 取 `data`，否则弹错误提示

---

## 7. 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.1 | 2026-10-15 | 初稿，未定稿 |
| v1.0 | 2026-10-16 | 定稿：KV 独立格式、auth 路径补齐、表结构带类型约束、保留 /health |

---

## 8. 备注

- 不做 API 版本前缀（如 `/v1`），保持路径简洁
- 单进程运行，自研 KV 不支持多进程共享
- 所有资源默认按 `user_id` 隔离，`user_id` 从 JWT 解析，不在请求体中传
- 日期时间统一用 ISO 8601，避免时区问题