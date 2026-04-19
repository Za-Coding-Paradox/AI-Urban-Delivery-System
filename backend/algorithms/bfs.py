# backend/algorithms/bfs.py

from collections import deque

from algorithms.base_runner import BaseRunner


class BFSRunner(BaseRunner):
    """
    Breadth-First Search.

    Frontier: Queue (FIFO — First In, First Out)
    Explores nodes in the exact order they were discovered.
    Ring by ring outward from the start — like ripples in water.

    Optimal: YES for hop count (number of steps).
    Optimal: NO for cost (ignores cell costs entirely).
    Heuristic: none (uses zero heuristic).

    Why FIFO? Because we want to finish exploring everything
    at distance 1 before moving to distance 2.
    A queue guarantees this — oldest items come out first.
    """

    def _init_frontier(self) -> None:
        # deque is Python's double-ended queue
        # appendleft/popleft = O(1)
        # A regular list would work but list.pop(0) is O(n) —
        # it shifts every element left after removing the first.
        # On 225 cells the difference is invisible,
        # but deque is the correct tool regardless.
        self._frontier: deque = deque()

    def _push(self, node: dict, priority) -> None:
        # Add to the RIGHT end of the queue
        self._frontier.append(node)

    def _pop(self) -> dict:
        # Remove from the LEFT end — oldest item first
        return self._frontier.popleft()

    def _is_empty(self) -> bool:
        return len(self._frontier) == 0

    def _frontier_size(self) -> int:
        return len(self._frontier)

    def _priority(self, g: float, h: float):
        # BFS doesn't use priority — insertion order is the priority
        # We return None and _push ignores it
        return None
