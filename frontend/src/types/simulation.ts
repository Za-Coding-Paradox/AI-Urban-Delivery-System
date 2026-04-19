// src/types/simulation.ts
//
// TypeScript interfaces that mirror every JSON schema in backend/schemas/.
// These are the contracts between the Python backend and the React frontend.
//
// Rule: every field name and type here must exactly match what the backend
// produces. If the backend changes a schema, update here first and let
// TypeScript surface every component that needs updating.
//
// Naming convention:
//   - Interfaces use PascalCase (CityProfile, TraceEvent)
//   - Union string types use lowercase literals ("bfs" | "dfs")
//   - Optional fields use ? — only where the backend schema allows null/missing

// ── algorithm identifiers ──────────────────────────────────────────────────

export type AlgorithmId = "bfs" | "dfs" | "ucs" | "greedy" | "astar";

export type HeuristicId = "manhattan" | "euclidean" | "none";

export type MovementMode = "cardinal" | "cardinal+diagonal";

export type CostModel = "edge_cost" | "node_cost";

export type TieBreaking = "first" | "lower_h" | "random";

export type CellType =
  | "road"
  | "traffic_zone"
  | "obstacle"
  | "delivery_point"
  | "base_station";

// ── cell type registry ─────────────────────────────────────────────────────
// Mirrors cell_type_registry.json

export interface CellTypeDefinition {
  passable: boolean;
  cost_range: [number, number] | null;
  color_token: string;
  display_name: string;
}

export type CellTypeRegistry = Record<CellType, CellTypeDefinition>;

// ── cell ───────────────────────────────────────────────────────────────────
// Mirrors cell.schema.json

export interface Cell {
  id: string;           // "{x},{y}"
  x: number;
  y: number;
  type: CellType;
  cost: number | null;  // null for obstacles
  passable: boolean;
  label: string | null;
  metadata: Record<string, unknown>;
}

// ── robot config ───────────────────────────────────────────────────────────
// Mirrors robot_config.schema.json

export interface RobotConfig {
  start: { x: number; y: number };
  movement: MovementMode;
  cost_model: CostModel;
  tie_breaking: TieBreaking;
}

// ── delivery sequence ──────────────────────────────────────────────────────
// Mirrors deliver_sequence.schema.json

export interface DeliveryDestination {
  id: string;    // "D1" … "D5"
  x: number;
  y: number;
  label: string;
}

export interface DeliverySequence {
  count: 5;
  destinations: DeliveryDestination[];
  order: "sequential";
}

// ── algorithm config ───────────────────────────────────────────────────────
// Mirrors algorithm_config.schema.json

export interface AlgorithmConfig {
  id: AlgorithmId;
  enabled: boolean;
  heuristic: HeuristicId;
  weight: number;
  visualize: boolean;
}

// ── city profile ───────────────────────────────────────────────────────────
// Mirrors city_profile.schema.json — the complete simulation environment

export interface ProfileMeta {
  id: string;
  name: string;
  seed: number;
  created_at: string;  // ISO 8601
  version: string;
}

export interface CityProfile {
  meta: ProfileMeta;
  grid: {
    width: 15;
    height: 15;
    cells: Cell[];
  };
  robot: RobotConfig;
  deliveries: DeliverySequence;
  algorithms: AlgorithmConfig[];
}

// ── trace event ────────────────────────────────────────────────────────────
// Mirrors trace_event.schema.json — one event emitted per node operation

export type TraceEventType =
  | "node_visit"
  | "node_expand"
  | "path_found"
  | "path_step"
  | "delivery_complete";

export type NodeStatus = "open" | "closed" | "path";

export type EdgeType = "expansion" | "path" | "backtrack";

export interface TraceNode {
  id: string;
  x: number;
  y: number;
  cell_type: CellType;
  g: number;
  h: number;
  f: number;
  depth: number;
  parent_id: string | null;
  status: NodeStatus;
}

export interface TraceEdge {
  from_id: string;
  to_id: string;
  edge_type: EdgeType;
  cost: number;
}

export interface TraceEvent {
  event_type: TraceEventType;
  step: number;
  timestamp_ms: number;
  algorithm_id: AlgorithmId;
  node?: TraceNode;
  edge?: TraceEdge | null;
  frontier_size?: number;
  visited_count?: number;
}

// ── metrics summary ────────────────────────────────────────────────────────
// Mirrors metrics_summary.schema.json — produced after each algorithm run

export interface MetricsSummary {
  algorithm_id: AlgorithmId;
  delivery_id: string;
  path_cost: number;
  execution_time_ms: number;
  nodes_explored: number;
  path_length: number;
  path_found: boolean;
  path: Array<{ x: number; y: number }>;
  heuristic_used: HeuristicId;
}

