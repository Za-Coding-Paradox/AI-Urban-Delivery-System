// src/lib/constants.ts
//
// Frontend constants. These mirror values from the backend (schemas, registry,
// plan) so the frontend never hardcodes domain knowledge independently.
// If a backend constant changes, update here and TypeScript surfaces the gaps.

import type { AlgorithmId, CellType, NodeStatus, EdgeType } from "@/types";

// ── grid ───────────────────────────────────────────────────────────────────

export const GRID_WIDTH  = 15;
export const GRID_HEIGHT = 15;
export const GRID_CELLS  = GRID_WIDTH * GRID_HEIGHT; // 225

// ── algorithms ─────────────────────────────────────────────────────────────

export const ALGORITHM_IDS: AlgorithmId[] = ["bfs", "dfs", "ucs", "greedy", "astar"];

export const ALGORITHM_LABELS: Record<AlgorithmId, string> = {
  bfs:    "Breadth-First Search",
  dfs:    "Depth-First Search",
  ucs:    "Uniform Cost Search",
  greedy: "Greedy Best-First",
  astar:  "A* Search",
};

export const ALGORITHM_SHORT: Record<AlgorithmId, string> = {
  bfs:    "BFS",
  dfs:    "DFS",
  ucs:    "UCS",
  greedy: "Greedy",
  astar:  "A*",
};

// Whether the algorithm is cost-optimal
export const ALGORITHM_OPTIMAL: Record<AlgorithmId, boolean> = {
  bfs:    true,   // optimal for hop count, not cost
  dfs:    false,
  ucs:    true,
  greedy: false,
  astar:  true,
};

// Accent colour per algorithm — used for badges, chart lines, graph overlays
export const ALGORITHM_COLOR: Record<AlgorithmId, string> = {
  bfs:    "#378add",  // blue
  dfs:    "#d85a30",  // coral
  ucs:    "#7f77dd",  // purple
  greedy: "#ef9f27",  // amber
  astar:  "#1d9e75",  // teal
};

// ── cell types ─────────────────────────────────────────────────────────────
// Mirrors cell_type_registry.json exactly

export const CELL_COLORS: Record<CellType, string> = {
  road:           "#1e2330",
  traffic_zone:   "#2d1f0a",
  obstacle:       "#0d0f12",
  delivery_point: "#1a2a1a",
  base_station:   "#0d1f1a",
};

export const CELL_BORDER_COLORS: Record<CellType, string> = {
  road:           "#2a3040",
  traffic_zone:   "#6b3d0a",
  obstacle:       "#1a1e26",
  delivery_point: "#2d6e2d",
  base_station:   "#1d9e75",
};

export const CELL_LABELS: Record<CellType, string> = {
  road:           "Road",
  traffic_zone:   "Traffic Zone",
  obstacle:       "Building",
  delivery_point: "Delivery Point",
  base_station:   "Base Station",
};

export const CELL_COST_RANGES: Record<CellType, [number, number] | null> = {
  road:           [1, 5],
  traffic_zone:   [10, 20],
  obstacle:       null,
  delivery_point: [1, 5],
  base_station:   [1, 3],
};

// ── node status ─────────────────────────────────────────────────────────────
// 3D graph visual encoding from the plan

export const NODE_STATUS_COLORS: Record<NodeStatus, string> = {
  open:   "#378add",  // blue  — on frontier
  closed: "#7f77dd",  // purple — expanded
  path:   "#639922",  // green  — final path
};

export const NODE_STATUS_LABELS: Record<NodeStatus, string> = {
  open:   "Frontier",
  closed: "Expanded",
  path:   "Path",
};

// ── edge types ─────────────────────────────────────────────────────────────

export const EDGE_COLORS: Record<EdgeType, string> = {
  expansion: "#888780",
  path:      "#639922",
  backtrack: "#d85a30",
};

export const EDGE_LABELS: Record<EdgeType, string> = {
  expansion: "Expansion",
  path:      "Path",
  backtrack: "Backtrack",
};

// ── WebSocket ──────────────────────────────────────────────────────────────

// Client ID sent to the server on WS connect
// In a multi-tab scenario each tab generates a unique ID
export const WS_CLIENT_ID = `ui-${Math.random().toString(36).slice(2, 9)}`;

// The WS URL goes through Vite's proxy (/ws → ws://localhost:8000/ws)
export const WS_URL = `/ws/${WS_CLIENT_ID}`;

// ── API ────────────────────────────────────────────────────────────────────

// All REST calls go through the Vite proxy (/api → http://localhost:8000)
export const API_BASE = "/api";

// ── playback ───────────────────────────────────────────────────────────────

export const PLAYBACK_SPEEDS = [0.5, 1, 2, 5] as const;
export type PlaybackSpeed = typeof PLAYBACK_SPEEDS[number];

// Milliseconds between steps at 1× speed
export const PLAYBACK_STEP_MS = 80;
