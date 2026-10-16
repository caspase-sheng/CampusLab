"""段文件层（记录编解码 + SegmentFile + SegmentManager）的单元测试。"""

from __future__ import annotations

from typing import Iterator

import pytest

from app.kv.datafile import (
    HEADER_SIZE,
    OP_DELETE,
    OP_SET,
    Record,
    SegmentFile,
    SegmentManager,
    decode_record,
    encode_record,
)


def _drain(scanner: Iterator[Record]) -> tuple[list[Record], int]:
    """把扫描生成器跑完，返回 (记录列表, 最后有效偏移)。"""
    records: list[Record] = []
    while True:
        try:
            records.append(next(scanner))
        except StopIteration as stop:
            return records, (stop.value if stop.value is not None else 0)


def test_encode_decode_roundtrip() -> None:
    """编解码往返一致：SET / DELETE / 中文 / 空字符串 value。"""
    cases = [
        (OP_SET, "name", "alice"),
        (OP_SET, "中文键", "中文值"),
        (OP_SET, "empty", ""),
        (OP_DELETE, "gone", ""),
    ]
    for op, key, value in cases:
        data = encode_record(op, key, value, 0.0)
        record = decode_record(data, 0)
        assert record is not None
        assert record.op == op
        assert record.key == key
        assert record.value == value
        assert record.record_offset == 0
        assert record.end_offset == len(data)
        assert record.value_len == len(value.encode("utf-8"))
        assert record.value_offset == HEADER_SIZE + len(key.encode("utf-8"))


def test_ttl_roundtrip() -> None:
    """ttl（绝对过期时间戳）往返一致。"""
    data = encode_record(OP_SET, "k", "v", 123456.75)
    record = decode_record(data, 0)
    assert record is not None
    assert record.ttl == pytest.approx(123456.75)


def test_tampered_byte_fails_crc() -> None:
    """篡改一个字节后 crc32 校验失败，decode 返回失败而不是抛异常。"""
    data = bytearray(encode_record(OP_SET, "key", "value", 0.0))
    data[-1] ^= 0xFF  # 改掉 value 的最后一个字节
    assert decode_record(bytes(data), 0) is None


def test_truncated_and_short_inputs_fail_gracefully() -> None:
    """长度不足 / 被截断时返回 None，不抛异常。"""
    full = encode_record(OP_SET, "key", "value", 0.0)
    assert decode_record(full[:-1], 0) is None  # 少了尾部字节
    assert decode_record(b"\x00" * 5, 0) is None  # 连固定头都不够
    assert decode_record(full, len(full)) is None  # 偏移越界


def test_segment_scan_order(tmp_path) -> None:
    """段文件追加多条记录后顺序扫描，顺序与写入一致。"""
    seg = SegmentFile(1, tmp_path / "00000001.seg")
    for i in range(5):
        seg.append(OP_SET, f"k{i}", f"v{i}", 0.0)

    records, last_end = _drain(seg.scan())
    assert [r.key for r in records] == [f"k{i}" for i in range(5)]
    assert [r.value for r in records] == [f"v{i}" for i in range(5)]
    assert last_end == seg.size()  # 全部有效，末偏移等于文件长度
    seg.close()


def test_scan_stops_at_bad_record(tmp_path) -> None:
    """扫描到坏记录时停止，返回最后一个有效记录的结束偏移。"""
    seg = SegmentFile(1, tmp_path / "00000001.seg")
    seg.append(OP_SET, "a", "1", 0.0)
    seg.append(OP_SET, "b", "2", 0.0)
    valid_size = seg.size()

    with open(seg.path, "ab") as f:
        f.write(b"\x00\x01garbage")

    records, last_end = _drain(seg.scan())
    assert [r.key for r in records] == ["a", "b"]
    assert last_end == valid_size
    seg.close()


def test_read_value_by_offset(tmp_path) -> None:
    """按 value_offset / value_len 读回的 value 与写入一致。"""
    seg = SegmentFile(1, tmp_path / "00000001.seg")
    _, offset, length = seg.append(OP_SET, "k", "hello", 0.0)
    seg.append(OP_SET, "k2", "world", 0.0)  # 后面再写一条，不应影响前面的偏移
    assert seg.read_value(offset, length) == "hello"
    seg.close()


def test_manager_lists_segments_sorted(tmp_path) -> None:
    """SegmentManager 按 seg_id 升序枚举段，文件名按 8 位左补零。"""
    manager = SegmentManager(tmp_path, segment_max_bytes=64)
    for i in range(10):
        manager.append(OP_SET, f"key-{i}", "z" * 12, 0.0)

    infos = manager.list_segments()
    ids = [info.seg_id for info in infos]
    assert ids == sorted(ids)
    assert infos[0].path.name == "00000001.seg"
    assert manager.segment_count() == len(infos)
    manager.close()


def test_oversized_record_gets_own_segment(tmp_path) -> None:
    """单条记录大于阈值时不丢、不死循环，各占一个新段。"""
    manager = SegmentManager(tmp_path, segment_max_bytes=8)
    big = "x" * 100

    seg_id_1, _, offset1, len1 = manager.append(OP_SET, "big1", big, 0.0)
    seg_id_2, _, offset2, len2 = manager.append(OP_SET, "big2", big, 0.0)

    assert (seg_id_1, seg_id_2) == (1, 2)
    assert manager.segment_count() == 2
    assert manager.open_segment(1).read_value(offset1, len1) == big
    assert manager.open_segment(2).read_value(offset2, len2) == big
    manager.close()