// ── trace graph ────────────────────────────────────────────────────────────
// Produced by StackTraceBuilder.finalize() — input to the 3D graph renderer

export interface EdgeHistoryEntry {
  step: number;
  cost: number;
  edge_type: EdgeType;
}

export interface TraceGraphEdge {
  from_id: string;
  to_id: string;
  edge_type: EdgeType;
  cost: number;
  visit_count: number;       // how many times this edge was traversed
  history: EdgeHistoryEntry[]; // every traversal in chronological order
}

export interface TraceGraphNode {
  id: string;
  x: number;
  y: number;
  cell_type: CellType;
  g: number;
  h: number;
  f: number;
  depth: number;
  parent_id: string | null;
  status: NodeStatus;
  step: number;              // global step when this node was first recorded
}

export interface TraceGraphMetadata {
  total_steps: number;
  max_depth: number;
  max_g: number;
  max_f: number;
  complete: boolean;
  node_count: number;
  edge_count: number;
}

export interface TraceGraph {
  algorithm_id: AlgorithmId;
  delivery_id: string;
  nodes: TraceGraphNode[];
  edges: TraceGraphEdge[];
  metadata: TraceGraphMetadata;
}

// ── server events ──────────────────────────────────────────────────────────
// Events the backend publishes beyond the trace event schema.
// These are progress/lifecycle events consumed by the frontend store.

export interface ConnectedEvent {
  event_type: "connected";
  client_id: string;
  message: string;
  bus_buffer_size: number;
}

export interface AlgorithmStartEvent {
  event_type: "algorithm_start";
  run_id: string;
  delivery_id: string;
  algorithm_id: AlgorithmId;
}

export interface AlgorithmCompleteEvent {
  event_type: "algorithm_complete";
  run_id: string;
  delivery_id: string;
  algorithm_id: AlgorithmId;
  path_found: boolean;
  path_cost: number;
  nodes_explored: number;
}

export interface DeliveryStartEvent {
  event_type: "delivery_start";
  run_id: string;
  delivery_id: string;
  start: { x: number; y: number };
  goal: { x: number; y: number };
}

export interface TraceGraphReadyEvent {
  event_type: "trace_graph_ready";
  algorithm_id: AlgorithmId;
  delivery_id: string;
  graph: TraceGraph;
}

export interface SimulationCompleteEvent {
  event_type: "simulation_complete";
  run_id: string;
  profile_name: string;
  total_metrics: MetricsSummary[];
}

export interface SimulationErrorEvent {
  event_type: "simulation_error";
  run_id: string;
  error: string;
}

export interface GridBuiltEvent {
  event_type: "grid_built";
  run_id: string;
  cell_count: number;
}

// Union of all possible WebSocket message shapes
export type ServerEvent =
  | ConnectedEvent
  | AlgorithmStartEvent
  | AlgorithmCompleteEvent
  | DeliveryStartEvent
  | TraceGraphReadyEvent
  | SimulationCompleteEvent
  | SimulationErrorEvent
  | GridBuiltEvent
  | TraceEvent
  | { event_type: "ping" }
  | { event_type: "pong" }
  | { event_type: string; [key: string]: unknown }; // fallback for unknown events

// ── API request/response shapes ────────────────────────────────────────────
// What the REST endpoints accept and return

export interface GenerateProfileRequest {
  seed: number;
  name?: string;
}

export interface RunRequest {
  profile_name?: string;
  profile?: CityProfile;
  algorithm_ids?: AlgorithmId[];
}

export interface RunResponse {
  run_id: string;
  status: RunStatus;
  profile_name: string;
  message: string;
}

export interface RunResultsResponse {
  run_id: string;
  profile_name: string;
  seed: number;
  status: RunStatus;
  metrics: MetricsSummary[];
  graphs: TraceGraph[];
}

export type RunStatus = "pending" | "running" | "complete" | "failed";

// ── UI-only types ──────────────────────────────────────────────────────────
// Not from backend schemas — internal frontend state shapes

// Which of the three main views is active
export type ActiveView = "grid" | "graph" | "metrics";

// A node that has been selected in either the grid or 3D graph
export interface SelectedNode {
  node: TraceGraphNode;
  algorithm_id: AlgorithmId;
  delivery_id: string;
}

// Playback state
export interface PlaybackState {
  cursor: number;          // index into the event buffer
  total: number;           // total events in buffer
  playing: boolean;
  speed: 0.5 | 1 | 2 | 5; // playback speed multiplier
}

// Per-algorithm run status visible in the UI
export interface AlgorithmRunState {
  id: AlgorithmId;
  status: "idle" | "running" | "complete" | "failed";
  current_delivery: string | null;
  nodes_explored: number;
  path_found: boolean | null;
}
