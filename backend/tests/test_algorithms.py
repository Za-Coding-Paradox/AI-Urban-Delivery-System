# backend/tests/test_algorithms.py

import pytest

from backend.algorithms.algorithms_registry import ALGORITHM_REGISTRY, get_runner
from backend.engine.event_bus import EventBus
from backend.engine.grid_builder import GridBuilder
from backend.engine.profile_manager import ProfileManager

# ── shared fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def simple_grid():
    """
    A minimal open grid — no obstacles, no traffic zones.
    Robot starts at (0,0). One delivery at (7,7).
    Used to verify all algorithms find A valid path.
    """
    from pathlib import Path

    manager = ProfileManager(profiles_dir=Path("/tmp/positron_test"))
    profile = manager.generate(seed=42)
    bus = EventBus()
    cells = GridBuilder().build(profile)
    return cells, profile, bus


@pytest.fixture
def all_configs():
    """One AlgorithmConfig dict per algorithm."""
    return [
        {"id": "bfs", "enabled": True, "heuristic": "none", "weight": 1.0, "visualize": True},
        {"id": "dfs", "enabled": True, "heuristic": "none", "weight": 1.0, "visualize": True},
        {"id": "ucs", "enabled": True, "heuristic": "none", "weight": 1.0, "visualize": True},
        {
            "id": "greedy",
            "enabled": True,
            "heuristic": "manhattan",
            "weight": 1.0,
            "visualize": True,
        },
        {
            "id": "astar",
            "enabled": True,
            "heuristic": "manhattan",
            "weight": 1.0,
            "visualize": True,
        },
    ]


# ── basic correctness ──────────────────────────────────────────────────────────


def test_all_algorithms_find_path(simple_grid, all_configs):
    """Every algorithm must find a path on an open grid."""
    cells, profile, bus = simple_grid
    start = next(c for c in cells if c["type"] == "base_station")
    goal = next(c for c in cells if c["type"] == "delivery_point")

    for config in all_configs:
        bus.clear_buffer()
        runner = get_runner(config["id"], bus)
        metrics = runner.run(cells, start, goal, config)
        assert metrics["path_found"], f"{config['id']} failed to find a path"


def test_path_starts_at_start_ends_at_goal(simple_grid, all_configs):
    cells, profile, bus = simple_grid
    start = next(c for c in cells if c["type"] == "base_station")
    goal = next(c for c in cells if c["type"] == "delivery_point")

    for config in all_configs:
        bus.clear_buffer()
        runner = get_runner(config["id"], bus)
        metrics = runner.run(cells, start, goal, config)

        if metrics["path_found"]:
            assert metrics["path"][0] == {"x": start["x"], "y": start["y"]}, (
                f"{config['id']} path does not start at start"
            )
            assert metrics["path"][-1] == {"x": goal["x"], "y": goal["y"]}, (
                f"{config['id']} path does not end at goal"
            )


def test_ucs_and_astar_find_optimal_cost(simple_grid):
    """
    UCS and A* are both cost-optimal.
    On the same grid they must return the same path cost.
    If they differ, one of them has a bug.
    """
    cells, profile, bus = simple_grid
    start = next(c for c in cells if c["type"] == "base_station")
    goal = next(c for c in cells if c["type"] == "delivery_point")

    ucs_config = {
        "id": "ucs",
        "enabled": True,
        "heuristic": "none",
        "weight": 1.0,
        "visualize": False,
    }
    astar_config = {
        "id": "astar",
        "enabled": True,
        "heuristic": "manhattan",
        "weight": 1.0,
        "visualize": False,
    }

    bus.clear_buffer()
    ucs_metrics = get_runner("ucs", bus).run(cells, start, goal, ucs_config)
    bus.clear_buffer()
    astar_metrics = get_runner("astar", bus).run(cells, start, goal, astar_config)

    assert ucs_metrics["path_cost"] == pytest.approx(astar_metrics["path_cost"]), (
        "UCS and A* must find the same optimal cost"
    )


def test_astar_explores_fewer_nodes_than_ucs(simple_grid):
    """
    A* should explore fewer nodes than UCS on the same grid
    because the heuristic guides it toward the goal.
    This is the practical benefit of A* over UCS.
    """
    cells, profile, bus = simple_grid
    start = next(c for c in cells if c["type"] == "base_station")
    goal = next(c for c in cells if c["type"] == "delivery_point")

    ucs_config = {
        "id": "ucs",
        "enabled": True,
        "heuristic": "none",
        "weight": 1.0,
        "visualize": False,
    }
    astar_config = {
        "id": "astar",
        "enabled": True,
        "heuristic": "manhattan",
        "weight": 1.0,
        "visualize": False,
    }

    bus.clear_buffer()
    ucs_metrics = get_runner("ucs", bus).run(cells, start, goal, ucs_config)
    bus.clear_buffer()
    astar_metrics = get_runner("astar", bus).run(cells, start, goal, astar_config)

    assert astar_metrics["nodes_explored"] <= ucs_metrics["nodes_explored"], (
        "A* should explore fewer or equal nodes compared to UCS"
    )


def test_metrics_schema_shape(simple_grid):
    """Every algorithm must return a properly shaped MetricsSummary."""
    cells, profile, bus = simple_grid
    start = next(c for c in cells if c["type"] == "base_station")
    goal = next(c for c in cells if c["type"] == "delivery_point")

    required_keys = {
        "algorithm_id",
        "delivery_id",
        "path_cost",
        "execution_time_ms",
        "nodes_explored",
        "path_length",
        "path_found",
        "path",
        "heuristic_used",
    }

    config = {
        "id": "astar",
        "enabled": True,
        "heuristic": "manhattan",
        "weight": 1.0,
        "visualize": False,
    }
    metrics = get_runner("astar", bus).run(cells, start, goal, config)

    assert required_keys.issubset(metrics.keys()), (
        f"MetricsSummary missing keys: {required_keys - metrics.keys()}"
    )


def test_trace_events_emitted(simple_grid):
    """
    Algorithms must emit TraceEvents to the EventBus.
    The buffer should be non-empty after a run.
    """
    cells, profile, bus = simple_grid
    start = next(c for c in cells if c["type"] == "base_station")
    goal = next(c for c in cells if c["type"] == "delivery_point")

    config = {
        "id": "astar",
        "enabled": True,
        "heuristic": "manhattan",
        "weight": 1.0,
        "visualize": True,
    }
    bus.clear_buffer()
    get_runner("astar", bus).run(cells, start, goal, config)

    assert bus.buffer_size() > 0, "No TraceEvents were emitted"


def test_get_runner_unknown_raises():
    with pytest.raises(ValueError, match="Unknown algorithm"):
        get_runner("teleport", EventBus())


def test_all_registry_ids_instantiate():
    """Every entry in the registry must instantiate without error."""
    for algo_id in ALGORITHM_REGISTRY:
        runner = get_runner(algo_id, EventBus())
        assert runner is not None
