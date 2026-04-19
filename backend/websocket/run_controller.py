# backend/websocket/run_controller.py
#
# The RunController is the director of the simulation.
# It knows the score: which algorithms to run, in which order, against
# which deliveries. It delegates all actual work to the components it
# coordinates: GridBuilder builds the grid, AlgorithmRunners navigate it,
# StackTraceBuilders record the journey, MetricsCollector tallies the cost.
#
# ── why synchronous? ──────────────────────────────────────────────────────────
# The algorithms are CPU-bound (tight while loops over a priority queue).
# Async/await adds no benefit when there is no I/O to overlap.
# The RunController is synchronous and is called from FastAPI via
# run_in_executor, which pushes it into a ThreadPoolExecutor so it
# does not block the async event loop. This is the correct pattern for
# CPU-bound work in an async Python application.
#
# ── single responsibility ─────────────────────────────────────────────────────
# The RunController does NOT know how to:
#   - build a grid (GridBuilder)
#   - navigate it (AlgorithmRunner)
#   - record the search (StackTraceBuilder)
#   - measure performance (MetricsCollector — built into base_runner)
# It only knows the ORDER and COORDINATION of those operations.

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from backend.algorithms.algorithms_registry import get_runner
from backend.engine.event_bus import EventBus
from backend.engine.grid_builder import GridBuilder, GridBuilderError
from backend.engine.profile_manager import ProfileManager
from backend.trace.trace_builder import StackTraceBuilder, TraceBuilderError


# ── run status ─────────────────────────────────────────────────────────────────


class RunStatus(str, Enum):
    """
    Lifecycle states of a simulation run.

    Using str + Enum means the values are valid JSON strings without
    extra serialisation — status can be included directly in event dicts.
    """
    PENDING   = "pending"    # Created, not yet started
    RUNNING   = "running"    # Algorithms are executing
    COMPLETE  = "complete"   # All deliveries done, all algorithms finished
    FAILED    = "failed"     # An unrecoverable error occurred


# ── result containers ──────────────────────────────────────────────────────────


@dataclass
class DeliveryResult:
    """
    Results for one delivery destination across all enabled algorithms.

    Groups results by delivery so the frontend can show per-destination
    performance comparison: "For Delivery 3, which algorithm was cheapest?"
    """
    delivery_id: str
    destination: dict                         # {id, x, y, label}
    metrics:     list[dict] = field(default_factory=list)   # one per algorithm
    graphs:      list[dict] = field(default_factory=list)   # TraceGraph per algorithm


@dataclass
class RunResult:
    """
    Complete results of one full simulation run.

    Contains:
      - All MetricsSummary dicts (one per algorithm per delivery)
      - All TraceGraph dicts (one per algorithm per delivery)
      - Run metadata (id, profile info, status)

    This is what the /run/{run_id}/results REST endpoint returns.
    It is also serialised and published as a "simulation_complete" event
    on the EventBus so the frontend receives it via WebSocket.
    """
    run_id:           str
    profile_name:     str
    seed:             int
    status:           RunStatus
    delivery_results: list[DeliveryResult] = field(default_factory=list)
    error:            str | None = None

    def all_metrics(self) -> list[dict]:
        """Flat list of every MetricsSummary across all deliveries."""
        result = []
        for dr in self.delivery_results:
            result.extend(dr.metrics)
        return result

    def all_graphs(self) -> list[dict]:
        """Flat list of every TraceGraph across all deliveries."""
        result = []
        for dr in self.delivery_results:
            result.extend(dr.graphs)
        return result


# ── main class ─────────────────────────────────────────────────────────────────


