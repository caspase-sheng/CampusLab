"""模型包入口。契约见 docs/CONTRACT.md §5。

这里必须把四个模型全部导入：Alembic 的 env.py 会 ``import app.models``，只有被
导入过的模型才会注册到 ``Base.metadata``。漏掉任何一个，``alembic revision
--autogenerate`` 就扫不到对应的表，会生成一个空迁移。
"""

from app.models.course import Course
from app.models.deadline import Deadline
from app.models.note import Note
from app.models.user import User

__all__ = ["User", "Course", "Deadline", "Note"]
