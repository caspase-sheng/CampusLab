// src/lib/sorting.ts 的永久测试，用 Node 24 内置的 node:test + node:assert/strict，不引任何依赖。
//
// 为什么导入路径要带 .ts 扩展名？
// 这里跑在 Node 的类型剥离模式下（不是 Vite），它对相对导入要求写全扩展名；
// 而 src 下的代码互相 import 是不带扩展名的（交给 Vite 解析）。
// sorting.ts 内部不 import 任何东西，所以这样写能直接跑通。
//
// 这个文件放在 frontend/tests/ 而不是 src/ 下：tsconfig 的 include 只有 ["src"]，
// 放进 src 会被 tsc 一起检查，而 tsc 那边的模块解析又和 Node 的扩展名要求打架。

import test from "node:test";
import assert from "node:assert/strict";

import { generateFrames, randomArray } from "../src/lib/sorting.ts";

const algorithms = ["bubble", "insertion", "merge", "quick"] as const;

test("randomArray：长度等于传入值，值落在 5..100，且互不重复", () => {
  // 多跑几组，包括边界：0（空）和 96（池子 5..100 正好 96 个数，取满时要求全不重复）
  for (const size of [0, 1, 5, 10, 40, 60, 96]) {
    const arr = randomArray(size);
    assert.equal(arr.length, size);
    for (const value of arr) {
      assert.ok(Number.isInteger(value), `值 ${value} 不是整数`);
      assert.ok(value >= 5 && value <= 100, `值 ${value} 越界`);
    }
    // 不重复：去重后个数应当没变
    assert.equal(new Set(arr).size, arr.length, "出现了重复值");
  }
});

test("generateFrames：四种算法都排成严格升序的终态，且逐帧快照不共享引用", () => {
  for (const algorithm of algorithms) {
    for (const size of [2, 3, 7, 15, 26, 40]) {
      // randomArray 保证互不重复，所以终态应当是严格升序
      const input = randomArray(size);
      const frames = generateFrames(algorithm, input);

      assert.ok(frames.length > 0, `${algorithm} 长度 ${size} 时没有任何帧`);

      const last = frames[frames.length - 1];
      assert.equal(last.array.length, size, `${algorithm} 终态长度不对`);
      for (let i = 1; i < last.array.length; i++) {
        assert.ok(
          last.array[i - 1] < last.array[i],
          `${algorithm} 终态不是严格升序`
        );
      }

      // 终态的 sorted 必须覆盖全部下标，且长度等于数组长度
      assert.equal(last.sorted.length, size, `${algorithm} 终态 sorted 长度不对`);
      assert.deepEqual(
        [...last.sorted].sort((a, b) => a - b),
        Array.from({ length: size }, (_, i) => i),
        `${algorithm} 终态 sorted 没覆盖全部下标`
      );

      // 相邻两帧的 array 不能是同一个引用，否则播放时会直接跳到终态
      for (let i = 0; i + 1 < frames.length; i++) {
        assert.notEqual(
          frames[i].array,
          frames[i + 1].array,
          `${algorithm} 相邻帧共享了 array 引用`
        );
      }
    }
  }
});

test("generateFrames：空数组各算法都不抛异常（空输入行为目前不统一，不断言帧数）", () => {
  for (const algorithm of algorithms) {
    assert.doesNotThrow(() => generateFrames(algorithm, []));
  }
});

test("generateFrames：单元素数组的终态就是那一个元素，sorted 含下标 0", () => {
  for (const algorithm of algorithms) {
    const frames = generateFrames(algorithm, [42]);
    assert.ok(frames.length > 0, `${algorithm} 单元素时没有任何帧`);
    const last = frames[frames.length - 1];
    assert.deepEqual(last.array, [42]);
    assert.ok(last.sorted.includes(0), `${algorithm} 单元素的 sorted 里没有下标 0`);
  }
});
