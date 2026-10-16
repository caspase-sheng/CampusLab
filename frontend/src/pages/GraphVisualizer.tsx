import { useEffect, useRef, useState, type MouseEvent, type PointerEvent } from "react";

import {
  addEdge,
  addNode,
  generateGraphFrames,
  isSameEdge,
  moveNode,
  removeEdge,
  removeNode,
  sampleGraph,
  type GraphAlgorithm,
  type GraphData,
  type GraphEdge,
  type GraphFrame,
} from "../lib/graph";

// 图遍历可视化页。
// 帧序列由 lib/graph.ts 同步算好（见那边的文件头），这里只管按速度回放：
// 用一个 index 指向当前帧，定时器每 intervalMs 推进一步。
// 图本身这一刀从模块级常量挪进了 state，因为要支持编辑：加节点、拖拽、连边、删节点 / 删边。
// 编辑只改 graph，遍历算法和播放逻辑原样不动。

// 工具模式：默认移动，播放中整组禁用（见下面的 toolbar）。
type ToolMode = "move" | "add" | "connect" | "delete";

const toolOptions: { value: ToolMode; label: string }[] = [
  { value: "move", label: "移动" },
  { value: "add", label: "加节点" },
  { value: "connect", label: "连边" },
  { value: "delete", label: "删除" },
];

// 画布角落里那行「当前模式怎么操作」的小字。
const toolHint: Record<ToolMode, string> = {
  move: "移动：拖拽节点",
  add: "加节点：点画布空白处",
  connect: "连边：依次点两个节点（自环 / 重复会被忽略）",
  delete: "删除：点节点会连边一起删，点边只删这条边（删错了可「重置为示例图」）",
};

const algorithmOptions: { value: GraphAlgorithm; label: string }[] = [
  { value: "bfs", label: "BFS（广度优先）" },
  { value: "dfs", label: "DFS（深度优先）" },
  { value: "dijkstra", label: "Dijkstra（最短路）" },
];

// 节点四种状态，颜色优先级从高到低：当前 > 已访问 > 在 frontier > 普通。
// 一个节点可能同时满足多个条件（比如刚取出的节点还在 frontier 里），用优先级决定画哪个颜色。
type NodeState = "current" | "visited" | "frontier" | "normal";

const nodeFill: Record<NodeState, string> = {
  current: "#f59e0b", // amber-500
  visited: "#10b981", // emerald-500
  frontier: "#0ea5e9", // sky-500
  normal: "#cbd5e1", // slate-300
};

// 浅色底上用深色字、深色底上用白字，保证 A..G 任何时候都看得清。
const nodeTextFill: Record<NodeState, string> = {
  current: "#ffffff",
  visited: "#ffffff",
  frontier: "#ffffff",
  normal: "#334155",
};

