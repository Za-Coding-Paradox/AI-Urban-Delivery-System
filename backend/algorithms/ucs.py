# backend/algorithms/ucs.py

import heapq

from algorithms.base_runner import BaseRunner


class UCSRunner(BaseRunner):
    """
    Uniform Cost Search.

    Frontier: Min-heap priority queue ordered by g (cost from start).
    Always expands the cheapest node discovered so far.

    Optimal: YES for cost. Guaranteed to find the minimum cost path.
    Heuristic: none (h=0, only g matters).

    This is Dijkstra's algorithm under a different name.
    The only difference is Dijkstra traditionally works on
    the full graph at once. UCS discovers the graph lazily
    as it searches — which is what we want for a simulation.

    Why a heap? Because we always want the minimum g node next.
    A heap gives us the minimum in O(1) and insertion in O(log n).
    Sorting the whole list every time would be O(n log n) per step.
    """

    def _init_frontier(self) -> None:
        # heapq in Python is a min-heap —
        # the smallest item always comes out first.
        # We store tuples: (priority, counter, node)
        # The counter breaks ties when priorities are equal —
        # without it Python tries to compare dicts and crashes.
        self._frontier: list = []
        self._counter: int = 0

    def _push(self, node: dict, priority) -> None:
        heapq.heappush(self._frontier, (priority, self._counter, node))
        self._counter += 1

    def _pop(self) -> dict:
        _, _, node = heapq.heappop(self._frontier)
        return node

    def _is_empty(self) -> bool:
        return len(self._frontier) == 0

    def _frontier_size(self) -> int:
        return len(self._frontier)

    def _priority(self, g: float, h: float) -> float:
        # UCS only cares about cost so far — ignore h completely
        return g
