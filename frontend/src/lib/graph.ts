/**
 * 图遍历可视化用的纯函数模块：只做数据变换，不 import React，也不碰 DOM。
 *
 * 为什么把帧序列和渲染分开？
 * 跟排序页一个思路：BFS/DFS/Dijkstra 都是同步计算，一瞬间就能跑完，而界面要的是「一格一格动」。
 * 如果在遍历过程里直接 setTimeout，算法就被计时器绑住了——改速度、暂停、重置都得把遍历打断重建。
 * 所以这里先把整段过程算成一个不可变的帧序列，界面只在一个下标上游走：
 * 暂停=停定时器，改速度=换 interval，重置=下标归零，全都不用重跑算法。
 * 另外帧序列是纯数据，可以丢到 Node 里单独跑断言，正确性验证不用起前端。
 *
 * 为什么邻居顺序要固定？
 * 帧序列是按「邻接表里邻居的先后」一条条边走的。如果邻接表直接按 edges 数组的顺序攒，
 * 那同一张图，只要边的书写顺序换一下，遍历顺序就跟着漂，手点时前后两次根本对不上。
 * 所以 buildAdjacency 统一按 graph.nodes 里的节点顺序给邻居排序，让结果只由「图本身」决定，
 * 跟边怎么写的无关。
 */

export interface GraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
}

