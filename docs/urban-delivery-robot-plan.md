# Urban Delivery Robot — System Implementation Plan
**National University of Computer & Emerging Sciences — Faisalabad-Chiniot Campus**
*AI Search Algorithms · Palantir Foundry-Inspired Simulator · 3D Stack Trace Visualization*

---

## 0. Document scope

This document is a **plan only** — no code, no implementations. It describes what to build, why, how it is organized, what methodologies govern each layer, and what decisions must be made before implementation begins. Two methodologies govern the entire system:

- **Data-driven methodology** — governs the simulation engine. The environment, its entities, its costs, its events, and its behavior are all defined entirely in JSON. No environment logic lives in code. Code only reads and executes data.
- **Component-driven methodology** — governs the frontend application. Every visual and interactive element is an isolated, reusable component with a defined interface. No component knows about another component directly — they communicate through a shared state store.

---

## 1. Project overview

### 1.1 What was explicitly assigned

A 15×15 grid-based urban delivery simulation where a robot navigates from a base station to five sequential delivery destinations using five search algorithms: BFS, DFS, UCS, Greedy Best-First Search, and A*. Performance is evaluated across three metrics: path cost, execution time, and nodes explored. Traversal costs are randomised at generation time — normal roads cost 1–5, traffic zones cost 10–20. Heuristics use Euclidean and Manhattan distance.

### 1.2 What this plan builds instead

A **profile-based real-time simulator** with a JSON-driven simulation engine, a live 2D grid viewer, a full algorithm benchmarking dashboard, and — the centrepiece — a **3D interactive node graph** that renders each algorithm's search tree as a spatial, explorable object. Every node in the graph is interactive, typed, color-coded, and inspectable via a Foundry-style node inspector panel. Edges carry animated, typed particles. The graph is fully rotatable, zoomable, and stretchable.

### 1.3 Design inspiration

The UI paradigm is directly inspired by **Palantir Foundry's Object Explorer and Pipeline Builder** — specifically: the concept of every entity being a typed object with inspectable properties, edges representing relationships with directionality and type, and the canvas being an infinite, navigable space rather than a fixed viewport.

---

## 2. Methodology declarations

### 2.1 Data-driven methodology — simulation engine

> Every aspect of the environment that can vary must be expressed as data, not code.

**What this means in practice:**
- The grid layout is a JSON document, not a programmatically generated array.
- Cell types (road, obstacle, traffic zone, delivery point, base station) are defined in a JSON schema with their traversal rules, cost ranges, and visual tokens.
- The robot's behavior profile (movement rules, cost calculation, tie-breaking policy) is a JSON config object.
- Delivery sequences are JSON arrays of coordinate pairs.
- Simulation events (robot moves, algorithm steps, delivery completions) are emitted as structured JSON event objects consumed by the visualization layer.
- Algorithm configurations (which heuristic, which tie-breaking rule, which cost function) are JSON objects passed to algorithm runners — not hardcoded.

**What code does:**
Code reads JSON, validates it against schemas, executes the rules it describes, and emits structured output. Code contains zero domain knowledge about what a "traffic zone" is — that lives in the schema.

**Why:**
This makes the system instantly extensible. A new cell type, a new robot behavior, a new cost model — none of them require touching algorithm logic. They require adding a JSON definition.

### 2.2 Component-driven methodology — frontend application

> Every UI element is a self-contained component. Components are composed, not tangled.

**What this means in practice:**
- Every visual element — the grid cell, the node in the 3D graph, the edge particle, the inspector panel, the algorithm toggle, the metric card — is defined as an independent component with explicit props and emitted events.
- No component queries global state directly except through a defined store interface.
- The 3D graph is itself a component. The node inspector is a component. They communicate only through the store — the graph fires a "node selected" event to the store; the inspector reads "selected node" from the store.
- Components do not contain simulation logic. They render data and emit user interactions.

