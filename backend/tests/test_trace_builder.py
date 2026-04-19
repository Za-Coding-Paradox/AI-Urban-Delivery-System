# backend/tests/test_trace_builder.py
#
# Tests for StackTraceBuilder.
#
# Testing philosophy (mirrors existing test files):
#   - Each test has one clear assertion about one behaviour
#   - Fixtures create minimal valid state (no unnecessary complexity)
#   - Test names are sentences: what it does, what should happen
#   - Edge cases are tested explicitly, not assumed to work
#
# The builder is tested in isolation — no GridBuilder, no algorithms.
# We publish synthetic TraceEvents directly to the bus and verify
# the builder's state. This makes tests fast and deterministic.

import pytest

from backend.engine.event_bus import EventBus
from backend.trace.trace_builder import StackTraceBuilder, TraceBuilderError


# ── fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def bus() -> EventBus:
    """A fresh EventBus for each test. Prevents event bleed between tests."""
    return EventBus()


@pytest.fixture
def builder(bus) -> StackTraceBuilder:
    """A builder for algorithm 'astar', delivery 'D1'."""
    b = StackTraceBuilder("astar", "D1", bus)
    yield b
    # Always detach to prevent subscription leaks between tests
    b.detach()


def make_visit_event(
    algo_id: str = "astar",
    cell_id: str = "3,4",
    x: int = 3,
    y: int = 4,
    g: float = 5.0,
    h: float = 3.0,
    depth: int = 2,
    parent_id: str | None = "2,4",
    step: int = 1,
    edge: dict | None = None,
) -> dict:
    """
    Builds a minimal valid node_visit event.
    All parameters have sensible defaults so tests only override what matters.
    """
    return {
        "event_type":   "node_visit",
        "algorithm_id": algo_id,
        "step":         step,
        "timestamp_ms": 100.0,
        "node": {
            "id":        cell_id,
            "x":         x,
            "y":         y,
            "cell_type": "road",
            "g":         g,
            "h":         h,
            "f":         g + h,
            "depth":     depth,
            "parent_id": parent_id,
            "status":    "open",
        },
        "edge": edge,
        "frontier_size": 3,
        "visited_count": 1,
    }


def make_expand_event(
    algo_id: str = "astar",
    cell_id: str = "3,4",
    x: int = 3,
    y: int = 4,
    g: float = 5.0,
    h: float = 3.0,
    depth: int = 2,
    step: int = 2,
) -> dict:
    """Builds a minimal valid node_expand event."""
    return {
        "event_type":   "node_expand",
        "algorithm_id": algo_id,
        "step":         step,
        "timestamp_ms": 110.0,
        "node": {
            "id":        cell_id,
            "x":         x,
            "y":         y,
            "cell_type": "road",
            "g":         g,
            "h":         h,
            "f":         g + h,
            "depth":     depth,
            "parent_id": None,
            "status":    "closed",
        },
        "edge": None,
        "frontier_size": 2,
        "visited_count": 2,
    }


def make_path_event(
    algo_id: str = "astar",
    cell_id: str = "3,4",
    x: int = 3,
    y: int = 4,
    step: int = 3,
) -> dict:
    """Builds a minimal valid path_step event."""
    return {
        "event_type":   "path_step",
        "algorithm_id": algo_id,
        "step":         step,
        "timestamp_ms": 120.0,
        "node": {
            "id":        cell_id,
            "x":         x,
            "y":         y,
            "cell_type": "road",
            "g":         5.0,
            "h":         0.0,
            "f":         5.0,
            "depth":     2,
            "parent_id": None,
            "status":    "path",
        },
        "edge": None,
        "frontier_size": 0,
        "visited_count": 5,
    }


def make_delivery_complete_event(
    algo_id: str = "astar",
    delivery_id: str = "D1",
    step: int = 10,
) -> dict:
    """Builds a delivery_complete event."""
    return {
        "event_type":   "delivery_complete",
        "algorithm_id": algo_id,
        "goal_id":      delivery_id,
        "step":         step,
    }


# ── node recording ─────────────────────────────────────────────────────────────


def test_node_recorded_on_visit(builder, bus):
    """A visited node must appear in the builder's node store."""
    bus.publish(make_visit_event())
    assert builder.node_count() == 1


def test_node_has_open_status_after_visit(builder, bus):
    """Freshly visited nodes must have status 'open'."""
    bus.publish(make_visit_event(cell_id="5,5", x=5, y=5))
    graph = builder.finalize()
    node = graph["nodes"][0]
    assert node["status"] == "open"


