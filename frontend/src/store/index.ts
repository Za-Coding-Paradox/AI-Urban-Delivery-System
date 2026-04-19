// src/store/index.ts
//
// The global state store. Built with Zustand — minimal, hook-based, no
// provider wrapping needed. Every component reads from this store via
// selector hooks and never holds local copies of simulation data.
//
// ── slice structure ────────────────────────────────────────────────────────
// The store is split into logical slices, all merged into one flat object:
//
//   simulation  — current profile, grid cells, run status, run id
//   algorithms  — per-algorithm run state (running/complete/failed)
//   graphs      — TraceGraph per (algorithm_id, delivery_id)
//   events      — raw event buffer for playback
//   playback    — cursor, play/pause, speed
//   selected    — currently inspected node
//   ui          — active view, sidebar open state
//   metrics     — MetricsSummary collection from completed runs
//
// ── design: flat store, selector access ───────────────────────────────────
// All state lives at the top level of one store object. Components use
// fine-grained selectors: useStore(s => s.grid) rather than useStore().
// This prevents unnecessary re-renders — a component subscribed to
// s.selectedNode will NOT re-render when s.grid changes.

import { create } from "zustand";
import type {
  ActiveView,
  AlgorithmId,
  AlgorithmRunState,
  CityProfile,
  MetricsSummary,
  PlaybackState,
  RunStatus,
  SelectedNode,
  ServerEvent,
  TraceGraph,
} from "@/types";
import { PLAYBACK_STEP_MS } from "@/lib/constants";

// ── store shape ────────────────────────────────────────────────────────────

interface SimStore {
  // ── simulation ─────────────────────────────────────────────────────────
  profile:    CityProfile | null;
  runId:      string | null;
  runStatus:  RunStatus | "idle";
  connected:  boolean;   // WebSocket connection status

  // ── algorithms ─────────────────────────────────────────────────────────
  // Keyed by algorithm_id — tracks per-algorithm run progress
  algorithmStates: Record<AlgorithmId, AlgorithmRunState>;

  // ── trace graphs ────────────────────────────────────────────────────────
  // Keyed by "${algorithm_id}:${delivery_id}" — one TraceGraph per pair
  graphs: Record<string, TraceGraph>;

  // ── event buffer (for playback) ─────────────────────────────────────────
  // The raw stream of ServerEvents received from the WebSocket.
  // Playback scrubs through this array.
  events: ServerEvent[];

  // ── playback ────────────────────────────────────────────────────────────
  playback: PlaybackState;

  // ── selected node (inspector panel) ────────────────────────────────────
  selectedNode: SelectedNode | null;

  // ── metrics ─────────────────────────────────────────────────────────────
  // All MetricsSummary objects from the current run
  metrics: MetricsSummary[];

  // ── ui ──────────────────────────────────────────────────────────────────
  activeView:      ActiveView;
  inspectorOpen:   boolean;
  activeDelivery:  string;  // "D1" … "D5" — which delivery tab is shown

  // ── actions ─────────────────────────────────────────────────────────────

  // WebSocket / connection
  setConnected: (connected: boolean) => void;

  // Profile and run
  setProfile:   (profile: CityProfile) => void;
  setRunId:     (runId: string) => void;
  setRunStatus: (status: RunStatus | "idle") => void;
  resetRun:     () => void;

  // Event ingestion — called by the WebSocket hook for every incoming event
  ingestEvent: (event: ServerEvent) => void;

  // Algorithm state
  setAlgorithmState: (id: AlgorithmId, state: Partial<AlgorithmRunState>) => void;

  // Graphs
  setGraph: (key: string, graph: TraceGraph) => void;

  // Metrics
  addMetrics: (metrics: MetricsSummary[]) => void;

  // Node selection
  selectNode:    (selection: SelectedNode) => void;
  clearSelected: () => void;

  // Playback
  setPlaybackCursor:  (cursor: number) => void;
  setPlaybackPlaying: (playing: boolean) => void;
  setPlaybackSpeed:   (speed: PlaybackState["speed"]) => void;
  stepForward:        () => void;
  stepBack:           () => void;

  // UI
  setActiveView:     (view: ActiveView) => void;
  setInspectorOpen:  (open: boolean) => void;
  setActiveDelivery: (id: string) => void;
}

// ── initial algorithm states ───────────────────────────────────────────────

function initialAlgorithmStates(): Record<AlgorithmId, AlgorithmRunState> {
  const ids: AlgorithmId[] = ["bfs", "dfs", "ucs", "greedy", "astar"];
  return Object.fromEntries(
    ids.map((id) => [
      id,
      {
        id,
        status:           "idle",
        current_delivery: null,
        nodes_explored:   0,
        path_found:       null,
      } satisfies AlgorithmRunState,
    ])
  ) as Record<AlgorithmId, AlgorithmRunState>;
}

// ── store ──────────────────────────────────────────────────────────────────

