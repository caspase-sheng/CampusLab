---
title: SQLite 的外键默认关着，级联删除会静默失败
description: 模型里写了 ondelete="CASCADE"，删用户时子行却一条没少，也不报错。记一下 SQLite 的外键开关和那个要在每个连接上挂一次的监听器。
date: 2026-10-18
tags:
  - SQLite
  - SQLAlchemy
  - 数据库
draft: false
---

给模型加 `ondelete` 的时候，我默认以为写了就会生效。删一个用户，他名下的课程、DDL、笔记应该跟着一起走。跑起来才发现，用户没了，子行一条不少，也没有任何报错。

问题出在 SQLite 身上。它默认不强制外键。建表语句里写的 `ondelete="CASCADE"`、`ondelete="SET NULL"` 都还在，但它们要等 `PRAGMA foreign_keys=ON` 打开之后才真正执行。不开这个开关，删父行时子行纹丝不动——典型的静默失败，没有异常，没有日志，只能靠数行数发现。

## 给每个连接挂一个监听器

修法在 backend/app/db/session.py。那里有个 `enable_sqlite_foreign_keys(target_engine)`，用 SQLAlchemy 的事件钩子在每个新连接建立时把 PRAGMA 打开：

```python
@event.listens_for(target_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
```

`isinstance` 那个判断是有意的。这个 PRAGMA 是 SQLite 方言，别的数据库不认。判断成 `sqlite3.Connection` 之后，切到 MySQL 时这个监听器直接跳过，不会去执行一条对方看不懂的语句。所以同一份代码在两种库上都能跑。

## 内存库也要挂

这个函数没有写成模块私有，是为了复用。测试里的内存库同样默认不强制外键，如果不挂上它，级联删除的用例会假绿——表建出来了，删父行也「成功」了，但断言子行已经消失的那一句根本不会触发，因为子行压根没被删。tests/test_models.py 的 fixture 里复用了 `enable_sqlite_foreign_keys`，每个用例新建的 engine 都过一遍，这样才敢相信内存库上的级联行为和真实库一致。

## 两个验证点

级联到底有没有生效，看两个用例：

- `test_delete_user_cascades_children`：删掉 user 之后，名下的 courses / deadlines / notes 全部消失。
- `test_delete_course_sets_deadline_course_id_null`：删掉 course 之后，对应的 DDL 记录还在，只是 `course_id` 变成了 NULL。

一个验证 CASCADE，一个验证 SET NULL，两条语义都踩到了。

## 约束写在模型里

这些 `ondelete` 不是写在路由里的，是写在 backend/app/models/ 下的模型上：user.py、course.py、deadline.py、note.py 四个文件。子表指向 `users.id` 的外键配 CASCADE，`deadlines.course_id` 配 SET NULL。例如课程挂到用户是这样：

```python
user_id: Mapped[int] = mapped_column(
    ForeignKey("users.id", ondelete="CASCADE"), nullable=False
)
```

而 DDL 关联课程这一条，删课程时子行要留、只是断开关联：

```python
course_id: Mapped[int | None] = mapped_column(
    ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
)
```

模型层把意图写清楚，能不能真的执行则取决于连接上的那个 PRAGMA。这两件事是分开的，别指望其中之一单独就能兜住。
