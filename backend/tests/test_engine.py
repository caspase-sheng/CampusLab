"""KVEngine 磁盘持久化层的单元测试。

所有用例都用 pytest 的 tmp_path 作为 data_dir，不往仓库目录写任何东西。
"""

from __future__ import annotations

import threading
import time

import pytest

from app.kv.datafile import OP_SET, decode_record
from app.kv.engine import KVEngine


def _open(tmp_path, **kwargs) -> KVEngine:
    """用临时目录建一个引擎，省得每个用例重复拼 data_dir。"""
    return KVEngine(data_dir=str(tmp_path), **kwargs)


def test_set_then_get_from_disk(tmp_path) -> None:
    """set 之后 get 能拿到值，且值确实落在磁盘段文件里。"""
    engine = _open(tmp_path)
    engine.set("name", "alice")

    # 段文件确实生成了，而且里面能找到 key / value 的原始字节
    seg_files = list(tmp_path.glob("*.seg"))
    assert len(seg_files) == 1
    blob = seg_files[0].read_bytes()
    assert b"name" in blob
    assert b"alice" in blob

    # 直接从文件的第一个字节解出这条记录，确认头 / 偏移都对
    record = decode_record(blob, 0)
    assert record is not None
    assert record.op == OP_SET
    assert record.key == "name"
    assert record.value == "alice"

    assert engine.get("name") == "alice"
    assert engine.exists("name") is True
    engine.close()


def test_restart_recovers_values(tmp_path) -> None:
    """重启恢复：close 后用同一 data_dir 新建引擎，值和 keys 都在。"""
    engine = _open(tmp_path)
    engine.set("a", "1")
    engine.set("b", "2")
    engine.set("c", "3", ttl=60)
    keys_before = sorted(engine.keys())
    engine.close()

    engine2 = _open(tmp_path)
    assert engine2.get("a") == "1"
    assert engine2.get("b") == "2"
    assert engine2.get("c") == "3"
    assert sorted(engine2.keys()) == keys_before
    engine2.close()


def test_restart_replays_tombstone(tmp_path) -> None:
    """重启后 delete 仍然生效，tombstone 被正确重放。"""
    engine = _open(tmp_path)
    engine.set("gone", "x")
    assert engine.delete("gone") is True
    engine.set("keep", "y")
    engine.close()

    engine2 = _open(tmp_path)
    assert engine2.get("gone") is None
    assert "gone" not in engine2.keys()
    assert engine2.get("keep") == "y"
    engine2.close()


def test_ttl_expires_and_stays_expired_after_restart(tmp_path) -> None:
    """ttl 过期后 get 返回 None；重启后仍然返回 None。"""
    engine = _open(tmp_path)
    engine.set("k", "v", ttl=1)
    assert engine.get("k") == "v"
    time.sleep(1.2)
    assert engine.get("k") is None
    engine.close()

    engine2 = _open(tmp_path)
    assert engine2.get("k") is None
    assert "k" not in engine2.keys()
    engine2.close()


def test_ttl_must_be_positive(tmp_path) -> None:
    """ttl <= 0 抛 ValueError。"""
    engine = _open(tmp_path)
    with pytest.raises(ValueError):
        engine.set("k", "v", ttl=0)
    with pytest.raises(ValueError):
        engine.set("k", "v", ttl=-1)
    engine.close()


def test_cache_capacity_must_be_positive(tmp_path) -> None:
    """cache_capacity <= 0 抛 ValueError。"""
    with pytest.raises(ValueError):
        KVEngine(data_dir=str(tmp_path), cache_capacity=0)


def test_get_with_ttl_remaining(tmp_path) -> None:
    """get_with_ttl 的剩余秒数在合理区间，永不过期 / 不存在的键行为正确。"""
    engine = _open(tmp_path)
    engine.set("k", "v", ttl=60)
    result = engine.get_with_ttl("k")
    assert result is not None
    value, remaining = result
    assert value == "v"
    assert remaining in (59, 60)  # 向下取整，可能是 59 或 60

    engine.set("forever", "v")
    assert engine.get_with_ttl("forever") == ("v", None)
    assert engine.get_with_ttl("nope") is None
    engine.close()


def test_keys_excludes_expired(tmp_path) -> None:
    """keys() 不包含已过期的键。"""
    engine = _open(tmp_path)
    engine.set("keep", "1")
    engine.set("gone", "2", ttl=1)
    time.sleep(1.2)
    keys = engine.keys()
    assert "keep" in keys
    assert "gone" not in keys
    engine.close()


