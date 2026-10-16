"""LRUCache 的单元测试。"""

import threading

import pytest

from app.kv.lru import LRUCache


def test_capacity_must_be_positive() -> None:
    """容量为 0 或负数时应该抛 ValueError。"""
    with pytest.raises(ValueError):
        LRUCache(0)
    with pytest.raises(ValueError):
        LRUCache(-5)


def test_evicts_least_recently_used() -> None:
    """容量满时淘汰最久未使用的键。"""
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # 访问 a，让 b 变成最久未使用
    cache.put("c", 3)  # 触发淘汰
    assert cache.get("b") is None  # b 已被淘汰
    assert cache.get("a") == 1  # a 还在
    assert cache.get("c") == 3
    assert cache.size() == 2


def test_get_refreshes_usage_order() -> None:
    """get 命中会刷新使用顺序，改变后续淘汰的对象。"""
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)  # 顺序：a(旧) -> b(新)
    cache.get("a")  # 顺序：b(旧) -> a(新)
    cache.put("c", 3)  # 淘汰 b
    assert cache.get("b") is None
    assert cache.size() == 2


def test_remove() -> None:
    """remove 存在返回 True，不存在返回 False。"""
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.remove("a") is True
    assert cache.remove("a") is False
    assert cache.size() == 0


def test_hit_rate() -> None:
    """命中率计算正确，从未访问时为 0.0。"""
    cache = LRUCache(2)
    assert cache.hit_rate() == 0.0  # 一次访问都没有

    cache.put("a", 1)
    assert cache.get("a") == 1  # 1 次命中
    assert cache.get("x") is None  # 1 次未命中
    assert cache.hit_rate() == pytest.approx(0.5)

    assert cache.get("a") == 1  # 再来一次命中
    assert cache.hit_rate() == pytest.approx(2 / 3)


def test_clear_resets() -> None:
    """clear 清空条目并重置计数。"""
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.get("a")
    cache.clear()
    assert cache.size() == 0
    assert cache.hit_rate() == 0.0


def test_concurrent_put_get() -> None:
    """多线程并发 put / get 不应崩溃，容量约束仍成立。"""
    cache = LRUCache(16)
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(200):
                key = f"k{n}-{i}"
                cache.put(key, i)
                cache.get(key)
                cache.get("missing")
        except BaseException as exc:  # pragma: no cover - 出错才会走到
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert cache.size() <= 16
