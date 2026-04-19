# backend/algorithms/greedy.py

import heapq

from algorithms.base_runner import BaseRunner


class GreedyRunner(BaseRunner):
    """
    Greedy Best-First Search.

    Frontier: Min-heap priority queue ordered by h (heuristic estimate).
    Always expands the node that looks closest to the goal.

    Optimal: NO. The heuristic can mislead it badly.
    Fast: YES in practice on open grids without many obstacles.
    Heuristic: manhattan (default) or euclidean.

    The classic failure case: imagine a wall between the robot
    and the goal. Greedy runs straight at the wall, hits it,
    panics, and has to backtrack. A* would have anticipated the
    wall by considering the cost already paid (g).

    Greedy has no memory of how expensive the path was to get here.
    It only asks "how far do I think I still have to go?"
    """

    def _init_frontier(self) -> None:
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
        # Greedy only cares about estimated distance to goal — ignore g
        return h