def test_node_status_upgraded_to_closed_on_expand(builder, bus):
    """A node that is visited and then expanded must end up 'closed'."""
    bus.publish(make_visit_event(cell_id="2,2", x=2, y=2, step=1))
    bus.publish(make_expand_event(cell_id="2,2", x=2, y=2, step=2))
    graph = builder.finalize()
    node = next(n for n in graph["nodes"] if n["id"] == "2,2")
    assert node["status"] == "closed"


def test_node_status_upgraded_to_path_on_path_step(builder, bus):
    """A node on the final path must have status 'path'."""
    bus.publish(make_visit_event(cell_id="7,7", x=7, y=7, step=1))
    bus.publish(make_expand_event(cell_id="7,7", x=7, y=7, step=2))
    bus.publish(make_path_event(cell_id="7,7", x=7, y=7, step=3))
    graph = builder.finalize()
    node = next(n for n in graph["nodes"] if n["id"] == "7,7")
    assert node["status"] == "path"


def test_path_status_is_never_downgraded(builder, bus):
    """
    A node that received path_step must stay 'path' even if subsequent
    expand or visit events arrive (shouldn't happen in practice, but
    the builder must be defensive).
    """
    bus.publish(make_path_event(cell_id="1,1", x=1, y=1, step=1))
    # Simulate a late expand event for the same cell
    bus.publish(make_expand_event(cell_id="1,1", x=1, y=1, step=2))
    graph = builder.finalize()
    node = next(n for n in graph["nodes"] if n["id"] == "1,1")
    assert node["status"] == "path", "path status must never be downgraded"


def test_duplicate_visits_produce_one_node(builder, bus):
    """
    Visiting the same cell twice (different g values — UCS re-queuing)
    must produce exactly one node in the graph.
    """
    bus.publish(make_visit_event(cell_id="3,3", x=3, y=3, g=5.0, step=1))
    bus.publish(make_visit_event(cell_id="3,3", x=3, y=3, g=3.0, step=2))
    assert builder.node_count() == 1


def test_expand_without_prior_visit_creates_node(builder, bus):
    """
    The start node is expanded without a prior visit event.
    The builder must handle this gracefully by creating the node.
    """
    bus.publish(make_expand_event(cell_id="0,0", x=0, y=0, step=1))
    assert builder.node_count() == 1


def test_multiple_cells_all_recorded(builder, bus):
    """Each unique cell produces one node in the graph."""
    cells = [("1,0", 1, 0), ("2,0", 2, 0), ("3,0", 3, 0)]
    for cid, x, y in cells:
        bus.publish(make_visit_event(cell_id=cid, x=x, y=y))
    assert builder.node_count() == len(cells)


# ── edge recording ─────────────────────────────────────────────────────────────


def test_edge_recorded_when_visit_has_edge_data(builder, bus):
    """
    A visit event with edge data must produce an edge in the graph.
    """
    edge = {"from_id": "2,4", "to_id": "3,4", "edge_type": "expansion", "cost": 2.0}
    bus.publish(make_visit_event(cell_id="3,4", x=3, y=4, edge=edge))
    assert builder.edge_count() == 1


def test_no_edge_recorded_when_visit_has_no_edge(builder, bus):
    """A visit without edge data (start node) produces no edges."""
    bus.publish(make_visit_event(cell_id="0,0", x=0, y=0, parent_id=None, edge=None))
    assert builder.edge_count() == 0


def test_duplicate_edges_are_deduplicated(builder, bus):
    """
    Publishing two visit events for the same (from, to) pair must produce
    exactly one edge.
    """
    edge = {"from_id": "1,0", "to_id": "2,0", "edge_type": "expansion", "cost": 1.0}
    bus.publish(make_visit_event(cell_id="2,0", x=2, y=0, edge=edge, step=1))
    bus.publish(make_visit_event(cell_id="2,0", x=2, y=0, edge=edge, step=2))
    assert builder.edge_count() == 1


def test_path_edge_overwrites_expansion_edge(builder, bus):
    """
    When a path_step is received for a node, the edge leading into it
    must be upgraded from 'expansion' to 'path'.
    """
    edge = {"from_id": "0,0", "to_id": "1,0", "edge_type": "expansion", "cost": 1.0}
    bus.publish(make_visit_event(cell_id="1,0", x=1, y=0, edge=edge, step=1))
    bus.publish(make_path_event(cell_id="1,0", x=1, y=0, step=2))

    graph = builder.finalize()
    path_edges = [e for e in graph["edges"] if e["edge_type"] == "path"]
    assert len(path_edges) == 1