export const useStore = create<SimStore>((set, get) => ({
  // ── initial state ────────────────────────────────────────────────────────
  profile:         null,
  runId:           null,
  runStatus:       "idle",
  connected:       false,
  algorithmStates: initialAlgorithmStates(),
  graphs:          {},
  events:          [],
  playback: {
    cursor:  0,
    total:   0,
    playing: false,
    speed:   1,
  },
  selectedNode:   null,
  metrics:        [],
  activeView:     "grid",
  inspectorOpen:  false,
  activeDelivery: "D1",

  // ── WebSocket / connection ────────────────────────────────────────────────
  setConnected: (connected) => set({ connected }),

  // ── profile and run ──────────────────────────────────────────────────────
  setProfile:   (profile)  => set({ profile }),
  setRunId:     (runId)    => set({ runId }),
  setRunStatus: (runStatus) => set({ runStatus }),

  resetRun: () =>
    set({
      runId:           null,
      runStatus:       "idle",
      graphs:          {},
      events:          [],
      metrics:         [],
      selectedNode:    null,
      inspectorOpen:   false,
      algorithmStates: initialAlgorithmStates(),
      playback: {
        cursor:  0,
        total:   0,
        playing: false,
        speed:   get().playback.speed, // preserve speed preference across runs
      },
    }),

  // ── event ingestion ──────────────────────────────────────────────────────
  //
  // Called by useWebSocket for every message received from the server.
  // Routes each event to the right slice of the store.
  //
  // This is the central nervous system of the frontend: every backend
  // event flows through here and updates exactly the right state.
  ingestEvent: (event) => {
    const type = event.event_type;

    // Always append to the event buffer for playback
    set((s) => ({
      events: [...s.events, event],
      playback: { ...s.playback, total: s.events.length + 1 },
    }));

    // Route to specific state updates
    if (type === "algorithm_start" && "algorithm_id" in event) {
      const algEvent = event as { algorithm_id: AlgorithmId; delivery_id: string };
      set((s) => ({
        algorithmStates: {
          ...s.algorithmStates,
          [algEvent.algorithm_id]: {
            ...s.algorithmStates[algEvent.algorithm_id],
            status:           "running",
            current_delivery: algEvent.delivery_id,
          },
        },
      }));
    }

    else if (type === "algorithm_complete" && "algorithm_id" in event) {
      const algEvent = event as {
        algorithm_id: AlgorithmId;
        path_found: boolean;
        nodes_explored: number;
      };
      set((s) => ({
        algorithmStates: {
          ...s.algorithmStates,
          [algEvent.algorithm_id]: {
            ...s.algorithmStates[algEvent.algorithm_id],
            status:         "complete",
            path_found:     algEvent.path_found,
            nodes_explored: algEvent.nodes_explored,
          },
        },
      }));
    }

    else if (type === "trace_graph_ready" && "graph" in event) {
      const graphEvent = event as {
        algorithm_id: AlgorithmId;
        delivery_id: string;
        graph: TraceGraph;
      };
      const key = `${graphEvent.algorithm_id}:${graphEvent.delivery_id}`;
      set((s) => ({
        graphs: { ...s.graphs, [key]: graphEvent.graph },
      }));
    }

    else if (type === "simulation_complete" && "total_metrics" in event) {
      const simEvent = event as { total_metrics: MetricsSummary[] };
      set({
        runStatus: "complete",
        metrics:   simEvent.total_metrics,
      });
    }

    else if (type === "simulation_error") {
      set({ runStatus: "failed" });
    }
  },

  // ── algorithm state ──────────────────────────────────────────────────────
  setAlgorithmState: (id, partial) =>
    set((s) => ({
      algorithmStates: {
        ...s.algorithmStates,
        [id]: { ...s.algorithmStates[id], ...partial },
      },
    })),

  // ── graphs ───────────────────────────────────────────────────────────────
  setGraph: (key, graph) =>
    set((s) => ({ graphs: { ...s.graphs, [key]: graph } })),

  // ── metrics ──────────────────────────────────────────────────────────────
  addMetrics: (newMetrics) =>
    set((s) => ({ metrics: [...s.metrics, ...newMetrics] })),

  // ── node selection ────────────────────────────────────────────────────────
  selectNode: (selection) =>
    set({ selectedNode: selection, inspectorOpen: true }),

  clearSelected: () =>
    set({ selectedNode: null, inspectorOpen: false }),

  // ── playback ─────────────────────────────────────────────────────────────
  setPlaybackCursor: (cursor) =>
    set((s) => ({
      playback: { ...s.playback, cursor: Math.max(0, Math.min(cursor, s.playback.total - 1)) },
    })),

  setPlaybackPlaying: (playing) =>
    set((s) => ({ playback: { ...s.playback, playing } })),

  setPlaybackSpeed: (speed) =>
    set((s) => ({ playback: { ...s.playback, speed } })),

  stepForward: () =>
    set((s) => ({
      playback: {
        ...s.playback,
        cursor: Math.min(s.playback.cursor + 1, s.playback.total - 1),
      },
    })),

  stepBack: () =>
    set((s) => ({
      playback: {
        ...s.playback,
        cursor: Math.max(s.playback.cursor - 1, 0),
      },
    })),

  // ── ui ───────────────────────────────────────────────────────────────────
  setActiveView:     (activeView)     => set({ activeView }),
  setInspectorOpen:  (inspectorOpen)  => set({ inspectorOpen }),
  setActiveDelivery: (activeDelivery) => set({ activeDelivery }),
}));

// ── convenience selector hooks ─────────────────────────────────────────────
// Fine-grained selectors prevent unnecessary re-renders.
// Each hook subscribes to exactly one slice of state.

export const useProfile        = () => useStore((s) => s.profile);
export const useRunStatus      = () => useStore((s) => s.runStatus);
export const useConnected      = () => useStore((s) => s.connected);
const EMPTY_CELLS: any[] = [];
export const useGridCells      = () => useStore((s) => s.profile?.grid.cells ?? EMPTY_CELLS);
export const useMetrics        = () => useStore((s) => s.metrics);
export const useGraphs         = () => useStore((s) => s.graphs);
export const useSelectedNode   = () => useStore((s) => s.selectedNode);
export const usePlayback       = () => useStore((s) => s.playback);
export const useActiveView     = () => useStore((s) => s.activeView);
export const useInspectorOpen  = () => useStore((s) => s.inspectorOpen);
export const useActiveDelivery = () => useStore((s) => s.activeDelivery);
export const useAlgorithmStates = () => useStore((s) => s.algorithmStates);
export const useEvents         = () => useStore((s) => s.events);
