# backend/tests/test_grid_builder.py

import pytest

from backend.engine.grid_builder import GridBuilder, GridBuilderError

# ── minimal valid profile fixture ───────────────────────────────────────────────


def make_profile(seed=42, obstacle_positions=None, delivery_positions=None, start=None):
    obstacle_positions = obstacle_positions or []
    start = start or {"x": 0, "y": 0}
    delivery_positions = delivery_positions or [
        {"id": "D1", "x": 14, "y": 0, "label": "D1"},
        {"id": "D2", "x": 14, "y": 14, "label": "D2"},
        {"id": "D3", "x": 0, "y": 14, "label": "D3"},
        {"id": "D4", "x": 7, "y": 7, "label": "D4"},
        {"id": "D5", "x": 7, "y": 0, "label": "D5"},
    ]

    obstacle_set = set(obstacle_positions)
    delivery_set = {(d["x"], d["y"]) for d in delivery_positions}
    start_xy = (start["x"], start["y"])

    cells = []
    for y in range(15):
        for x in range(15):
            xy = (x, y)
            if xy in obstacle_set:
                cell_type = "obstacle"
                cost = None
                passable = False
            elif xy == start_xy:
                cell_type = "base_station"
                cost = 1
                passable = True
            elif xy in delivery_set:
                cell_type = "delivery_point"
                cost = 1
                passable = True
            else:
                cell_type = "road"
                cost = 1
                passable = True

            cells.append(
                {
                    "id": f"{x},{y}",
                    "x": x,
                    "y": y,
                    "type": cell_type,
                    "cost": cost,
                    "passable": passable,
                    "label": None,
                    "metadata": {},
                }
            )

    return {
        "meta": {
            "id": "test-001",
            "name": "Test Grid",
            "seed": seed,
            "created_at": "2026-01-01T00:00:00Z",
            "version": "1.0",
        },
        "grid": {"width": 15, "height": 15, "cells": cells},
        "robot": {
            "start": start,
            "movement": "cardinal",
            "cost_model": "edge_cost",
            "tie_breaking": "first",
        },
        "deliveries": {"count": 5, "destinations": delivery_positions, "order": "sequential"},
        "algorithms": [
            {
                "id": "astar",
                "enabled": True,
                "heuristic": "manhattan",
                "weight": 1.0,
                "visualize": True,
            }
        ],
    }


# ── tests ────────────────────────────────────────────────────────────────────────


def test_build_returns_225_cells():
    profile = make_profile()
    cells = GridBuilder().build(profile)
    assert len(cells) == 225


def test_cells_sorted_row_major():
    cells = GridBuilder().build(make_profile())
    for i, cell in enumerate(cells):
        assert cell["x"] == i % 15
        assert cell["y"] == i // 15


def test_obstacle_cost_is_null():
    profile = make_profile(obstacle_positions=[(5, 5)])
    cells = GridBuilder().build(profile)
    cell = cells[5 * 15 + 5]
    assert cell["type"] == "obstacle"
    assert cell["cost"] is None
    assert cell["passable"] is False


def test_road_cost_within_range():
    cells = GridBuilder().build(make_profile())
    road_cells = [c for c in cells if c["type"] == "road"]
    for cell in road_cells:
        assert 1 <= cell["cost"] <= 5


def test_same_seed_produces_same_grid():
    profile = make_profile(seed=99)
    cells_a = GridBuilder().build(profile)
    cells_b = GridBuilder().build(profile)
    assert [c["cost"] for c in cells_a] == [c["cost"] for c in cells_b]


def test_different_seeds_produce_different_grids():
    cells_a = GridBuilder().build(make_profile(seed=1))
    cells_b = GridBuilder().build(make_profile(seed=2))
    costs_a = [c["cost"] for c in cells_a if c["cost"] is not None]
    costs_b = [c["cost"] for c in cells_b if c["cost"] is not None]
    assert costs_a != costs_b


def test_impassable_start_raises():
    with pytest.raises(GridBuilderError, match="impassable"):
        profile = make_profile(obstacle_positions=[(0, 0)], start={"x": 0, "y": 0})
        GridBuilder().build(profile)


def test_unreachable_destination_raises():
    # Surround delivery point D4 at (7,7) with a wall of obstacles
    wall = [(6, 6), (7, 6), (8, 6), (6, 7), (8, 7), (6, 8), (7, 8), (8, 8)]
    with pytest.raises(GridBuilderError, match="unreachable"):
        GridBuilder().build(make_profile(obstacle_positions=wall))


def test_cell_id_format():
    cells = GridBuilder().build(make_profile())
    for cell in cells:
        assert cell["id"] == f"{cell['x']},{cell['y']}"
