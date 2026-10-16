import { useEffect, useState } from "react";

import {
  generateFrames,
  randomArray,
  type SortAlgorithm,
  type SortFrame,
} from "../lib/sorting";

// 排序可视化页。
// 排序本身是同步计算（见 lib/sorting.ts），这里只负责把算好的帧序列按速度回放：
// 用一个 index 指向当前帧，定时器每 intervalMs 推进一步。

const algorithmOptions: { value: SortAlgorithm; label: string }[] = [
  { value: "bubble", label: "冒泡排序" },
  { value: "insertion", label: "插入排序" },
  { value: "merge", label: "归并排序" },
  { value: "quick", label: "快速排序" },
];

export default function Visualizer() {
  const [algorithm, setAlgorithm] = useState<SortAlgorithm>("bubble");
  const [size, setSize] = useState(24);
  const [speed, setSpeed] = useState(60);

  // baseArray 是「还没排的原始数组」；frames 是点开始后生成的整段帧序列。
  // frames 为空表示还没开始，这时柱状图直接显示 baseArray。
  const [baseArray, setBaseArray] = useState<number[]>(() => randomArray(24));
  const [frames, setFrames] = useState<SortFrame[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  // 速度到定时器间隔的映射：intervalMs = 200 - speed * 1.9。
  // speed=1 时约 198ms（很慢），speed=100 时正好 10ms（很快），这个区间手调起来比较顺手。
  const intervalMs = 200 - speed * 1.9;

  // 推进帧。定时器只依赖 playing / speed（intervalMs 由 speed 派生），
  // index 用函数式更新：这样 index 每次都变也不会把定时器反复重建，
  // 只有「暂停/继续」或「改速度」才会重建定时器。
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setIndex((prev) => Math.min(prev + 1, Math.max(frames.length - 1, 0)));
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [playing, speed, frames.length, intervalMs]);

  // 到最后一帧自动停。这个 effect 和上面分工不同：
  // 上面那个只管「每隔多久推进一步」，这个管「什么时候该停」，
  // 两者都读 index，但关心的是不同边界，所以拆成两个、不要合并。
  useEffect(() => {
    if (playing && frames.length > 0 && index >= frames.length - 1) {
      setPlaying(false);
    }
  }, [playing, index, frames.length]);

  // 当前该画的那一帧：还没开始时为 null，退回 baseArray。
  const current = frames.length > 0 ? frames[Math.min(index, frames.length - 1)] : null;
  const values = current !== null ? current.array : baseArray;
  const comparing = new Set(current?.comparing ?? []);
  const changed = new Set(current?.changed ?? []);
  const sorted = new Set(current?.sorted ?? []);
  const maxValue = Math.max(...values, 1);

  /** 柱子的颜色，优先级从高到低：已归位 > 刚变动 > 正在比较 > 普通。 */
  function barColor(i: number): string {
    if (sorted.has(i)) return "bg-emerald-500";
    if (changed.has(i)) return "bg-red-500";
    if (comparing.has(i)) return "bg-amber-500";
    return "bg-slate-300";
  }

  function handlePlayPause() {
    if (playing) {
      // 暂停：只停定时器，保留 index
      setPlaying(false);
      return;
    }
    if (frames.length === 0) {
      // 第一次开始：按当前算法和原始数组生成整段帧序列，再播放
      setFrames(generateFrames(algorithm, baseArray));
      setIndex(0);
    } else if (index >= frames.length - 1) {
      // 已经播到最后一帧再点开始：从头重播，否则会立刻被自动停逻辑按下
      setIndex(0);
    }
    setPlaying(true);
  }

  function handleReset() {
    // 重置：停定时器并把 index 归零
    setPlaying(false);
    setIndex(0);
  }

  function handleAlgorithmChange(next: SortAlgorithm) {
    // 换算法：停定时器、清空 frames，下次点开始重新生成
    setPlaying(false);
    setAlgorithm(next);
    setFrames([]);
    setIndex(0);
  }

  function handleSizeChange(next: number) {
    // 换大小：连原始数组一起换一份新的，同样清空 frames
    setPlaying(false);
    setSize(next);
    setBaseArray(randomArray(next));
    setFrames([]);
    setIndex(0);
  }

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold text-slate-900">排序可视化</h1>

      <div className="flex flex-wrap items-end gap-4 rounded-lg border border-slate-200 bg-white p-4">
        <div>
          <label className="mb-1 block text-sm text-slate-600" htmlFor="algo-select">
            算法
          </label>
          <select
            id="algo-select"
            value={algorithm}
            disabled={playing}
            onChange={(e) => handleAlgorithmChange(e.target.value as SortAlgorithm)}
            className="rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {algorithmOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm text-slate-600" htmlFor="size-range">
            数组大小（{size}）
          </label>
          <input
            id="size-range"
            type="range"
            min={10}
            max={60}
            value={size}
            disabled={playing}
            onChange={(e) => handleSizeChange(Number(e.target.value))}
            className="w-40 disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm text-slate-600" htmlFor="speed-range">
            速度（{speed}）
          </label>
          <input
            id="speed-range"
            type="range"
            min={1}
            max={100}
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            className="w-40"
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handlePlayPause}
            className="rounded bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-700"
          >
            {playing ? "暂停" : "开始"}
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100"
          >
            重置
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex h-80 items-end gap-0.5">
          {values.map((value, i) => (
            <div
              key={i}
              className={`flex-1 rounded-t ${barColor(i)}`}
              style={{ height: `${(value / maxValue) * 100}%` }}
              title={String(value)}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