export interface GraphEdge {
  from: string;
  to: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export type GraphAlgorithm = "bfs" | "dfs" | "dijkstra";

export interface GraphFrame {
  /** 已经访问完的节点 id。 */
  visited: string[];
  /** 这一帧正在处理的节点。 */
  current: string | null;
  /** 待访问集合：BFS 是队列，DFS 是栈，Dijkstra 是「还没确定最短路的节点」。 */
  frontier: string[];
  /** 这一帧正在走的边，没有则为 null。 */
  activeEdge: [string, string] | null;
  /** 仅 Dijkstra 有值（目前已发现的最短距离），其余算法恒为 null。 */
  distances: Record<string, number> | null;
}

/** 邻接表里一条邻居记录：连到哪个节点、这条边的权重。 */
interface Neighbor {
  to: string;
  weight: number;
}

/**
 * 建邻接表：Map<节点id, 邻居数组>。
 * 无向图，一条边两个方向都塞一遍。
 * 每个邻居数组最后按 graph.nodes 里的顺序排序（见文件头第二条说明）。
 */
export function buildAdjacency(graph: GraphData): Map<string, Neighbor[]> {
  const order = new Map<string, number>();
  graph.nodes.forEach((node, i) => {
    order.set(node.id, i);
  });

  const adj = new Map<string, Neighbor[]>();
  for (const node of graph.nodes) {
    adj.set(node.id, []);
  }

  for (const edge of graph.edges) {
    adj.get(edge.from)?.push({ to: edge.to, weight: edge.weight });
    adj.get(edge.to)?.push({ to: edge.from, weight: edge.weight });
  }

  for (const list of adj.values()) {
    list.sort((a, b) => (order.get(a.to) ?? 0) - (order.get(b.to) ?? 0));
  }

  return adj;
}

/**
 * 判断 edge 是否连接 a、b 这两个点。
 * 无向比较：{from:"n1",to:"n2"} 和 {from:"n2",to:"n1"} 是同一对，顺序不影响。
 * 页面高亮当前边时用它，不要自己写字符串相等。
 */
export function isSameEdge(edge: GraphEdge, a: string, b: string): boolean {
  return (
    (edge.from === a && edge.to === b) || (edge.from === b && edge.to === a)
  );
}

/** 记录器：把「当前状态」按帧拍下来，帧里的数组一律新拷贝。 */
interface FrameRecorder {
  frames: GraphFrame[];
  /** 已访问集合，累积状态，每帧拍快照时展开成新数组。 */
  visited: Set<string>;
  push: (
    current: string | null,
    frontier: string[],
    activeEdge: [string, string] | null,
    distances: Record<string, number> | null,
  ) => void;
}

function createRecorder(): FrameRecorder {
  const frames: GraphFrame[] = [];
  const visited = new Set<string>();

  const push = (
    current: string | null,
    frontier: string[],
    activeEdge: [string, string] | null,
    distances: Record<string, number> | null,
  ): void => {
    frames.push({
      visited: [...visited], // 关键：新数组，不能复用同一引用
      current,
      frontier: frontier.slice(),
      activeEdge: activeEdge ? [activeEdge[0], activeEdge[1]] : null,
      distances: distances ? { ...distances } : null,
    });
  };

  return { frames, visited, push };
}

/** BFS：队列，先进先出；邻接表顺序即入队顺序。 */
function bfs(adj: Map<string, Neighbor[]>, startId: string, rec: FrameRecorder): void {
  const { push, visited } = rec;
  const frontier: string[] = [startId]; // 队列内容即 frontier
  const seen = new Set<string>([startId]); // 已入过队（或已访问），防止重复入队

  push(null, frontier, null, null); // 开局

  while (frontier.length > 0) {
    const node = frontier.shift();
    if (node === undefined) break;
    push(node, frontier, null, null); // 从 frontier 取出

    for (const nbr of adj.get(node) ?? []) {
      push(node, frontier, [node, nbr.to], null); // 检查一条边
      if (!seen.has(nbr.to)) {
        seen.add(nbr.to);
        frontier.push(nbr.to);
        push(node, frontier, null, null); // 新节点入队
      }
    }

    visited.add(node);
    push(node, frontier, null, null); // 处理完，移入 visited
  }

  push(null, frontier, null, null); // 最后一帧
}

/** DFS：栈，后进先出；邻接表逆序压栈，好让排在前面的邻居先被取出。 */
function dfs(adj: Map<string, Neighbor[]>, startId: string, rec: FrameRecorder): void {
  const { push, visited } = rec;
  const frontier: string[] = [startId]; // 栈内容即 frontier，栈顶在数组末尾
  const seen = new Set<string>([startId]);

  push(null, frontier, null, null); // 开局

  while (frontier.length > 0) {
    const node = frontier.pop();
    if (node === undefined) break;
    push(node, frontier, null, null); // 从栈顶取出

    const neighbors = adj.get(node) ?? [];
    // 倒着压栈：邻接表里靠前的邻居最后压、最早弹，于是「先列出的邻居先访问」。
    for (let i = neighbors.length - 1; i >= 0; i--) {
      const nbr = neighbors[i];
      push(node, frontier, [node, nbr.to], null); // 检查一条边
      if (!seen.has(nbr.to)) {
        seen.add(nbr.to);
        frontier.push(nbr.to);
        push(node, frontier, null, null); // 新节点入栈
      }
    }

    visited.add(node);
    push(node, frontier, null, null); // 处理完，移入 visited
  }

  push(null, frontier, null, null); // 最后一帧
}

/**
 * Dijkstra：单源最短路。
 * 要求所有权重非负——有负权边时「已确定」的节点还可能被更短的路径推翻，这套贪心就不成立了。
 * 这里 frontier 是「已发现但还没确定最短路的节点」，distances 是「目前已发现的最短距离」，
 * 还没连上的节点压根不出现在表里（页面显示为 ∞）。
 */
function dijkstra(adj: Map<string, Neighbor[]>, startId: string, rec: FrameRecorder): void {
  const { push, visited } = rec;
  const dist: Record<string, number> = { [startId]: 0 };
  const frontier: string[] = [startId]; // 未确定最短路的节点

  push(null, frontier, null, { ...dist }); // 开局

  while (frontier.length > 0) {
    // 挑 frontier 里当前距离最小的节点
    let bestIndex = 0;
    for (let i = 1; i < frontier.length; i++) {
      if ((dist[frontier[i]] ?? Infinity) < (dist[frontier[bestIndex]] ?? Infinity)) {
        bestIndex = i;
      }
    }
    const node = frontier[bestIndex];
    frontier.splice(bestIndex, 1);
    push(node, frontier, null, { ...dist }); // 取出

    for (const nbr of adj.get(node) ?? []) {
      push(node, frontier, [node, nbr.to], { ...dist }); // 检查一条边

      const candidate = (dist[node] ?? Infinity) + nbr.weight;
      if (dist[nbr.to] === undefined || candidate < dist[nbr.to]) {
        dist[nbr.to] = candidate;
        if (!visited.has(nbr.to) && !frontier.includes(nbr.to)) {
          frontier.push(nbr.to);
        }
        push(node, frontier, null, { ...dist }); // 更新距离 / 新节点加入 frontier
      }
    }

    visited.add(node);
    push(node, frontier, null, { ...dist }); // 处理完，移入 visited
  }

  push(null, frontier, null, { ...dist }); // 最后一帧
}

/**
 * 同步生成整段帧序列。内部没有 setTimeout / async，返回的就是一个现成数组。
 * startId 不在图里时返回空数组。
 */
export function generateGraphFrames(
  algorithm: GraphAlgorithm,
  graph: GraphData,
  startId: string,
): GraphFrame[] {
  if (!graph.nodes.some((node) => node.id === startId)) {
    return [];
  }

  const adj = buildAdjacency(graph);
  const rec = createRecorder();

  switch (algorithm) {
    case "bfs":
      bfs(adj, startId, rec);
      break;
    case "dfs":
      dfs(adj, startId, rec);
      break;
    case "dijkstra":
      dijkstra(adj, startId, rec);
      break;
    default:
      // GraphAlgorithm 已穷尽，这里只为满足 switch 的完整性要求
      break;
  }

  return rec.frames;
}

/**
 * 固定示例图：7 个节点，坐标落在 0..600 x 0..320，连通且带环，权重都是正整数。
 * 写死返回、不用随机，这样每次打开都一样，手点几次也能对比。
 */
export function sampleGraph(): GraphData {
  return {
    nodes: [
      { id: "n1", label: "A", x: 80, y: 60 },
      { id: "n2", label: "B", x: 260, y: 60 },
      { id: "n3", label: "C", x: 440, y: 60 },
      { id: "n4", label: "D", x: 170, y: 200 },
      { id: "n5", label: "E", x: 350, y: 200 },
      { id: "n6", label: "F", x: 530, y: 200 },
      { id: "n7", label: "G", x: 260, y: 300 },
    ],
    edges: [
      { from: "n1", to: "n2", weight: 4 },
      { from: "n1", to: "n4", weight: 2 },
      { from: "n2", to: "n3", weight: 5 },
      { from: "n2", to: "n4", weight: 1 },
      { from: "n2", to: "n5", weight: 7 },
      { from: "n3", to: "n5", weight: 3 },
      { from: "n4", to: "n5", weight: 2 },
      { from: "n4", to: "n7", weight: 6 },
      { from: "n5", to: "n6", weight: 4 },
      { from: "n5", to: "n7", weight: 3 },
    ],
  };
}

/* ------------------------------------------------------------------ *
 * 图编辑：下面五个也是纯函数，只是从「读图」变成「造一张新图」。
 *
 * 为什么一律返回新对象，而不是在传进来的 graph 上原地改？
 * 因为这份 graph 要放进 React 的 useState。React 判断「要不要重渲染」靠的是引用比较（Object.is）：
 * 原地 push / splice 之后再 setGraph(同一个引用)，React 会认为状态没变，界面根本不会更新。
 * 所以每次编辑都返回一份新的 GraphData（连同新的 nodes / edges 数组），
 * 新旧两份互不影响，以后想拿旧图做撤销或者对比也方便。
 *
 * 关于「原样返回」：校验不通过（比如删一个不存在的节点）时直接 return 传进来的 graph，
 * 引用没变，React 也会自动跳过这次重渲染，不浪费一次渲染。
 *
 * 注意：这里只换数组和对象的「壳」，数组里的节点 / 边对象本身不做深拷贝——
 * 因为这些函数从不修改元素，只整体替换，浅拷贝就够了，也更省。
 * ------------------------------------------------------------------ */

/**
 * 新增一个节点。
 * - id 取当前没被占用的最小 "n{数字}"：从 n1 开始往后试，撞上已有的就 +1。
 *   这样删掉中间某个节点之后再加，会优先把空出来的号补上。
 * - label 取当前没被用掉的字母 A..Z；26 个都用完了就退回 id（形如 "n27"）。
 *   label 只是显示用，不保证唯一——用完就退回 id，页面上照样分得清。
 * - x / y 直接透传（调用方已经换算并夹到画布内了）。
 */
export function addNode(graph: GraphData, x: number, y: number): GraphData {
  const usedIds = new Set(graph.nodes.map((node) => node.id));
  let index = 1;
  while (usedIds.has(`n${index}`)) index++;
  const id = `n${index}`;

  const usedLabels = new Set(graph.nodes.map((node) => node.label));
  let label = id;
  for (let code = 65; code <= 90; code++) {
    const candidate = String.fromCharCode(code);
    if (!usedLabels.has(candidate)) {
      label = candidate;
      break;
    }
  }

  return {
    nodes: [...graph.nodes, { id, label, x, y }],
    edges: [...graph.edges],
  };
}

/**
 * 移动一个节点：只改这一个节点的 x / y，边跟坐标无关，原样带过去。
 * 节点不存在就 return 传进来的 graph（拖拽事件有可能比状态更新晚到，点位已经没了，不该抛异常）。
 */
export function moveNode(graph: GraphData, id: string, x: number, y: number): GraphData {
  if (!graph.nodes.some((node) => node.id === id)) {
    return graph;
  }
  return {
    nodes: graph.nodes.map((node) => (node.id === id ? { ...node, x, y } : node)),
    edges: [...graph.edges],
  };
}

/**
 * 删掉一个节点，同时把它连带的所有边一起删掉。
 *
 * 为什么必须连带删边？
 * 图里的边是拿 from / to 两个 id 指向节点的。节点没了、边却还留着，就成了「悬空边」：
 * 它的 from / to 指向一个根本不存在的 id，后面 buildAdjacency 会把邻居塞进一个不存在的 key，
 * 渲染时 find 出 undefined 只能整条跳过，遍历也会顺着它走到空节点上。
 * 与其让下游到处判空，不如在删节点的这一刻就把相关边清干净，
 * 守住「任意一条边的两端一定都有节点」这个不变量。
 */
export function removeNode(graph: GraphData, id: string): GraphData {
  if (!graph.nodes.some((node) => node.id === id)) {
    return graph;
  }
  return {
    nodes: graph.nodes.filter((node) => node.id !== id),
    edges: graph.edges.filter((edge) => edge.from !== id && edge.to !== id),
  };
}

/**
 * 加一条边。下面几类输入视为无效，一律 return 传进来的 graph（原样返回）：
 * - from / to 有一个不存在 → 会造出悬空边；
 * - from === to → 自环，这套遍历和渲染都没打算支持；
 * - 两端之间已经有边 → 用 isSameEdge 做「无向」判重，n1-n2 和 n2-n1 算同一条；
 * - weight 不是正整数（0、负数、小数、NaN）→ 权重得能当正的长度用。
 */
export function addEdge(graph: GraphData, from: string, to: string, weight: number): GraphData {
  const hasNode = (id: string): boolean => graph.nodes.some((node) => node.id === id);
  if (!hasNode(from) || !hasNode(to)) return graph;
  if (from === to) return graph;
  if (graph.edges.some((edge) => isSameEdge(edge, from, to))) return graph;
  if (!Number.isInteger(weight) || weight <= 0) return graph;

  return {
    nodes: [...graph.nodes],
    edges: [...graph.edges, { from, to, weight }],
  };
}

/**
 * 删边：同样按无向来删，from / to 顺序反过来也算同一条（判重交给 isSameEdge）。
 * 没有这条边就原样返回。
 */
export function removeEdge(graph: GraphData, from: string, to: string): GraphData {
  if (!graph.edges.some((edge) => isSameEdge(edge, from, to))) {
    return graph;
  }
  return {
    nodes: [...graph.nodes],
    edges: graph.edges.filter((edge) => !isSameEdge(edge, from, to)),
  };
}
