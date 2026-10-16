"""courses 接口的接口测试（契约 §4.2）。用 conftest 里的 ``client`` / ``auth_headers``。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import register_and_login

COURSE = {
    "name": "数据结构",
    "teacher": "张老师",
    "location": "教三-201",
    "day_of_week": 1,
    "start_time": "08:00",
    "end_time": "09:40",
    "week_range": "1-16",
}


def _create_course(
    client: TestClient, headers: dict[str, str], **overrides
) -> dict:
    """按 COURSE 建一门课（可覆盖字段），断言 200，返回 data。"""
    payload = dict(COURSE)
    payload.update(overrides)
    r = client.post("/api/courses", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _me_id(client: TestClient, headers: dict[str, str]) -> int:
    """取当前 token 对应用户的 id。"""
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


# ------------------------------------------------------------------ 创建 / 列表


def test_create_course_ok(client: TestClient, auth_headers: dict[str, str]) -> None:
    """创建成功：200 信封，字段正确，user_id 等于当前用户。"""
    r = client.post("/api/courses", json=COURSE, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["message"] == "ok"

    data = body["data"]
    assert data["name"] == "数据结构"
    assert data["teacher"] == "张老师"
    assert data["location"] == "教三-201"
    assert data["day_of_week"] == 1
    assert data["start_time"] == "08:00"
    assert data["end_time"] == "09:40"
    assert data["week_range"] == "1-16"
    assert isinstance(data["id"], int)
    assert data["user_id"] == _me_id(client, auth_headers)


def test_list_only_own(client: TestClient, auth_headers: dict[str, str]) -> None:
    """列表只返回自己的课程，不含别人的。"""
    _create_course(client, auth_headers, name="我的课")
    other = register_and_login(client)
    _create_course(client, other, name="别人的课")

    r = client.get("/api/courses", headers=auth_headers)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["data"]]
    assert names == ["我的课"]


def test_get_course_ok(client: TestClient, auth_headers: dict[str, str]) -> None:
    """取单条成功：200，data 里的 id 对得上。"""
    course = _create_course(client, auth_headers)
    r = client.get(f"/api/courses/{course['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["id"] == course["id"]


# -------------------------------------------------------------------- 鉴权 / 404


def test_list_without_token_401(client: TestClient) -> None:
    """不带 token：401 信封。"""
    r = client.get("/api/courses")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == 401
    assert body["data"] is None


def test_get_unknown_id_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """取不存在的 id：404 信封。"""
    r = client.get("/api/courses/999999", headers=auth_headers)
    assert r.status_code == 404
    assert r.json() == {"code": 404, "message": "课程不存在", "data": None}


def test_get_other_users_course_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """越权：A 建的课，B 拿自己的 token 去 GET → 404（不是 200 也不是 403）。"""
    course = _create_course(client, auth_headers)
    other = register_and_login(client)

    r = client.get(f"/api/courses/{course['id']}", headers=other)
    assert r.status_code == 404
    assert r.json() == {"code": 404, "message": "课程不存在", "data": None}


# ------------------------------------------------------------------------ 更新


def test_partial_update_keeps_other_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """部分更新：只传一个字段，其他字段保持原值。"""
    course = _create_course(client, auth_headers)

    r = client.put(
        f"/api/courses/{course['id']}", json={"location": "新地点"}, headers=auth_headers
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["location"] == "新地点"
    # 没传的字段原样保留
    assert data["name"] == "数据结构"
    assert data["teacher"] == "张老师"
    assert data["day_of_week"] == 1
    assert data["start_time"] == "08:00"


def test_partial_update_can_set_null(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """部分更新能把可空字段显式置成 null（teacher）。"""
    course = _create_course(client, auth_headers)
    assert course["teacher"] == "张老师"

    r = client.put(
        f"/api/courses/{course['id']}", json={"teacher": None}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["teacher"] is None

    # 再读回来确认落库了
    r = client.get(f"/api/courses/{course['id']}", headers=auth_headers)
    assert r.json()["data"]["teacher"] is None


def test_update_other_users_course_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """更新不存在 / 别人的课程：都 404，且别人的课没被改动。"""
    course = _create_course(client, auth_headers)
    other = register_and_login(client)

    r = client.put(
        f"/api/courses/{course['id']}",
        json={"name": "被篡改"},
        headers=other,
    )
    assert r.status_code == 404

    r = client.put("/api/courses/999999", json={"name": "x"}, headers=auth_headers)
    assert r.status_code == 404

    # A 再查一次，名字没变
    r = client.get(f"/api/courses/{course['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "数据结构"


# ------------------------------------------------------------------------ 删除


def test_delete_then_get_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """删除成功：200 信封 data 为 null，删完再 GET → 404。"""
    course = _create_course(client, auth_headers)

    r = client.delete(f"/api/courses/{course['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"code": 0, "message": "ok", "data": None}

    r = client.get(f"/api/courses/{course['id']}", headers=auth_headers)
    assert r.status_code == 404


def test_delete_other_users_course_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """删除别人的课程：404，且课程仍然存在。"""
    course = _create_course(client, auth_headers)
    other = register_and_login(client)

    r = client.delete(f"/api/courses/{course['id']}", headers=other)
    assert r.status_code == 404
    assert r.json()["code"] == 404

    # A 用自己 token 再查一次，确认没被删掉
    r = client.get(f"/api/courses/{course['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["id"] == course["id"]


# --------------------------------------------------------------------- 校验


def test_update_rejects_null_on_required_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """PUT 给非空字段显式传 null：422 信封，且原值不被写坏。

    这些字段在库里是 NOT NULL，之前允许显式传 null，commit 时直接撞 IntegrityError
    变成 500；现在 schema 层的校验器提前拦成 422。
    """
    course = _create_course(client, auth_headers)

    r = client.put(
        f"/api/courses/{course['id']}", json={"name": None}, headers=auth_headers
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422
    assert body["data"] is None

    # 再 GET 一次，确认这次被拒的更新没有把 name 写坏
    r = client.get(f"/api/courses/{course['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "数据结构"

    # day_of_week 同样是 NOT NULL，也必须拦下
    r = client.put(
        f"/api/courses/{course['id']}",
        json={"day_of_week": None},
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert r.json()["code"] == 422
    assert r.json()["data"] is None


def test_create_validation_error_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """校验失败：day_of_week 越界 / 时间格式不对，都 422 信封。"""
    r = client.post(
        "/api/courses", json={**COURSE, "day_of_week": 8}, headers=auth_headers
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422
    assert body["data"] is None

    r = client.post(
        "/api/courses", json={**COURSE, "start_time": "8:00"}, headers=auth_headers
    )
    assert r.status_code == 422
    assert r.json()["code"] == 422
