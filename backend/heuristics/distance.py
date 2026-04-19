# backend/heuristics/distance.py

import math
from typing import Protocol

# ── what a "position" looks like ───────────────────────────────────────────────
# A Protocol is like a contract. It says: "anything I accept must have
# an x and a y attribute that are numbers."
# This is called structural typing — we don't care what class it is,
# only that it has the right shape.
#
# Alternative: just use tuples (x, y) everywhere.
# Pro of tuples: simpler, no Protocol needed.
# Con of tuples: less readable — (7, 3) tells you nothing,
#                but node.x=7, node.y=3 is self-documenting.
# We use dicts in practice, so we access pos["x"] — the Protocol
# documents the expected shape without enforcing a class.


class Position(Protocol):
    x: int
    y: int


# ── heuristic functions ────────────────────────────────────────────────────────


def manhattan(ax: int, ay: int, bx: int, by: int) -> int:
    """
    Manhattan distance between two grid positions.

    Named after Manhattan island — you can only move in 4 directions,
    like walking city blocks. No diagonals.

    Formula: |ax - bx| + |ay - by|

    Why integers? On a cardinal grid with integer coordinates,
    Manhattan distance is always a whole number. No rounding needed.

    Admissible: YES — never overestimates on a cardinal grid.
    Consistent: YES — satisfies the triangle inequality.
                      (consistency is a stronger property than admissibility
                       and guarantees A* never re-expands a node)

    When to use: cardinal movement grids. This is our default.
    """
    return abs(ax - bx) + abs(ay - by)


def euclidean(ax: int, ay: int, bx: int, by: int) -> float:
    """
    Euclidean distance between two grid positions.

    The straight-line "as the crow flies" distance.
    Ignores walls, grid structure, everything — pure geometry.

    Formula: sqrt((ax - bx)² + (ay - by)²)

    Why float? sqrt() produces a decimal number. A diagonal
    on a unit grid is sqrt(2) ≈ 1.414, not a whole number.

    Admissible: YES — straight line is always ≤ real path on a grid.
    Consistent: YES.

    Looser than Manhattan on cardinal grids — underestimates more,
    so A* explores slightly more nodes before committing to the best path.

    When to use: when you want to compare A* behavior with a different
    heuristic, or when diagonal movement is added later.
    """
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def zero(ax: int, ay: int, bx: int, by: int) -> int:
    """
    The null heuristic. Always returns 0.

    When h = 0, A* becomes UCS — it ignores the goal entirely
    and expands purely by cost from start.

    This is not a mistake. BFS and DFS don't use heuristics at all.
    Rather than special-casing them ("if algorithm is BFS, skip heuristic"),
    we give them this function. They call it, get 0, and the math works
    out correctly with no branching logic needed in the algorithm code.

    This is called the Null Object Pattern — instead of checking for None,
    you provide an object that does nothing but satisfies the interface.

    Admissible: YES — 0 never overestimates anything.
    """
    return 0


# ── heuristic registry ─────────────────────────────────────────────────────────
# A dict that maps the string names from AlgorithmConfig JSON
# to the actual functions above.
#
# Why a dict and not if/elif?
# Because if/elif is code. This dict is data.
# Adding a new heuristic = adding one line to this dict.
# Adding a new heuristic with if/elif = editing existing code, risking breakage.
#
# This pattern is called a Dispatch Table.
# It's one of the most important patterns in data-driven systems.
#
# Alternative: match/case statement (Python 3.10+)
# Pro: readable, explicit.
# Con: still code. Still requires editing existing logic to add new options.
#
# Alternative: auto-discover functions by name using getattr()
# Pro: zero registration needed — just name a function "manhattan" and it works.
# Con: magic. Invisible. Hard to debug. New developers don't know what's available.
#
# The dict wins because it's explicit, data-driven, and one line to extend.

HEURISTIC_REGISTRY: dict[str, callable] = {
    "manhattan": manhattan,
    "euclidean": euclidean,
    "none": zero,
}


def get_heuristic(name: str) -> callable:
    """
    Returns the heuristic function for the given name.
    Name comes from AlgorithmConfig JSON — "manhattan", "euclidean", or "none".

    Raises ValueError if the name isn't registered.
    This is intentional — an unknown heuristic name is a configuration error
    and should fail loudly at startup, not silently during a run.
    """
    if name not in HEURISTIC_REGISTRY:
        raise ValueError(
            f"Unknown heuristic '{name}'. Available: {list(HEURISTIC_REGISTRY.keys())}"
        )
    return HEURISTIC_REGISTRY[name]
