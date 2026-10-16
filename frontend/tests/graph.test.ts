// src/lib/graph.ts 的永久测试，用 Node 24 内置的 node:test + node:assert/strict，不引任何依赖。
//
// 导入路径带 .ts 扩展名、文件放在 tests/ 而不是 src/ 的原因，见 sorting.test.ts 顶部注释。

import test from "node:test";
import assert from "node:assert/strict";

import {
  generateGraphFrames,
  sampleGraph,
  buildAdjacency,
  isSameEdge,
  addNode,
  moveNode,
  removeNode,
  addEdge,
  removeEdge,
} from "../src/lib/graph.ts";

test("sampleGraph：7 个节点、边权重都是正整数，且从 n1 能走到全部节点", () => {
  const graph = sampleGraph();
  assert.equal(graph.nodes.length, 7);

  for (const edge of graph.edges) {
    assert.ok(Number.isInteger(edge.weight), `权重 ${edge.weight} 不是整数`);
    assert.ok(edge.weight > 0, `权重 ${edge.weight} 不是正整数`);
  }

  // 连通性：从 n1 走一趟 BFS，看能到达几个节点
  const adj = buildAdjacency(graph);
  const seen = new Set(["n1"]);
  const queue = ["n1"];
  while (queue.length > 0) {
    const node = queue.shift();
    for (const nbr of adj.get(node) ?? []) {
      if (!seen.has(nbr.to)) {
        seen.add(nbr.to);
        queue.push(nbr.to);
      }
    }
  }
  assert.equal(seen.size, 7, "从 n1 到不了全部节点，示例图不连通");
});

test("buildAdjacency：邻居顺序只由 graph.nodes 的顺序决定，与 edges 的书写顺序无关", () => {
  const graph = sampleGraph();
  const base = buildAdjacency(graph);
  const ids = graph.nodes.map((node) => node.id);
  const order = new Map(ids.map((id, i) => [id, i]));

  // 直接把边的顺序反过来，重新建一次邻接表
  const shuffled = { nodes: graph.nodes, edges: [...graph.edges].reverse() };
  const rebuilt = buildAdjacency(shuffled);

  for (const id of ids) {
    const baseNeighbors = base.get(id).map((n) => n.to);
    const rebuiltNeighbors = rebuilt.get(id).map((n) => n.to);
    // 邻居列表跟边怎么写无关
    assert.deepEqual(rebuiltNeighbors, baseNeighbors, `${id} 的邻居顺序随 edges 顺序变了`);

    // 而且，邻居确实按 nodes 里的下标升序排列（文件头写死的设计）
    const indexSeq = baseNeighbors.map((neighborId) => order.get(neighborId));
    assert.deepEqual(indexSeq, [...indexSeq].sort((a, b) => a - b), `${id} 的邻居没按 nodes 顺序排`);
  }
});

test("isSameEdge：无向，(n1,n2) 与 (n2,n1) 都算同一条", () => {
  const edge = { from: "n1", to: "n2", weight: 4 };
  assert.ok(isSameEdge(edge, "n1", "n2"));
  assert.ok(isSameEdge(edge, "n2", "n1"));
  assert.ok(!isSameEdge(edge, "n1", "n3"));
  assert.ok(!isSameEdge(edge, "n2", "n3"));
});

test("generateGraphFrames：三种算法都访问完可达节点、收尾帧 current / activeEdge 为 null，且访问集合一致", () => {
  const graph = sampleGraph();
  const visitedSets = [];

  for (const algorithm of ["bfs", "dfs", "dijkstra"]) {
    const frames = generateGraphFrames(algorithm, graph, "n1");
    assert.ok(frames.length > 0, `${algorithm} 没有任何帧`);

    // 相邻两帧的 visited 不能是同一个引用
    for (let i = 0; i + 1 < frames.length; i++) {
      assert.notEqual(frames[i].visited, frames[i + 1].visited, `${algorithm} 相邻帧共享 visited 引用`);
    }

    const last = frames[frames.length - 1];
    assert.equal(last.current, null, `${algorithm} 收尾帧 current 不是 null`);
    assert.equal(last.activeEdge, null, `${algorithm} 收尾帧 activeEdge 不是 null`);
    // 无重复
    assert.equal(new Set(last.visited).size, last.visited.length, `${algorithm} visited 有重复`);
    // 示例图连通，7 个节点应当全被访问
    assert.equal(last.visited.length, 7, `${algorithm} 没有访问完全部节点`);

    visitedSets.push([...last.visited].sort());
  }

  // 三种算法访问到的节点集合完全相同
  assert.deepEqual(visitedSets[0], visitedSets[1]);
  assert.deepEqual(visitedSets[1], visitedSets[2]);
});

