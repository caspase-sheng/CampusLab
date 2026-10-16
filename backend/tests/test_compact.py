"""KVEngine compaction 的单元测试。

所有用例都用 pytest 的 tmp_path 作为 data_dir，不往仓库目录写任何东西。
重点验证：旧版本 / tombstone / 过期记录被丢掉，段文件被清干净、编号连续，
以及 compaction 之后引擎仍然可读可写、重启可恢复。
"""

from __future__ import annotations

import time

import pytest

from app.kv.engine import KVEngine


def _open(tmp_path, **kwargs) -> KVEngine:
    """用临时目录建一个引擎，省得每个用例重复拼 data_dir。"""
    return KVEngine(data_dir=str(tmp_path), **kwargs)


def _seg_names(tmp_path) -> list[str]:
    """返回 data_dir 下所有段文件名（已排序）。"""
    return sorted(path.name for path in tmp_path.glob("*.seg"))


def _consecutive_names(files_after: int) -> list[str]:
    """按「编号从 1 连续到 files_after」拼出期望的文件名列表。"""
    return [f"{i:08d}.seg" for i in range(1, files_after + 1)]


def test_compact_overwrites_collapse_to_latest(tmp_path) -> None:
    """覆盖写 100 次后 compact：旧段清干净、只留最新值、重启仍正确。"""
    # 阈值给得很小，让每条记录基本独占一个段，制造出大量可回收的旧段
    engine = _open(tmp_path, segment_max_bytes=128)
    key = "hot"
    writer = "x" * 60  # 单条记录约 84 字节，小于 128，不会撑爆阈值
    for i in range(100):
        engine.set(key, f"{i:02d}{writer}")

    files_before = engine.stats()["files"]
    assert files_before > 1  # 100 次覆盖写确实滚出了多个段

    result = engine.compact()
    assert result["ok"] is True
    assert result["files_before"] == files_before
    assert result["files_after"] < files_before

    # 旧段被清干净，剩下的是 00000001.seg 到 0000000N.seg 连续编号
    assert _seg_names(tmp_path) == _consecutive_names(result["files_after"])

    # 读到的必须是最后一次写的值
    assert engine.get(key) == f"99{writer}"
    engine.close()

    # 重启后仍然正确
    engine2 = _open(tmp_path, segment_max_bytes=128)
    assert engine2.get(key) == f"99{writer}"
    assert engine2.keys() == [key]
    engine2.close()


def test_compact_drops_deleted_keys(tmp_path) -> None:
    """被 delete 的键不产生记录：compact 后读不到，keys() 也不含它们。"""
    engine = _open(tmp_path, segment_max_bytes=128)
    survivors = ["keep-1", "keep-2", "keep-3"]
    removed = ["gone-1", "gone-2"]
    for key in survivors:
        engine.set(key, f"value-of-{key}")
    for key in removed:
        engine.set(key, "temp")
    for key in removed:
        assert engine.delete(key) is True

    engine.compact()

    for key in removed:
        assert engine.get(key) is None
    for key in survivors:
        assert engine.get(key) == f"value-of-{key}"

    keys = engine.keys()
    for key in removed:
        assert key not in keys
    for key in survivors:
        assert key in keys
    engine.close()

    # 重启后 tombstone 依然生效
    engine2 = _open(tmp_path, segment_max_bytes=128)
    for key in removed:
        assert engine2.get(key) is None
    for key in survivors:
        assert engine2.get(key) == f"value-of-{key}"
    engine2.close()


def test_compact_drops_expired_keys(tmp_path) -> None:
    """过期键被丢弃：compact 后从 keys() 消失、重启也读不到。"""
    # 阈值压到 40，让两条记录各自滚成一个段，便于观察段数减少
    engine = _open(tmp_path, segment_max_bytes=40)
    engine.set("short-lived", "v", ttl=1)
    engine.set("forever", "keep", ttl=None)
    files_before = engine.stats()["files"]
    assert files_before >= 2

    time.sleep(1.2)

    result = engine.compact()
    assert "short-lived" not in engine.keys()
    assert "forever" in engine.keys()
    # 过期键被丢掉，段里只剩一条记录，段数相应减少
    assert result["files_after"] < files_before
    engine.close()

    engine2 = _open(tmp_path, segment_max_bytes=40)
    assert engine2.get("short-lived") is None
    assert "short-lived" not in engine2.keys()
    assert engine2.get("forever") == "keep"
    engine2.close()


