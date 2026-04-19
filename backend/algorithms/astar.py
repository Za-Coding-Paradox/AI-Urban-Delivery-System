# backend/algorithms/astar.py

import heapq

from algorithms.base_runner import BaseRunner


class AStarRunner(BaseRunner):
    """
    A* Search.

    Frontier: Min-heap priority queue ordered by f = g + h.
    Balances actual cost paid (g) with estimated remaining cost (h).

    Optimal: YES — if the heuristic is admissible (never overestimates).
    Complete: YES — will always find a path if one exists.
    Heuristic: manhattan or euclidean.

    A* is the synthesis of UCS and Greedy:
      UCS    → uses g only → optimal but slow (explores everywhere)
      Greedy → uses h only → fast but not optimal (can be misled)
      A*     → uses g + h  → optimal AND focused toward the goal

    Why does f = g + h work?
    g is what you have already paid. You can't change it.
    h is what you estimate you still need to pay. It's a guess.
    f is your best estimate of the total path cost through this node.
    By always expanding the node with the lowest f,
    you are always pursuing the most promising total path first.

    This is the algorithm that powers Google Maps, game AI,
    robot navigation, and most real-world pathfinding.
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
        # The one line that makes A* what it is
        return g + h
