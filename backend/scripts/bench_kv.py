r"""KV 引擎的横向性能对比脚本（benchmark）。

用同一份数据集，把四种读写的单次操作耗时量一遍，打印对齐表格：
Python dict / sqlite3 / KVEngine（热缓存读）/ KVEngine（近似冷读）。

运行方式（在 backend 目录下）：::

    .\.venv\Scripts\python.exe -m scripts.bench_kv

注意：必须用 ``-m`` 方式跑，这样 ``app`` 包才可导入；直接
``python scripts/bench_kv.py`` 会因为找不到 ``app`` 而报错。
本脚本只用于横向感受量级，不断言任何性能阈值，退出码固定为 0。
"""

from __future__ import annotations

import os
import platform
import sqlite3
import sys
import tempfile
import time
from typing import Callable, NamedTuple

from app.kv.engine import KVEngine

# 数据集规模：键从 bench:00000 到 bench:01999
KEY_COUNT: int = 2000
# 正式计时样本量（每个组合写、读各这么多）
SAMPLES: int = 2000
# 每个组合正式计时前的预热次数
WARMUP: int = 100


class BenchRow(NamedTuple):
    """一行 benchmark 结果。

    Attributes:
        name: 实现名（含缓存容量等说明）。
        phase: 阶段，``"write"`` 或 ``"read"``。
        ops_per_sec: 每秒操作数。
        p50_us: 50 分位单次耗时（微秒）。
        p99_us: 99 分位单次耗时（微秒）。
        max_us: 最大单次耗时（微秒）。
    """

    name: str
    phase: str
    ops_per_sec: float
    p50_us: float
    p99_us: float
    max_us: float


def build_dataset() -> tuple[list[str], list[str]]:
    """构造键值数据集：键 ``bench:00000`` … ``bench:01999``，值约 11 字节。"""
    keys = [f"bench:{i:05d}" for i in range(KEY_COUNT)]
    values = [f"val{i:08d}" for i in range(KEY_COUNT)]  # "val" + 8 位数字 = 11 字节
    return keys, values


def _percentile(sorted_lat: list[int], ratio: float) -> int:
    """按排序后样本的索引取分位数，索引为 ``int(ratio * (n - 1))``。

    Args:
        sorted_lat: 已升序排好的单次耗时（纳秒）。
        ratio: 分位比例，例如 0.5 或 0.99。

    Returns:
        对应下标的耗时（纳秒）。
    """
    n = len(sorted_lat)
    index = int(ratio * (n - 1))
    return sorted_lat[index]


def _summarize(name: str, phase: str, latencies: list[int]) -> BenchRow:
    """把一组单次耗时汇总成一行结果（ops/sec + p50 / p99 / max，单位微秒）。"""
    total_ns = sum(latencies)
    ops_per_sec = len(latencies) * 1_000_000_000 / total_ns if total_ns else 0.0
    ordered = sorted(latencies)
    return BenchRow(
        name=name,
        phase=phase,
        ops_per_sec=ops_per_sec,
        p50_us=_percentile(ordered, 0.5) / 1000.0,
        p99_us=_percentile(ordered, 0.99) / 1000.0,
        max_us=ordered[-1] / 1000.0,
    )


def _measure_write(
    write_op: Callable[[str, str], None],
    keys: list[str],
    values: list[str],
    samples: int,
    warmup: int,
) -> list[int]:
    """预热若干次后，对一批写操作逐次计时，返回单次耗时（纳秒）列表。"""
    n = len(keys)
    for i in range(warmup):
        write_op(keys[i % n], values[i % n])
    latencies: list[int] = []
    for i in range(samples):
        key = keys[i % n]
        value = values[i % n]
        start = time.perf_counter_ns()
        write_op(key, value)
        latencies.append(time.perf_counter_ns() - start)
    return latencies


def _measure_read(
    read_op: Callable[[str], None],
    keys: list[str],
    samples: int,
    warmup: int,
) -> list[int]:
    """预热若干次后，对一批读操作逐次计时，返回单次耗时（纳秒）列表。"""
    n = len(keys)
    for i in range(warmup):
        read_op(keys[i % n])
    latencies: list[int] = []
    for i in range(samples):
        key = keys[i % n]
        start = time.perf_counter_ns()
        read_op(key)
        latencies.append(time.perf_counter_ns() - start)
    return latencies


def bench_dict(keys: list[str], values: list[str]) -> list[BenchRow]:
    """测 Python dict 的写与读。"""
    data: dict[str, str] = {}

    def write_op(key: str, value: str) -> None:
        data[key] = value

    def read_op(key: str) -> None:
        data.get(key)

    return [
        _summarize("Python dict", "write", _measure_write(write_op, keys, values, SAMPLES, WARMUP)),
        _summarize("Python dict", "read", _measure_read(read_op, keys, SAMPLES, WARMUP)),
    ]


