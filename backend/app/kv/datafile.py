"""Bitcask 风格 KV 引擎的磁盘段文件层。

这一层只做两件事：记录编解码、段文件读写。它不碰 TTL 语义，也不碰内存索引，
是纯字节层，方便单独测试。

记录格式（小端）：
    固定头 21 字节
    [0:4]   crc32    uint32   校验范围 = 从 op 字节到 value 结束
    [4]     op       uint8    0x01 = SET，0x02 = DELETE
    [5:9]   key_len  uint32
    [9:13]  val_len  uint32   DELETE 固定为 0
    [13:21] ttl      float64  绝对过期时间戳（time.time() 秒），0.0 表示永不过期
    之后依次是 key（utf-8，key_len 字节）和 value（utf-8，val_len 字节）

段文件是只追加的：写入永远发生在文件末尾。扫描时一旦遇到坏记录
（crc32 校验不过、长度非法、文件被截断），就认为后面全是垃圾，属于「坏尾」，
由上层截断到最后一个有效记录的结束偏移。

并发说明：本模块自身不加锁，调用方（KVEngine）用一把可重入锁把段文件
I/O 串行化即可，单进程语义。
"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from typing import Iterator, NamedTuple

# 操作码
OP_SET: int = 0x01
OP_DELETE: int = 0x02

# 固定头长度
HEADER_SIZE: int = 21

# 段文件名格式：{seg_id:08d}.seg
SEGMENT_SUFFIX: str = ".seg"
SEGMENT_NAME_WIDTH: int = 8

# 完整头：crc32 / op / key_len / val_len / ttl
_HEADER = struct.Struct("<IBIId")
# 参与 crc32 计算的部分：op / key_len / val_len / ttl
_BODY = struct.Struct("<BIId")


class Record(NamedTuple):
    """解码后的一条记录。

    Attributes:
        op: 操作码，``OP_SET`` 或 ``OP_DELETE``。
        key: 键。
        value: 值；DELETE 记录固定为空串。
        ttl: 绝对过期时间戳（秒），``0.0`` 表示永不过期。
        record_offset: 记录头在文件中的起始偏移。
        value_offset: value 在文件中的起始偏移。
        value_len: value 的字节长度；DELETE 记录为 0。
        end_offset: 该记录结束后的偏移，等于下一条记录的起始偏移。
    """

    op: int
    key: str
    value: str
    ttl: float
    record_offset: int
    value_offset: int
    value_len: int
    end_offset: int


class SegmentInfo(NamedTuple):
    """段文件的元信息，供上层枚举。

    Attributes:
        seg_id: 段编号（从 1 开始）。
        path: 段文件路径。
    """

    seg_id: int
    path: Path


def encode_record(op: int, key: str, value: str, ttl: float) -> bytes:
    """把一条记录编码成字节串。

    Args:
        op: 操作码，``OP_SET`` 或 ``OP_DELETE``。
        key: 键。
        value: 值；DELETE 记录会被强制写成空串。
        ttl: 绝对过期时间戳（秒），``0.0`` 表示永不过期。

    Returns:
        编码后的完整记录，不含任何长度前缀。

    Raises:
        ValueError: op 不是已知操作码时。
    """
    if op not in (OP_SET, OP_DELETE):
        raise ValueError(f"未知的操作码：{op}")

    key_bytes = key.encode("utf-8")
    # DELETE 记录不带 value，val_len 固定为 0
    value_bytes = b"" if op == OP_DELETE else value.encode("utf-8")

    body = _BODY.pack(op, len(key_bytes), len(value_bytes), float(ttl))
    crc = zlib.crc32(body + key_bytes + value_bytes) & 0xFFFFFFFF
    header = _HEADER.pack(crc, op, len(key_bytes), len(value_bytes), float(ttl))
    return header + key_bytes + value_bytes


def decode_record(data: bytes, offset: int = 0) -> Record | None:
    """从字节串的 offset 处解出一条记录。

    解码过程只做校验、不抛异常：任何不合法（crc32 不匹配、长度非法、
    数据不足、op 未知、utf-8 解码失败）都返回 ``None``，让上层当成坏记录处理。

    Args:
        data: 待解析的字节串（通常是整个段文件内容）。
        offset: 记录起始偏移。

    Returns:
        解析成功返回 :class:`Record`，失败返回 ``None``。
    """
    if offset < 0 or offset + HEADER_SIZE > len(data):
        return None

    crc, op, key_len, val_len, ttl = _HEADER.unpack_from(data, offset)

    if op not in (OP_SET, OP_DELETE):
        return None
    # DELETE 记录不该带 value
    if op == OP_DELETE and val_len != 0:
        return None

    end = offset + HEADER_SIZE + key_len + val_len
    if end > len(data):
        return None

    # 校验范围：从 op 字节开始，到 value 结束
    payload = data[offset + 4 : end]
    if (zlib.crc32(payload) & 0xFFFFFFFF) != crc:
        return None

    key_start = offset + HEADER_SIZE
    value_start = key_start + key_len
    try:
        key = data[key_start:value_start].decode("utf-8")
        value = data[value_start:end].decode("utf-8")
    except UnicodeDecodeError:
        return None

    return Record(
        op=op,
        key=key,
        value=value,
        ttl=float(ttl),
        record_offset=offset,
        value_offset=value_start,
        value_len=val_len,
        end_offset=end,
    )


def record_size(key: str, value: str) -> int:
    """返回一条记录编码后的字节长度（不真正编码，只算长度）。"""
    return HEADER_SIZE + len(key.encode("utf-8")) + len(value.encode("utf-8"))


class SegmentFile:
    """封装单个段文件：追加写、按偏移读、顺序扫描。

    文件以 ``a+b`` 打开，写入永远落在文件末尾（O_APPEND），读的时候
    自己 seek 到目标偏移，两者互不干扰。

    Args:
        seg_id: 段编号。
        path: 段文件路径。
    """

    def __init__(self, seg_id: int, path: Path) -> None:
        self.seg_id: int = seg_id
        self.path: Path = path
        self._file = open(path, "a+b")

    # ----------------------------------------------------------------- 写

    def append(self, op: int, key: str, value: str, ttl: float) -> tuple[int, int, int]:
        """在文件末尾追加一条记录。

        Args:
            op: 操作码。
            key: 键。
            value: 值。
            ttl: 绝对过期时间戳（秒），``0.0`` 表示永不过期。

        Returns:
            ``(record_offset, value_offset, value_len)``。
        """
        data = encode_record(op, key, value, ttl)
        value_len = len(value.encode("utf-8")) if op == OP_SET else 0
        record_offset = self.size()

        self._file.seek(0, os.SEEK_END)
        self._file.write(data)
        self._file.flush()

        value_offset = record_offset + HEADER_SIZE + len(key.encode("utf-8"))
        return record_offset, value_offset, value_len

    def truncate(self, offset: int) -> None:
        """把文件截断到指定偏移，用于修复坏尾。

        Args:
            offset: 保留的字节长度，通常是最后一个有效记录的结束偏移。
        """
        self._file.truncate(offset)
        self._file.flush()

    # ----------------------------------------------------------------- 读

    def size(self) -> int:
        """返回文件的当前字节长度。"""
        return os.path.getsize(self.path)

    def read_value(self, value_offset: int, value_len: int) -> str:
        """按偏移和长度读回一个 value。

        Args:
            value_offset: value 在文件中的起始偏移。
            value_len: value 的字节长度。

        Returns:
            解码后的字符串。

        Raises:
            UnicodeDecodeError: 磁盘上的字节不是合法 utf-8 时（正常情况下不会发生）。
        """
        self._file.seek(value_offset)
        raw = self._file.read(value_len)
        return raw.decode("utf-8")

    def read_all(self) -> bytes:
        """把整个文件读进内存，供扫描使用。"""
        self._file.seek(0)
        return self._file.read()

    def scan(self) -> Iterator[Record]:
        """顺序扫描本段的所有记录。

        扫到坏记录就停止，并通过生成器的返回值给出「最后一个有效记录的
        结束偏移」，调用方可用 ``except StopIteration as e: e.value`` 拿到。
        生成器正常扫完时，返回值同样是最后一条记录的结束偏移（空文件为 0）。

        Yields:
            依次解析成功的 :class:`Record`。
        """
        data = self.read_all()
        total = len(data)
        offset = 0
        last_end = 0
        while offset < total:
            record = decode_record(data, offset)
            if record is None:
                break
            yield record
            last_end = record.end_offset
            offset = record.end_offset
        return last_end

    # --------------------------------------------------------------- 生命周期

    def close(self) -> None:
        """关闭文件句柄，重复调用不报错。"""
        if self._file is not None and not self._file.closed:
            self._file.close()


class SegmentManager:
    """管理一个目录下的所有段文件。

    段文件名形如 ``00000001.seg``，seg_id 从 1 开始递增。追加时写入
    「活跃段」；活跃段非空且再写会超过 ``segment_max_bytes`` 时滚动到新段。
    单条记录本身就超过阈值时，让它独占一个新段，不会死循环。

    Args:
        data_dir: 段文件目录，不存在会自动创建。
        segment_max_bytes: 单个段文件的字节上限（软限制）。
    """

    def __init__(self, data_dir: str | Path, segment_max_bytes: int) -> None:
        self._dir: Path = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_bytes: int = segment_max_bytes
        self._handles: dict[int, SegmentFile] = {}

        # 启动时列出所有段，按 seg_id 升序
        seg_ids: list[int] = []
        for path in self._dir.iterdir():
            if path.is_file() and path.suffix == SEGMENT_SUFFIX:
                stem = path.name[: -len(SEGMENT_SUFFIX)]
                if stem.isdigit():
                    seg_ids.append(int(stem))
        seg_ids.sort()
        self._seg_ids: list[int] = seg_ids
        self._next_id: int = (seg_ids[-1] + 1) if seg_ids else 1
        # 活跃段默认是最新的那个，后面写入都往它追加
        self._active_id: int | None = seg_ids[-1] if seg_ids else None

    # ------------------------------------------------------------ 内部工具

    def _path(self, seg_id: int) -> Path:
        """拼出段文件路径。"""
        name = f"{seg_id:0{SEGMENT_NAME_WIDTH}d}{SEGMENT_SUFFIX}"
        return self._dir / name

    def _open(self, seg_id: int) -> SegmentFile:
        """按需打开并缓存一个段文件句柄。"""
        handle = self._handles.get(seg_id)
        if handle is None:
            handle = SegmentFile(seg_id, self._path(seg_id))
            self._handles[seg_id] = handle
        return handle

    def _active_segment(self) -> SegmentFile:
        """取当前活跃段；目录里一个段都没有时创建 1 号段。"""
        if self._active_id is None:
            new_id = self._next_id
            self._next_id += 1
            self._seg_ids.append(new_id)
            self._active_id = new_id
        return self._open(self._active_id)

    def _roll(self) -> SegmentFile:
        """滚动到新段并返回它。"""
        new_id = self._next_id
        self._next_id += 1
        self._seg_ids.append(new_id)
        self._active_id = new_id
        return self._open(new_id)

    # ------------------------------------------------------------------ 写

    def append(self, op: int, key: str, value: str, ttl: float) -> tuple[int, int, int, int]:
        """把一条记录写到活跃段，必要时先滚动到新段。

        Args:
            op: 操作码。
            key: 键。
            value: 值。
            ttl: 绝对过期时间戳（秒）。

        Returns:
            ``(seg_id, record_offset, value_offset, value_len)``，
            其中 value_offset 是相对该段文件的绝对偏移。
        """
        need = record_size(key, value)
        active = self._active_segment()
        # 活跃段非空、再加一条会超阈值 → 先滚动。
        # 段为空时不滚，保证超大单条记录只占一个新段，不会无限滚动。
        if active.size() > 0 and active.size() + need > self._max_bytes:
            active = self._roll()

        record_offset, value_offset, value_len = active.append(op, key, value, ttl)
        return active.seg_id, record_offset, value_offset, value_len

    def truncate(self, seg_id: int, offset: int) -> None:
        """把指定段截断到 offset，用于坏尾修复。"""
        self._open(seg_id).truncate(offset)

    # ------------------------------------------------------------------ 查询

    def open_segment(self, seg_id: int) -> SegmentFile:
        """返回指定段的句柄，供上层扫描或读取。"""
        return self._open(seg_id)

    def list_segments(self) -> list[SegmentInfo]:
        """按 seg_id 升序返回所有段（含 id 与路径）。"""
        return [SegmentInfo(seg_id, self._path(seg_id)) for seg_id in self._seg_ids]

    def active_segment_size(self) -> int:
        """返回当前活跃段文件的字节长度；还没有活跃段时为 0。"""
        if self._active_id is None:
            return 0
        return self._open(self._active_id).size()

    def segment_count(self) -> int:
        """返回段文件数量。"""
        return len(self._seg_ids)

    # --------------------------------------------------------------- 生命周期

    def close(self) -> None:
        """关闭所有已打开的段文件句柄，重复调用不报错。"""
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
