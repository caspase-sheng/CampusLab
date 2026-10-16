"""CampusLab 自研 KV 引擎：Bitcask 风格的持久化实现。

设计要点：
- 数据真正落在磁盘段文件里，采用只追加（append-only）写法；
  一个键的多次写入在段文件里表现为多条记录，读到的是最新那条。
- 内存只保留两样东西：KeyDir 索引和一份 value 读缓存（:class:`LRUCache`）。
  KeyDir 记录 ``key -> (seg_id, value_offset, value_len, expire_at)``，
  定位到 value 在哪个段文件的哪个偏移；读缓存只是热点 value 的副本，
  缓存淘汰（容量满时丢最久未使用的条目）不会造成数据丢失，
  下次读不到缓存就回磁盘拿。
- 没有单独的 WAL 模块：段文件本身就是追加日志。启动时按 seg_id 升序
  扫描每个段顺序重放，就能还原全部状态。遇到坏记录（crc32 不匹配、
  长度非法、文件被截断）视为该段坏尾，停下并把该段截断到最后一个有效记录末尾。
- TTL 惰性判断，不起后台清理线程；``expire_at`` 为 ``None`` 表示永不过期。

并发：单进程、线程安全。一把 :class:`threading.RLock` 同时保护段文件 I/O
和 KeyDir，段文件读写都被同一把锁串行化（Windows 上不做 pread）。
和契约 docs/CONTRACT.md §8 一样，不支持多进程共享。
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from threading import RLock
from typing import Any

from app.kv.datafile import OP_DELETE, OP_SET, SEGMENT_SUFFIX, SegmentManager
from app.kv.lru import LRUCache

# KeyDir 里每条索引的形态：key -> (seg_id, value_offset, value_len, expire_at)
KeyDirEntry = tuple[int, int, int, float | None]

# compaction 用的临时子目录名；它位于 data_dir 之下，但不是 *.seg 文件，
# 因此不会被 SegmentManager 当成正式段枚举到。
_COMPACT_DIR_NAME: str = "_compact"


class KVEngine:
    """基于磁盘段文件的持久化 KV 引擎。

    Args:
        data_dir: 段文件目录，不存在会自动创建。
        segment_max_bytes: 单个段文件字节上限，默认 8 MiB。
        cache_capacity: value 读缓存容量，默认 1024，必须为正整数。

    Raises:
        ValueError: ``cache_capacity <= 0`` 时。
    """

    def __init__(
        self,
        data_dir: str,
        segment_max_bytes: int = 8 * 1024 * 1024,
        cache_capacity: int = 1024,
    ) -> None:
        # LRUCache 自己会校验容量，<= 0 时抛 ValueError
        if cache_capacity <= 0:
            raise ValueError(f"cache_capacity 必须是正整数，收到 {cache_capacity}")

        # 记住构造参数：compaction 需要按同样的阈值重建段管理器与读缓存
        self._data_dir: Path = Path(data_dir)
        self._segment_max_bytes: int = segment_max_bytes
        self._cache_capacity: int = cache_capacity

        self._segments: SegmentManager = SegmentManager(data_dir, segment_max_bytes)
        self._cache: LRUCache = LRUCache(cache_capacity)
        self._keydir: dict[str, KeyDirEntry] = {}
        self._hits: int = 0
        self._misses: int = 0
        # 一把可重入锁同时保护段文件 I/O 与 KeyDir
        self._lock: RLock = RLock()

        # 启动即恢复：重放所有段文件
        with self._lock:
            self._recover()

    # ------------------------------------------------------------------ 写

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """写入或覆盖一个键，先落盘再更新索引与缓存。

        Args:
            key: 键。
            value: 字符串值。
            ttl: 存活秒数。``None`` 表示永不过期；``ttl <= 0`` 抛 ValueError。

        Raises:
            ValueError: ttl 不是正整数秒时。
        """
        expire_at = self._expire_at(ttl)
        with self._lock:
            seg_id, _, value_offset, value_len = self._segments.append(
                OP_SET, key, value, expire_at or 0.0
            )
            self._keydir[key] = (seg_id, value_offset, value_len, expire_at)
            self._cache.put(key, (value, expire_at))

    def delete(self, key: str) -> bool:
        """删除一个键。

        键不存在、或者已经过期都视为「不存在」，返回 False，且不写任何记录；
        只有确实存在且未过期，才追加一条 tombstone（DELETE 记录）并返回 True。

        Args:
            key: 要删除的键。

        Returns:
            存在并删除返回 True，否则 False。
        """
        with self._lock:
            entry = self._keydir.get(key)
            if entry is None:
                return False
            expire_at = entry[3]
            if self._is_expired(expire_at):
                # 过期键不算存在，只做内存清理，不写记录
                self._keydir.pop(key, None)
                self._cache.remove(key)
                return False
            # 真实删除：追加 tombstone，再更新索引与缓存
            self._segments.append(OP_DELETE, key, "", 0.0)
            self._keydir.pop(key, None)
            self._cache.remove(key)
            return True

    # ------------------------------------------------------------------ 读

    def get(self, key: str) -> str | None:
        """读一个键。

        Returns:
            值；键不存在或已过期返回 None。
        """
        result = self.get_with_ttl(key)
        if result is None:
            return None
        return result[0]

    def get_with_ttl(self, key: str) -> tuple[str, int | None] | None:
        """读一个键，并带上剩余 ttl，供 HTTP 层拼 ``/kv/get`` 的响应。

        读路径：先查读缓存，未命中再查 KeyDir，最后按
        ``(seg_id, value_offset, value_len)`` 从段文件读出 value，
        成功后写回读缓存。命中未过期键记一次 hits，其余情况记一次 misses。

        Args:
            key: 键。

        Returns:
            ``(value, remaining_ttl)``；键不存在或已过期返回 None。
            ``remaining_ttl`` 是整数秒（向下取整），永不过期时为 None。
        """
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                value, expire_at = cached
                if not self._is_expired(expire_at):
                    self._hits += 1
                    return value, self._remaining_ttl(expire_at)
                # 缓存里是过期值，清掉后继续走 KeyDir 兜底判断
                self._cache.remove(key)

            entry = self._keydir.get(key)
            if entry is None:
                self._misses += 1
                return None

            seg_id, value_offset, value_len, expire_at = entry
            if self._is_expired(expire_at):
                # 过期按未命中处理，顺手按 delete 语义清理（追加 tombstone）
                self._purge_expired(key)
                self._misses += 1
                return None

            value = self._segments.open_segment(seg_id).read_value(value_offset, value_len)
            self._cache.put(key, (value, expire_at))
            self._hits += 1
            return value, self._remaining_ttl(expire_at)

    def exists(self, key: str) -> bool:
        """判断键是否存在且未过期。

        纯查询：只查 KeyDir 并判断过期，不改变 hits / misses，
        也不动读缓存的顺序。
        """
        with self._lock:
            entry = self._keydir.get(key)
            if entry is None:
                return False
            return not self._is_expired(entry[3])

    def keys(self) -> list[str]:
        """返回所有未过期的键。

        纯查询：直接遍历 KeyDir 过滤过期项，不改变 hits / misses，
        也不写任何记录。
        """
        with self._lock:
            now = time.time()
            return [
                key
                for key, entry in self._keydir.items()
                if entry[3] is None or now < entry[3]
            ]

    def stats(self) -> dict[str, Any]:
        """返回引擎统计信息，固定六个字段。

        Returns:
            含 ``hits`` / ``misses`` / ``hit_rate`` / ``keys`` / ``wal_size`` / ``files``：
            ``hit_rate`` 取值 0.0 ~ 1.0，从未访问时为 0.0；
            ``keys`` 是当前未过期键数；``wal_size`` 是活跃段文件字节数；
            ``files`` 是段文件数量。

        本方法自身不改变 hits / misses。
        """
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": (self._hits / total) if total else 0.0,
                "keys": len(self._live_keys()),
                "wal_size": self._segments.active_segment_size(),
                "files": self._segments.segment_count(),
            }

    def compact(self) -> dict[str, Any]:
        """把「一个键留下多条历史记录」合并成「每个存活键只留一条最新记录」。

        丢弃三类垃圾：被后续写入覆盖掉的旧版本、DELETE（tombstone）记录、
        已经过期的记录。流程分四步：

        1. 遍历 KeyDir，跳过并清理过期键；存活的键从旧段读出 value，
           得到一批 ``(key, value, expire_at)``；
        2. 在 ``data_dir`` 下建临时子目录 ``_compact``，用临时 SegmentManager
           顺序写入存活记录，``segment_max_bytes`` 与当前引擎一致、按需轮转；
        3. 关闭旧段句柄，把临时目录里的 ``00000001.seg`` … 逐个 ``os.replace``
           覆盖进 ``data_dir``，删掉编号超出的旧段，删临时目录，重建 SegmentManager；
        4. KeyDir 整体替换为新映射，读缓存整体清空（段号与偏移全变了），
           hits / misses 计数保持不变。

        compaction 会短暂阻塞读写（全程持有引擎的那把 RLock），单进程场景可接受。

        Returns:
            ``{"ok": True, "files_before": 旧段数, "files_after": 新段数}``；
            ``files_before`` 在 compaction 开始前取，新引擎返回 0 / 0。
        """
        with self._lock:
            files_before = self._segments.segment_count()
            if files_before == 0:
                # 本来就是空引擎：没有任何段文件，直接返回
                return {"ok": True, "files_before": 0, "files_after": 0}

            live = self._collect_live_records()
            temp_dir, new_keydir, files_after = self._write_compacted_segments(live)
            self._swap_in_compacted_segments(temp_dir, new_keydir, files_after)
            return {"ok": True, "files_before": files_before, "files_after": files_after}

    # ----------------------------------------------------------- compaction 辅助

    def _collect_live_records(self) -> dict[str, tuple[str, float | None]]:
        """收集所有未过期键的 ``(value, expire_at)``，顺手清理过期键。

        过期键从 KeyDir 与读缓存里移除。调用前必须已持有 ``self._lock``。
        """
        now = time.time()
        live: dict[str, tuple[str, float | None]] = {}
        expired: list[str] = []
        for key, entry in self._keydir.items():
            seg_id, value_offset, value_len, expire_at = entry
            if expire_at is not None and now >= expire_at:
                expired.append(key)
                continue
            value = self._segments.open_segment(seg_id).read_value(value_offset, value_len)
            live[key] = (value, expire_at)
        for key in expired:
            self._keydir.pop(key, None)
            self._cache.remove(key)
        return live

    def _write_compacted_segments(
        self, live: dict[str, tuple[str, float | None]]
    ) -> tuple[Path, dict[str, KeyDirEntry], int]:
        """把存活记录写进临时子目录，返回 ``(临时目录, 新 KeyDir, 新段数)``。

        段号从 1 开始、按阈值自然轮转；存活键为空时不会产生任何段文件，
        新段数为 0。调用前必须已持有 ``self._lock``。
        """
        temp_dir = self._data_dir / _COMPACT_DIR_NAME
        # 清掉上一次可能残留的临时目录，保证新段编号从 1 开始且不与旧文件混在一起
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        temp_mgr = SegmentManager(temp_dir, self._segment_max_bytes)
        new_keydir: dict[str, KeyDirEntry] = {}
        try:
            for key, (value, expire_at) in live.items():
                seg_id, _, value_offset, value_len = temp_mgr.append(
                    OP_SET, key, value, expire_at or 0.0
                )
                new_keydir[key] = (seg_id, value_offset, value_len, expire_at)
            files_after = temp_mgr.segment_count()
        finally:
            temp_mgr.close()
        return temp_dir, new_keydir, files_after

    def _swap_in_compacted_segments(
        self,
        temp_dir: Path,
        new_keydir: dict[str, KeyDirEntry],
        files_after: int,
    ) -> None:
        """用临时目录里的新段整体替换 ``data_dir`` 中的旧段，再重建索引与缓存。

        替换顺序尽量压缩崩溃时的数据丢失窗口：先关句柄、再覆盖移动、最后清理。
        调用前必须已持有 ``self._lock``。
        """
        # 1. 关闭旧段所有句柄，释放文件占用（Windows 上不先关会挡 os.replace）
        self._segments.close()

        # 2. 新段逐个覆盖移动进 data_dir，同名直接覆盖
        for src in sorted(temp_dir.iterdir(), key=lambda p: p.name):
            if src.is_file() and src.suffix == SEGMENT_SUFFIX:
                os.replace(src, self._data_dir / src.name)

        # 3. 删掉编号超出新段数的旧段（编号 <= files_after 的已被覆盖）
        for path in self._data_dir.iterdir():
            if not path.is_file() or path.suffix != SEGMENT_SUFFIX:
                continue
            stem = path.name[: -len(SEGMENT_SUFFIX)]
            if stem.isdigit() and int(stem) > files_after:
                path.unlink()

        # 4. 删掉临时子目录
        shutil.rmtree(temp_dir, ignore_errors=True)

        # 5. 用 data_dir 重新构造 SegmentManager
        self._segments = SegmentManager(self._data_dir, self._segment_max_bytes)

        # 6. KeyDir 整体替换，读缓存整体清空；hits / misses 保持不动
        self._keydir = new_keydir
        self._cache = LRUCache(self._cache_capacity)

    # --------------------------------------------------------------- 生命周期

    def close(self) -> None:
        """关闭所有段文件句柄，重复调用不报错。"""
        with self._lock:
            self._segments.close()

    # --------------------------------------------------------------- 恢复

    def _recover(self) -> None:
        """启动时扫描所有段文件，按 seg_id 升序顺序重放，修复坏尾。

        重放规则：
        - SET：过期则跳过，否则写入 KeyDir；
        - DELETE：从 KeyDir 移除该键；
        - 坏记录：停止扫描该段，并把该段截断到最后一个有效记录的结束偏移。
        """
        for info in self._segments.list_segments():
            segment = self._segments.open_segment(info.seg_id)
            scanner = segment.scan()
            last_end = 0
            while True:
                try:
                    record = next(scanner)
                except StopIteration as stop:
                    # 生成器把「最后有效偏移」放在返回值里
                    last_end = stop.value if stop.value is not None else 0
                    break

                if record.op == OP_SET:
                    expire_at = record.ttl if record.ttl > 0 else None
                    if expire_at is not None and time.time() >= expire_at:
                        continue
                    self._keydir[record.key] = (
                        info.seg_id,
                        record.value_offset,
                        record.value_len,
                        expire_at,
                    )
                elif record.op == OP_DELETE:
                    self._keydir.pop(record.key, None)

            if last_end < segment.size():
                # 坏尾：截断到最后一个有效记录之后
                segment.truncate(last_end)

    # --------------------------------------------------------------- 工具

    def _live_keys(self) -> list[str]:
        """在已持锁的前提下收集未过期键（内部用，不计命中）。"""
        now = time.time()
        return [
            key
            for key, entry in self._keydir.items()
            if entry[3] is None or now < entry[3]
        ]

    def _purge_expired(self, key: str) -> None:
        """清理一个已过期的键：追加 tombstone，再移除索引与读缓存。"""
        self._segments.append(OP_DELETE, key, "", 0.0)
        self._keydir.pop(key, None)
        self._cache.remove(key)

    @staticmethod
    def _expire_at(ttl: int | None) -> float | None:
        """把 ttl 换算成绝对过期时间戳；None 原样返回。"""
        if ttl is None:
            return None
        if ttl <= 0:
            raise ValueError(f"ttl 必须是正整数秒，收到 {ttl}")
        return time.time() + ttl

    @staticmethod
    def _is_expired(expire_at: float | None) -> bool:
        """判断是否已过期；expire_at 为 None 表示永不过期。"""
        return expire_at is not None and time.time() >= expire_at

    @staticmethod
    def _remaining_ttl(expire_at: float | None) -> int | None:
        """剩余存活秒数，向下取整；永不过期返回 None。"""
        if expire_at is None:
            return None
        return max(0, int(expire_at - time.time()))
