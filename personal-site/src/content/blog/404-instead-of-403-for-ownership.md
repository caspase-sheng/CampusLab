---
title: 越权访问为什么返回 404 而不是 403
description: 取别人的课程、DDL、笔记时，后端统一回 404，而不是「存在但不属于你」的 403。记一下这个选择背后的理由，以及一处反例。
date: 2026-10-18
tags:
  - 后端
  - API
  - 鉴权
draft: false
---

写「取单条」这几个接口时，碰到一个选择：如果这条记录存在，但不属于当前用户，该回什么状态码。第一反应是 403——资源在，只是你没权限。后来放弃了这条路。

backend/app/api/ 下的 courses.py、deadlines.py、notes.py 三个文件里，各有一个同名的私有函数 `_get_owned_or_404`。它的查询把 `id` 和 `user_id` 一起放进条件：

```python
def _get_owned_or_404(db: Session, course_id: int, user_id: int) -> Course:
    course = db.scalar(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course
```

查不到就 404。这里没有走「先按 id 查出来、再比对 user_id、不相等就返回 403」那条路。

## 为什么不用 403

因为 403 本身带着信息。它等于告诉调用方：这个 id 是存在的，只是不属于你。把状态码当成探针，就能一个个试出别人数据的 id 范围——虽然拿不到内容，但能确认存在性，这已经是不该给的东西。

把「不存在」和「属于别人」合并成同一个 404，消息也保持完全一致，调用方就区分不了这两种情况。想探测的那一方拿不到任何有效信号。三个文件的 docstring 里都把这个理由写了下来，省得以后有人看到 404 觉得是写错了、顺手改成 403。

## 一处不一样的地方

deadlines.py 里还有个 `_ensure_course_owned`，它会返回 422，而不是 404。这看着矛盾，其实处理的是另一件事。

`_get_owned_or_404` 校验的是 URI 里的 id，那是对「要访问的资源」的判断。而 `_ensure_course_owned` 校验的是请求体里引用的 `course_id`——创建或更新一条 DDL 时，如果带了课程，得先确认这门课存在且属于当前用户：

```python
if course is None:
    raise HTTPException(status_code=422, detail="课程不存在或不属于当前用户")
```

问题出在请求体里引用的资源无效，属于参数校验失败，不是 URI 里的资源找不到。用 404 会让调用方以为要访问的 DDL 路径有问题，语义就歪了。同样地，这里也不区分「课程不存在」和「课程是别人的」，两种情况共用一句 422，免得靠状态码去猜别人的课程是否存在。

## 对应的测试

越权这块在 backend/tests/ 下有专门的用例：`test_get_other_users_course_404`、`test_get_other_users_deadline_404`、`test_get_other_users_note_404`，三个资源各一个。它们断言的是「拿别人的 id 去取，得到 404」，正好锁住上面这个约定，后面谁把 404 改成 403，测试就会红。
