# backend/tests/test_websocket_server.py
#
# Tests for the FastAPI simulation server.
#
# Two categories:
#
#   REST tests  — synchronous, use TestClient. Test JSON in/out, status codes,
#                 error handling, profile management endpoints.
#
#   WebSocket tests — use TestClient's websocket_connect context manager.
#                     Test connection handshake, message handling, and that
#                     events published to the bus reach the WS client.
#
# We override the lifespan singleton initialisation with a test fixture
# so tests use isolated EventBus instances rather than sharing state.
#
# ── note on async testing ──────────────────────────────────────────────────────
# FastAPI's TestClient runs the ASGI app in a synchronous context using
# anyio under the hood. This means you do NOT need pytest-asyncio for
# TestClient-based tests — they run as regular sync pytest functions.
# The WS tests use client.websocket_connect() which is also synchronous.

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.websocket.server as server_module
from backend.engine.event_bus import EventBus
from backend.websocket.server import app


# ── test fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_server_state(tmp_path):
    """
    Before each test:
      - Reset all module-level singletons to clean state
      - Point ProfileManager at a temp directory (no disk pollution)
      - Clear ws_clients and active_runs

    autouse=True means this fixture runs for every test in this file
    without each test having to request it explicitly.

    Why patch module-level singletons rather than refactoring to DI?
    Because the server is designed for simplicity (one EventBus, one server).
    For a production system, dependency injection (FastAPI Depends()) would
    be cleaner. For this simulator, patching is correct.
    """
    from backend.engine.event_bus import EventBus
    from backend.engine.profile_manager import ProfileManager

    # Inject fresh singletons.
    # _bus and _profile_mgr are pre-injected so the lifespan guard
    # (if x is None: create) skips reinitialising them, preserving
    # test isolation (fresh bus, tmp_path profile dir).
    #
    # _executor and _event_queue are reset to None so the lifespan
    # ALWAYS creates fresh instances. The executor from the previous
    # test's lifespan is shut down during that test's teardown —
    # leaving a dead executor would cause "cannot schedule new futures
    # after shutdown" on any run_in_executor call in the next test.
    server_module._bus         = EventBus()
    server_module._event_queue = None   # lifespan creates fresh per-test
    server_module._executor    = None   # lifespan creates fresh per-test
    server_module._profile_mgr = ProfileManager(profiles_dir=tmp_path)
    server_module._ws_clients  = set()
    server_module._active_runs = {}
    server_module._run_results = {}

    yield

    # Cleanup — ensure no lingering subscribers or state leaks
    server_module._ws_clients  = set()
    server_module._active_runs = {}
    server_module._run_results = {}
    # Reset executor and queue to None so the next test's lifespan
    # creates fresh ones (the current ones will be shut down by the
    # lifespan teardown that runs after this yield block returns)
    server_module._executor    = None
    server_module._event_queue = None


@pytest.fixture
def client() -> TestClient:
    """
    A synchronous TestClient for the FastAPI app.
    TestClient handles lifespan startup/shutdown automatically.
    """
    # We bypass the lifespan by using the already-patched module state
    # The TestClient raises_server_exceptions=True by default — good,
    # it means test failures from server errors are visible immediately.
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── health endpoint ────────────────────────────────────────────────────────────


def test_health_returns_ok(client):
    """GET /health must return 200 with status 'ok'."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_includes_client_count(client):
    """Health response must include ws_clients count."""
    response = client.get("/health")
    assert "ws_clients" in response.json()


def test_health_includes_bus_buffer_size(client):
    """Health response must include the EventBus buffer size."""
    response = client.get("/health")
    assert "bus_buffer_size" in response.json()


# ── profile endpoints ──────────────────────────────────────────────────────────


def test_list_profiles_empty_initially(client):
    """GET /profiles on a fresh server returns an empty list."""
    response = client.get("/profiles")
    assert response.status_code == 200
    assert response.json()["profiles"] == []


def test_generate_profile_returns_valid_structure(client):
    """POST /profiles/generate must return a profile with the correct schema."""
    response = client.post("/profiles/generate", json={"seed": 42})
    assert response.status_code == 200

    profile = response.json()["profile"]
    assert profile["meta"]["seed"] == 42
    assert len(profile["grid"]["cells"]) == 225
    assert len(profile["deliveries"]["destinations"]) == 5


def test_generate_profile_is_deterministic(client):
    """Same seed must produce the same profile on successive calls."""
    r1 = client.post("/profiles/generate", json={"seed": 99})
    r2 = client.post("/profiles/generate", json={"seed": 99})

    assert r1.json()["profile"]["robot"]["start"] == r2.json()["profile"]["robot"]["start"]


def test_generate_profile_with_custom_name(client):
    """Generated profile's meta.name must match the requested name."""
    response = client.post("/profiles/generate", json={"seed": 7, "name": "my_test_city"})
    assert response.json()["profile"]["meta"]["name"] == "my_test_city"