class RunController:
    """
    Orchestrates a full simulation run: all algorithms × all deliveries.

    Usage (synchronous, called from a thread):
        controller = RunController(profile, bus)
        result = controller.run()

    Usage (from FastAPI, non-blocking):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, controller.run)

    ── execution order ───────────────────────────────────────────────────
    For each delivery destination D (sequential, robot visits in order):
      For each enabled algorithm A:
        1. Create a StackTraceBuilder(A, D, bus)
        2. Emit "algorithm_start" (bus handles WS broadcast)
        3. Run A from previous endpoint to D
        4. Collect MetricsSummary from the runner
        5. Collect TraceGraph from the builder (it finalises on delivery_complete)
        6. builder.detach() — clean up subscription

    After all deliveries:
      7. Emit "simulation_complete" with full RunResult
      8. Return RunResult to caller

    ── why sequential deliveries, parallel algorithms is NOT done ────────
    We could run all 5 algorithms against one delivery in parallel
    (separate threads, separate builders). But:
      - Python's GIL limits true parallelism on pure-Python code
      - The EventBus is not thread-safe for concurrent publishes
      - The bus buffer ordering would be non-deterministic, breaking playback
    Sequential is correct for this simulator. If we needed true parallelism,
    we would partition the bus (one bus per algorithm) — a larger rearchitecture
    not needed at 15×15 scale.

    ── progress callbacks ────────────────────────────────────────────────
    The controller accepts optional callbacks for progress reporting.
    These are called synchronously from the run thread, so they must be
    either fast (just enqueue something) or thread-safe. The FastAPI
    server uses these to push progress events to WS clients.
    """

    def __init__(
        self,
        profile:      dict,
        bus:          EventBus,
        run_id:       str | None = None,
        profile_name: str = "unnamed",
        on_progress:  Callable[[str, dict], None] | None = None,
    ):
        """
        Parameters:
            profile      — validated CityProfile dict (from ProfileManager)
            bus          — shared EventBus (all events flow through here)
            run_id       — unique identifier for this run (generated if None)
            profile_name — human-readable name for logging and results
            on_progress  — optional callback(event_type, event_data) for
                           progress reporting (called from run thread)
        """
        self._profile      = profile
        self._bus          = bus
        self._run_id       = run_id or str(uuid.uuid4())
        self._profile_name = profile_name
        self._on_progress  = on_progress

        # Algorithms to run — only enabled ones from the profile
        self._algorithm_configs = [
            cfg for cfg in profile.get("algorithms", [])
            if cfg.get("enabled", False)
        ]

        # Lock for thread-safe status updates
        # The FastAPI server may read status from the main thread while
        # the run thread is updating it
        self._status_lock = threading.Lock()
        self._status      = RunStatus.PENDING

    # ── public ──────────────────────────────────────────────────────────────────

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def status(self) -> RunStatus:
        with self._status_lock:
            return self._status

    def run(self) -> RunResult:
        """
        Execute the full simulation. Blocking — call from a thread.

        Returns a RunResult with all metrics and trace graphs.
        Also emits a "simulation_complete" event on the bus when done,
        which the WebSocket server forwards to all connected clients.

        If any error occurs, sets status to FAILED and includes the
        error message in RunResult. Partial results (from deliveries
        that completed before the error) are preserved.
        """
        self._set_status(RunStatus.RUNNING)

        result = RunResult(
            run_id=self._run_id,
            profile_name=self._profile_name,
            seed=self._profile["meta"]["seed"],
            status=RunStatus.RUNNING,
        )

        try:
            # ── step 1: build the grid ─────────────────────────────────────────
            cells = GridBuilder().build(self._profile)

            self._emit_progress("grid_built", {
                "run_id":    self._run_id,
                "cell_count": len(cells),
            })

            # ── step 2: run each delivery in sequence ──────────────────────────
            destinations = self._profile["deliveries"]["destinations"]

            for delivery in destinations:
                delivery_result = self._run_delivery(cells, delivery)
                result.delivery_results.append(delivery_result)

            # ── step 3: wrap up ────────────────────────────────────────────────
            result.status = RunStatus.COMPLETE
            self._set_status(RunStatus.COMPLETE)

            self._bus.publish({
                "event_type":   "simulation_complete",
                "run_id":       self._run_id,
                "profile_name": self._profile_name,
                "total_metrics": result.all_metrics(),
            })

        except GridBuilderError as e:
            result.status = RunStatus.FAILED
            result.error  = f"Grid building failed: {e}"
            self._set_status(RunStatus.FAILED)
            self._bus.publish({
                "event_type": "simulation_error",
                "run_id":     self._run_id,
                "error":      result.error,
            })

        except Exception as e:
            result.status = RunStatus.FAILED
            result.error  = f"Unexpected error: {e}"
            self._set_status(RunStatus.FAILED)
            self._bus.publish({
                "event_type": "simulation_error",
                "run_id":     self._run_id,
                "error":      result.error,
            })

        return result

    # ── private ─────────────────────────────────────────────────────────────────

    def _run_delivery(self, cells: list[dict], delivery: dict) -> DeliveryResult:
        """
        Runs all enabled algorithms against one delivery destination.

        The robot navigates from the base station to this delivery.
        Each algorithm gets a fresh StackTraceBuilder and runs independently.
        Results are collected and returned as a DeliveryResult.
        """
        delivery_id  = delivery["id"]
        delivery_result = DeliveryResult(
            delivery_id=delivery_id,
            destination=delivery,
        )

        # Find start cell (base station) and goal cell
        cell_map  = {c["id"]: c for c in cells}
        start_key = "{x},{y}".format(**self._profile["robot"]["start"])
        goal_key  = "{x},{y}".format(**delivery)

        start_cell = cell_map[start_key]
        goal_cell  = cell_map[goal_key]

        self._emit_progress("delivery_start", {
            "run_id":      self._run_id,
            "delivery_id": delivery_id,
            "start":       {"x": start_cell["x"], "y": start_cell["y"]},
            "goal":        {"x": goal_cell["x"],  "y": goal_cell["y"]},
        })

        # ── run each algorithm ─────────────────────────────────────────────────
        for algo_config in self._algorithm_configs:
            algo_id = algo_config["id"]

            # Create a builder for this (algorithm, delivery) pair
            builder = StackTraceBuilder(algo_id, delivery_id, self._bus)

            try:
                self._emit_progress("algorithm_start", {
                    "run_id":       self._run_id,
                    "delivery_id":  delivery_id,
                    "algorithm_id": algo_id,
                })

                # Run the algorithm — synchronous, emits events to bus
                runner  = get_runner(algo_id, self._bus)
                metrics = runner.run(cells, start_cell, goal_cell, algo_config)

                # BaseRunner._make_metrics sets delivery_id to the cell id
                # string (e.g. "7,3"). Override it with the logical delivery
                # label ("D1"…"D5") so the frontend can group metrics correctly.
                metrics["delivery_id"] = delivery_id

                # Collect results
                delivery_result.metrics.append(metrics)

                # TraceGraph was published via "trace_graph_ready" event
                # by the builder's _on_delivery_complete handler.
                # We also grab it here for the RunResult return value.
                if builder.is_complete():
                    try:
                        graph = builder.finalize()
                        delivery_result.graphs.append(graph)
                    except TraceBuilderError:
                        # visualize=False in config — no graph, that's ok
                        pass

                self._emit_progress("algorithm_complete", {
                    "run_id":        self._run_id,
                    "delivery_id":   delivery_id,
                    "algorithm_id":  algo_id,
                    "path_found":    metrics["path_found"],
                    "path_cost":     metrics["path_cost"],
                    "nodes_explored": metrics["nodes_explored"],
                })

            finally:
                # Always detach — even if the algorithm raised an exception
                builder.detach()

        return delivery_result

    def _set_status(self, status: RunStatus) -> None:
        """Thread-safe status update."""
        with self._status_lock:
            self._status = status

    def _emit_progress(self, event_type: str, data: dict) -> None:
        """
        Emits a progress event to both the EventBus and the optional callback.

        The EventBus handles WS broadcasting.
        The callback handles any additional notification (e.g. logging).
        """
        event = {"event_type": event_type, **data}
        self._bus.publish(event)

        if self._on_progress:
            self._on_progress(event_type, data)
