/**
 * ⚠️ 这份文件是从 frontend/src/lib/sorting.ts 原样复制过来的。
 *
 * 为什么是复制而不是共享？
 * 个人站（personal-site）和前端应用（frontend）在仓库里是两个互不依赖的项目，
 * 个人站没有 workspace / monorepo 那一套，也不打算为了一个演示页把两者绑在一起，
 * 所以只能拷一份自包含的实现。改动时两边要手动同步，没有自动机制帮忙对齐。
 *
 * 原件的测试覆盖在 frontend/tests/sorting.test.ts，这份拷贝没有测试覆盖，
 * 改了它不会有人拦你，所以动之前先想清楚。
 *
 * 以下正文与原文件逐字一致，未做任何逻辑改动。
 */

/**
 * 排序可视化用的纯函数模块：只做数据变换，不 import 任何 React，也不碰 DOM。
 *
 * 为什么先算出全部帧、再由 UI 回放，而不是「边排序边画」？
 * 1. 排序是同步的、几乎一瞬间就算完的计算，而 UI 想要的是逐帧动画，两者的时间尺度对不上。
 *    如果在排序递归里直接 setTimeout 一帧帧地画，排序逻辑就被计时器绑架了：
 *    改速度、暂停、重置都要把递归打断再重建，算法和动画搅在一起很难维护。
 * 2. 把「算」和「放」拆开后，排序只跑一遍，产出一个不可变的帧序列；
 *    UI 只是在一个数组下标上游走（改 index），暂停就是停定时器、改速度就是换 interval，
 *    完全不用重跑排序。
 * 3. 帧序列是纯数据，可以脱离浏览器单独在 Node 里跑断言，正确性和交互解耦，测试不用起前端。
 */

export type SortAlgorithm = "bubble" | "insertion" | "merge" | "quick";

export interface SortFrame {
  /** 这一帧的数组快照。 */
  array: number[];
  /** 正在比较的下标。 */
  comparing: number[];
  /** 刚发生交换或写入的下标。 */
  changed: number[];
  /** 已确定最终位置的下标。 */
  sorted: number[];
}

interface Recorder {
  /** 就地排序用的工作数组，push 时对它做快照。 */
  arr: number[];
  frames: SortFrame[];
  /** 已确定最终位置的下标集合，所有帧共享这一份累积状态。 */
  sorted: Set<number>;
  /** 记一帧：array 必须浅拷贝，否则所有帧指向同一个数组，播放时会直接跳到终态。 */
  push: (comparing: number[], changed: number[]) => void;
}

function createRecorder(input: number[]): Recorder {
  const arr = input.slice();
  const frames: SortFrame[] = [];
  const sorted = new Set<number>();

  const push = (comparing: number[], changed: number[]): void => {
    frames.push({
      array: arr.slice(), // 关键：新数组，不能复用同一引用
      comparing: comparing.slice(),
      changed: changed.slice(),
      sorted: [...sorted],
    });
  };

  return { arr, frames, sorted, push };
}

/** 交换 arr[i] 与 arr[j]。 */
function swap(arr: number[], i: number, j: number): void {
  const tmp = arr[i];
  arr[i] = arr[j];
  arr[j] = tmp;
}

/** 冒泡排序：每趟把当前最大值顶到右端，该下标此后不再动。 */
function bubble(rec: Recorder): void {
  const { arr, push, sorted } = rec;

  for (let end = arr.length - 1; end > 0; end--) {
    for (let i = 0; i < end; i++) {
      push([i, i + 1], []); // 比较
      if (arr[i] > arr[i + 1]) {
        swap(arr, i, i + 1);
        push([], [i, i + 1]); // 交换
      }
    }
    // 每趟结束，最大值落到 end，这个下标不会再动
    sorted.add(end);
    push([], []); // 单单为了把 sorted 的变化呈现给 UI
  }

  if (arr.length > 0) {
    sorted.add(0); // 剩下的最后一个下标也已就位
    push([], []);
  }
}

/** 插入排序：用相邻比较 + 交换实现「把 arr[i] 往左插」。 */
function insertion(rec: Recorder): void {
  const { arr, push, sorted } = rec;
  const n = arr.length;

  for (let i = 1; i < n; i++) {
    let j = i;
    while (j > 0) {
      push([j - 1, j], []); // 比较相邻两个
      if (arr[j - 1] <= arr[j]) {
        break; // 左边已有序且不大于它，就插到这
      }
      swap(arr, j - 1, j);
      push([], [j - 1, j]); // 交换
      j--;
    }
  }

  // 插入排序过程中不标 sorted，整体结束后一次性全标
  for (let k = 0; k < n; k++) {
    sorted.add(k);
  }
  push([], []);
}

