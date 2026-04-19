# backend/algorithms/dfs.py

from collections import deque

from backend.algorithms.base_runner import BaseRunner


class DFSRunner(BaseRunner):
    """
    Depth-First Search.

    Frontier: Stack (LIFO — Last In, First Out)
    Always explores the most recently discovered node next.
    Dives as deep as possible before backtracking.

    Optimal: NO. Finds A path, almost never THE best path.
    Complete: NO on infinite graphs, YES on our finite 15x15 grid.
    Heuristic: none.

    Why LIFO? Because we want to follow one branch all the way
    to the end before trying another. The most recent node is
    always the deepest one on the current branch.

    Fun observation: DFS and BFS are literally identical code
    except appendleft vs append on one line. The data structure
    IS the algorithm. This is why the base class design works so well.
    """

    def _init_frontier(self) -> None:
        self._frontier: deque = deque()

    def _push(self, node: dict, priority) -> None:
        # Add to the RIGHT end — same as BFS
        self._frontier.append(node)

    def _pop(self) -> dict:
        # Remove from the RIGHT end — newest item first
        # This one line is the entire difference from BFS
        return self._frontier.pop()

    def _is_empty(self) -> bool:
        return len(self._frontier) == 0

    def _frontier_size(self) -> int:
        return len(self._frontier)

    def _priority(self, g: float, h: float):
        return None