def test_save_and_list_profile(client):
    """Saving a profile must make it appear in the list endpoint."""
    profile = client.post("/profiles/generate", json={"seed": 1}).json()["profile"]
    client.post("/profiles/alpha/save", json={"profile": profile})

    profiles = client.get("/profiles").json()["profiles"]
    assert "alpha" in profiles


def test_get_profile_returns_saved_data(client):
    """GET /profiles/{name} must return exactly what was saved."""
    profile = client.post("/profiles/generate", json={"seed": 42}).json()["profile"]
    client.post("/profiles/roundtrip/save", json={"profile": profile})

    loaded = client.get("/profiles/roundtrip").json()["profile"]
    assert loaded["meta"]["seed"] == 42


def test_get_nonexistent_profile_returns_404(client):
    """GET /profiles/{name} for a missing profile must return 404."""
    response = client.get("/profiles/does_not_exist")
    assert response.status_code == 404
    assert "error" in response.json()


# ── run endpoints ──────────────────────────────────────────────────────────────


def test_run_requires_profile_or_profile_name(client):
    """POST /run without profile data must return 422."""
    response = client.post("/run", json={})
    assert response.status_code == 422


def test_run_with_nonexistent_profile_name_returns_404(client):
    """POST /run referencing a profile that doesn't exist must return 404."""
    response = client.post("/run", json={"profile_name": "ghost_profile"})
    assert response.status_code == 404


def test_run_with_inline_profile_starts_successfully(client):
    """
    POST /run with an inline profile dict must start a run and return a run_id.
    We don't wait for completion — just verify the response shape.
    """
    profile = client.post("/profiles/generate", json={"seed": 5}).json()["profile"]

    # Disable all algorithms to make the run instant
    for algo in profile["algorithms"]:
        algo["enabled"] = False

    response = client.post("/run", json={"profile": profile})
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert len(data["run_id"]) > 0


def test_run_status_endpoint_exists(client):
    """
    GET /run/{run_id}/status for an unknown run_id must return 404.
    This verifies the endpoint exists and handles the not-found case.
    """
    response = client.get("/run/nonexistent-run-id/status")
    assert response.status_code == 404


def test_run_results_for_unknown_run_returns_404(client):
    """GET /run/{run_id}/results for an unknown id must return 404."""
    response = client.get("/run/no-such-run/results")
    assert response.status_code == 404


# ── bus buffer endpoint ────────────────────────────────────────────────────────


def test_bus_buffer_returns_events(client):
    """GET /bus/buffer must return the current event buffer."""
    # Publish an event directly to the module-level bus
    server_module._bus.publish({"event_type": "test_event", "data": "hello"})

    response = client.get("/bus/buffer")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert isinstance(data["events"], list)


def test_bus_buffer_respects_limit_and_offset(client):
    """Pagination parameters must slice the buffer correctly."""
    for i in range(10):
        server_module._bus.publish({"event_type": "test_event", "step": i})

    response = client.get("/bus/buffer?limit=3&offset=2")
    data = response.json()
    assert len(data["events"]) == 3
    assert data["offset"] == 2


# ── WebSocket connection ───────────────────────────────────────────────────────


def test_websocket_connects_and_receives_confirmation(client):
    """
    A WebSocket client must receive a 'connected' confirmation message
    immediately after connecting. This is the handshake.
    """
    with client.websocket_connect("/ws/test-client") as ws:
        data = ws.receive_json()
        assert data["event_type"] == "connected"
        assert data["client_id"] == "test-client"


def test_websocket_confirmation_includes_bus_buffer_size(client):
    """
    The connected message must include the current bus buffer size.
    The frontend uses this to decide whether to request a replay.
    """
    with client.websocket_connect("/ws/my-client") as ws:
        data = ws.receive_json()
        assert "bus_buffer_size" in data


