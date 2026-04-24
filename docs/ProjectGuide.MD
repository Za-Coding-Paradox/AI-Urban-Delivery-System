# Positron — Project Guide

**Comprehensive technical reference for the Urban Delivery Simulator**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Backend Deep Dive](#3-backend-deep-dive)
4. [Frontend Deep Dive](#4-frontend-deep-dive)
5. [Data Schemas](#5-data-schemas)
6. [Algorithm Reference](#6-algorithm-reference)
7. [Event System](#7-event-system)
8. [Playback System](#8-playback-system)
9. [City Profiles](#9-city-profiles)
10. [API Reference](#10-api-reference)
11. [Testing](#11-testing)
12. [Configuration](#12-configuration)
13. [Deployment](#13-deployment)
14. [Design Decisions](#14-design-decisions)
15. [Known Issues & Roadmap](#15-known-issues--roadmap)

---

## 1. Project Overview

Positron is a profile-driven, real-time simulation system for visualizing AI search algorithms navigating an urban delivery grid. It was built as an educational tool for demonstrating and comparing BFS, DFS, UCS, Greedy Best-First, and A★ — but the architecture is designed to be general-purpose: any graph search algorithm can be plugged in by implementing a four-method interface.

### Design Philosophies

**Data-driven simulation.** Every aspect of the environment that can vary is expressed as data, not code. Grid layout, cell types, traversal costs, delivery sequences, robot behavior, and algorithm configurations are all JSON. Code only reads and executes data. This makes the system instantly extensible — adding a new cell type or cost model requires a JSON definition, not a code change.

**Component-driven frontend.** Every UI element is a self-contained component with explicit props and no direct knowledge of sibling components. Communication happens only through the Zustand store. The 3D graph, the 2D grid, the playback bar, and the metrics panel can all be swapped or extended without touching each other.

**Dual-indexed event stream.** The backend emits a single stream of structured trace events over WebSocket. The frontend indexes these events simultaneously into a flat buffer (for global playback control) and a segment map keyed by `"algorithm_id:delivery_id"` (for per-pair visualization). This lets a single scrubber control global time while each algorithm/delivery pair renders its own isolated progress.

---

## 2. Architecture

### System Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                    JSON City Profiles                           │
│          (alpha.json, roundtrip.json, dense_city.json...)       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Python Backend (FastAPI)                      │
│                                                                 │
│  ProfileManager          GridBuilder          EventBus          │
│  (load/save/generate) →  (build + validate) → (pub/sub/buffer) │
│                                                                 │
│  RunController                                                  │
│  └── for each delivery:                                         │
│      └── for each algorithm:                                    │
│          StackTraceBuilder + AlgorithmRunner → emit events      │
│                                                                 │
│  WebSocket Server (FastAPI + asyncio.Queue bridge)              │
│  └── broadcasts events to all connected clients in real time    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │  WebSocket  (JSON TraceEvents)
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   React Frontend (Vite + TS)                    │
│                                                                 │
│  useWebSocket                                                   │
│  └── ingestEvent()  ──────────────────────────────────┐        │
│                                                        │        │
│  Zustand Store                                         │        │
│  ├── events[]              ← flat buffer               │        │
│  └── eventsBySegment{}     ← "bfs:D2" → [...events]   │        │
│                                                        │        │
│  Components                                            │        │
│  ├── GridView      (2D canvas, reads segmentEvents)    │        │
│  ├── GraphView     (Three.js 3D, reads trace graphs)   │        │
│  ├── PlaybackBar   (segment-aware scrubber)            │        │
│  ├── MetricsView   (Recharts comparison charts)        │        │
│  └── NodeInspector (selected node details)             │        │
└────────────────────────────────────────────────────────┘        │
```

### Key Engineering Decisions

**Async/sync bridge.** Algorithms run synchronously in a `ThreadPoolExecutor` (they are CPU-bound; async adds no benefit). The `EventBus.publish()` call is synchronous from the algorithm thread. WebSocket sends (`await ws.send_json()`) are async and must run on the event loop. The bridge is `asyncio.Queue` + `loop.call_soon_threadsafe()`: the thread schedules a `queue.put_nowait`, and an async `broadcast_task()` drains the queue and sends to clients. This decouples algorithm speed from client speed.

**Sequential deliveries, not parallel.** Each delivery runs all algorithms to completion before moving to the next delivery. True parallelism across algorithms would require separate EventBus instances (the bus is not thread-safe for concurrent publishes) and would produce non-deterministic buffer ordering, breaking playback. Sequential is correct at 15×15 scale.

**Segment map pre-bucketing.** Every event with `algorithm_id` and `delivery_id` is indexed into `eventsBySegment["algo:deliveryId"]` at ingestion time. This turns per-segment event access from O(n) (scan flat buffer) to O(1) (map lookup). The `segmentFlatIndices` array built in `PlaybackBar` provides a pre-computed lookup for translating between segment-space cursor positions and flat-space cursor positions.

---

## 3. Backend Deep Dive

### Module Map

```
backend/
├── algorithms/
│   ├── base_runner.py        # Abstract base: shared search loop, neighbors, metrics
│   ├── bfs.py                # Queue frontier (FIFO)
│   ├── dfs.py                # Stack frontier (LIFO)
│   ├── ucs.py                # Priority queue by g cost
│   ├── greedy.py             # Priority queue by h cost
│   ├── astar.py              # Priority queue by f = g + h
│   └── algorithms_registry.py  # {"bfs": BFSRunner, ...} dispatch table
├── common/
│   └── constants.py          # GRID_WIDTH=15, GRID_HEIGHT=15, density bounds
├── engine/
│   ├── event_bus.py          # Pub/sub message broker with replay buffer
│   ├── grid_builder.py       # Builds + validates Cell[225] from profile JSON
│   └── profile_manager.py    # Load/save/generate city profiles
├── heuristics/
│   └── distance.py           # manhattan(), euclidean(), zero() + registry
├── profiles/                 # Saved .json city profiles
├── schemas/                  # JSON Schema files for all data types
├── tests/                    # pytest test suite
├── trace/
│   └── trace_builder.py      # StackTraceBuilder: subscribes to bus, builds TraceGraph
└── websocket/
    ├── web_server.py          # FastAPI app, endpoints, WebSocket handler, broadcaster
    └── run_controller.py      # Orchestrates runs: deliveries × algorithms
```

### EventBus

The EventBus is the central message broker. It maintains three structures:

- `_handlers: dict[str, list[Handler]]` — per-event-type subscribers plus a wildcard `"*"` key
- `_buffer: list[dict]` — complete ordered history of every event, used for playback replay
- `_websocket_connections: list` — active WS connections for live broadcasting

Every `publish(event)` call appends to the buffer, calls specific-type handlers, calls wildcard handlers, and sends to active WS connections. The buffer grows monotonically for the lifetime of a run; it is cleared between runs.

### Algorithm Base Runner

`BaseRunner` (ABC) defines the complete search loop in `run()`. Child classes implement only four methods:

```python
def _init_frontier(self) -> None    # set up data structure
def _push(self, node, priority)     # add to frontier
def _pop(self) -> dict              # remove next node
def _is_empty(self) -> bool         # check if done
def _frontier_size(self) -> int     # for metrics
def _priority(self, g, h) -> Any    # BFS/DFS ignore; UCS=g; Greedy=h; A*=g+h
```

The search loop is identical for all five algorithms. What differs is the frontier data structure (queue, stack, or priority queue) and the priority function. This is the Template Method pattern.

Every node visit and expansion emits a `node_visit` or `node_expand` TraceEvent to the EventBus with `algorithm_id`, `delivery_id`, step number, node data (x, y, g, h, f, depth, parent), and edge data. These events are what the frontend visualizes.

### ProfileManager

Profiles are generated from a numeric seed using `GridBuilder.build()`, which:
1. Places one base station at the robot's configured start position
2. Places 5 delivery points at the configured destinations
3. Randomly places obstacles (5–20% of cells, seeded for reproducibility)
4. Randomly places traffic zones (15% of remaining passable cells, cost = 10)
5. Runs a BFS connectivity check to verify all delivery points are reachable from the base station. If not, it retries with the seed incremented until a valid layout is found.

Profiles are validated against `city_profile.schema.json` before saving.

### RunController

Execution order:
1. `GridBuilder().build(profile)` → `cells: list[dict]`
2. Emit `grid_built` event
3. For each delivery destination D (sequential):
   - Emit `delivery_start`
   - For each enabled algorithm A:
     - Create `StackTraceBuilder(A, D, bus)`
     - Emit `algorithm_start`
     - `runner.run(cells, start, goal, config)` → `metrics: dict`
     - Collect `TraceGraph` from builder
     - Emit `algorithm_complete`
     - `builder.detach()`
4. Emit `simulation_complete` with all metrics

---

## 4. Frontend Deep Dive

### Store Architecture

The Zustand store is the single source of truth for all application state. Key slices:

```typescript
// Playback state
playback: {
  cursor: number,       // position in flat events[]
  total: number,        // flat events[].length
  playing: boolean,
  speed: number,        // multiplier on PLAYBACK_STEP_MS
}

// Dual-indexed event store
events: ServerEvent[]                         // flat, ordered, all events
eventsBySegment: Record<string, ServerEvent[]> // keyed "algo:deliveryId"

// Active view selection
activeAlgorithm: AlgorithmId
activeDelivery: string  // "D1" ... "D5"

// Algorithm lifecycle
algorithmStates: Record<string, AlgorithmState>  // per algo: idle/running/complete/error

// Results
graphs: TraceGraph[]       // 3D graph data per algo per delivery
metrics: MetricsSummary[]  // performance data per algo per delivery
```

### ingestEvent()

Called by `useWebSocket` for every incoming message. Simultaneously:

1. Appends to `events[]` (flat buffer)
2. Updates `playback.total`
3. If event has `algorithm_id` + `delivery_id`: appends to `eventsBySegment[key]`
4. Routes lifecycle events to the appropriate state slices:
   - `algorithm_start` → `algorithmStates[algo] = "running"`
   - `algorithm_complete` → `algorithmStates[algo] = "complete"` + update metrics
   - `trace_graph_ready` → push to `graphs[]`
   - `simulation_complete` → `runStatus = "complete"`

### PlaybackBar — Segment-Aware Scrubbing

The `PlaybackBar` component maintains:

```typescript
// Pre-computed index: position N → flat index of Nth segment event
const segmentFlatIndices: number[] = useMemo(() => {
  // single O(n) scan of flatEvents, built when segment changes
}, [flatEvents, segmentKey]);

// Binary search for current segment cursor position
const segmentCursor: number = useMemo(() => {
  // O(log n) binary search on segmentFlatIndices
}, [segmentFlatIndices, playback.cursor]);
```

The slider operates entirely in segment space (`min=0`, `max=segmentTotal-1`, `value=segmentCursor`). When dragged to position `n`, it translates to flat space via `segmentFlatIndices[n-1]` and calls `store.setPlaybackCursor(flatIdx)`.

The playback interval reads live state via `useStore.getState()` to avoid stale closures. It depends on `[playing, speed, total]` — `total` is included so the interval fires when events first arrive while `playing` is already `true`.

### GridView — Simulation State

`GridView` derives `simState` by replaying segment events up to `segmentCursor`:

```typescript
const simState = useMemo(() => {
  const visited = new Set<string>();
  const frontier = new Set<string>();
  const pathSet = new Set<string>();
  let robotPos = { x: startX, y: startY };

  for (let i = 0; i < segmentCursor; i++) {
    const ev = segmentEvents[i];
    if (ev.event_type === "node_expand")  visited.add(ev.node.id);
    if (ev.event_type === "node_visit")   frontier.add(ev.node.id);
    if (ev.event_type === "path_step")    pathSet.add(ev.node.id);
    if (ev.event_type === "node_expand")  robotPos = { x: ev.node.x, y: ev.node.y };
  }

  return { visited, frontier, pathSet, robotPos };
}, [segmentEvents, segmentCursor]);
```

This produces a purely derived, deterministic render — scrubbing backward is just re-deriving from a smaller `segmentCursor`.

### GraphView — 3D Search Tree

The `GraphView` uses Three.js via `@react-three/fiber` and `@react-three/drei`. Each node in the trace graph is rendered as a typed, color-coded sphere. Edges are rendered as line segments or animated tubes. The camera is orbitable and zoomable. Selecting a node fires a store action that updates `selectedNode`, which `NodeInspectorPanel` reads to show g, h, f, depth, parent, and cell type.

---

## 5. Data Schemas

All schemas live in `backend/schemas/` and are enforced by `jsonschema` at profile load/save time.

### TraceEvent (trace_event.schema.json)

```json
{
  "event_type": "node_visit | node_expand | path_step | delivery_complete | ...",
  "step": 42,
  "timestamp_ms": 1234.5,
  "algorithm_id": "bfs | dfs | ucs | greedy | astar",
  "delivery_id": "D1",
  "node": {
    "id": "7,3",
    "x": 7, "y": 3,
    "cell_type": "road",
    "g": 5.0, "h": 3.0, "f": 8.0,
    "depth": 5,
    "parent_id": "6,3",
    "status": "open | closed | path"
  },
  "edge": {
    "from_id": "6,3", "to_id": "7,3",
    "edge_type": "expansion | path | backtrack",
    "cost": 1.0
  },
  "frontier_size": 8,
  "visited_count": 12
}
```

### CityProfile (city_profile.schema.json)

```json
{
  "meta": { "id": "uuid", "name": "alpha", "seed": 1, "created_at": "...", "version": "1.0" },
  "grid": {
    "width": 15, "height": 15,
    "cells": [ /* 225 Cell objects */ ]
  },
  "robot": { "start": {"x": 9, "y": 10}, "movement": "cardinal", "cost_model": "edge_cost", "tie_breaking": "first" },
  "deliveries": {
    "count": 5,
    "destinations": [ {"id": "D1", "x": 13, "y": 13, "label": "Delivery 1"}, ... ],
    "order": "sequential"
  },
  "algorithms": [
    {"id": "bfs", "enabled": true, "heuristic": "none", "weight": 1.0, "visualize": true},
    ...
  ]
}
```

### Cell Types

| Type | Passable | Cost | Description |
|------|----------|------|-------------|
| `road` | true | 1 | Standard road cell |
| `traffic_zone` | true | 10 | High-cost congestion zone |
| `delivery_point` | true | 1 | Delivery destination |
| `base_station` | true | 1 | Robot starting position |
| `obstacle` | false | null | Impassable wall |

---

## 6. Algorithm Reference

All algorithms share the same `BaseRunner.run()` loop. They differ only in frontier structure and priority.

### BFS — Breadth-First Search

- **Frontier:** `collections.deque` (FIFO queue)
- **Priority:** insertion order (FIFO, ignores g and h)
- **Heuristic:** `zero` (null object — h always 0, has no effect)
- **Guarantees:** optimal path on unweighted graphs. Not optimal on weighted grids (traffic zones cost 10, not 1).
- **Characteristic behavior:** expands outward in concentric rings from start. Thorough but expensive.

### DFS — Depth-First Search

- **Frontier:** `list` as stack (LIFO)
- **Priority:** insertion order (LIFO, ignores g and h)
- **Heuristic:** `zero`
- **Guarantees:** none. May find a very suboptimal path. May explore most of the grid.
- **Characteristic behavior:** plunges deep into one branch before backtracking. Edges are tagged `"backtrack"` for the 3D graph visualization.

### UCS — Uniform Cost Search

- **Frontier:** `heapq` priority queue
- **Priority:** `g` (cumulative cost from start)
- **Heuristic:** `zero` (h=0, so f=g+0=g)
- **Guarantees:** optimal path on weighted graphs. Dijkstra's algorithm.
- **Characteristic behavior:** expands in order of true path cost. Will route around traffic zones correctly.

### Greedy Best-First Search

- **Frontier:** `heapq` priority queue
- **Priority:** `h` (heuristic estimate to goal)
- **Heuristic:** `manhattan` or `euclidean`
- **Guarantees:** none. Fast but not optimal — ignores actual path cost.
- **Characteristic behavior:** beelines toward the goal. May find a short path quickly but walks through expensive traffic zones.

### A★

- **Frontier:** `heapq` priority queue
- **Priority:** `f = g + h`
- **Heuristic:** `manhattan` or `euclidean`
- **Guarantees:** optimal path when heuristic is admissible (never overestimates). Manhattan on a cardinal grid is admissible and consistent.
- **Characteristic behavior:** balances actual cost and estimated remaining cost. Generally explores fewer nodes than BFS/UCS while still finding the optimal path.

### Heuristics

| Heuristic | Formula | Admissible | Consistent | Best for |
|-----------|---------|------------|------------|----------|
| `manhattan` | `|ax-bx| + |ay-by|` | Yes | Yes | Cardinal movement grids |
| `euclidean` | `sqrt((ax-bx)² + (ay-by)²)` | Yes | Yes | When diagonals added |
| `none` (zero) | `0` | Yes | Yes | BFS, DFS, UCS (null object) |

---

## 7. Event System

### Event Types

| Event Type | Emitted By | Contains |
|------------|------------|---------|
| `connected` | Server | `client_id`, `bus_buffer_size` |
| `grid_built` | RunController | `run_id`, `cell_count` |
| `delivery_start` | RunController | `run_id`, `delivery_id`, `start`, `goal` |
| `algorithm_start` | BaseRunner | `run_id`, `delivery_id`, `algorithm_id` |
| `node_visit` | BaseRunner | Full TraceEvent with node + edge |
| `node_expand` | BaseRunner | Full TraceEvent with node |
| `path_step` | BaseRunner | Full TraceEvent, status="path" |
| `delivery_complete` | BaseRunner | `algorithm_id`, `delivery_id`, `goal_id`, `step` |
| `algorithm_complete` | RunController | `path_found`, `path_cost`, `nodes_explored` |
| `trace_graph_ready` | StackTraceBuilder | Full TraceGraph object |
| `simulation_complete` | RunController | `run_id`, `profile_name`, `total_metrics` |
| `simulation_error` | RunController | `error` message |
| `ping` / `pong` | Server / Client | Keepalive |

### WebSocket Lifecycle

```
Client connects → /ws/{client_id}
Server sends: { event_type: "connected", bus_buffer_size: N }

Client sends: { type: "ping" }
Server sends: { event_type: "pong" }

Client sends: { type: "replay", run_id: "...", event_type: "*" }
Server replays buffer events to this client only

Client sends: { type: "status" }
Server sends: { event_type: "server_status", ws_clients: N, active_runs: M, ... }

Server sends events live as simulation runs
Server sends: { event_type: "ping" } every 30s as keepalive if client is quiet
Client disconnects → removed from _ws_clients set
```

---

## 8. Playback System

The playback system has two coordinate spaces that must stay in sync:

**Flat space** — `0` to `events.length - 1`. The global playback cursor operates here. Includes lifecycle events (`grid_built`, `algorithm_start`, etc.) that have no `algorithm_id`/`delivery_id`.

**Segment space** — `0` to `segmentEvents.length - 1`. Scoped to one `(algorithm, delivery)` pair. The scrubber thumb, fill bar, and counter all operate here.

### segmentFlatIndices

`segmentFlatIndices[n]` = the flat index of the n-th event belonging to the active segment. Built with a single O(n) scan when the active segment changes. Never rebuilt on cursor changes.

```
Flat buffer:  [lifecycle, A:D1, lifecycle, A:D1, A:D1, B:D1, A:D1, ...]
                           ↑               ↑     ↑           ↑
segmentFlatIndices for A:D1: [1, 3, 4, 6]
```

### segmentCursor

`segmentCursor` = how many segment events fall at or before the current flat `cursor`. Computed with binary search on `segmentFlatIndices`. O(log n).

```
flat cursor = 4
segmentFlatIndices for A:D1 = [1, 3, 4, 6]
Binary search: how many values ≤ 4? → 3
segmentCursor = 3
```

### Play Button Behavior

When Play is clicked while `segmentCursor === 0`, the flat cursor is immediately jumped to `segmentFlatIndices[0]` (the first real trace event for this segment) before starting the interval. This skips the pre-segment lifecycle events that would otherwise make the grid appear frozen.

---

## 9. City Profiles

### Generating a Profile

```bash
# Via API
curl -X POST http://localhost:8000/profiles/generate \
  -H "Content-Type: application/json" \
  -d '{"seed": 99, "name": "my_city"}'

# Via Python
from backend.engine.profile_manager import ProfileManager
mgr = ProfileManager()
profile = mgr.generate(seed=99, name="my_city")
mgr.save(profile, "my_city")
```

### Profile Constraints

- Grid: always 15×15 (225 cells)
- Obstacles: 5–20% of cells
- Traffic zones: 15% of passable cells, cost = 10
- Delivery points: exactly 5
- Connectivity: guaranteed — GridBuilder retries seeds until all delivery points are reachable from base station

### Custom Profiles

You can hand-craft a profile JSON and submit it inline:

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"profile": { ...full profile JSON... }}'
```

The profile is validated against `city_profile.schema.json` before the run starts.

---

## 10. API Reference

### POST /run

**Request:**
```json
{
  "profile_name": "alpha",
  "algorithm_ids": ["bfs", "astar"]
}
```

`algorithm_ids` is optional. If provided, only those algorithms run regardless of the profile's `enabled` flags.

**Response:**
```json
{
  "run_id": "uuid",
  "status": "pending",
  "profile_name": "alpha",
  "message": "Run started. Connect to WebSocket /ws/{client_id} for live events."
}
```

### GET /run/{id}/results

**Response:**
```json
{
  "run_id": "uuid",
  "profile_name": "alpha",
  "seed": 1,
  "status": "complete",
  "metrics": [
    {
      "algorithm_id": "bfs",
      "delivery_id": "D1",
      "path_cost": 14.0,
      "execution_time_ms": 2.3,
      "nodes_explored": 87,
      "path_length": 14,
      "path_found": true,
      "path": [{"x": 9, "y": 10}, ...],
      "heuristic_used": "none"
    },
    ...
  ],
  "graphs": [ /* TraceGraph objects */ ]
}
```

### GET /bus/buffer

Paginated access to the raw event buffer for debugging.

```bash
curl "http://localhost:8000/bus/buffer?limit=50&offset=100"
```

---

## 11. Testing

### Test Suite Structure

```
backend/tests/
├── test_algorithms.py        # All 5 runners: path found, path cost, metrics
├── test_event_bus.py         # publish, subscribe, replay, buffer, wildcard
├── test_grid_builder.py      # build, connectivity check, obstacle constraints
├── test_heuristics.py        # manhattan, euclidean, zero, registry
├── test_profile_manager.py   # generate, save, load, list, validation errors
├── test_trace_builder.py     # StackTraceBuilder subscribe/finalize/detach
└── test_websocket_server.py  # FastAPI endpoints via httpx async client
```

### Running Tests

```bash
# Full suite
pytest backend/tests/ -v

# Single file
pytest backend/tests/test_algorithms.py -v

# Single test
pytest backend/tests/test_algorithms.py::test_bfs_finds_path -v

# With coverage
pytest backend/tests/ --cov=backend --cov-report=term-missing
```

### Test Isolation

WebSocket server tests use a `reset_server_state` fixture that pre-injects fresh `EventBus` and `ProfileManager` instances into the server module's singletons before `TestClient` enters the lifespan. This prevents test contamination without mocking.

---

## 12. Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSITRON_HOST` | `0.0.0.0` | Server bind address |
| `POSITRON_PORT` | `8000` | Server port |
| `POSITRON_ENV` | `dev` | Environment name |
| `PYTHONPATH` | project root | Must include project root |

### Frontend Constants (frontend/src/lib/constants.ts)

| Constant | Default | Description |
|----------|---------|-------------|
| `PLAYBACK_STEP_MS` | `50` | Base interval between playback steps (ms) |
| `WS_URL` | `ws://localhost:8000/ws/...` | WebSocket endpoint |

### Algorithm Speed

Playback speed is controlled by the speed multiplier in the PlaybackBar. The actual tick interval is `PLAYBACK_STEP_MS / speed`. Speed options are: 0.5×, 1×, 2×, 4×, 8×.

---

## 13. Deployment

### Development

```bash
# Terminal 1 — backend with hot reload
source .venv/bin/activate
export PYTHONPATH=$PWD
uvicorn backend.websocket.web_server:app --reload --port 8000

# Terminal 2 — frontend with HMR
cd frontend
pnpm dev
```

Frontend: http://localhost:5173  
Backend API: http://localhost:8000  
API docs: http://localhost:8000/docs

### Production

```bash
# Build frontend
cd frontend && pnpm build && cd ..

# Deploy static files
cp -r frontend/dist/* backend/static/

# Patch server to mount static files (one time)
# (Done automatically by setup.sh --prod and Dockerfile)

# Start production server
uvicorn backend.websocket.web_server:app \
  --host 0.0.0.0 --port 8000 \
  --workers 1 \
  --log-level info
```

> **Note:** Use `--workers 1` only. Multiple workers cannot share the in-memory EventBus, active runs dict, or WebSocket client set. For multi-worker production, replace these with Redis pub/sub.

### Docker

```bash
docker build -t positron .
docker run -p 8000:8000 --name positron-app positron

# With custom port
docker run -p 9000:8000 positron

# With profile persistence
docker run -p 8000:8000 -v ./profiles:/app/backend/profiles positron
```

---

## 14. Design Decisions

### Why ThreadPoolExecutor for algorithms?

Algorithms are CPU-bound (tight while loops). Async/await is for I/O-bound work. Running algorithms in `asyncio.run_in_executor` pushes them off the event loop thread so they don't block WebSocket sends, without the overhead of full multiprocessing.

### Why a flat buffer AND a segment map?

The flat buffer enables a single global playback cursor that controls time across all algorithms and deliveries simultaneously. The segment map enables O(1) event access for a specific (algorithm, delivery) pair during rendering. You need both to have both a coherent global timeline and efficient per-segment rendering.

### Why not re-scan the flat buffer every render?

At `5 algorithms × 5 deliveries × ~200 events each = ~5,000 events`, scanning on every render frame (60fps) would be 300,000 iterations per second just for playback. The pre-bucketed segment map reduces this to 0 scans at render time — all buckets are pre-built at ingestion time.

### Why sequential deliveries?

1. The EventBus is not thread-safe for concurrent publishes from multiple algorithm threads.
2. Non-deterministic buffer ordering would break playback replay.
3. At 15×15 scale, sequential runs complete in milliseconds — parallelism buys nothing.

### Why `useStore.getState()` in the interval callback?

React's `useEffect` captures variables from the render scope (closure). If the interval callback used the closed-over `total` or `cursor` values, it would operate on stale data as state updates. `useStore.getState()` reads the current Zustand state synchronously and directly, bypassing React's render cycle. This is the correct pattern for imperative side effects that need live state.

---

## 15. Known Issues & Roadmap

### Known Issues

- **WebGL context loss on some browsers** — Three.js logs `WebGL context was lost` in Firefox due to the deprecated `mozPressure`/`mozInputSource` properties. This is a browser compatibility warning, not a functional error. The 3D graph recovers automatically.
- **Large event buffers on long runs** — the flat `events[]` array grows unboundedly during a run. For very dense profiles or many deliveries, this can grow to 10,000+ events. No pagination is implemented on the frontend event buffer.

### Roadmap

- **Diagonal movement** — add `diagonal` to `RobotConfig.movement`. Requires Euclidean heuristic and 8-directional neighbor expansion in `BaseRunner`.
- **Custom cell types** — allow new cell types to be defined in `cell_type_registry.json` without code changes.
- **Parallel algorithm runs** — partition the EventBus (one per algorithm), merge events with a synthetic timestamp for ordered replay.
- **Export** — export simulation results as CSV or JSON for offline analysis.
- **Shareable profile URLs** — encode profile seed in the URL for one-click sharing.
- **Multi-robot** — multiple robots with independent base stations and delivery sequences.