/**
 * 参照实现：Bellman-Ford，用来核对 Dijkstra 的距离表。
 * 特意不用 Dijkstra 自己验自己——两者实现思路不同，对不上就说明有一方错了。
 * 无向图，每条边两个方向各算一条有向弧。
 */
function bellmanFord(nodes, edges, startId) {
  const dist = new Map();
  for (const node of nodes) {
    dist.set(node.id, Infinity);
  }
  dist.set(startId, 0);

  const arcs = [];
  for (const edge of edges) {
    arcs.push([edge.from, edge.to, edge.weight]);
    arcs.push([edge.to, edge.from, edge.weight]);
  }

  for (let iter = 0; iter < nodes.length - 1; iter++) {
    for (const [u, v, w] of arcs) {
      const candidate = dist.get(u) + w;
      if (candidate < dist.get(v)) {
        dist.set(v, candidate);
      }
    }
  }

  return dist;
}

test("Dijkstra：终态 distances 覆盖全部节点，且每个值等于真实最短路（Bellman-Ford 核对）", () => {
  const graph = sampleGraph();

  // 换几个起点分别核对：n1（全网）、n2、n6、n7（边缘节点）
  for (const startId of ["n1", "n2", "n6", "n7"]) {
    const frames = generateGraphFrames("dijkstra", graph, startId);
    assert.ok(frames.length > 0, `起点 ${startId} 没有任何帧`);

    const last = frames[frames.length - 1];
    assert.ok(last.distances !== null, `${startId} 的终态 distances 是 null`);

    const expected = bellmanFord(graph.nodes, graph.edges, startId);
    for (const node of graph.nodes) {
      assert.equal(
        last.distances[node.id],
        expected.get(node.id),
        `起点 ${startId} 到 ${node.id} 的最短路不对`
      );
    }
    // 覆盖全部节点：键的数量应当等于节点数
    assert.equal(Object.keys(last.distances).length, graph.nodes.length, `${startId} 的 distances 没覆盖全部节点`);
  }
});

test("addNode：新 id 取最小未占用编号、label 取最小未用字母，且不改传入的图", () => {
  const graph = sampleGraph();
  const beforeCount = graph.nodes.length;
  const beforeFirst = { x: graph.nodes[0].x, y: graph.nodes[0].y };

  const next = addNode(graph, 10, 20);
  const added = next.nodes[next.nodes.length - 1];
  // 示例图占了 n1..n7，A..G 也都在用
  assert.equal(added.id, "n8");
  assert.equal(added.label, "H");
  assert.equal(added.x, 10);
  assert.equal(added.y, 20);
  assert.equal(next.nodes.length, beforeCount + 1);

  // 原图不受影响
  assert.equal(graph.nodes.length, beforeCount);
  assert.equal(graph.nodes[0].x, beforeFirst.x);
  assert.equal(graph.nodes[0].y, beforeFirst.y);

  // 删掉中间一个节点后，空出来的编号和字母会被优先补上
  const withoutN4 = removeNode(graph, "n4");
  const refilled = addNode(withoutN4, 0, 0);
  assert.equal(refilled.nodes[refilled.nodes.length - 1].id, "n4");
  assert.equal(refilled.nodes[refilled.nodes.length - 1].label, "D");
});

