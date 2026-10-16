"""LRU 缓存，CampusLab 自研 KV 引擎的内存基础件。

设计说明：
- 用 collections.OrderedDict 记录访问顺序，队首是最久未使用的键，队尾是最近使用的。
- 命中 / 未命中计数只在 get 里更新，put / remove 不动这两个计数。
- 所有操作都在同一把 threading.RLock 下执行，保证多线程 put / get 不会把内部结构弄乱。

这个组件只管「按容量淘汰最久未使用」，不做 TTL / 过期判断，
过期是上层 KVEngine 的职责。
"""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Any


class LRUCache:
    """固定容量的 LRU 缓存。

    Args:
        capacity: 最多能装多少个键，必须是正整数，否则抛 ValueError。

    Attributes:
        _data: 存数据的 OrderedDict，键为 str，值为任意对象。
        _hits: 命中次数，由 get 更新。
        _misses: 未命中次数，由 get 更新。
        _lock: 可重入锁，保护上面几个字段。
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity 必须是正整数，收到 {capacity}")
        self._capacity: int = capacity
        self._data: OrderedDict[str, Any] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0
        self._lock: RLock = RLock()

    def get(self, key: str) -> Any | None:
        """取键对应的值。

        命中的话把该键挪到队尾（标记为最近使用）并累加命中计数；
        没命中则累加未命中计数并返回 None。

        Args:
            key: 要查询的键。

        Returns:
            缓存里存在则返回值，否则返回 None。
        """
        with self._lock:
            if key in self._data:
                self._hits += 1
                self._data.move_to_end(key)
                return self._data[key]
            self._misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        """写入或更新一个键。

        键已存在时直接覆盖并挪到队尾；写入后如果条数超过容量，
        从队首淘汰最久未使用的键，直到条数回到容量以内。

        Args:
            key: 键。
            value: 值，类型不限。
        """
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._capacity:
                # last=False 表示从队首弹出，也就是最久未使用的那个
                self._data.popitem(last=False)

    def remove(self, key: str) -> bool:
        """删除一个键。

        Args:
            key: 要删除的键。

        Returns:
            键存在并删除返回 True，不存在返回 False。
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def size(self) -> int:
        """返回当前缓存里的条目数。"""
        with self._lock:
            return len(self._data)

    def hit_rate(self) -> float:
        """返回命中率。

        命中率 = 命中次数 / (命中次数 + 未命中次数)，取值 0.0 ~ 1.0；
        一次访问都没有时返回 0.0，避免除零。
        """
        with self._lock:
            total = self._hits + self._misses
            if total == 0:
                return 0.0
            return self._hits / total

    def clear(self) -> None:
        """清空所有条目，并把命中 / 未命中计数一并归零。"""
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0

    def items(self) -> list[tuple[str, Any]]:
        """按访问顺序返回 (key, value) 的快照，队首是最久未使用的。

        这是一个只读快照：不改动访问顺序，也不计入命中 / 未命中。
        KVEngine 需要枚举全部键（keys / stats）时用它，
        避免用 get 枚举导致计数被污染、使用顺序被打乱。
        """
        with self._lock:
            return list(self._data.items())
