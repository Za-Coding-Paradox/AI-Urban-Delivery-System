# Positron — Urban Delivery Simulator

> A real-time AI search algorithm simulator for urban robot delivery. Watch BFS, DFS, UCS, Greedy, and A\* navigate a city grid — simultaneously — with step-by-step playback, a 3D trace graph, and a full benchmarking dashboard.

---

## What It Does

Positron simulates a delivery robot navigating a 15×15 urban grid to reach five sequential delivery destinations. Five search algorithms run in parallel against the same city layout. Every node visit, expansion, and path decision is streamed live to the frontend as a structured trace event, where it is rendered in real time across a 2D grid, a 3D interactive node graph, and a performance metrics panel.

The simulation is fully profile-driven — city layouts, obstacle density, traffic zones, robot behavior, and algorithm configurations are all defined in JSON. No hardcoded environments.

---

## Screenshots

> 2D Grid · 3D Search Tree · Metrics Dashboard · Node Inspector

*(Screenshots go here — run the simulator and use the browser screenshot tool.)*

---

## Features

- **Five search algorithms** — BFS, DFS, UCS, Greedy Best-First, A★
- **Heuristics** — Manhattan distance, Euclidean distance, or none (zero heuristic / null-object pattern)
- **Real-time 2D grid** — color-coded visited cells, frontier expansion, final path overlay, animated robot sprite
- **3D interactive search tree** — each node is a typed, inspectable object; edges carry directionality and type; the graph is rotatable and zoomable
- **Per-algorithm per-delivery segmented playback** — scrub through any algorithm's trace for any delivery independently
- **Metrics dashboard** — path cost, execution time ms, nodes explored, path length, per-algorithm comparison charts
- **City profiles** — four built-in profiles (alpha, roundtrip, dense\_city, open\_grid) plus seed-based generation and save/load
- **Node inspector** — Foundry-style inspector panel showing g, h, f, depth, parent, cell type for any selected node
- **REST + WebSocket API** — full server API for external tooling, curl testing, or building your own frontend

---

## Architecture in 30 Seconds

```
JSON City Profile
      │
      ▼
Python Backend (FastAPI + uvicorn)
  GridBuilder → EventBus → RunController
  AlgorithmRunners (BFS/DFS/UCS/Greedy/A★)
  TraceBuilder → MetricsCollector
      │
      │  WebSocket (structured JSON TraceEvents)
      ▼
React Frontend (Vite + TypeScript)
  useWebSocket → Zustand Store (ingestEvent)
  ├── events[]              ← flat buffer, global playback cursor
  └── eventsBySegment{}     ← keyed by "algo:deliveryId"
      │
      ├── GridView (2D canvas)
      ├── GraphView (Three.js 3D)
      ├── PlaybackBar (segment-aware scrubber)
      ├── MetricsView (Recharts)
      └── NodeInspectorPanel
```

---

## Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| pnpm | any recent |

### One-command setup (Linux / macOS)

```bash
bash setup.sh --dev
```

### One-command setup (Windows)

```bat
setup.bat dev
```

Both scripts install all dependencies, generate default city profiles, run the test suite, and offer to launch both servers automatically.

### Manual setup

```bash
# 1. Clone
git clone <repo-url>
cd AI-Urban-Delivery-System

# 2. Python environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# 3. Generate default profiles
export PYTHONPATH=$PWD
python -c "
from backend.engine.profile_manager import ProfileManager
mgr = ProfileManager()
for seed, name in [(1,'alpha'),(42,'roundtrip'),(7,'dense_city'),(100,'open_grid')]:
    mgr.save(mgr.generate(seed, name), name)
"

# 4. Start backend
uvicorn backend.websocket.web_server:app --reload --port 8000

# 5. In a second terminal — frontend
cd frontend
pnpm install
pnpm dev
```

Open **http://localhost:5173** in your browser.

---

## Running with Docker

```bash
# Build and run
docker build -t positron .
docker run -p 8000:8000 positron

# Open http://localhost:8000
```

