# backend/algorithms/__init__.py

from backend.algorithms.astar import AStarRunner
from backend.algorithms.bfs import BFSRunner
from backend.algorithms.dfs import DFSRunner
from backend.algorithms.greedy import GreedyRunner
from backend.algorithms.ucs import UCSRunner
from backend.engine.event_bus import EventBus

ALGORITHM_REGISTRY = {
    "bfs": BFSRunner,
    "dfs": DFSRunner,
    "ucs": UCSRunner,
    "greedy": GreedyRunner,
    "astar": AStarRunner,
}


def get_runner(algorithm_id: str, bus: EventBus):
    if algorithm_id not in ALGORITHM_REGISTRY:
        raise ValueError(
            f"Unknown algorithm '{algorithm_id}'. Available: {list(ALGORITHM_REGISTRY.keys())}"
        )
    return ALGORITHM_REGISTRY[algorithm_id](bus)
