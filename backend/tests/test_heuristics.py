# backend/tests/test_heuristics.py

import pytest

from backend.heuristics.distance import euclidean, get_heuristic, manhattan, zero

# ── manhattan ───────────────────────────────────────────────────────────────────


def test_manhattan_same_point():
    # Distance from a point to itself is always 0
    assert manhattan(5, 5, 5, 5) == 0


def test_manhattan_horizontal():
    # 3 steps right, 0 steps up/down
    assert manhattan(0, 0, 3, 0) == 3


def test_manhattan_vertical():
    # 0 steps sideways, 4 steps up
    assert manhattan(0, 0, 0, 4) == 4


def test_manhattan_diagonal():
    # 3 steps right + 4 steps up = 7 total
    assert manhattan(0, 0, 3, 4) == 7


def test_manhattan_symmetric():
    # Distance A→B equals distance B→A
    assert manhattan(2, 3, 7, 1) == manhattan(7, 1, 2, 3)


def test_manhattan_returns_integer():
    result = manhattan(0, 0, 3, 4)
    assert isinstance(result, int)


def test_manhattan_never_negative():
    assert manhattan(5, 5, 0, 0) >= 0
    assert manhattan(0, 0, 5, 5) >= 0


# ── euclidean ───────────────────────────────────────────────────────────────────


def test_euclidean_same_point():
    assert euclidean(5, 5, 5, 5) == 0.0


def test_euclidean_horizontal():
    assert euclidean(0, 0, 3, 0) == pytest.approx(3.0)


def test_euclidean_classic_triangle():
    # 3-4-5 right triangle: sqrt(3² + 4²) = sqrt(9+16) = sqrt(25) = 5.0
    assert euclidean(0, 0, 3, 4) == pytest.approx(5.0)


def test_euclidean_symmetric():
    assert euclidean(2, 3, 7, 1) == pytest.approx(euclidean(7, 1, 2, 3))


def test_euclidean_returns_float():
    result = euclidean(0, 0, 3, 4)
    assert isinstance(result, float)


def test_euclidean_always_leq_manhattan():
    # Euclidean is always ≤ Manhattan — it's a tighter lower bound
    # This property confirms both are admissible and euclidean
    # is the more optimistic (looser) estimate
    pairs = [(0, 0, 14, 14), (3, 7, 9, 2), (0, 0, 7, 0), (5, 5, 5, 10)]
    for ax, ay, bx, by in pairs:
        assert euclidean(ax, ay, bx, by) <= manhattan(ax, ay, bx, by) + 1e-9


# ── zero ────────────────────────────────────────────────────────────────────────


def test_zero_always_returns_zero():
    assert zero(0, 0, 14, 14) == 0
    assert zero(7, 7, 7, 7) == 0
    assert zero(0, 0, 0, 0) == 0


# ── registry ────────────────────────────────────────────────────────────────────


def test_get_heuristic_manhattan():
    fn = get_heuristic("manhattan")
    assert fn(0, 0, 3, 4) == 7


def test_get_heuristic_euclidean():
    fn = get_heuristic("euclidean")
    assert fn(0, 0, 3, 4) == pytest.approx(5.0)


def test_get_heuristic_none():
    fn = get_heuristic("none")
    assert fn(0, 0, 14, 14) == 0


def test_get_heuristic_unknown_raises():
    with pytest.raises(ValueError, match="Unknown heuristic"):
        get_heuristic("chebyshev")


def test_heuristic_callable_from_config():
    # Simulates what the algorithm runner does:
    # reads heuristic name from config, gets function, calls it
    config = {"heuristic": "manhattan"}
    fn = get_heuristic(config["heuristic"])
    assert fn(0, 0, 5, 5) == 10