def bench_sqlite(work_dir: str, keys: list[str], values: list[str]) -> list[BenchRow]:
    """测 sqlite3 的写与读；写入放在一个事务里，最后 commit 一次。"""
    db_path = os.path.join(work_dir, "bench.sqlite3")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE kv(k TEXT PRIMARY KEY, v TEXT)")
    conn.commit()

    insert_sql = "INSERT OR REPLACE INTO kv(k, v) VALUES(?, ?)"
    select_sql = "SELECT v FROM kv WHERE k = ?"

    def write_op(key: str, value: str) -> None:
        cur.execute(insert_sql, (key, value))

    def read_op(key: str) -> None:
        cur.execute(select_sql, (key,))
        cur.fetchone()

    # 预热：预热写也提交一次，避免把预热的事务拖进正式计时
    n = len(keys)
    for i in range(WARMUP):
        write_op(keys[i % n], values[i % n])
    conn.commit()

    # 正式写入：整批放进一个事务，最后 commit 一次
    write_lat: list[int] = []
    for i in range(SAMPLES):
        key = keys[i % n]
        value = values[i % n]
        start = time.perf_counter_ns()
        write_op(key, value)
        write_lat.append(time.perf_counter_ns() - start)
    conn.commit()

    read_lat = _measure_read(read_op, keys, SAMPLES, WARMUP)
    conn.close()

    return [
        _summarize("sqlite3 (单事务 + 主键读)", "write", write_lat),
        _summarize("sqlite3 (单事务 + 主键读)", "read", read_lat),
    ]


def bench_engine(
    work_dir: str,
    cache_capacity: int,
    label: str,
    keys: list[str],
    values: list[str],
) -> list[BenchRow]:
    """测 KVEngine 的写与读；用指定缓存容量控制「热 / 冷」程度。"""
    engine = KVEngine(
        data_dir=os.path.join(work_dir, f"kv_cache_{cache_capacity}"),
        cache_capacity=cache_capacity,
    )
    try:
        write_lat = _measure_write(engine.set, keys, values, SAMPLES, WARMUP)
        read_lat = _measure_read(engine.get, keys, SAMPLES, WARMUP)
    finally:
        engine.close()
    return [
        _summarize(label, "write", write_lat),
        _summarize(label, "read", read_lat),
    ]


def print_table(rows: list[BenchRow]) -> None:
    """打印对齐的结果表格。"""
    header = (
        f"{'实现':<40} {'阶段':<6} {'ops per sec':>14} "
        f"{'p50 us':>10} {'p99 us':>10} {'max us':>10}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.name:<40} {row.phase:<6} {row.ops_per_sec:>14,.0f} "
            f"{row.p50_us:>10.2f} {row.p99_us:>10.2f} {row.max_us:>10.2f}"
        )


def print_env() -> None:
    """打印环境信息。"""
    print("== 环境信息 ==")
    print(f"Python 版本 : {platform.python_version()} ({sys.version.split()[0]})")
    print(f"平台        : {platform.platform()}")
    print(f"数据集      : {KEY_COUNT} 个键（bench:00000 ~ bench:{KEY_COUNT - 1:05d}）")
    print(f"样本量      : 每个组合写、读各 {SAMPLES} 次（正式计时前预热 {WARMUP} 次）")
    print()


def print_notes() -> None:
    """打印一小段口径说明。"""
    print()
    print("== 口径说明 ==")
    print("1. sqlite 的写入放进了单个事务、最后 commit 一次，所以写入数字偏乐观，")
    print("   不代表逐条提交（每条都 commit）的性能。")
    print("2. KVEngine 的冷读是近似值：只是把 cache_capacity 从 1024 压到 16，")
    print("   缓存里仍然会命中一部分热点，并不是严格意义上的冷读。")
    print("3. 三者的持久化语义不同：dict 完全不落盘；sqlite 落盘且有自己的 B 树和")
    print("   事务开销；KVEngine 是追加写段文件 + 内存 KeyDir 索引 + LRU 读缓存。")
    print("   因此这组数字只用于横向感受量级，不能当作严格的存储引擎对比。")


def main() -> int:
    """跑完四组对比并打印结果，返回退出码 0。"""
    print_env()

    keys, values = build_dataset()
    with tempfile.TemporaryDirectory(prefix="campuslab_bench_") as work_dir:
        rows: list[BenchRow] = []
        rows += bench_dict(keys, values)
        rows += bench_sqlite(work_dir, keys, values)
        rows += bench_engine(work_dir, 1024, "KVEngine (cache=1024, 热缓存读)", keys, values)
        rows += bench_engine(work_dir, 16, "KVEngine (cache=16, 近似冷读)", keys, values)

        print_table(rows)

    print_notes()
    return 0


if __name__ == "__main__":
    sys.exit(main())