The Docker build produces a single container serving both the frontend and backend on port 8000.

---

## Project Structure

```
AI-Urban-Delivery-System/
├── backend/
│   ├── algorithms/          # BFS, DFS, UCS, Greedy, A★ runners + base class
│   ├── common/              # Grid constants
│   ├── engine/              # EventBus, GridBuilder, ProfileManager
│   ├── heuristics/          # Manhattan, Euclidean, zero heuristics
│   ├── profiles/            # Saved city profile JSON files
│   ├── schemas/             # JSON Schema definitions for all data types
│   ├── tests/               # Full pytest test suite
│   ├── trace/               # StackTraceBuilder
│   ├── websocket/           # FastAPI app, RunController, WebSocket server
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── controls/    # PlaybackBar, ProfilePanel
│       │   ├── graph/       # GraphView (Three.js)
│       │   ├── grid/        # GridView (Canvas)
│       │   ├── inspector/   # NodeInspectorPanel
│       │   ├── metrics/     # MetricsView
│       │   └── shared/      # StatusBar
│       ├── hooks/           # useWebSocket, useSimulation
│       ├── lib/             # API client, constants, utilities
│       ├── store/           # Zustand store with dual-index event system
│       └── types/           # TypeScript type definitions
├── docs/                    # Planning documents
├── Dockerfile
├── setup.sh
└── setup.bat
```

---

## API Reference

The backend exposes a REST API alongside the WebSocket stream.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Server status, connected clients, buffer size |
| GET | `/profiles` | List all saved profiles |
| GET | `/profiles/{name}` | Load a profile by name |
| POST | `/profiles/generate` | Generate a profile from a seed |
| POST | `/profiles/{name}/save` | Save a profile |
| POST | `/run` | Start a simulation run |
| GET | `/run/{id}/status` | Poll run status |
| GET | `/run/{id}/results` | Fetch full results after completion |
| POST | `/run/{id}/replay` | Replay events to all connected clients |
| GET | `/bus/buffer` | Inspect raw event buffer (paginated) |
| WS | `/ws/{client_id}` | Real-time event stream |

### Example: start a run with curl

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"profile_name": "alpha"}'
```

### WebSocket messages (client → server)

```json
{ "type": "ping" }
{ "type": "status" }
{ "type": "replay", "run_id": "...", "event_type": "*" }
```

---

## City Profiles

A city profile is a JSON document that fully describes one simulation scenario. It specifies the grid layout (all 225 cells with their types, costs, and passability), the robot configuration (start position, movement type, cost model), the delivery sequence (up to 5 destinations), and the algorithm configuration (which algorithms run and with what heuristics).

Profiles are generated from a numeric seed for reproducibility, validated against JSON Schema, and saved to `backend/profiles/`. They can be loaded by name or submitted inline to the `/run` endpoint.

Built-in profiles:

| Profile | Seed | Character |
|---------|------|-----------|
| alpha | 1 | Balanced, moderate obstacles |
| roundtrip | 42 | Deliveries form a loop |
| dense\_city | 7 | High obstacle density |
| open\_grid | 100 | Minimal obstacles, lots of traffic zones |

---

## Running Tests

```bash
source .venv/bin/activate
export PYTHONPATH=$PWD
pytest backend/tests/ -v
```

Test coverage includes: all five algorithm runners, EventBus publish/subscribe/replay, GridBuilder connectivity validation, ProfileManager generate/save/load, StackTraceBuilder, and WebSocket server endpoints via httpx async client.

---

## Tech Stack

**Backend:** Python 3.11 · FastAPI · uvicorn · asyncio · ThreadPoolExecutor · Pydantic v2 · jsonschema · pytest · ruff

**Frontend:** React 18 · TypeScript · Vite · Zustand 5 · Three.js · @react-three/fiber · @react-three/drei · Recharts · Tailwind CSS v4 · reconnecting-websocket

---

## License

MIT — see [LICENSE.MD](LICENSE.MD)

---

## Contributing

See [CONTRIBUTING.MD](CONTRIBUTING.MD)