export default function GraphVisualizer() {
  // 图进 state：增删改都走 setGraph，这样 React 才能靠新引用感知到「图变了」。
  const [graph, setGraph] = useState<GraphData>(() => sampleGraph());
  const [algorithm, setAlgorithm] = useState<GraphAlgorithm>("bfs");
  const [startId, setStartId] = useState<string>("");
  const [speed, setSpeed] = useState(60);

  // frames 为空表示还没开始，这时画布上的图不做任何高亮。
  const [frames, setFrames] = useState<GraphFrame[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  // 当前工具模式。
  const [tool, setTool] = useState<ToolMode>("move");
  // 正在拖拽的节点 id（只有移动模式会用到）。
  const [draggingId, setDraggingId] = useState<string | null>(null);
  // 连边模式里第一次点中的节点 id；点第二个点时和它配对，null 表示还没选。
  const [connectFrom, setConnectFrom] = useState<string | null>(null);

  // 换算坐标要用 <svg> 的 getBoundingClientRect；读权重要用输入框的当前值。
  const svgRef = useRef<SVGSVGElement | null>(null);
  const weightRef = useRef<HTMLInputElement | null>(null);

  // 速度到定时器间隔的映射沿用排序页：intervalMs = 200 - speed * 1.9。
  // speed=1 约 198ms（很慢），speed=100 正好 10ms（很快），手调起来比较顺手。
  const intervalMs = 200 - speed * 1.9;

  // 推进帧。定时器只依赖 playing / speed，index 用函数式更新，
  // 这样 index 每次变化都不会把定时器反复重建，只有暂停/继续或改速度才重建。
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setIndex((prev) => Math.min(prev + 1, Math.max(frames.length - 1, 0)));
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [playing, speed, frames.length, intervalMs]);

  // 到最后一帧自动停：和上面那个 effect 分工不同，上面管「多久推一步」，这个管「什么时候停」。
  useEffect(() => {
    if (playing && frames.length > 0 && index >= frames.length - 1) {
      setPlaying(false);
    }
  }, [playing, index, frames.length]);

  // 起点可能因为编辑而失效（比如它刚被删掉）。图里还有节点时，回落到第一个节点。
  useEffect(() => {
    if (graph.nodes.length > 0 && !graph.nodes.some((node) => node.id === startId)) {
      setStartId(graph.nodes[0].id);
    }
  }, [graph, startId]);

  // 「有效起点」：就算上面那个 effect 还没跑完，渲染和取帧也不会拿到一个不存在的 id。
  // 图空了就是空串，这时起点 select 和开始按钮都会禁用。
  const firstNodeId = graph.nodes.length > 0 ? graph.nodes[0].id : "";
  const startExists = graph.nodes.some((node) => node.id === startId);
  const effectiveStartId = startExists ? startId : firstNodeId;

  // 当前该画的那一帧：还没开始时为 null，四类高亮全按「普通」处理。
  const frame = frames.length > 0 ? frames[Math.min(index, frames.length - 1)] : null;

  const visitedSet = new Set(frame?.visited ?? []);
  const frontierSet = new Set(frame?.frontier ?? []);
  const currentId = frame?.current ?? null;
  const activeEdge = frame?.activeEdge ?? null;

  const algorithmLabel =
    algorithmOptions.find((opt) => opt.value === algorithm)?.label ?? algorithm;

  /** 把节点 id 翻成它展示用的字母。 */
  function labelOf(id: string): string {
    return graph.nodes.find((node) => node.id === id)?.label ?? id;
  }

  /** 节点状态，按优先级判定。 */
  function stateOf(id: string): NodeState {
    if (currentId === id) return "current";
    if (visitedSet.has(id)) return "visited";
    if (frontierSet.has(id)) return "frontier";
    return "normal";
  }

  /** 边的颜色：命中当前边（两个方向都算）→ red-500，其余 → slate-300。 */
  function edgeColor(edge: GraphEdge): string {
    if (activeEdge && isSameEdge(edge, activeEdge[0], activeEdge[1])) {
      return "#ef4444";
    }
    return "#cbd5e1";
  }

  /** 节点的鼠标指针样式，提示当前模式在节点上能干什么。 */
  function nodeCursor(id: string): string {
    if (playing) return "cursor-default";
    if (tool === "move") return draggingId === id ? "cursor-grabbing" : "cursor-grab";
    return "cursor-pointer";
  }

  /** 停播、清空帧、下标归零。 */
  function resetPlayback() {
    setPlaying(false);
    setFrames([]);
    setIndex(0);
  }

  /**
   * 所有「改变图」的操作统一走这里。
   * 编辑之后必须清空 frames：frames 是照着「旧图」拍下来的快照，里面记着节点 id、访问顺序。
   * 图一变，这些帧就可能引用已经不存在的节点（比如刚被删掉的那个），
   * 继续播要么渲染出空节点、要么下标越界，所以干脆清掉，
   * 下次点「开始」时拿新图重新生成一整段帧序列。
   * 另外，addEdge / removeNode 这些校验不通过时会原样返回同一个 graph（引用没变），
   * 这时什么都不用做，也别白白清掉当前的播放状态。
   */
  function applyGraph(next: GraphData) {
    if (next === graph) return;
    setGraph(next);
    resetPlayback();
  }

  /**
   * 把鼠标事件的 client 坐标换算成 SVG 的 viewBox 坐标，并夹到画布内。
   *
   * 这一步最容易写错：viewBox 是 0 0 640 360，但 <svg> 的实际显示宽度是自适应的（w-full）。
   * 直接拿 clientX 当坐标，等于把「屏幕像素」当成「viewBox 单位」，整体会错位，
   * 而且窗口一缩放，错位的比例还会跟着变。
   * 所以要先减去画布左上角（rect.left / rect.top）把坐标挪到画布原点，
   * 再乘上「viewBox 尺寸 / 实际显示尺寸」，把像素换算成 viewBox 单位。
   */
  function toViewBoxCoords(clientX: number, clientY: number): { x: number; y: number } {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * 640;
    const y = ((clientY - rect.top) / rect.height) * 360;
    // 节点圆半径 16，夹到 [16, 624] x [16, 344] 才能保证整个圆留在画布里（640-16=624、360-16=344）。
    return {
      x: Math.min(Math.max(x, 16), 624),
      y: Math.min(Math.max(y, 16), 344),
    };
  }

  function handleToolChange(next: ToolMode) {
    setTool(next);
    // 换模式就把「连边的第一个点」清掉，免得切走再切回来还留着那圈高亮。
    setConnectFrom(null);
  }

  /** 节点上的 pointerdown：只有移动模式才开始拖拽。 */
  function handleNodePointerDown(e: PointerEvent<SVGGElement>, id: string) {
    if (playing) return;
    if (tool !== "move") return;

    // 点中节点就不算「点空白」，拦住冒泡，别让画布把它当成加节点。
    e.stopPropagation();

    // setPointerCapture 是关键：把接下来这一串指针事件锁定到当前节点上。
    // 拖拽时鼠标很容易滑出节点圆圈、甚至滑出整个画布，
    // 不 capture 的话 pointermove 会发给指针下面的别的元素，拖拽到一半就断了；
    // capture 之后不管指针跑到哪，pointermove / pointerup 都还会送回这个节点。
    e.currentTarget.setPointerCapture(e.pointerId);

    resetPlayback(); // 位置马上要变，旧帧（记着旧坐标）先作废
    setDraggingId(id);
  }

  /** 节点上的 pointermove：拖拽中更新该节点坐标。 */
  function handleNodePointerMove(e: PointerEvent<SVGGElement>, id: string) {
    if (tool !== "move" || draggingId !== id) return;
    const { x, y } = toViewBoxCoords(e.clientX, e.clientY);
    // 函数式更新：拖拽期间 setGraph 会连续触发，用 prev 拿最新的图，免得用到旧闭包里的 graph。
    setGraph((prev) => moveNode(prev, id, x, y));
  }

  /**
   * 节点上的 pointerup / pointercancel：结束拖拽。
   *
   * pointercancel 是浏览器主动取消这一次指针交互时发的（触屏被系统手势接管、
   * 窗口失焦、指针设备被拔掉等），它跟 pointerup 是两条路，不一定会先有 pointerup。
   * 只挂 pointerup 的话，这些情况会漏掉收尾：draggingId 一直挂在那个节点上，
   * 之后鼠标划过它、不用按着也会跟着走（pointermove 里只判了 draggingId === id）。
   * 所以两个事件都指向这里。
   *
   * 下面的 hasPointerCapture 检查保留：cancel 场景下浏览器可能已经把捕获释放掉了，
   * 这颗检查正好让「重复释放」不会抛异常。
   */
  function handleNodePointerEnd(e: PointerEvent<SVGGElement>, id: string) {
    if (draggingId !== id) return;
    // 浏览器在 pointerup 后一般会自动释放捕获，这里显式放一次让语义更清楚；
    // 先用 hasPointerCapture 问一下，已经放开过就不会重复释放报错。
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    setDraggingId(null);
  }

  /** 节点的 click：连边模式配对，删除模式删节点，其余模式什么都不做。 */
  function handleNodeClick(e: MouseEvent<SVGGElement>, id: string) {
    if (playing) return;
    // 点中节点就不是「空白」，一律拦住冒泡，避免画布把它当成加节点。
    e.stopPropagation();

    if (tool === "connect") {
      if (connectFrom === null) {
        setConnectFrom(id); // 第一次点：记下来并高亮，等第二个点
        return;
      }
      // 第二次点：拿权重输入框的值去加边。
      // 两次点同一个点（自环）、两点之间已有边、权重非法，都会被 addEdge 挡下并原样返回。
      const weight = Number(weightRef.current?.value ?? "");
      const next = addEdge(graph, connectFrom, id, weight);
      if (next !== graph) applyGraph(next);
      // 不管这次成没成，都把第一个点的选择清掉，别一直挂着高亮。
      setConnectFrom(null);
      return;
    }

    if (tool === "delete") {
      // 删节点不做 confirm：删错了「重置为示例图」一键还原（工具栏那行小字有提示）。
      applyGraph(removeNode(graph, id));
    }
  }

  /** 边的 click：删除模式下删这条边；其余模式只拦住冒泡。 */
  function handleEdgeClick(e: MouseEvent<SVGGElement>, from: string, to: string) {
    if (playing) return;
    e.stopPropagation();
    if (tool !== "delete") return;
    applyGraph(removeEdge(graph, from, to));
  }

  /** 画布的 click：只有「加节点」模式才会在空白处落一个点。 */
  function handleCanvasClick(e: MouseEvent<SVGSVGElement>) {
    if (playing) return;
    if (tool !== "add") return;
    const { x, y } = toViewBoxCoords(e.clientX, e.clientY);
    applyGraph(addNode(graph, x, y));
  }

  function handlePlayPause() {
    if (playing) {
      // 暂停：只停定时器，保留 index
      setPlaying(false);
      return;
    }
    if (graph.nodes.length === 0) return; // 没有节点没什么可放的（按钮也置灰了）
    if (frames.length === 0) {
      // 第一次开始：按当前算法和起点生成整段帧序列，再播放
      setFrames(generateGraphFrames(algorithm, graph, effectiveStartId));
      setIndex(0);
    } else if (index >= frames.length - 1) {
      // 已经播到最后一帧再点开始：从头重播，否则会立刻被自动停逻辑按下
      setIndex(0);
    }
    setPlaying(true);
  }

  function handleReset() {
    // 重置播放：停定时器、index 归零，保留 frames
    setPlaying(false);
    setIndex(0);
  }

  function handleAlgorithmChange(next: GraphAlgorithm) {
    // 换算法：停定时器、清空 frames，下次点开始重新生成
    setPlaying(false);
    setAlgorithm(next);
    setFrames([]);
    setIndex(0);
  }

  function handleStartChange(next: string) {
    // 换起点：同上，清空 frames
    setPlaying(false);
    setStartId(next);
    setFrames([]);
    setIndex(0);
  }

  function handleResetToSample() {
    const next = sampleGraph();
    setGraph(next);
    // 和别的编辑一样：停播、清帧、下标归零——旧帧里的节点 id 已经对不上新图了。
    resetPlayback();
    setConnectFrom(null);
    setDraggingId(null);
    // 起点直接设成新图的第一个节点，不必等「起点回落」那个 effect。
    setStartId(next.nodes[0].id);
  }

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold text-slate-900">图遍历可视化</h1>

      <div className="flex flex-wrap items-end gap-4 rounded-lg border border-slate-200 bg-white p-4">
        <div>
          <span className="mb-1 block text-sm text-slate-600">工具</span>
          <div className="flex items-center gap-3">
            {toolOptions.map((opt) => (
              <label key={opt.value} className="flex items-center gap-1 text-sm text-slate-700">
                <input
                  type="radio"
                  name="graph-tool"
                  value={opt.value}
                  checked={tool === opt.value}
                  disabled={playing}
                  onChange={() => handleToolChange(opt.value)}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm text-slate-600" htmlFor="graph-weight-input">
            连边权重
          </label>
          <input
            id="graph-weight-input"
            ref={weightRef}
            type="number"
            min={1}
            step={1}
            defaultValue={1}
            disabled={playing}
            className="w-24 rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm text-slate-600" htmlFor="graph-algo-select">
            算法
          </label>
          <select
            id="graph-algo-select"
            value={algorithm}
            disabled={playing}
            onChange={(e) => handleAlgorithmChange(e.target.value as GraphAlgorithm)}
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
          <label className="mb-1 block text-sm text-slate-600" htmlFor="graph-start-select">
            起点
          </label>
          <select
            id="graph-start-select"
            value={effectiveStartId}
            disabled={playing || graph.nodes.length === 0}
            onChange={(e) => handleStartChange(e.target.value)}
            className="rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {graph.nodes.map((node) => (
              <option key={node.id} value={node.id}>
                {node.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm text-slate-600" htmlFor="graph-speed-range">
            速度（{speed}）
          </label>
          <input
            id="graph-speed-range"
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
            disabled={graph.nodes.length === 0}
            className="rounded bg-slate-900 px-4 py-2 text-sm text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {playing ? "暂停" : "开始"}
          </button>
          <button
            type="button"
            onClick={handleReset}
            disabled={playing}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            重置
          </button>
          <button
            type="button"
            onClick={handleResetToSample}
            disabled={playing}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            重置为示例图
          </button>
        </div>
      </div>

      <div className="relative rounded-lg border border-slate-200 bg-white p-4">
        <svg
          ref={svgRef}
          viewBox="0 0 640 360"
          onClick={handleCanvasClick}
          className="h-auto w-full rounded-lg border border-slate-200 bg-white"
        >
          {/* 先画边，再画节点，节点压在上层不会被线盖住 */}
          {graph.edges.map((edge) => {
            const from = graph.nodes.find((node) => node.id === edge.from);
            const to = graph.nodes.find((node) => node.id === edge.to);
            if (!from || !to) return null;
            const midX = (from.x + to.x) / 2;
            const midY = (from.y + to.y) / 2;
            return (
              <g
                key={`${edge.from}-${edge.to}`}
                onClick={(e) => handleEdgeClick(e, edge.from, edge.to)}
                className={!playing && tool === "delete" ? "cursor-pointer" : undefined}
              >
                {/* 透明的粗线只当点击热区：2px 的可见线太难点，删除模式下这点很关键 */}
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke="transparent"
                  strokeWidth={10}
                />
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={edgeColor(edge)}
                  strokeWidth={2}
                />
                <text
                  x={midX}
                  y={midY - 8}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={11}
                  fill="#64748b"
                >
                  {edge.weight}
                </text>
              </g>
            );
          })}

          {graph.nodes.map((node) => {
            const state = stateOf(node.id);
            const isConnectSource = connectFrom === node.id;
            return (
              <g
                key={node.id}
                onPointerDown={(e) => handleNodePointerDown(e, node.id)}
                onPointerMove={(e) => handleNodePointerMove(e, node.id)}
                onPointerUp={(e) => handleNodePointerEnd(e, node.id)}
                onPointerCancel={(e) => handleNodePointerEnd(e, node.id)}
                onClick={(e) => handleNodeClick(e, node.id)}
                className={nodeCursor(node.id)}
              >
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={16}
                  fill={nodeFill[state]}
                  // 连边模式里选中的第一个节点：加一圈虚线深色描边，提示「在等第二个点」
                  stroke={isConnectSource ? "#0f172a" : "none"}
                  strokeWidth={isConnectSource ? 3 : 0}
                  strokeDasharray={isConnectSource ? "4 3" : undefined}
                />
                <text
                  x={node.x}
                  y={node.y}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={14}
                  fontWeight={600}
                  fill={nodeTextFill[state]}
                >
                  {node.label}
                </text>
              </g>
            );
          })}
        </svg>

        {/* 画布角落那行小字，说明当前模式怎么操作。pointer-events-none 免得挡住点击 */}
        <div className="pointer-events-none absolute right-5 top-5 max-w-[70%] rounded bg-white/85 px-2 py-1 text-right text-xs text-slate-500">
          {toolHint[tool]}
        </div>
      </div>

      <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <div className="text-slate-700">
          <span className="text-slate-500">当前算法：</span>
          {algorithmLabel}
          <span className="ml-4 text-slate-500">起点：</span>
          {graph.nodes.length > 0 ? labelOf(effectiveStartId) : "（无节点）"}
        </div>

        <div className="text-slate-700">
          <span className="text-slate-500">访问顺序：</span>
          {(frame?.visited ?? []).length > 0
            ? (frame?.visited ?? []).map((id) => labelOf(id)).join(" → ")
            : "（还没开始）"}
        </div>

        <div className="text-slate-700">
          <span className="text-slate-500">frontier：</span>
          {(frame?.frontier ?? []).length > 0
            ? (frame?.frontier ?? []).map((id) => labelOf(id)).join(", ")
            : "（空）"}
        </div>

        {algorithm === "dijkstra" && (
          <div className="text-slate-700">
            <span className="text-slate-500">距离表：</span>
            {graph.nodes
              .map((node) => `${node.label}: ${frame?.distances?.[node.id] ?? "∞"}`)
              .join(", ")}
          </div>
        )}
      </div>
    </section>
  );
}
