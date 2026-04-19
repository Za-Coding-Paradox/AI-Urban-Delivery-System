# backend/websocket/server.py
#
# The simulation server. Two faces:
#
#   REST face  — standard HTTP endpoints for profile management and run control.
#                Stateless request/response. Easy to call from Postman or curl.
#
#   WebSocket face — a persistent connection the frontend holds open.
#                   Receives every EventBus event in real time as JSON.
#                   Powers the live 2D grid animation and 3D graph growth.
#
# ── the async/sync bridge problem ─────────────────────────────────────────────
# This is the hardest engineering problem in this file. Here is the full
# explanation:
#
#   Algorithms run synchronously in a ThreadPoolExecutor.
#   They call bus.publish() from that thread.
#   WebSocket sends (await ws.send_json()) are coroutines that must run
#   on the async event loop.
#   You CANNOT await inside a regular thread — the two worlds do not mix.
#
# Solution: asyncio.Queue as a thread-safe hand-off point.
#
#   Thread side:  loop.call_soon_threadsafe(queue.put_nowait, event)
#                 This schedules the put on the event loop thread-safely.
#                 It returns immediately — the thread is never blocked.
#
#   Async side:   A long-running broadcast_task() awaits queue.get() in a loop.
#                 When an event arrives, it sends to all connected WS clients.
#
# This pattern decouples algorithm speed from client speed.
# A slow client queues up rather than stalling the algorithm.
# If the queue grows unbounded (client never reads), we cap it.
#
# ── connection management ──────────────────────────────────────────────────────
# Connected WebSocket clients are stored in a module-level set.
# When a client disconnects (WebSocketDisconnect), it is removed.
# Dead connections are also pruned during broadcast attempts.
# This is correct for a single-server simulator. For multi-server
# deployments, you would replace the set with a Redis pub/sub channel.
#
# ── run management ─────────────────────────────────────────────────────────────
# Active runs are tracked in a dict: run_id → RunController.
# The /run endpoint starts a run in the ThreadPoolExecutor and returns
# the run_id immediately. The frontend subscribes to the WS to receive
# events as the run progresses.

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.engine.event_bus import EventBus
from backend.engine.profile_manager import ProfileManager, ProfileManagerError
from backend.websocket.run_controller import RunController, RunResult, RunStatus

# ── application setup ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Urban Delivery Robot — Simulation Server",
    description=(
        "REST + WebSocket API for the AI search algorithm simulator. "
        "Load city profiles, start simulation runs, and receive live "
        "TraceEvents via WebSocket for real-time 3D graph rendering."
    ),
    version="1.0.0",
)

# Allow the React frontend (running on a different port) to call this server.
# In development the frontend is typically on localhost:5173 (Vite default).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── module-level shared state ──────────────────────────────────────────────────
# These are singletons for the lifetime of the server process.
# FastAPI's lifespan events (startup/shutdown) initialise and tear them down.
#
# Why module-level and not class attributes?
# FastAPI is function-based. Dependency injection with Depends() is the
# idiomatic pattern, but for a simulator with a single global EventBus,
# module-level singletons are simpler and more readable. A production
# service would use Depends() and a proper DI container.

_bus: EventBus | None = None
_event_queue: asyncio.Queue | None = None
_loop: asyncio.AbstractEventLoop | None = None
_executor: ThreadPoolExecutor | None = None
_profile_mgr: ProfileManager | None = None
_ws_clients: set[WebSocket] = set()
_active_runs: dict[str, RunController] = {}
_run_results: dict[str, RunResult] = {}