**Why:**
This enforces the separation between what the simulation produces (data) and what the interface shows (rendered data). Swapping out the 3D renderer, adding a new inspector tab, or changing how edges animate never touches algorithm or simulation code.

---

## 3. High-level system topology

```
JSON City Profiles
        │
        ▼
┌─────────────────────────────────────────────────────┐
│            SIMULATION ENGINE  (Python)              │
│  Grid Builder → Cost Assigner → Event Bus           │
│  Robot State Machine → Algorithm Runner             │
│  Stack Trace Builder → Metrics Collector            │
└────────────────────┬────────────────────────────────┘
                     │  WebSocket  (structured JSON events)
                     ▼
┌─────────────────────────────────────────────────────┐
│           FRONTEND APPLICATION  (React + Three.js)  │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────┐  │
│  │  2D Grid     │  │  3D Node      │  │ Metrics  │  │
│  │  Viewer      │  │  Graph        │  │ Dashboard│  │
│  └──────────────┘  └───────────────┘  └──────────┘  │
│  ┌──────────────────────────────────────────────┐   │
│  │           Node Inspector Panel               │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │         Profile Manager + Playback Bar       │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 4. JSON schema design — simulation engine data layer

This section defines every JSON structure the simulation engine reads or produces. These schemas must be finalised before implementation begins. They are the contract between data and code.

### 4.1 City profile schema

A city profile is a complete, reproducible description of one simulation environment.

```
CityProfile {
  meta: {
    id: string                  // UUID
    name: string                // Human-readable e.g. "Downtown Grid Alpha"
    seed: integer               // RNG seed for reproducibility
    created_at: ISO8601 string
    version: string             // Schema version
  }

  grid: {
    width: 15
    height: 15
    cells: Cell[225]            // Row-major order, index = y*15 + x
  }

  robot: RobotConfig
  deliveries: DeliverySequence
  algorithms: AlgorithmConfig[]
}
```

### 4.2 Cell schema

```
Cell {
  id: string                    // "{x},{y}"
  x: integer
  y: integer
  type: CellType                // see CellType registry below
  cost: integer                 // Assigned at generation time within type range
  passable: boolean             // Derived from type but stored explicitly
  label: string | null          // Optional display label
  metadata: object              // Type-specific extra data
}
```

### 4.3 CellType registry (JSON, not enum in code)

```
CellTypeRegistry {
  road: {
    passable: true
    cost_range: [1, 5]
    color_token: "cell.road"
    display_name: "Road"
  }
  traffic_zone: {
    passable: true
    cost_range: [10, 20]
    color_token: "cell.traffic"
    display_name: "Traffic Zone"
  }
  obstacle: {
    passable: false
    cost_range: null
    color_token: "cell.obstacle"
    display_name: "Building / Obstacle"
  }
  delivery_point: {
    passable: true
    cost_range: [1, 5]
    color_token: "cell.delivery"
    display_name: "Delivery Location"
  }
  base_station: {
    passable: true
    cost_range: [1, 3]
    color_token: "cell.base"
    display_name: "Base Station"
  }
}
```

### 4.4 Robot config schema

```
RobotConfig {
  start: { x: integer, y: integer }
  movement: "cardinal" | "cardinal+diagonal"
  cost_model: "edge_cost" | "node_cost"
  tie_breaking: "first" | "lower_h" | "random"
}
```

### 4.5 Delivery sequence schema

```
DeliverySequence {
  count: 5
  destinations: [
    { id: "D1", x: integer, y: integer, label: string },
    ...
  ]
  order: "sequential"
}
```

### 4.6 Algorithm config schema

```
AlgorithmConfig {
  id: string                    // "bfs" | "dfs" | "ucs" | "greedy" | "astar"
  enabled: boolean
  heuristic: "manhattan" | "euclidean" | "none"
  weight: float                 // For weighted A* — default 1.0
  visualize: boolean            // Whether to emit step-level trace events
}
```

### 4.7 Stack trace event schema

This is the most critical schema in the system. Every node visited by an algorithm emits one TraceEvent. The 3D graph is built entirely from this stream.

```
TraceEvent {
  event_type: "node_visit" | "node_expand" | "path_found" | "path_step" | "delivery_complete"

  // Identity
  step: integer                 // Global step counter for this algorithm run
  timestamp_ms: float           // Wall-clock millisecond from run start
  algorithm_id: string

  // Node data (present on node_visit and node_expand)
  node: {
    id: string                  // "{x},{y}"
    x: integer
    y: integer
    cell_type: string
    g: float                    // Cost from start
    h: float                    // Heuristic estimate to goal
    f: float                    // g + h
    depth: integer              // Depth in search tree
    parent_id: string | null    // Parent node id in search tree
    status: "open" | "closed" | "path"
  }

  // Edge data (relationship to parent — drives edge rendering)
  edge: {
    from_id: string
    to_id: string
    edge_type: "expansion" | "path" | "backtrack"
    cost: float
  } | null

  // Frontier snapshot (optional, for frontier visualization)
  frontier_size: integer
  visited_count: integer
}
```

### 4.8 Metrics summary schema

Produced after each full delivery run per algorithm.

```
MetricsSummary {
  algorithm_id: string
  delivery_id: string
  path_cost: float
  execution_time_ms: float
  nodes_explored: integer
  path_length: integer          // Number of steps
  path_found: boolean
  path: [{ x: integer, y: integer }]
  heuristic_used: string
}
```

---

## 5. Simulation engine — component plan

### 5.1 GridBuilder

**Responsibility:** Consume a CityProfile JSON and produce a validated 15×15 grid with all cells assigned types and costs.

**Inputs:** `CityProfile` JSON

**Outputs:** Validated `Cell[225]` array

**Design notes:**
- All cost assignment uses the seed from the profile for reproducibility.
- Validates that base station and all delivery points are on passable cells.
- Validates that at least one path exists between base and each delivery point (connectivity check).
- Emits a `grid_ready` event to the event bus when complete.

### 5.2 EventBus

**Responsibility:** The central message broker of the simulation. All simulation components emit to it; all visualization consumers subscribe to it.

**Event types it carries:**
- `grid_ready`
- `delivery_assigned`
- `algorithm_start`
- `trace_event` (high-frequency — one per node visit)
- `delivery_complete`
- `simulation_complete`

**Design notes:**
- Must support WebSocket transport so the frontend can receive events in real time.
- Must buffer events for playback (the playback bar scrubs through the event log).
- Each event is a self-contained JSON object — no shared mutable state.

### 5.3 AlgorithmRunner

**Responsibility:** Execute one algorithm against one delivery task, emitting a `TraceEvent` for every node operation.

**Inputs:** Grid state, start position, goal position, `AlgorithmConfig` JSON

**Outputs:** Stream of `TraceEvent` objects → EventBus, final `MetricsSummary`

**Algorithms to implement:**

| Algorithm | Data Structure | Optimal? | Heuristic |
|-----------|---------------|----------|-----------|
| BFS | Queue (FIFO) | Yes (hop count) | None |
| DFS | Stack (LIFO) | No | None |
| UCS | Priority queue (by g) | Yes (cost) | None |
| Greedy BFS | Priority queue (by h) | No | Manhattan or Euclidean |
| A* | Priority queue (by f = g + h) | Yes (with admissible h) | Manhattan or Euclidean |

**Design notes:**
- All five share a common `run(grid, start, goal, config) → trace_stream` interface.
- The algorithm itself is selected by `config.id` — no if/else branches outside the runner dispatch table.
- TraceEvent emission is the only side effect. Algorithms are pure functions over grid state.

### 5.4 StackTraceBuilder

**Responsibility:** Consume TraceEvents and assemble a complete `TraceGraph` — a tree (or DAG in some cases) of node visits that can be serialised to JSON and consumed by the 3D graph renderer.

**Outputs:**
```
TraceGraph {
  algorithm_id: string
  delivery_id: string
  nodes: TraceNode[]
  edges: TraceEdge[]
  metadata: { total_steps, max_depth, max_g, max_f }
}
```

**Design notes:**
- The TraceGraph is the direct input to the 3D node graph component.
- It is emitted once per algorithm per delivery, but also updated incrementally during real-time mode so the graph grows live.

### 5.5 MetricsCollector

**Responsibility:** Wrap each AlgorithmRunner execution, measure wall-clock time, count nodes, accumulate path cost, and produce a `MetricsSummary`.

### 5.6 ProfileManager

**Responsibility:** Load, validate, save, and list city profiles. Supports named presets. Generates new profiles from a seed.

**Preset profiles to ship:**
- `default_grid` — standard layout as per the assignment brief
- `dense_city` — high obstacle density, narrow corridors
- `traffic_heavy` — most road cells are traffic zones
- `open_grid` — minimal obstacles, pure cost comparison
- `random_{seed}` — generated on demand

---

## 6. Frontend application — component plan

### 6.1 Application shell

The shell provides the layout frame: a top navigation bar, a left sidebar for profile/algorithm controls, and a main content area that renders whichever of the three primary views is active. The shell owns the global state store.

**Global store slices:**
- `simulation` — current profile, grid state, robot position, delivery queue
- `algorithms` — enabled algorithms, their configs, their current run status
- `traceGraph` — the live/completed TraceGraph for each algorithm
- `selectedNode` — the node currently open in the inspector panel
- `playback` — event log cursor, play/pause/speed state
- `metrics` — MetricsSummary array for the current session

### 6.2 Profile manager panel

A sidebar panel for selecting, loading, and configuring city profiles.

**Sub-components:**
- `ProfileCard` — displays profile name, seed, obstacle density, traffic density
- `ProfileSelector` — dropdown or list of available profiles
- `SeedInput` — numeric input to generate a random profile from seed
- `AlgorithmToggleRow` — enable/disable individual algorithms and set heuristic per algorithm
- `RunButton` — triggers simulation start

### 6.3 2D grid viewer

A live, animated top-down map of the 15×15 grid showing cell types, robot position, and planned path.

**Sub-components:**

| Component | Responsibility |
|-----------|---------------|
| `GridCanvas` | Renders all 225 cells as a scaled grid. Owner of the canvas or SVG element. |
| `GridCell` | Renders one cell — color from cell type token, cost label, highlight state. |
| `RobotSprite` | Animated robot marker. Moves along the path step by step. |
| `PathOverlay` | Draws the current planned path as a line over the grid. |
| `CellTooltip` | On hover — shows cell type, cost, coordinates. |
| `LegendStrip` | Color key for cell types at the bottom of the viewer. |

**Design notes:**
- Cell color tokens come from the CellTypeRegistry JSON — the component never hardcodes colors.
- During a live run, the path overlay updates with each `trace_event` received from the bus.
- Clicking a cell opens it in the Node Inspector Panel if it is part of the current trace.

### 6.4 3D node graph — the centrepiece

The 3D graph renders the `TraceGraph` as an interactive three-dimensional scene. This is the Foundry-inspired visualisation.

#### 6.4.1 Conceptual layout

The search tree is laid out in 3D space according to these axis conventions:

- **X axis** — spatial X position of the grid cell (mirrors the map)
- **Y axis** — depth in the search tree (deeper = higher up in the scene)
- **Z axis** — spatial Y position of the grid cell (mirrors the map)

This means the 3D graph is literally the search tree "growing upward" from the grid plane. At depth 0 sits the start node. At the maximum depth sits the goal. Branches are the paths the algorithm considered.

#### 6.4.2 Node types and visual encoding

Every node in the graph has a `node_type` that determines its shape, color, and size.

| Node type | Condition | Shape | Color |
|-----------|-----------|-------|-------|
| `start` | Depth 0, root | Large sphere | Teal |
| `goal` | Matches delivery destination | Large sphere | Amber |
| `path_node` | On the final returned path | Medium sphere | Green |
| `expanded` | Was expanded (popped from frontier) | Medium sphere | Purple |
| `visited` | Was visited but not expanded | Small sphere | Gray |
| `pruned` | Was generated but never visited | Tiny sphere | Coral, low opacity |
| `frontier` | Currently on frontier (live mode) | Pulsing sphere | Blue |

Node size additionally encodes `g` cost — higher cost nodes are slightly larger.

#### 6.4.3 Edge types and animated particles

Every edge between two nodes has a `edge_type` that determines its visual treatment. Edges carry **animated dot particles** moving along them in real time. Particle type, color, and speed encode the edge's semantic role.

| Edge type | Meaning | Line style | Particle color | Particle speed |
|-----------|---------|-----------|---------------|---------------|
| `expansion` | Parent expanded to reveal child | Solid thin | Gray | Slow |
| `path` | Final optimal path edge | Solid thick | Green | Fast |
| `backtrack` | DFS backtrack edge | Dashed | Coral | Medium |
| `g_update` | Node re-queued with lower g (A*) | Dotted | Amber | Fast pulse |

Multiple particles travel along each edge simultaneously. The density of particles on a path edge is proportional to how many times that edge was traversed during the search.

#### 6.4.4 Graph interaction model

The graph is a fully interactive 3D canvas.

**Camera controls:**
- **Rotate** — left-click drag orbits the camera around the scene centre
- **Zoom** — scroll wheel or pinch-to-zoom
- **Pan** — right-click drag or two-finger drag
- **Reset view** — double-click on empty space resets to the default isometric angle
- **Stretch axes** — axis stretch sliders in the toolbar allow the user to exaggerate the Y axis (depth) or X/Z axes independently to better distinguish levels

**Node interaction:**
- **Hover** — displays a mini tooltip: node ID, type, g/h/f values, depth
- **Click** — selects the node and opens the Node Inspector Panel
- **Highlight path to root** — clicking a node highlights the chain of edges from that node back to the start, tracing its ancestry through the search tree
- **Focus mode** — double-clicking a node zooms the camera to center on it and dims all non-adjacent nodes

**Graph filtering toolbar:**
- Toggle visibility by node type (e.g. hide all `visited` nodes to see only the path)
- Toggle visibility by depth range (slider from 0 to max_depth)
- Toggle particle animation on/off
- Switch between algorithms (shows one TraceGraph at a time, or overlays two)

#### 6.4.5 3D graph sub-components

| Component | Responsibility |
|-----------|---------------|
| `GraphCanvas3D` | Owns the Three.js scene, camera, renderer, and animation loop |
| `NodeMesh` | Renders one node as a 3D sphere with type-driven material |
| `EdgeLine` | Renders one edge as a 3D line with type-driven style |
| `EdgeParticleSystem` | Manages animated dot particles along all edges in the scene |
| `GraphCameraController` | Handles orbit, zoom, pan, and reset |
| `AxisStretchControls` | UI sliders that scale the scene along each axis |
| `GraphFilterToolbar` | Toggles for node type visibility and depth range |
| `NodeTooltip3D` | Billboard-style tooltip that follows hovered nodes |
| `AlgorithmLayerSwitcher` | Tabs to switch which algorithm's trace is displayed |

### 6.5 Node inspector panel

Inspired directly by Palantir Foundry's Object Inspector. Opens as a right-side panel when any node is selected — in either the 2D grid view or the 3D graph.

**Panel sections:**

**Identity section**
- Node ID (grid coordinate)
- Node type badge (color-coded)
- Algorithm that produced this node
- Step number when this node was visited

**Search values section**
- `g` — cost from start to this node
- `h` — heuristic estimate to goal
- `f` — total estimated cost (g + h)
- Depth in search tree
- Parent node ID (clickable — selects parent)

**Cell data section**
- Grid cell type
- Assigned traversal cost
- Map coordinates (x, y)
- Whether cell is on final path

**Ancestry chain section**
- Collapsible list of all ancestors from root to this node
- Each entry shows step number, node ID, and g cost at that point
- Clicking any ancestor selects it

**Adjacent nodes section**
- All neighbors of this cell
- For each: node ID, passable, cost, whether visited, whether on path

**Raw trace data section**
- Collapsible raw JSON of the `TraceEvent` that produced this node
- Allows full inspection for debugging

### 6.6 Metrics dashboard

A tabbed panel showing algorithm performance comparison.

**Sub-components:**

| Component | Responsibility |
|-----------|---------------|
| `MetricsTable` | Row per algorithm, columns for cost, time, nodes, path length |
| `CostBarChart` | Grouped bars comparing path cost per delivery per algorithm |
| `NodesExploredChart` | Line chart showing node count growth during search |
| `TimeComparisonCard` | Execution time comparison with percentage deltas |
| `PathQualityBadge` | Flags optimal vs suboptimal paths per algorithm |
| `DeliverySelector` | Tabs to switch between delivery 1–5 results |

### 6.7 Playback bar

A timeline control at the bottom of the application for stepping through a completed simulation.

**Controls:**
- Play / Pause
- Step forward / Step back (one TraceEvent at a time)
- Speed selector (0.5×, 1×, 2×, 5×, instant)
- Scrub slider (jump to any point in the event log)
- Delivery marker indicators on the timeline (shows when each delivery started and completed)

**Design notes:**
- In playback mode, the 2D grid viewer, 3D graph, and metrics dashboard all respond to the playback cursor — they show the state of the simulation at that moment in time.
- Playback state is in the global store so all components stay synchronised without direct communication.

### 6.8 Export module

Allows the user to export simulation artifacts.

**Exports:**
- Full `TraceGraph` as JSON (for offline analysis)
- `MetricsSummary` array as CSV
- City profile JSON (to share or reload)
- Screenshot of the current 3D graph view

---

## 7. Heuristic design

Both heuristics will be implemented and selectable per algorithm run via the `AlgorithmConfig` JSON.

**Manhattan distance:**
`h(n) = |n.x - goal.x| + |n.y - goal.y|`
Admissible for cardinal-movement grids. Preferred for this grid since the robot moves in four directions.

**Euclidean distance:**
`h(n) = sqrt((n.x - goal.x)² + (n.y - goal.y)²)`
Always ≤ true cost for cardinal grids, so also admissible. Less tight than Manhattan. Produces slightly different A* behavior worth visualising.

**Heuristic comparison mode:**
The metrics dashboard will support running A* twice on the same delivery — once with each heuristic — and showing the side-by-side trace in the 3D graph as two overlapping trees rendered in different opacity.

---

## 8. What is not in the assignment brief but must be designed

### 8.1 Stack trace schema (critical — design before coding)

The assignment mentions nothing about a stack trace. The schema in Section 4.7 must be agreed upon and frozen before any algorithm is implemented. Every subsequent component depends on it.

### 8.2 Profile system

The assignment implies a single random environment. The profile system adds reproducibility, shareability, and preset scenarios. Without it, the simulator cannot be compared fairly across runs.

### 8.3 Heuristic toggle

The brief mentions both heuristics but does not specify when each is used. The plan requires an explicit per-algorithm config switch.

### 8.4 Dynamic traffic

The current plan uses static costs assigned at generation time. A future extension (not in scope for v1 but worth designing for) would re-randomise traffic zone costs between deliveries, simulating real-time traffic fluctuation. The event bus design supports this without changes to algorithm code.

### 8.5 Multi-algorithm overlay in 3D graph

Running all five algorithms against the same delivery and overlaying their trace graphs in the 3D scene simultaneously is visually powerful and analytically compelling. This is an extension to plan for but implement after single-algorithm rendering is stable.

### 8.6 Accessibility of the 3D graph

The 3D graph should offer a 2D fallback view (the search tree rendered as a flat hierarchical diagram) for environments where WebGL is unavailable or for users who prefer it.

---

## 9. Technology selections (plan-level, not final)

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Simulation engine | Python 3.11+ | Standard for AI coursework, fast enough for this grid scale |
| JSON schema validation | `jsonschema` (Python) | Validates all JSON inputs against defined schemas at load time |
| WebSocket transport | `websockets` (Python) | Streams TraceEvents to frontend in real time |
| Frontend framework | React 18 | Component-driven, hooks for store integration |
| Global state | Zustand | Minimal, does not require wrapping components in providers |
| 3D rendering | Three.js | The only viable browser-native 3D scene graph for this use case |
| 2D grid viewer | React + SVG or Canvas API | Simple enough not to need a library |
| Charts | Recharts | React-native, composable |
| Styling | Tailwind CSS utility classes | Enforces design consistency |

---

## 10. Development phases

### Phase 1 — Foundation
Finalise all JSON schemas. Implement GridBuilder and ProfileManager. Write schema validation. Generate and validate two city profiles manually. No algorithms yet.

### Phase 2 — Algorithm engine
Implement all five algorithms against the frozen TraceEvent schema. Each algorithm emits events but nothing renders them yet — validate output by reading the JSON directly. Implement MetricsCollector. Run all five on a test profile, compare MetricsSummary outputs.

### Phase 3 — 2D viewer
Build the GridCanvas and GridCell components. Connect to the EventBus. Animate robot movement. Verify the simulation looks correct visually before touching 3D.

### Phase 4 — 3D graph core
Build GraphCanvas3D, NodeMesh, EdgeLine. Consume a static TraceGraph JSON and render it. No animation, no interaction. Verify the tree layout is correct and readable.

### Phase 5 — 3D graph interaction
Add EdgeParticleSystem, GraphCameraController, NodeTooltip3D, AxisStretchControls, GraphFilterToolbar. Make nodes clickable. Connect to NodeInspectorPanel.

### Phase 6 — Dashboard and playback
Build MetricsDashboard components. Build PlaybackBar. Connect playback cursor to all three views so they all respond to scrubbing.

### Phase 7 — Profile manager and export
Build ProfileManagerPanel, ProfileSelector, SeedInput, RunButton. Build ExportModule. End-to-end test: load a profile, run all five algorithms, inspect nodes, export results.

### Phase 8 — Polish and comparison modes
Heuristic comparison overlay in 3D graph. Multi-algorithm side-by-side metrics. Preset profiles. Performance profiling on large trace graphs. Accessibility 2D fallback.

---

## 11. Open decisions (must be resolved before implementation)

| Decision | Options | Recommended |
|----------|---------|-------------|
| WebSocket vs REST polling for trace events | WebSocket (real-time) vs HTTP streaming | WebSocket |
| 3D layout algorithm for trace graph | Depth-layer + grid-position vs force-directed | Depth-layer + grid-position |
| How many particles per edge | Fixed count vs proportional to edge weight | Proportional |
| Inspector panel position | Right side drawer vs floating panel | Right side drawer |
| What happens to 3D graph between deliveries | Clear and rebuild vs accumulate all deliveries | Clear and rebuild, with option to overlay |
| Heuristic for Greedy BFS default | Manhattan vs Euclidean | Manhattan |
| Robot movement — cardinal only or diagonal | Cardinal only vs cardinal + diagonal | Cardinal only (matches assignment) |
| Persistence of city profiles | JSON files on disk vs browser localStorage | JSON files (for portability) |

---

*End of plan.*
