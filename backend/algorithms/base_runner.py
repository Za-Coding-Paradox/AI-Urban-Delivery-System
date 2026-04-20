# backend/algorithms/base_runner.py

import time
from abc import ABC, abstractmethod
from typing import Any

from backend.engine.event_bus import EventBus
from backend.heuristics.distance import get_heuristic


class BaseRunner(ABC):
    """
    The shared foundation for all five search algorithms.

    What lives here (shared by all):
      - Grid access helpers
      - Neighbor finding (cardinal movement)
      - TraceEvent construction and emission
      - Metrics accumulation
      - The run() entry point

    What does NOT live here (defined by each child):
      - The frontier data structure
      - How to push a node onto the frontier
      - How to pop the next node from the frontier
      - Whether the frontier is empty

    ABC means Abstract Base Class.
    You cannot instantiate BaseRunner directly — it is a template.
    You can only instantiate BFSRunner, DFSRunner, etc.

    Why ABC and not just a regular class?
    Because if someone tries to create a BaseRunner() directly,
    Python will raise an error immediately telling them they forgot
    to implement the required methods. Without ABC, it would fail
    silently in a confusing way much later.
    """

    # Cardinal directions — up, down, left, right
    # No diagonals — matches the assignment spec and RobotConfig "cardinal"
    DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0)]

    def __init__(self, bus: EventBus):
        self._bus = bus

    # ── public entry point ─────────────────────────────────────────────────────

    def run(
        self,
        cells: list[dict],
        start: dict,
        goal: dict,
        config: dict,
    ) -> dict:
        """
        Execute this algorithm from start to goal on the given grid.

        Parameters:
            cells  — the Cell[225] list from GridBuilder
            start  — the cell dict where the robot starts
            goal   — the cell dict for this delivery destination
            config — AlgorithmConfig dict from the profile

        Returns a MetricsSummary dict.

        This method is the same for all five algorithms.
        The only thing that differs is what happens inside
        _push(), _pop(), and _is_empty() — which each child defines.
        """
        algo_id = config["id"]
        heuristic = get_heuristic(config["heuristic"])

        # delivery_id is the logical label ("D1"…"D5") stored in goal["label"].
        # It is used on every emitted event so the frontend can bucket events
        # by (algorithm_id, delivery_id) for per-pair playback.
        # Fall back to the cell id string if label is missing (should never happen).
        delivery_id: str = goal.get("delivery_id", "")

        # Build a fast lookup dict: "x,y" → cell
        # O(1) access instead of scanning 225 cells every time
        cell_map = {cell["id"]: cell for cell in cells}

        # Initialise the frontier with the start node
        # g=0 because we haven't moved yet, cost from start is zero
        self._init_frontier()

        start_node = self._make_node(
            cell=start,
            g=0,
            h=heuristic(start["x"], start["y"], goal["x"], goal["y"]),
            depth=0,
            parent_id=None,
        )
        self._push(start_node, priority=0)

        # visited tracks cells we have already expanded
        # Using a set of cell id strings for O(1) lookup
        # e.g. {"0,0", "1,0", "2,0"}
        visited: set[str] = set()

        # step counts every node operation for the TraceEvent
        step = 0
        start_time = time.perf_counter()

        # Emit algorithm_start event so the frontend knows we began.
        # delivery_id is included so the frontend store can route this event
        # to the correct (algo, delivery) segment bucket.
        self._bus.publish(
            {
                "event_type": "algorithm_start",
                "algorithm_id": algo_id,
                "delivery_id": delivery_id,
                "start_id": start["id"],
                "goal_id": goal["id"],
            }
        )

        # ── main search loop ───────────────────────────────────────────────────
        while not self._is_empty():
            node = self._pop()
            cell_id = node["id"]

            # Skip if we already expanded this cell
            # This matters for UCS and A* where a cell can be
            # pushed multiple times with different g values
            if cell_id in visited:
                continue

            visited.add(cell_id)
            step += 1

            # Emit node_expand event — this node is being processed
            self._emit_node_event(
                event_type="node_expand",
                node=node,
                status="closed",
                algo_id=algo_id,
                delivery_id=delivery_id,
                step=step,
                frontier_size=self._frontier_size(),
                visited_count=len(visited),
            )

            # ── goal check ─────────────────────────────────────────────────────
            if cell_id == goal["id"]:
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                # Reconstruct path by following parent_id chain back to start
                path = self._reconstruct_path(node)

                # Emit path events so the frontend can highlight the path
                for path_cell in path:
                    self._bus.publish(
                        {
                            "event_type": "path_step",
                            "algorithm_id": algo_id,
                            "delivery_id": delivery_id,
                            "node": {
                                **path_cell,
                                "status": "path",
                            },
                            "step": step,
                            "timestamp_ms": (time.perf_counter() - start_time) * 1000,
                            "edge": None,
                            "frontier_size": 0,
                            "visited_count": len(visited),
                        }
                    )

                self._bus.publish(
                    {
                        "event_type": "delivery_complete",
                        "algorithm_id": algo_id,
                        "delivery_id": delivery_id,
                        "goal_id": goal["id"],
                        "step": step,
                    }
                )

                return self._make_metrics(
                    algo_id=algo_id,
                    goal_id=goal["id"],
                    path=path,
                    path_cost=node["g"],
                    elapsed_ms=elapsed_ms,
                    nodes_explored=len(visited),
                    heuristic_used=config["heuristic"],
                    path_found=True,
                )

            # ── expand neighbours ──────────────────────────────────────────────
            for neighbour_cell in self._get_neighbours(cell_id, cell_map):
                n_id = neighbour_cell["id"]

                if n_id in visited:
                    continue

                # Calculate g cost for this neighbour
                # edge_cost model: cost is the neighbour's traversal cost
                # node_cost model: same in our implementation
                new_g = node["g"] + neighbour_cell["cost"]
                new_h = heuristic(
                    neighbour_cell["x"],
                    neighbour_cell["y"],
                    goal["x"],
                    goal["y"],
                )
                new_f = new_g + new_h
                new_depth = node["depth"] + 1

                neighbour_node = self._make_node(
                    cell=neighbour_cell,
                    g=new_g,
                    h=new_h,
                    depth=new_depth,
                    parent_id=cell_id,
                    parent_node=node,
                )

                step += 1

                # Determine edge type for the 3D graph
                edge_type = self._edge_type(node, neighbour_node)

                # Emit node_visit event — we are considering this neighbour
                self._emit_node_event(
                    event_type="node_visit",
                    node=neighbour_node,
                    status="open",
                    algo_id=algo_id,
                    delivery_id=delivery_id,
                    step=step,
                    frontier_size=self._frontier_size(),
                    visited_count=len(visited),
                    edge={
                        "from_id": cell_id,
                        "to_id": n_id,
                        "edge_type": edge_type,
                        "cost": neighbour_cell["cost"],
                    },
                )

                self._push(neighbour_node, priority=self._priority(new_g, new_h))

        # ── no path found ──────────────────────────────────────────────────────
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        self._bus.publish(
            {
                "event_type": "path_found",
                "algorithm_id": algo_id,
                "delivery_id": delivery_id,
                "path_found": False,
                "goal_id": goal["id"],
            }
        )

        return self._make_metrics(
            algo_id=algo_id,
            goal_id=goal["id"],
            path=[],
            path_cost=0,
            elapsed_ms=elapsed_ms,
            nodes_explored=len(visited),
            heuristic_used=config["heuristic"],
            path_found=False,
        )

    # ── abstract methods — each child MUST implement these ────────────────────

    @abstractmethod
    def _init_frontier(self) -> None:
        """Initialise the frontier data structure."""

    @abstractmethod
    def _push(self, node: dict, priority: Any) -> None:
        """Add a node to the frontier."""

    @abstractmethod
    def _pop(self) -> dict:
        """Remove and return the next node to explore."""

    @abstractmethod
    def _is_empty(self) -> bool:
        """Is the frontier empty?"""

    @abstractmethod
    def _frontier_size(self) -> int:
        """How many nodes are currently in the frontier?"""

    @abstractmethod
    def _priority(self, g: float, h: float) -> Any:
        """
        Compute the priority for a node given its g and h values.
        BFS/DFS ignore this — they use insertion order.
        UCS uses g. Greedy uses h. A* uses g + h.
        """

    # ── shared helpers — same for all five algorithms ─────────────────────────

    def _get_neighbours(self, cell_id: str, cell_map: dict[str, dict]) -> list[dict]:
        """
        Returns all passable cardinal neighbours of a cell.

        Parses the cell_id string "x,y" to get coordinates.
        Checks grid bounds (0–14).
        Skips obstacles (passable=False).
        """
        x, y = map(int, cell_id.split(","))
        neighbours = []

        for dx, dy in self.DIRECTIONS:
            nx, ny = x + dx, y + dy

            if not (0 <= nx <= 14 and 0 <= ny <= 14):
                continue

            neighbour_id = f"{nx},{ny}"
            cell = cell_map.get(neighbour_id)

            if cell and cell["passable"]:
                neighbours.append(cell)

        return neighbours

    def _make_node(
        self,
        cell: dict,
        g: float,
        h: float,
        depth: int,
        parent_id: str | None,
        parent_node: dict | None = None,
    ) -> dict:
        """
        Builds a search node dict.

        A search node is NOT the same as a grid cell.
        The grid cell is fixed — it has a type and a cost.
        The search node wraps the cell with algorithm-specific data:
        g (cost so far), h (heuristic estimate), depth, parent.

        The same grid cell can appear as multiple search nodes
        with different g values if reached by different paths.
        This is critical to understand for UCS and A*.
        """
        return {
            # Identity
            "id": cell["id"],
            "x": cell["x"],
            "y": cell["y"],
            "cell_type": cell["type"],
            # Algorithm values
            "g": g,
            "h": h,
            "f": g + h,
            "depth": depth,
            "parent_id": parent_id,
            # Store full parent node for path reconstruction
            # This is NOT emitted in TraceEvents — internal only
            "_parent": parent_node,
            "status": "open",
        }

    def _reconstruct_path(self, goal_node: dict) -> list[dict]:
        """
        Traces the parent chain from goal back to start.
        Returns the path as a list of node dicts from start to goal.

        This works because every node stores a reference to its parent.
        We follow the chain: goal → parent → grandparent → ... → start.
        Then reverse it so the path reads start → goal.
        """
        path = []
        current = goal_node

        while current is not None:
            path.append(current)
            current = current.get("_parent")

        path.reverse()
        return path

    def _emit_node_event(
        self,
        event_type: str,
        node: dict,
        status: str,
        algo_id: str,
        step: int,
        frontier_size: int,
        visited_count: int,
        delivery_id: str = "",
        edge: dict | None = None,
    ) -> None:
        """
        Constructs and publishes one TraceEvent.
        Strips internal fields (_parent) before emitting
        so the event matches the schema exactly.
        delivery_id is included so the frontend can bucket events
        by (algorithm_id, delivery_id) for per-pair playback.
        """
        import time

        self._bus.publish(
            {
                "event_type": event_type,
                "step": step,
                "timestamp_ms": time.perf_counter() * 1000,
                "algorithm_id": algo_id,
                "delivery_id": delivery_id,
                "node": {
                    "id": node["id"],
                    "x": node["x"],
                    "y": node["y"],
                    "cell_type": node["cell_type"],
                    "g": node["g"],
                    "h": node["h"],
                    "f": node["f"],
                    "depth": node["depth"],
                    "parent_id": node["parent_id"],
                    "status": status,
                },
                "edge": edge,
                "frontier_size": frontier_size,
                "visited_count": visited_count,
            }
        )

    def _edge_type(self, parent: dict, child: dict) -> str:
        """
        Determines the visual edge type for the 3D graph.
        DFS backtracks — its edges are visually different from expansion edges.
        All other algorithms just expand forward.
        """
        # DFS is identified by the runner class name
        # This is the one place we break the abstraction slightly —
        # it is acceptable because edge_type is purely visual metadata
        if self.__class__.__name__ == "DFSRunner":
            return "backtrack"
        return "expansion"

    @staticmethod
    def _make_metrics(
        algo_id: str,
        goal_id: str,
        path: list[dict],
        path_cost: float,
        elapsed_ms: float,
        nodes_explored: int,
        heuristic_used: str,
        path_found: bool,
    ) -> dict:
        """Builds the MetricsSummary dict."""
        return {
            "algorithm_id": algo_id,
            "delivery_id": goal_id,
            "path_cost": path_cost,
            "execution_time_ms": elapsed_ms,
            "nodes_explored": nodes_explored,
            "path_length": len(path),
            "path_found": path_found,
            "path": [{"x": node["x"], "y": node["y"]} for node in path],
            "heuristic_used": heuristic_used,
        }