def test_compact_all_keys_deleted(tmp_path) -> None:
    """全部键都被删除时 compact：不产生新段，data_dir 下没有 *.seg。"""
    engine = _open(tmp_path, segment_max_bytes=128)
    for i in range(5):
        engine.set(f"k{i}", "v")
    for i in range(5):
        assert engine.delete(f"k{i}") is True
    files_before = engine.stats()["files"]
    assert files_before >= 1

    result = engine.compact()
    assert result == {"ok": True, "files_before": files_before, "files_after": 0}
    assert _seg_names(tmp_path) == []
    engine.close()

    engine2 = _open(tmp_path, segment_max_bytes=128)
    assert engine2.keys() == []
    assert engine2.stats()["files"] == 0
    engine2.close()


def test_compact_empty_engine(tmp_path) -> None:
    """空引擎 compact 返回固定的 0 / 0。"""
    engine = _open(tmp_path)
    assert engine.compact() == {"ok": True, "files_before": 0, "files_after": 0}
    engine.close()


def test_compact_then_writable_and_recoverable(tmp_path) -> None:
    """compact 之后仍可正常 set，重启后新写入的键也能恢复。"""
    engine = _open(tmp_path, segment_max_bytes=128)
    for i in range(20):
        engine.set(f"old-{i}", "v")
    engine.compact()

    fresh = {f"new-{i}": f"value-{i}" for i in range(15)}
    for key, value in fresh.items():
        engine.set(key, value)
    for key, value in fresh.items():
        assert engine.get(key) == value

    # 文件名保持从 1 开始的连续编号
    assert _seg_names(tmp_path) == _consecutive_names(engine.stats()["files"])
    engine.close()

    engine2 = _open(tmp_path, segment_max_bytes=128)
    for key, value in fresh.items():
        assert engine2.get(key) == value
    engine2.close()


def test_compact_clears_read_cache_without_dirty_read(tmp_path) -> None:
    """压缩后读缓存被清空，且不会脏读：前后取值一致。"""
    engine = _open(tmp_path, segment_max_bytes=128)
    pairs = {f"k-{i:03d}": f"value-{i:03d}" for i in range(60)}
    for key, value in pairs.items():
        engine.set(key, value)

    # 先把一整批发进读缓存，再确认缓存确实有内容
    for key in pairs:
        assert engine.get(key) == pairs[key]
    assert engine._cache.size() > 0

    engine.compact()

    # 段号与偏移全变了，旧缓存条目必须被整体清空
    assert engine._cache.size() == 0
    # 清空之后逐个比对，全部与 compaction 之前一致
    for key, value in pairs.items():
        assert engine.get(key) == value
    engine.close()


def test_compact_keeps_hits_and_misses(tmp_path) -> None:
    """compaction 不改变 hits / misses 计数。"""
    engine = _open(tmp_path, segment_max_bytes=128, cache_capacity=4)
    for i in range(10):
        engine.set(f"k{i}", f"v{i}")
    # 制造一些命中与未命中
    for i in range(10):
        engine.get(f"k{i}")
    engine.get("definitely-missing")

    before = engine.stats()
    engine.compact()
    after = engine.stats()

    assert after["hits"] == before["hits"]
    assert after["misses"] == before["misses"]
    assert after["hit_rate"] == pytest.approx(before["hit_rate"])
    engine.close()


def test_compact_large_mixed_dataset_matches_after_restart(tmp_path) -> None:
    """大数据量混合读写删：compact 后的值 == 期望值 == 重启后的值。"""
    engine = _open(tmp_path, segment_max_bytes=256)
    expected: dict[str, str] = {}
    deleted: list[str] = []

    for i in range(200):
        key = f"key-{i:03d}"
        for round_no in range(4):  # 每个键覆盖写多次
            value = f"value-{i:03d}-round-{round_no}"
            engine.set(key, value)
            expected[key] = value
        if i % 5 == 0:  # 每 5 个删一个
            assert engine.delete(key) is True
            expected.pop(key, None)
            deleted.append(key)

    files_before = engine.stats()["files"]
    assert files_before > 1

    result = engine.compact()
    assert result["files_before"] == files_before
    assert result["files_after"] < files_before
    assert _seg_names(tmp_path) == _consecutive_names(result["files_after"])

    # compact 后逐一比对最终值
    for key, value in expected.items():
        assert engine.get(key) == value
    for key in deleted:
        assert engine.get(key) is None
    assert sorted(engine.keys()) == sorted(expected)
    engine.close()

    # 重启后再读一遍，结果必须一致
    engine2 = _open(tmp_path, segment_max_bytes=256)
    for key, value in expected.items():
        assert engine2.get(key) == value
    for key in deleted:
        assert engine2.get(key) is None
    assert sorted(engine2.keys()) == sorted(expected)
    engine2.close()