def test_stats_six_fields(tmp_path) -> None:
    """stats() 六个字段齐全且数值正确，exists() / stats() 不改变计数。"""
    engine = _open(tmp_path, cache_capacity=8)
    engine.set("a", "1")
    engine.set("b", "2")
    assert engine.get("a") == "1"  # 1 次命中
    assert engine.get("missing") is None  # 1 次未命中

    stats = engine.stats()
    assert set(stats) == {"hits", "misses", "hit_rate", "keys", "wal_size", "files"}
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == pytest.approx(0.5)
    assert stats["keys"] == 2
    assert stats["files"] == 1
    assert stats["wal_size"] > 0

    # 纯查询不改变 hits / misses
    assert engine.exists("a") is True
    engine.exists("nope")
    engine.keys()
    again = engine.stats()
    assert again["hits"] == 1
    assert again["misses"] == 1
    engine.close()


def test_hit_rate_zero_when_never_accessed(tmp_path) -> None:
    """从未访问时 hit_rate 为 0.0。"""
    engine = _open(tmp_path)
    engine.set("a", "1")
    assert engine.stats()["hit_rate"] == 0.0
    engine.close()


def test_segment_rotation(tmp_path) -> None:
    """小阈值下写多条记录会滚动出多个段文件，且所有键都能读回。"""
    engine = _open(tmp_path, segment_max_bytes=128)
    count = 40
    for i in range(count):
        engine.set(f"key-{i:03d}", f"value-{i:03d}")

    assert engine.stats()["files"] > 1
    for i in range(count):
        assert engine.get(f"key-{i:03d}") == f"value-{i:03d}"
    engine.close()

    # 重启后把这些跨段数据全部读回来
    engine2 = _open(tmp_path, segment_max_bytes=128)
    assert engine2.stats()["files"] > 1
    for i in range(count):
        assert engine2.get(f"key-{i:03d}") == f"value-{i:03d}"
    engine2.close()


def test_bad_tail_is_repaired(tmp_path) -> None:
    """段尾追加垃圾字节后重启：有效键仍在，文件被截断到最后一条有效记录末尾。"""
    engine = _open(tmp_path)
    engine.set("a", "1")
    engine.set("b", "2")
    engine.close()

    seg_files = sorted(tmp_path.glob("*.seg"))
    assert len(seg_files) == 1
    target = seg_files[0]
    valid_size = target.stat().st_size

    # 往段尾塞几个垃圾字节（不足一条记录的固定头长度）
    garbage = b"\x00\x01garbage"
    with open(target, "ab") as f:
        f.write(garbage)
    assert target.stat().st_size == valid_size + len(garbage)

    engine2 = _open(tmp_path)
    assert engine2.get("a") == "1"
    assert engine2.get("b") == "2"
    assert target.stat().st_size == valid_size  # 坏尾被截掉
    engine2.close()


def test_compact_response_shape(tmp_path) -> None:
    """compact() 的响应形状——三个字段齐全、ok 为 True；空引擎返回 0 / 0。

    compact() 早已是真实现（app/kv/engine.py 里会真的合并段文件），真正的合并逻辑
    由 tests/test_compact.py 覆盖，这里只锁定返回结构的契约。
    """
    engine = _open(tmp_path, segment_max_bytes=128)
    for i in range(5):
        engine.set(f"k{i}", "v")

    result = engine.compact()
    assert set(result) == {"ok", "files_before", "files_after"}
    assert result["ok"] is True
    # files_before / files_after 都是非负整数。
    # 这里不再断言 before == after：那是「无操作占位」才成立的性质，
    # 真实现下 compact 会合并段文件，两个数只有碰巧相等，不能当契约。
    assert isinstance(result["files_before"], int) and result["files_before"] >= 0
    assert isinstance(result["files_after"], int) and result["files_after"] >= 0

    # 空引擎也应返回 0 / 0
    empty = _open(tmp_path / "sub")
    assert empty.compact() == {"ok": True, "files_before": 0, "files_after": 0}
    empty.close()
    engine.close()


def test_concurrent_set_get(tmp_path) -> None:
    """多线程并发 set / get 不应崩溃，写进去的值读得回来。"""
    # 缓存容量给足，避免并发写时把刚写的键从读缓存淘汰，让断言保持稳定
    engine = _open(tmp_path, cache_capacity=4096)
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(50):
                key = f"k{n}-{i}"
                engine.set(key, str(i))
                assert engine.get(key) == str(i)
        except BaseException as exc:  # pragma: no cover - 出错才会走到
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert engine.stats()["keys"] == 8 * 50
    engine.close()