def test_path_edge_is_not_overwritten_by_expansion(builder, bus):
    """
    Once an edge is marked 'path', a subsequent event with 'expansion'
    type for the same pair must not downgrade it.
    """
    edge_exp  = {"from_id": "0,0", "to_id": "1,0", "edge_type": "expansion", "cost": 1.0}
    edge_path = {"from_id": "0,0", "to_id": "1,0", "edge_type": "path",      "cost": 1.0}

    bus.publish(make_visit_event(cell_id="1,0", x=1, y=0, edge=edge_path, step=1))
    bus.publish(make_visit_event(cell_id="1,0", x=1, y=0, edge=edge_exp,  step=2))

    graph = builder.finalize()
    assert graph["edges"][0]["edge_type"] == "path"


# ── algorithm filtering ────────────────────────────────────────────────────────


def test_builder_ignores_events_from_other_algorithms(bus):
    """
    A builder for 'bfs' must not record events published for 'astar'.
    Algorithm isolation is critical when multiple builders coexist on one bus.
    """
    bfs_builder   = StackTraceBuilder("bfs",   "D1", bus)
    astar_builder = StackTraceBuilder("astar", "D1", bus)

    bus.publish(make_visit_event(algo_id="bfs",   cell_id="1,1", x=1, y=1, step=1))
    bus.publish(make_visit_event(algo_id="astar", cell_id="2,2", x=2, y=2, step=2))

    assert bfs_builder.node_count()   == 1, "bfs builder must see only its events"
    assert astar_builder.node_count() == 1, "astar builder must see only its events"

    bfs_builder.detach()
    astar_builder.detach()


def test_two_builders_same_algorithm_different_deliveries(bus):
    """
    Two builders for the same algorithm but different deliveries must
    both receive events — filtering is by algorithm_id, not delivery_id.
    This is intentional: the builder collects all events for its algorithm
    and the delivery_id is metadata, not a filter key.
    """
    builder_d1 = StackTraceBuilder("astar", "D1", bus)
    builder_d2 = StackTraceBuilder("astar", "D2", bus)

    bus.publish(make_visit_event(algo_id="astar", cell_id="1,1", x=1, y=1))

    # Both builders receive the same event — the delivery_id is just a label
    assert builder_d1.node_count() == 1
    assert builder_d2.node_count() == 1

    builder_d1.detach()
    builder_d2.detach()


# ── metadata ───────────────────────────────────────────────────────────────────


def test_metadata_max_depth_tracks_deepest_node(builder, bus):
    """max_depth must equal the largest depth value seen across all events."""
    bus.publish(make_visit_event(cell_id="1,0", x=1, y=0, depth=2, step=1))
    bus.publish(make_visit_event(cell_id="2,0", x=2, y=0, depth=7, step=2))
    bus.publish(make_visit_event(cell_id="3,0", x=3, y=0, depth=4, step=3))
    graph = builder.finalize()
    assert graph["metadata"]["max_depth"] == 7


def test_metadata_max_g_tracks_highest_cost(builder, bus):
    """max_g must reflect the most expensive path cost seen."""
    bus.publish(make_visit_event(cell_id="1,0", x=1, y=0, g=3.0,  step=1))
    bus.publish(make_visit_event(cell_id="2,0", x=2, y=0, g=12.0, step=2))
    bus.publish(make_visit_event(cell_id="3,0", x=3, y=0, g=7.0,  step=3))
    graph = builder.finalize()
    assert graph["metadata"]["max_g"] == 12.0


def test_metadata_total_steps_is_max_step_seen(builder, bus):
    """total_steps must be the highest step counter encountered."""
    bus.publish(make_visit_event(step=1))
    bus.publish(make_expand_event(step=5))
    bus.publish(make_visit_event(cell_id="9,9", x=9, y=9, step=3))
    graph = builder.finalize()
    assert graph["metadata"]["total_steps"] == 5


def test_metadata_node_and_edge_counts_match_actual(builder, bus):
    """node_count and edge_count in metadata must match actual list lengths."""
    edge = {"from_id": "0,0", "to_id": "1,0", "edge_type": "expansion", "cost": 1.0}
    bus.publish(make_visit_event(cell_id="0,0", x=0, y=0))
    bus.publish(make_visit_event(cell_id="1,0", x=1, y=0, edge=edge))
    graph = builder.finalize()
    assert graph["metadata"]["node_count"] == len(graph["nodes"])
    assert graph["metadata"]["edge_count"] == len(graph["edges"])


# ── completion lifecycle ───────────────────────────────────────────────────────


def test_is_complete_false_before_delivery_complete(builder, bus):
    """Builder must not report complete until delivery_complete arrives."""
    bus.publish(make_visit_event())
    assert builder.is_complete() is False


def test_is_complete_true_after_delivery_complete(builder, bus):
    """Builder must report complete immediately after delivery_complete."""
    bus.publish(make_visit_event())
    bus.publish(make_delivery_complete_event())
    assert builder.is_complete() is True