# ── lifespan ───────────────────────────────────────────────────────────────────
# FastAPI's lifespan replaces the deprecated @app.on_event("startup") pattern.
# Everything inside the try block runs at startup, after the yield at shutdown.

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Startup: initialise all singletons and start the background broadcaster.
    Shutdown: cancel the broadcaster, drain the queue, shut down the executor.
    """
    global _bus, _event_queue, _loop, _executor, _profile_mgr

    # Guard: only initialise singletons that are still None.
    # Tests pre-inject their own instances (fresh EventBus, tmp_path
    # ProfileManager) via the reset_server_state fixture BEFORE the
    # TestClient enters this lifespan. Unconditionally overwriting here
    # would discard the injected values and break test isolation.
    # In production every singleton starts as None so the full block runs.
    _loop = asyncio.get_event_loop()
    if _bus is None:
        _bus = EventBus()
    if _event_queue is None:
        _event_queue = asyncio.Queue(maxsize=10_000)
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sim-worker")
    if _profile_mgr is None:
        _profile_mgr = ProfileManager()

    # Subscribe the async bridge to the EventBus.
    # Every event published to the bus also gets enqueued for WS broadcast.
    # This runs synchronously inside algorithm threads — it is fast (just
    # schedules a put on the event loop) so it does not slow the algorithm.
    def _sync_bridge(event: dict) -> None:
        """
        Called synchronously by EventBus.publish() from any thread.
        Bridges to the async broadcast_task via thread-safe queue put.

        loop.call_soon_threadsafe is the ONLY correct way to communicate
        from a worker thread to the async event loop. Never use
        asyncio.run() or loop.run_until_complete() from inside a thread
        that is itself running inside an event loop — that deadlocks.
        """
        if _loop and not _loop.is_closed():
            _loop.call_soon_threadsafe(_event_queue.put_nowait, event)

    _bus.subscribe_all(_sync_bridge)

    # Start the background task that drains the queue to WS clients
    broadcaster = asyncio.create_task(_broadcast_task(), name="ws-broadcaster")

    yield  # ← server is running here

    # Shutdown
    broadcaster.cancel()
    try:
        await broadcaster
    except asyncio.CancelledError:
        pass

    _executor.shutdown(wait=False)


app.router.lifespan_context = lifespan


# ── WebSocket broadcaster (async background task) ──────────────────────────────


async def _broadcast_task() -> None:
    """
    Long-running coroutine that drains the event queue and sends
    each event to all connected WebSocket clients.

    Dead connections (disconnected clients) are detected during send
    and pruned from the set. Using a copy of the set for iteration
    prevents "set changed size during iteration" RuntimeError.

    Why not broadcast directly inside _sync_bridge?
    Because _sync_bridge is called from a thread — it cannot await.
    The queue is the required intermediary.

    ── why `global _ws_clients` is required here ────────────────────────
    Python scoping rule: if a name appears on the LEFT side of ANY
    assignment inside a function — including augmented assignment like
    `-=` — Python treats that name as LOCAL throughout the entire
    function, even for reads that precede the assignment.

    `_ws_clients -= dead` is augmented assignment (__isub__). Without
    the `global` declaration, Python marks `_ws_clients` as local. The
    earlier `if not _ws_clients:` then tries to read a local that has
    never been assigned — UnboundLocalError. Always declare `global` for
    module-level mutable variables you intend to mutate from a function.
    """
    global _ws_clients, _event_queue

    while True:
        try:
            event = await _event_queue.get()
        except asyncio.CancelledError:
            break

        if not _ws_clients:
            continue

        dead: set = set()

        for ws in list(_ws_clients):
            try:
                await ws.send_json(event)
            except Exception:
                # Client disconnected or errored — mark for removal
                dead.add(ws)

        _ws_clients -= dead


# ── request / response models (Pydantic) ───────────────────────────────────────
# Pydantic models document the API contract and provide automatic validation.
# FastAPI uses them to generate the /docs OpenAPI spec for free.


class GenerateProfileRequest(BaseModel):
    seed: int
    name: str | None = None


class RunRequest(BaseModel):
    profile_name: str | None = None
    profile: dict | None = None  # inline profile (alternative to name)
    algorithm_ids: list[str] | None = None  # override enabled algorithms


class ReplayRequest(BaseModel):
    run_id: str
    event_type: str = "*"


# ── REST endpoints ─────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    """
    Simple health check. Returns server status and connected client count.
    Use this to verify the server is running before starting the frontend.
    """
    return {
        "status": "ok",
        "ws_clients": len(_ws_clients),
        "active_runs": len(_active_runs),
        "bus_buffer_size": _bus.buffer_size() if _bus else 0,
    }


@app.get("/profiles")
async def list_profiles() -> dict:
    """
    Lists all saved city profiles by name.
    Returns names only — use GET /profiles/{name} to load a full profile.
    """
    return {"profiles": _profile_mgr.list()}


@app.get("/profiles/{name}")
async def get_profile(name: str) -> dict:
    """
    Loads a city profile by name and returns it as JSON.
    Raises 404 if the profile does not exist.
    """
    try:
        profile = _profile_mgr.load(name)
        return {"profile": profile}
    except ProfileManagerError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})


@app.post("/profiles/generate")
async def generate_profile(request: GenerateProfileRequest) -> dict:
    """
    Generates a new city profile from a seed and returns it.
    Does NOT save it — use POST /profiles/{name}/save to persist.

    This design separates generation from persistence:
    you can generate, inspect, tweak, and save only if you like the result.
    """
    loop = asyncio.get_event_loop()
    try:
        # ProfileManager.generate() calls GridBuilder.build() for connectivity
        # check — it is CPU-bound. Run in executor to avoid blocking the loop.
        profile = await loop.run_in_executor(
            _executor,
            lambda: _profile_mgr.generate(request.seed, request.name),
        )
        return {"profile": profile}
    except ProfileManagerError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


@app.post("/profiles/{name}/save")
async def save_profile(name: str, body: dict) -> dict:
    """
    Saves a profile dict (from the request body) with the given name.
    Validates the profile against city_profile.schema.json before saving.
    """
    try:
        profile = body.get("profile", body)
        path = _profile_mgr.save(profile, name)
        return {"saved": name, "path": str(path)}
    except ProfileManagerError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


@app.post("/run")
async def start_run(request: RunRequest) -> dict:
    """
    Starts a full simulation run and returns a run_id immediately.

    The run executes asynchronously in the ThreadPoolExecutor.
    Connect to WebSocket /ws/{client_id} to receive live events.
    Poll GET /run/{run_id}/status to check completion.
    Fetch GET /run/{run_id}/results after completion for full metrics.

    Profile resolution order:
      1. Inline profile in request body (request.profile)
      2. Named profile from disk (request.profile_name)
    At least one must be provided.
    """
    # ── resolve the profile ────────────────────────────────────────────────────
    if request.profile:
        profile = request.profile
        profile_name = profile.get("meta", {}).get("name", "inline")
    elif request.profile_name:
        try:
            profile = _profile_mgr.load(request.profile_name)
            profile_name = request.profile_name
        except ProfileManagerError as e:
            return JSONResponse(status_code=404, content={"error": str(e)})
    else:
        return JSONResponse(
            status_code=422,
            content={"error": "Provide either 'profile_name' or 'profile' in the request body."},
        )

    # ── override enabled algorithms if specified ───────────────────────────────
    if request.algorithm_ids:
        for algo_cfg in profile.get("algorithms", []):
            algo_cfg["enabled"] = algo_cfg["id"] in request.algorithm_ids

    # ── create and launch the run ──────────────────────────────────────────────
    run_id = str(uuid.uuid4())
    controller = RunController(
        profile=profile,
        bus=_bus,
        run_id=run_id,
        profile_name=profile_name,
    )

    _active_runs[run_id] = controller

    # Launch in executor — non-blocking, run proceeds in background thread
    loop = asyncio.get_event_loop()

    async def _execute_and_store():
        """Wrapper coroutine that awaits the executor and stores the result."""
        result = await loop.run_in_executor(_executor, controller.run)
        _run_results[run_id] = result
        # Remove from active once complete
        _active_runs.pop(run_id, None)

    asyncio.create_task(_execute_and_store(), name=f"run-{run_id}")

    return {
        "run_id": run_id,
        "status": RunStatus.PENDING,
        "profile_name": profile_name,
        "message": "Run started. Connect to WebSocket /ws/{client_id} for live events.",
    }


@app.get("/run/{run_id}/status")
async def get_run_status(run_id: str) -> dict:
    """
    Returns the current status of a run (pending, running, complete, failed).
    Lightweight — no result data included.
    """
    controller = _active_runs.get(run_id)
    if controller:
        return {"run_id": run_id, "status": controller.status}

    result = _run_results.get(run_id)
    if result:
        return {"run_id": run_id, "status": result.status}

    return JSONResponse(status_code=404, content={"error": f"Run '{run_id}' not found."})


@app.get("/run/{run_id}/results")
async def get_run_results(run_id: str) -> dict:
    """
    Returns the full RunResult once a run has completed.
    Includes all MetricsSummary and TraceGraph objects.

    The TraceGraph objects can be large (hundreds of nodes × edges).
    For production use, consider returning metrics and graphs separately.
    For the simulator at 15×15 scale, returning everything at once is fine.
    """
    result = _run_results.get(run_id)
    if not result:
        controller = _active_runs.get(run_id)
        if controller:
            return JSONResponse(
                status_code=202,
                content={"error": f"Run '{run_id}' is still running.", "status": controller.status},
            )
        return JSONResponse(status_code=404, content={"error": f"Run '{run_id}' not found."})

    return {
        "run_id": result.run_id,
        "profile_name": result.profile_name,
        "seed": result.seed,
        "status": result.status,
        "metrics": result.all_metrics(),
        "graphs": result.all_graphs(),
    }


@app.post("/run/{run_id}/replay")
async def replay_run(run_id: str, request: ReplayRequest) -> dict:
    """
    Replays the event buffer for a completed run to all connected WS clients.

    Useful for:
      - A frontend client that connected AFTER the run completed
      - Debugging: re-send all events to inspect them
      - Playback bar initialisation: client replays from scratch

    The replay is enqueued into the broadcast queue so it respects
    backpressure — it will not overwhelm a slow WS client.
    """
    result = _run_results.get(run_id)
    if not result:
        return JSONResponse(status_code=404, content={"error": f"Run '{run_id}' not found."})

    replayed = []

    def collect(event: dict) -> None:
        replayed.append(event)
        if _loop and not _loop.is_closed():
            _loop.call_soon_threadsafe(_event_queue.put_nowait, event)

    event_type = request.event_type if request.event_type != "*" else None
    _bus.replay(collect, event_type=request.event_type)

    return {"replayed_count": len(replayed)}


@app.get("/bus/buffer")
async def get_bus_buffer(limit: int = 100, offset: int = 0) -> dict:
    """
    Returns a paginated slice of the EventBus buffer.
    Useful for debugging: inspect every event the simulation produced.
    The buffer is the complete history — nothing is filtered.
    """
    total = _bus.buffer_size()
    events = _bus.get_buffer_slice(offset, offset + limit)
    return {"total": total, "offset": offset, "limit": limit, "events": events}


# ── WebSocket endpoint ─────────────────────────────────────────────────────────


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str) -> None:
    """
    The real-time event stream.

    Lifecycle:
      1. Accept the connection
      2. Send a "connected" confirmation message
      3. Register in _ws_clients (will receive all future events)
      4. Wait for messages from the client (ping/pong, replay requests)
      5. On disconnect (or error), deregister and close cleanly

    Why wait for client messages?
    Because WebSocket is bidirectional. The client can send:
      - {"type": "ping"}                → server responds {"type": "pong"}
      - {"type": "replay", "run_id": X} → server replays that run's events

    If we did not read from the websocket, the client's send buffer would
    fill up and eventually cause a connection reset (TCP backpressure).
    Always read from a WebSocket connection even if you mostly ignore it.

    ── client_id ─────────────────────────────────────────────────────────
    A string the client provides to identify itself (e.g. "main-tab-1").
    Not authenticated — this is a local simulator, not a production service.
    In production: validate with a JWT before accepting the connection.
    """
    await websocket.accept()
    _ws_clients.add(websocket)

    try:
        # Confirm connection
        await websocket.send_json(
            {
                "event_type": "connected",
                "client_id": client_id,
                "message": "Connected to simulation server. Listening for events.",
                "bus_buffer_size": _bus.buffer_size(),
            }
        )

        # Main read loop — keeps the connection alive and handles client requests
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a keepalive ping so the browser does not close the connection
                await websocket.send_json({"event_type": "ping"})
                continue

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "event_type": "error",
                        "message": "Invalid JSON",
                    }
                )
                continue

            await _handle_client_message(websocket, message)

    except WebSocketDisconnect:
        # Normal disconnect — client closed the tab or navigated away
        pass
    except Exception:
        # Any other error — still clean up
        pass
    finally:
        _ws_clients.discard(websocket)


async def _handle_client_message(ws: WebSocket, message: dict) -> None:
    """
    Handles messages sent FROM the client TO the server over WebSocket.

    Supported messages:
      {"type": "ping"}
      {"type": "replay", "run_id": "...", "event_type": "*"}
      {"type": "status"}
    """
    msg_type = message.get("type", "unknown")

    if msg_type == "ping":
        await ws.send_json({"event_type": "pong"})

    elif msg_type == "status":
        await ws.send_json(
            {
                "event_type": "server_status",
                "ws_clients": len(_ws_clients),
                "active_runs": len(_active_runs),
                "bus_buffer_size": _bus.buffer_size(),
            }
        )

    elif msg_type == "replay":
        run_id = message.get("run_id")
        event_type = message.get("event_type", "*")

        if not run_id:
            await ws.send_json({"event_type": "error", "message": "replay requires run_id"})
            return

        # Replay directly to this client (not to all clients)
        replayed = 0
        for event in _bus.get_buffer():
            if event_type == "*" or event.get("event_type") == event_type:
                await ws.send_json(event)
                replayed += 1

        await ws.send_json({"event_type": "replay_complete", "count": replayed})

    else:
        await ws.send_json(
            {
                "event_type": "error",
                "message": f"Unknown message type '{msg_type}'",
            }
        )


# ── entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    """
    Launch the server with uvicorn.

    Usage:
        python -m backend.websocket.web_server
    Or:
        uvicorn backend.websocket.web_server:app --reload --port 8000

    The --reload flag is for development only. In production omit it.
    host="0.0.0.0" makes the server accessible from other machines on the
    network (e.g. a frontend running on a different device). For localhost-
    only access use host="127.0.0.1".
    """
    import uvicorn

    uvicorn.run(
        "backend.websocket.web_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
