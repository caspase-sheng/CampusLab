"""三个 CRUD 测试文件（courses / deadlines / notes）公用的 fixture。

原来 auth 测试里那份 ``client`` fixture（在 ``tests/test_auth.py`` 里）行为一模一样，
这里把它提到公共位置复用。``tests/test_auth.py`` 自己那份同名局部 fixture 优先级更高，
会盖住这份，行为和以前完全一致，互不干扰——所以这次没动 test_auth.py。

``client`` 用 tmp_path 下的**文件** SQLite，不用内存库：TestClient 发请求时应用可能
跑在别的线程里，内存库「一个连接一个实例」的做法换线程就换库、表看不见，用例会莫名
其妙地红。文件库多线程连的是同一个库，没这个问题。``get_db`` 和 ``get_engine`` 都用
``app.dependency_overrides`` 换成 tmp 目录的实例，免得把段文件写进仓库的 ``data/kv``。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys, get_db
from app.kv.engine import KVEngine
from app.kv.server import get_engine
from app.main import app


def register_and_login(client: TestClient) -> dict[str, str]:
    """注册一个全新用户并登录，返回可直接用的 ``Authorization`` 请求头字典。

    用户名 / 邮箱都带一段 uuid 后缀，所以同一个用例里可以连着建好几个互不相干的
    用户（越权测试需要两个用户），不会撞用户名 / 邮箱的唯一约束。
    """
    suffix = uuid.uuid4().hex[:8]
    username = f"user_{suffix}"
    password = "secret123"

    r = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{suffix}@example.com",
            "password": password,
        },
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    token = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    """建一个 tmp 文件库、一个 tmp KV 引擎，注入 app，然后给一个 TestClient。"""
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


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    """一个已注册用户的 ``Authorization`` 请求头，供单用户用例直接用。"""
    return register_and_login(client)