def test_delivery_complete_publishes_trace_graph_ready_event(bus):
    """
    delivery_complete must cause the builder to publish a 'trace_graph_ready'
    event back onto the bus. The RunController and WS server rely on this
    to know when to collect the finished graph.
    """
    received = []
    bus.subscribe("trace_graph_ready", lambda e: received.append(e))

    builder = StackTraceBuilder("astar", "D1", bus)
    bus.publish(make_visit_event())
    bus.publish(make_delivery_complete_event())
    builder.detach()

    assert len(received) == 1
    assert received[0]["algorithm_id"] == "astar"
    assert received[0]["delivery_id"]  == "D1"
    assert "graph" in received[0]


def test_on_complete_callback_invoked(bus):
    """
    The on_complete callback registered by RunController must be called
    with the finished graph when delivery_complete arrives.
    """
    results = []
    builder = StackTraceBuilder("astar", "D1", bus)
    builder.on_complete(lambda graph: results.append(graph))

    bus.publish(make_visit_event())
    bus.publish(make_delivery_complete_event())
    builder.detach()

    assert len(results) == 1
    assert results[0]["algorithm_id"] == "astar"


# ── finalize ───────────────────────────────────────────────────────────────────


def test_finalize_returns_correct_schema_shape(builder, bus):
    """
    finalize() must return a dict with the exact top-level keys the
    3D renderer expects. Missing keys would cause a silent render failure.
    """
    bus.publish(make_visit_event())
    graph = builder.finalize()

    required_top_level = {"algorithm_id", "delivery_id", "nodes", "edges", "metadata"}
    assert required_top_level.issubset(graph.keys())

    required_metadata = {"total_steps", "max_depth", "max_g", "max_f", "complete", "node_count", "edge_count"}
    assert required_metadata.issubset(graph["metadata"].keys())


def test_finalize_before_any_events_raises(bus):
    """
    Calling finalize() on a builder that received no events must raise
    TraceBuilderError — not return an empty graph silently.
    An empty graph would cause a confusing 3D render with nothing shown.
    """
    builder = StackTraceBuilder("astar", "D1", bus)
    with pytest.raises(TraceBuilderError, match="no events received"):
        builder.finalize()
    builder.detach()


def test_finalize_returns_json_serialisable_dict(builder, bus):
    """
    The finalize() output must survive json.dumps() without errors.
    The WS server serialises it directly — any non-serialisable value
    (datetime, set, custom object) would crash the broadcast.
    """
    import json
    bus.publish(make_visit_event())
    graph = builder.finalize()
    serialised = json.dumps(graph)  # must not raise
    assert len(serialised) > 0


def test_finalize_can_be_called_multiple_times(builder, bus):
    """
    finalize() is non-destructive — calling it multiple times returns
    consistent results. The RunController and the delivery_complete handler
    both call it; they must get the same graph.
    """
    bus.publish(make_visit_event())
    graph_a = builder.finalize()
    graph_b = builder.finalize()
    assert graph_a == graph_b


# ── detach ─────────────────────────────────────────────────────────────────────


def test_detached_builder_stops_receiving_events(bus):
    """
    After detach(), the builder must not accumulate new events.
    This prevents memory leaks from stale builders on long-running servers.
    """
    builder = StackTraceBuilder("astar", "D1", bus)
    bus.publish(make_visit_event(cell_id="1,1", x=1, y=1, step=1))
    assert builder.node_count() == 1

    builder.detach()

    # Publish a new event — detached builder must not see it
    bus.publish(make_visit_event(cell_id="2,2", x=2, y=2, step=2))
    assert builder.node_count() == 1, "detached builder must not accumulate new events"


def test_multiple_builders_can_detach_independently(bus):
    """
    Detaching one builder must not affect other builders on the same bus.
    """
    builder_a = StackTraceBuilder("bfs",   "D1", bus)
    builder_b = StackTraceBuilder("astar", "D1", bus)

    bus.publish(make_visit_event(algo_id="bfs",   cell_id="1,1", x=1, y=1))
    bus.publish(make_visit_event(algo_id="astar", cell_id="2,2", x=2, y=2))

    builder_a.detach()

    # Publish more events — only builder_b should receive them
    bus.publish(make_visit_event(algo_id="bfs",   cell_id="3,3", x=3, y=3))
    bus.publish(make_visit_event(algo_id="astar", cell_id="4,4", x=4, y=4))

    assert builder_a.node_count() == 1, "detached builder_a must not see new events"
    assert builder_b.node_count() == 2, "builder_b must still receive its events"

    builder_b.detach()