def test_websocket_responds_to_ping(client):
    """
    Sending {"type": "ping"} must produce a {"event_type": "pong"} response.
    This keeps the connection alive and verifies the message loop works.
    """
    with client.websocket_connect("/ws/ping-test") as ws:
        ws.receive_json()  # consume the "connected" message first
        ws.send_json({"type": "ping"})
        response = ws.receive_json()
        assert response["event_type"] == "pong"


def test_websocket_responds_to_status_request(client):
    """
    Sending {"type": "status"} must return current server stats.
    """
    with client.websocket_connect("/ws/status-test") as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "status"})
        response = ws.receive_json()
        assert response["event_type"] == "server_status"
        assert "ws_clients" in response
        assert "bus_buffer_size" in response


def test_websocket_handles_unknown_message_type(client):
    """
    Sending an unknown message type must return an error response,
    not crash the server.
    """
    with client.websocket_connect("/ws/err-test") as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "teleport"})
        response = ws.receive_json()
        assert response["event_type"] == "error"


def test_websocket_replay_with_no_run_id_returns_error(client):
    """
    Sending a replay request without run_id must return an error.
    """
    with client.websocket_connect("/ws/replay-test") as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "replay"})  # missing run_id
        response = ws.receive_json()
        assert response["event_type"] == "error"


def test_websocket_receives_bus_events(client):
    """
    Events published to the module-level EventBus must be forwarded
    to all connected WebSocket clients.

    This is the core integration test — it verifies that the async
    bridge between the sync EventBus and the async WS send works.

    Note: In TestClient's synchronous test mode, the async broadcast_task
    does not run (no event loop). We test the REST replay endpoint as a
    proxy for this integration. For the full async test see the
    integration test comments below.
    """
    # Pre-populate the bus with a known event
    server_module._bus.publish({
        "event_type": "node_visit",
        "algorithm_id": "bfs",
        "step": 42,
    })

    with client.websocket_connect("/ws/event-test") as ws:
        ws.receive_json()  # connected

        # Request a replay of the bus buffer to this client
        ws.send_json({"type": "replay", "run_id": "any", "event_type": "*"})

        # Collect messages until we see replay_complete
        messages = []
        for _ in range(100):  # safety limit
            msg = ws.receive_json()
            if msg["event_type"] == "replay_complete":
                break
            messages.append(msg)

        event_types = {m["event_type"] for m in messages}
        assert "node_visit" in event_types


# ── run integration (lightweight) ─────────────────────────────────────────────


def test_full_run_with_single_algorithm_completes(client, tmp_path):
    """
    End-to-end: generate a profile → start a run with one algorithm →
    poll for completion → verify results are retrievable.

    We use only BFS (fast, no heuristic) and a fixed seed for speed.
    The run executes in a ThreadPoolExecutor in the background.
    We poll status until complete (or timeout).
    """
    import time

    # Generate a profile
    profile = client.post("/profiles/generate", json={"seed": 42}).json()["profile"]

    # Disable all algorithms except BFS
    for algo in profile["algorithms"]:
        algo["enabled"] = algo["id"] == "bfs"

    # Start the run
    run_resp = client.post("/run", json={"profile": profile})
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]

    # Poll for completion (max 30 seconds)
    deadline = time.time() + 30
    while time.time() < deadline:
        status_resp = client.get(f"/run/{run_id}/status")
        # Run may complete so fast it goes straight to results
        if status_resp.status_code == 404:
            # Check if result is ready instead
            result_resp = client.get(f"/run/{run_id}/results")
            if result_resp.status_code == 200:
                break
        status = status_resp.json().get("status", "")
        if status in ("complete", "failed"):
            break
        time.sleep(0.1)
    else:
        pytest.fail("Run did not complete within 30 seconds")

    # Fetch results
    result_resp = client.get(f"/run/{run_id}/results")
    assert result_resp.status_code == 200
    result = result_resp.json()

    assert result["status"] == "complete"
    assert len(result["metrics"]) > 0

    # BFS must have found paths to all 5 deliveries on an open grid
    for m in result["metrics"]:
        assert m["algorithm_id"] == "bfs"
        assert m["path_found"] is True
