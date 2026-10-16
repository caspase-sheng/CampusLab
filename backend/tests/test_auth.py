"""auth 接口的接口测试（契约 §4.1）。

库用 tmp_path 下的**文件** SQLite，不是 ``sqlite://`` 内存库：TestClient 发请求时
应用可能跑在别的线程里（anyio 的线程池），内存库是「一个连接一个实例」，换线程
就换库，表直接看不见，用例会红得莫名其妙。换成文件库，多线程连的是同一个文件，
没这个问题。

``get_db`` 用 ``app.dependency_overrides`` 换掉，鉴权依赖 ``get_current_user``
内部也是 ``Depends(get_db)``，所以一条 override 就能同时管到 auth 路由和依赖。
另外把 ``get_engine`` 也覆盖成 tmp 目录的引擎，免得第 13 条打到 ``/kv`` 的用例
把段文件写进仓库的 ``data/kv`` 里。

最后一个用例专门盯「两个异常处理器合并」这件事：``/kv`` 校验失败仍要是 400，
``/api`` 校验失败要是 422 信封。合并时只要不小心把 KV 那支漏掉，它就红。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, verify_password
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys, get_db
from app.kv.engine import KVEngine
from app.kv.server import get_engine
from app.main import app
from app.models.user import User

REGISTER = {
    "username": "alice",
    "email": "alice@example.com",
    "password": "secret123",
}


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    """建一个 tmp 文件库、一个 tmp KV 引擎，都注入 app，然后给一个 TestClient。"""
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db() -> Iterator[object]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    kv_engine = KVEngine(
        data_dir=str(tmp_path / "kv"), segment_max_bytes=256, cache_capacity=8
    )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_engine] = lambda: kv_engine
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        kv_engine.close()
        engine.dispose()


def _register(client: TestClient, **overrides) -> None:
    """注册一个用户，字段按需覆盖。"""
    payload = dict(REGISTER)
    payload.update(overrides)
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 200, r.text


def _login(client: TestClient, **overrides) -> str:
    """登录并返回 access_token。"""
    payload = {"username": REGISTER["username"], "password": REGISTER["password"]}
    payload.update(overrides)
    r = client.post("/api/auth/login", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


# ------------------------------------------------------------------ register


def test_register_ok(client: TestClient) -> None:
    """注册成功：200，信封三个字段齐，data 里只有 id/username/email。"""
    r = client.post("/api/auth/register", json=REGISTER)
    assert r.status_code == 200

    body = r.json()
    assert set(body) == {"code", "message", "data"}
    assert body["code"] == 0
    assert body["message"] == "ok"

    data = body["data"]
    assert set(data) == {"id", "username", "email"}
    assert isinstance(data["id"], int)
    assert data["username"] == "alice"
    assert data["email"] == "alice@example.com"
    # 哈希密码不能出现在响应里
    assert "hashed_password" not in data


def test_register_duplicate_username(client: TestClient) -> None:
    """用户名重复：422，信封 code 也是 422，data 为 null。"""
    _register(client)

    r = client.post(
        "/api/auth/register",
        json={"username": "alice", "email": "other@example.com", "password": "x"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body == {"code": 422, "message": "用户名已存在", "data": None}


def test_register_duplicate_email(client: TestClient) -> None:
    """邮箱重复：422。"""
    _register(client)

    r = client.post(
        "/api/auth/register",
        json={"username": "bob", "email": "alice@example.com", "password": "x"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422
    assert body["data"] is None
    assert body["message"] == "邮箱已被注册"


def test_register_missing_password_gets_envelope(client: TestClient) -> None:
    """缺 password 字段：422，且 body 是信封，不是裸的 {"detail": [...]}。"""
    r = client.post(
        "/api/auth/register",
        json={"username": "alice", "email": "alice@example.com"},
    )
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"code", "message", "data"}
    assert body["code"] == 422
    assert body["data"] is None
    assert "参数校验失败" in body["message"]
    # 校验错误的细节不能塞进 data
    assert not isinstance(body["data"], list)


def test_password_stored_hashed(client: TestClient, tmp_path) -> None:
    """库里存的是 bcrypt 哈希，不是明文；哈希能用 verify_password 校验通过。"""
    _register(client)

    # 另开一个 session 直接查表，绕开接口层
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with factory() as db:
            user = db.scalar(select(User).where(User.username == "alice"))
            assert user is not None
            assert user.hashed_password != REGISTER["password"]
            assert verify_password(REGISTER["password"], user.hashed_password) is True
    finally:
        engine.dispose()


# --------------------------------------------------------------------- login


def test_login_ok(client: TestClient) -> None:
    """登录成功：信封 data 里有 access_token 和 token_type=="bearer"。"""
    _register(client)

    r = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert set(body["data"]) == {"access_token", "token_type"}
    assert body["data"]["access_token"]
    assert body["data"]["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient) -> None:
    """密码不对：401，信封 code 为 401。"""
    _register(client)

    r = client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert r.status_code == 401
    assert r.json() == {"code": 401, "message": "用户名或密码错误", "data": None}


def test_login_unknown_username(client: TestClient) -> None:
    """用户名不存在：也是同样的 401，不泄露用户名是否存在。"""
    r = client.post(
        "/api/auth/login", json={"username": "nobody", "password": "whatever"}
    )
    assert r.status_code == 401
    assert r.json() == {"code": 401, "message": "用户名或密码错误", "data": None}


# ------------------------------------------------------------------------ me


def test_me_without_token(client: TestClient) -> None:
    """不带 Authorization：401 信封（不是 FastAPI 默认的 403）。"""
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == 401
    assert body["data"] is None


def test_me_with_valid_token(client: TestClient) -> None:
    """带合法 token：200，data 里的三个字段都对。"""
    _register(client)
    token = _login(client)

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["username"] == "alice"
    assert body["data"]["email"] == "alice@example.com"
    assert isinstance(body["data"]["id"], int)


def test_me_with_garbage_token(client: TestClient) -> None:
    """乱写的 token：401。"""
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["code"] == 401


def test_me_with_expired_token(client: TestClient) -> None:
    """过期 token：401。

    ``create_access_token`` 里写的是 ``expires_minutes or settings.xxx``，
    -1 是真值，不会被默认的 1440 顶掉，所以签出来的 exp 就是过去时间。
    """
    token = create_access_token(subject="1", expires_minutes=-1)

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["code"] == 401


# ------------------------------------------------------------------- 回归


def test_error_handling_split_between_kv_and_api(client: TestClient) -> None:
    """回归：合并处理器之后，/kv 校验失败还是 400 裸 detail，/api 是 422 信封。"""
    r = client.post("/kv/set", json={"key": "a"})
    assert r.status_code == 400
    body = r.json()
    assert set(body) == {"detail"}
    assert isinstance(body["detail"], str)
    assert "参数校验失败" in body["detail"]

    r = client.post("/api/auth/login", json={"username": "alice"})
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"code", "message", "data"}
    assert body["code"] == 422