/** 归并排序：辅助数组 + 写回主数组。 */
function merge(rec: Recorder): void {
  const { arr, push, sorted } = rec;
  const n = arr.length;

  const mergeRange = (lo: number, mid: number, hi: number): void => {
    const left = arr.slice(lo, mid); // 辅助数组：拷贝左半
    const right = arr.slice(mid, hi); // 辅助数组：拷贝右半
    let i = 0;
    let j = 0;
    let k = lo;

    while (i < left.length && j < right.length) {
      push([lo + i, mid + j], []); // 比较左右两侧当前元素
      if (left[i] <= right[j]) {
        arr[k] = left[i];
        i++;
      } else {
        arr[k] = right[j];
        j++;
      }
      push([], [k]); // 写回主数组
      k++;
    }
    while (i < left.length) {
      arr[k] = left[i];
      i++;
      push([], [k]);
      k++;
    }
    while (j < right.length) {
      arr[k] = right[j];
      j++;
      push([], [k]);
      k++;
    }
  };

  const sortRange = (lo: number, hi: number): void => {
    if (hi - lo <= 1) {
      return;
    }
    const mid = Math.floor((lo + hi) / 2);
    sortRange(lo, mid);
    sortRange(mid, hi);
    mergeRange(lo, mid, hi);
  };

  sortRange(0, n);

  // 归并过程中不标 sorted，整体结束后一次性全标
  for (let k = 0; k < n; k++) {
    sorted.add(k);
  }
  push([], []);
}

/** 快速排序：Lomuto 分区，取最右元素为基准。 */
function quick(rec: Recorder): void {
  const { arr, push, sorted } = rec;

  /** 就地分区，返回基准的最终下标。 */
  const partition = (lo: number, hi: number): number => {
    const pivot = arr[hi]; // 基准值固定在最右，直到最后一次交换前都不动
    let store = lo; // 下一个「小于基准」的元素该放的位置

    for (let scan = lo; scan < hi; scan++) {
      push([scan, hi], []); // 比较 arr[scan] 与基准
      if (arr[scan] < pivot) {
        if (store !== scan) {
          swap(arr, store, scan);
          push([], [store, scan]); // 交换
        }
        store++;
      }
    }

    swap(arr, store, hi); // 基准归位
    push([], [store, hi]); // 写入
    return store;
  };

  const sortRange = (lo: number, hi: number): void => {
    if (lo > hi) {
      return;
    }
    if (lo === hi) {
      // 单元素区间本身就位，直接标记
      sorted.add(lo);
      push([], []);
      return;
    }
    const p = partition(lo, hi);
    // partition 结束，基准的最终位置确定
    sorted.add(p);
    push([], []);
    sortRange(lo, p - 1);
    sortRange(p + 1, hi);
  };

  sortRange(0, arr.length - 1);
}

/**
 * 同步生成从初始状态到完全有序的整段帧序列。
 * 内部没有任何 setTimeout / async，调用方拿到的就是一个现成的数组。
 */
export function generateFrames(algorithm: SortAlgorithm, input: number[]): SortFrame[] {
  const rec = createRecorder(input);

  switch (algorithm) {
    case "bubble":
      bubble(rec);
      break;
    case "insertion":
      insertion(rec);
      break;
    case "merge":
      merge(rec);
      break;
    case "quick":
      quick(rec);
      break;
    default:
      // SortAlgorithm 已穷尽，这里只为满足 switch 的完整性要求
      break;
  }

  return rec.frames;
}

/**
 * 生成 size 个 5..100 之间互不重复的整数。
 * 用「整池洗牌再切前 size 个」而不是「随机抽到重复就重抽」：
 * 池子容量 96、size 最大 60，洗一遍是 O(96)，还能天然保证不重复。
 */
export function randomArray(size: number): number[] {
  const pool: number[] = [];
  for (let value = 5; value <= 100; value++) {
    pool.push(value);
  }

  // Fisher-Yates 洗牌
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = pool[i];
    pool[i] = pool[j];
    pool[j] = tmp;
  }

  return pool.slice(0, size);
}