test("moveNode：只改目标节点的 x / y，其他节点和原图都不变；id 不存在时原样返回", () => {
  const graph = sampleGraph();
  const targetId = graph.nodes[0].id;
  const otherBefore = { ...graph.nodes[1] };

  const next = moveNode(graph, targetId, 111, 222);
  assert.notEqual(next, graph, "应当返回新对象");
  const moved = next.nodes.find((node) => node.id === targetId);
  assert.equal(moved.x, 111);
  assert.equal(moved.y, 222);

  // 其他节点坐标不变
  assert.deepEqual(next.nodes.find((node) => node.id === graph.nodes[1].id), otherBefore);
  // 原图的节点坐标也不变
  assert.equal(graph.nodes[0].x, 80);
  assert.equal(graph.nodes[0].y, 60);

  // id 不存在 → 原样返回同一个对象
  assert.equal(moveNode(graph, "nope", 1, 2), graph);
});

test("removeNode：目标节点消失，连带边一起删干净，删掉的边数等于原先相连的边数；id 不存在时原样返回", () => {
  const graph = sampleGraph();
  const victim = "n4";
  const attachedBefore = graph.edges.filter(
    (edge) => edge.from === victim || edge.to === victim
  ).length;
  assert.ok(attachedBefore > 0, "示例图里 n4 应当有相连的边");

  const next = removeNode(graph, victim);
  assert.ok(!next.nodes.some((node) => node.id === victim), "节点没被删掉");
  assert.ok(
    !next.edges.some((edge) => edge.from === victim || edge.to === victim),
    "还存在与被删节点相连的悬空边"
  );
  assert.equal(next.edges.length, graph.edges.length - attachedBefore);

  // 原图不变
  assert.ok(graph.nodes.some((node) => node.id === victim));
  assert.equal(graph.edges.length, sampleGraph().edges.length);

  // id 不存在 → 原样返回
  assert.equal(removeNode(graph, "nope"), graph);
});

test("addEdge：合法时边数 +1；自环 / 重复 / 非法权重 / 端点缺失都被拒且原样返回", () => {
  const graph = sampleGraph();

  // n6 和 n7 在示例图里没有直接相连
  const added = addEdge(graph, "n6", "n7", 5);
  assert.notEqual(added, graph);
  assert.equal(added.edges.length, graph.edges.length + 1);
  assert.ok(
    added.edges.some((edge) => edge.from === "n6" && edge.to === "n7" && edge.weight === 5),
    "新边没加上"
  );

  // 自环
  assert.equal(addEdge(graph, "n1", "n1", 3), graph);
  // 重复边：正向和反向都算同一条
  assert.equal(addEdge(graph, "n1", "n2", 9), graph);
  assert.equal(addEdge(graph, "n2", "n1", 9), graph);
  // 权重非法：0、负数、非整数、NaN
  assert.equal(addEdge(graph, "n6", "n7", 0), graph);
  assert.equal(addEdge(graph, "n6", "n7", -1), graph);
  assert.equal(addEdge(graph, "n6", "n7", 1.5), graph);
  assert.equal(addEdge(graph, "n6", "n7", NaN), graph);
  // 端点不存在
  assert.equal(addEdge(graph, "n1", "n99", 2), graph);
  assert.equal(addEdge(graph, "n99", "n1", 2), graph);
});

test("removeEdge：正常删边数 -1，反向 (to, from) 也能删；边不存在时原样返回", () => {
  const graph = sampleGraph();

  const removed = removeEdge(graph, "n1", "n2");
  assert.notEqual(removed, graph);
  assert.equal(removed.edges.length, graph.edges.length - 1);
  assert.ok(!removed.edges.some((edge) => isSameEdge(edge, "n1", "n2")), "边没被删掉");

  // 无向：反过来传也能删
  const removedReverse = removeEdge(graph, "n2", "n1");
  assert.equal(removedReverse.edges.length, graph.edges.length - 1);

  // 边不存在（n6-n7 本来就没连）→ 原样返回
  assert.equal(removeEdge(graph, "n6", "n7"), graph);
});
