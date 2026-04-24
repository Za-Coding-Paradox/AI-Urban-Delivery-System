# Changelog

All notable changes to Positron will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Diagonal movement support (8-directional robot navigation)
- Custom cell type definitions via `cell_type_registry.json`
- Export simulation results as CSV / JSON
- Shareable profile URLs (seed encoded in query string)
- Multi-robot support with independent base stations

---

## [0.1.0] — 2026-04-25

### Added
- **Five search algorithms** — BFS, DFS, UCS, Greedy Best-First, A★ — all implemented as `BaseRunner` subclasses sharing a common search loop
- **Profile-driven simulation** — city layouts, robot config, delivery sequences, and algorithm configs are all JSON. No hardcoded environments.
- **ProfileManager** — generate, save, load, and list city profiles. Generates via seed with BFS connectivity validation (retries until all delivery points are reachable)
- **Four built-in profiles** — `alpha` (seed 1), `roundtrip` (seed 42), `dense_city` (seed 7), `open_grid` (seed 100)
- **EventBus** — pub/sub message broker with replay buffer. Supports synchronous and async handlers, wildcard subscriptions, and WebSocket connection management
- **RunController** — orchestrates full simulation runs (all algorithms × all deliveries × sequential execution)
- **StackTraceBuilder** — subscribes to EventBus and builds 3D TraceGraph objects per algorithm/delivery pair
- **FastAPI WebSocket server** — REST API + real-time WebSocket event stream with async/thread bridge via `asyncio.Queue`
- **Dual-indexed event store (Zustand)** — flat buffer for global playback, segment map keyed `"algo:deliveryId"` for O(1) per-pair access
- **Segment-aware PlaybackBar** — scrubber operates in segment space; `segmentFlatIndices` array translates between segment and flat coordinate spaces via binary search
- **2D GridView** — canvas-based grid renderer with color-coded visited, frontier, path cells, and animated robot sprite
- **3D GraphView** — Three.js interactive search tree with typed nodes and directed edges
- **MetricsView** — Recharts comparison dashboard (path cost, execution time, nodes explored, path length)
- **NodeInspectorPanel** — Foundry-inspired inspector showing g, h, f, depth, parent, cell type for selected nodes
- **StatusBar** — total event count, connection status, run status
- **ProfilePanel** — profile selector, seed-based generation, algorithm toggles
- **JSON Schema validation** — all data types (Cell, CityProfile, AlgorithmConfig, RobotConfig, TraceEvent, MetricsSummary) validated against schemas
- **Full pytest test suite** — algorithms, EventBus, GridBuilder, heuristics, ProfileManager, StackTraceBuilder, WebSocket endpoints
- **Multi-stage Dockerfile** — Node builds frontend, Python serves everything on port 8000
- **setup.sh** — full Linux/macOS setup with `--dev`, `--prod`, `--docker`, `--clean`, `--fresh` modes
- **setup.bat** — full Windows setup with equivalent modes

### Fixed
- `PlaybackBar`: `store = useStore()` returned state object, not store instance. Changed to `useStore` (no call) so `.getState()` is accessible in interval callbacks
- `PlaybackBar`: stale `total === 0` guard in `useEffect` prevented interval creation when clicking Play before events arrived. Guard moved inside interval callback using live `store.getState()`
- `PlaybackBar`: clicking Play at `segmentCursor === 0` appeared frozen because the flat cursor was still in the pre-segment lifecycle event zone. Play now jumps flat cursor to `segmentFlatIndices[0]` before starting the interval
- `PlaybackBar`: scrubber thumb and fill bar operated in different coordinate spaces (flat vs segment). Slider now operates entirely in segment space; `segmentFlatIndices[n-1]` translates back to flat on change
- `PlaybackBar`: `segmentTotal` and `segmentCursor` computed via two separate O(n) scans. Replaced with single O(n) `segmentFlatIndices` build + O(log n) binary search for cursor

### Technical Notes
- Algorithms run synchronously in `ThreadPoolExecutor` (CPU-bound; async adds no benefit)
- Async/thread bridge uses `asyncio.Queue` + `loop.call_soon_threadsafe()` to forward events from algorithm threads to WebSocket broadcaster
- Sequential delivery execution preserves deterministic event buffer ordering (required for playback correctness)
- Single worker (`--workers 1`) required in production — EventBus, active runs, and WS clients are in-process singletons
