# backend/trace/trace_builder.py
#
# The StackTraceBuilder is the bridge between the algorithm engine and
# the 3D visualisation layer. Algorithms speak in TraceEvents; the 3D graph
# speaks in TraceGraphs. This module translates between those two worlds.
#
# ── mental model ──────────────────────────────────────────────────────────────
# Imagine the algorithm is a reporter filing dispatches from the field.
# Every time it touches a node it sends a brief ("node_visit", "node_expand").
# The StackTraceBuilder is the editor back at the desk assembling those
# dispatches into a coherent story — the search tree — that the reader
# (the 3D graph) can navigate.

from __future__ import annotations

from typing import Callable

from backend.engine.event_bus import EventBus


# ── custom exception ───────────────────────────────────────────────────────────


class TraceBuilderError(Exception):
    """Raised when the builder is used incorrectly or receives bad data."""
    pass


# ── main class ─────────────────────────────────────────────────────────────────


class StackTraceBuilder:
    """
    Subscribes to the EventBus and assembles a TraceGraph from the stream
    of TraceEvents emitted by one (algorithm_id, delivery_id) run.

    One builder = one algorithm run against one delivery destination.
    Create a fresh builder before each run. Call finalize() after the run
    completes to get the serialisable graph dict.

    ── design: subscriber pattern ─────────────────────────────────────────
    The builder registers once with subscribe_all() then filters by
    algorithm_id. This means multiple builders can coexist on the same bus —
    one per algorithm running in parallel — without interfering.

    Alternative: give each AlgorithmRunner a direct reference to a builder
    and call builder.record(event) explicitly.
    Pro of alternative: no EventBus coupling, cleaner data flow.
    Con: the runner would have to know about the builder, coupling algorithm
         logic to visualisation logic. The bus is the right decoupling point.
    The subscriber pattern wins here.

    ── design: node storage ───────────────────────────────────────────────
    Nodes are stored in a dict keyed by cell id ("x,y"). The same cell
    cannot appear twice in the output — the last status wins. This is
    intentional: we show "what happened to each cell" not "every time a
    cell was pushed onto the frontier".

    The status lifecycle is: open → closed → path (path is terminal,
    never downgraded). The 3D renderer renders one sphere per unique cell,
    coloured by its final status. This gives a clean, readable graph even
    on a large simulation.

    ── design: edge deduplication ────────────────────────────────────────
    Edges are keyed by (from_id, to_id) tuple. The priority order is:
    path > backtrack > expansion. A path edge overwrites an expansion edge
    for the same node pair. This is the desired behaviour — path edges
    should be visually dominant (thick line, fast particles) in the 3D graph.

    ── scalability note ──────────────────────────────────────────────────
    A 15×15 grid with 5 deliveries produces at most 225 unique nodes per
    algorithm and O(225) edges. TraceGraph size is O(cells) per run.
    At 5 algorithms × 5 deliveries = 25 runs, total memory is bounded
    and negligible. If the grid grows to NxN, memory scales as O(N²) per
    run — still manageable up to N≈1000 before needing compression.
    """

    def __init__(self, algorithm_id: str, delivery_id: str, bus: EventBus):
        self._algorithm_id = algorithm_id
        self._delivery_id  = delivery_id
        self._bus          = bus

        # Node store: cell_id → TraceNode dict
        # Updated in-place as status progresses open → closed → path
        self._nodes: dict[str, dict] = {}

        # Edge store: (from_id, to_id) → TraceEdge dict
        # Deduplicated — path edges overwrite lesser types
        self._edges: dict[tuple[str, str], dict] = {}

        # Running metadata — updated as events arrive so finalize() is O(1)
        self._max_depth:   int   = 0
        self._max_g:       float = 0.0
        self._max_f:       float = 0.0
        self._total_steps: int   = 0

        # Completion flag — set on delivery_complete
        self._complete: bool = False

        # Optional external callback — called when delivery_complete arrives
        # Used by RunController to know when it is safe to move to the next run
        self._on_complete_cb: Callable[[dict], None] | None = None

        # Register with the bus — from this moment all events flow here
        # We keep a reference to the bound method so we can unsubscribe later
        self._bus.subscribe_all(self._handle_event)

    # ── public API ─────────────────────────────────────────────────────────────

    def on_complete(self, callback: Callable[[dict], None]) -> None:
        """
        Register a callback to be invoked with the finished TraceGraph
        when delivery_complete is received.

        Usage (in RunController):
            builder.on_complete(lambda graph: results.append(graph))

        Why a callback instead of polling is_complete()?
        The algorithm runs synchronously. The RunController calls run() and
        then waits. The callback lets the RunController react to completion
        without polling in a loop, which would busy-wait and waste CPU.
        """
        self._on_complete_cb = callback

    def finalize(self) -> dict:
        """
        Returns the complete TraceGraph as a JSON-serialisable dict.

        This is the direct input to:
          - The 3D graph component (consumed by Three.js renderer)
          - The WebSocket broadcast (serialised and sent to frontend)
          - The export module (saved to disk for offline analysis)
          - Tests (structure assertions)

        The graph is a snapshot at the moment finalize() is called.
        Call it after is_complete() returns True for the authoritative
        final graph. Call it mid-run for a partial graph (useful for
        the playback scrub bar showing partial trees).

        Raises TraceBuilderError if called before any events arrived —
        this indicates a usage error (builder created but algorithm
        was never started, or visualize=False in AlgorithmConfig).
        """
        if not self._nodes and not self._complete:
            raise TraceBuilderError(
                f"finalize() called but no events received for "
                f"algorithm='{self._algorithm_id}', delivery='{self._delivery_id}'. "
                f"Ensure the algorithm config has visualize=True and the "
                f"algorithm was actually run."
            )

        return {
            "algorithm_id": self._algorithm_id,
            "delivery_id":  self._delivery_id,
            "nodes":        list(self._nodes.values()),
            "edges":        list(self._edges.values()),
            "metadata": {
                "total_steps": self._total_steps,
                "max_depth":   self._max_depth,
                "max_g":       self._max_g,
                "max_f":       self._max_f,
                "complete":    self._complete,
                "node_count":  len(self._nodes),
                "edge_count":  len(self._edges),
            },
        }

    def is_complete(self) -> bool:
        """True once delivery_complete has been received for our algorithm."""
        return self._complete

    def node_count(self) -> int:
        """How many unique grid cells have been recorded."""
        return len(self._nodes)

    def edge_count(self) -> int:
        """How many unique directed edges have been recorded."""
        return len(self._edges)

    def detach(self) -> None:
        """
        Unsubscribes this builder from the EventBus.

        ALWAYS call this after finalize() to prevent memory leaks.
        A builder that stays subscribed will receive every event from
        subsequent runs, wasting CPU and accumulating stale data.

        The RunController calls this automatically. If you use builders
        manually, call detach() in a try/finally:

            builder = StackTraceBuilder(algo_id, delivery_id, bus)
            try:
                runner.run(...)
                graph = builder.finalize()
            finally:
                builder.detach()

        Why "finally"? Because if the algorithm raises an exception,
        you still want to clean up the subscription. Leaked subscriptions
        are a silent bug — nothing breaks immediately, but over many runs
        the bus accumulates dead handlers and slows down.
        """
        # subscribe_all uses the "*" key internally — unsubscribe with "*"
        self._bus.unsubscribe("*", self._handle_event)

    # ── event dispatch ─────────────────────────────────────────────────────────

    def _handle_event(self, event: dict) -> None:
        """
        Single entry point for all EventBus events.

        Filters to our algorithm_id first — this is the critical gate.
        Without this filter, a builder for "bfs" would accumulate
        events from "astar" and produce a nonsensical mixed graph.

        After filtering, dispatches by event_type using a dict table.

        Why dispatch table instead of if/elif?
        Same reason as the heuristic registry: data is easier to extend
        than code. Adding a new event type = one dict line. With if/elif
        = editing existing logic, risking unintended side effects.

        The dispatch table is rebuilt on every call. This is intentional —
        the methods are bound at construction, so the dict creation is
        O(1) key lookups, not closures. Python dicts are fast enough that
        this has zero measurable overhead at our event volume.

        Alternative: build the dispatch dict once in __init__ as self._dispatch.
        Pro: marginal CPU saving.
        Con: the dict would hold strong references to self through bound
             methods, complicating garbage collection if you wanted to
             pool builders. Not worth the complexity at this scale.
        """
        # Gate 1: only process events from our algorithm
        if event.get("algorithm_id") != self._algorithm_id:
            return

        # Gate 2: only process events we care about
        dispatch: dict[str, Callable[[dict], None]] = {
            "node_visit":        self._on_node_visit,
            "node_expand":       self._on_node_expand,
            "path_step":         self._on_path_step,
            "delivery_complete": self._on_delivery_complete,
        }

        handler = dispatch.get(event["event_type"])
        if handler:
            handler(event)

    # ── event-specific handlers ─────────────────────────────────────────────────

    def _on_node_visit(self, event: dict) -> None:
        """
        A node was discovered and pushed onto the frontier. Status = "open".

        "Visit" means the algorithm noticed this neighbour and added it
        to the frontier for future expansion. The node has been evaluated
        (g, h, f computed) but not yet committed to.

        In the 3D graph: small blue pulsing sphere.

        We add the node if unseen. If already present (e.g. visited before
        with a different parent in UCS), we do NOT overwrite — the first
        visit establishes the node's identity. Status upgrades happen
        only in _on_node_expand and _on_path_step.
        """
        node_data = event.get("node")
        if not node_data:
            return

        node_id = node_data["id"]
        step    = event.get("step", 0)

        if node_id not in self._nodes:
            self._nodes[node_id] = self._build_node(node_data, step, "open")

        self._update_metadata(node_data, step)

        # Record the directed edge that brought us here
        edge_data = event.get("edge")
        if edge_data:
            self._record_edge(edge_data)

    def _on_node_expand(self, event: dict) -> None:
        """
        A node was popped from the frontier and expanded. Status = "closed".

        "Expand" means the algorithm committed to this node — it left the
        frontier and entered the visited set. It will not be processed again.

        In the 3D graph: medium purple sphere.

        This is the most common event in a typical search run. On a 15×15
        open grid, UCS will expand every cell before finding an optimal path.
        """
        node_data = event.get("node")
        if not node_data:
            return

        node_id = node_data["id"]
        step    = event.get("step", 0)

        if node_id in self._nodes:
            # Upgrade status: open → closed
            # But never downgrade from path — path is the terminal status
            if self._nodes[node_id]["status"] != "path":
                self._nodes[node_id]["status"] = "closed"
            self._nodes[node_id]["step"] = step
        else:
            # Start node is expanded without a prior visit event — handle it
            self._nodes[node_id] = self._build_node(node_data, step, "closed")

        self._update_metadata(node_data, step)

    def _on_path_step(self, event: dict) -> None:
        """
        This node is on the final optimal path. Status = "path" (terminal).

        Path status is the highest priority and is never downgraded.
        If a node is already closed, it becomes path. If somehow not yet
        recorded (shouldn't happen but we handle it defensively), it is added.

        In the 3D graph: medium green sphere, fast animated particles on edges.

        Additionally, we upgrade the edge leading *into* this node to
        edge_type="path" so it gets thick-line treatment in the renderer.
        Walking backwards through edges to find the parent is O(edges) but
        the path is at most 15+15=30 nodes long, so this is O(30) at worst.
        """
        node_data = event.get("node")
        if not node_data:
            return

        node_id = node_data["id"]
        step    = event.get("step", 0)

        if node_id in self._nodes:
            self._nodes[node_id]["status"] = "path"
        else:
            self._nodes[node_id] = self._build_node(node_data, step, "path")

        # Upgrade the incoming edge for this node to "path"
        # This makes the path visually pop out in the 3D graph
        for (from_id, to_id), edge in self._edges.items():
            if to_id == node_id and edge["edge_type"] != "path":
                edge["edge_type"] = "path"

    def _on_delivery_complete(self, event: dict) -> None:
        """
        The algorithm reached the delivery destination.

        Mark complete, publish the finished graph back onto the bus
        (so the WebSocket server can forward it), and invoke any
        registered callback.

        Why publish back to the bus?
        The RunController subscribes to "trace_graph_ready" events.
        This lets it collect all finished graphs without polling builders.
        The server also forwards this event to WebSocket clients so the
        frontend can trigger 3D graph rendering immediately.
        """
        self._complete = True

        finished_graph = self.finalize()

        # Publish back to bus — RunController and WS server both consume this
        self._bus.publish({
            "event_type":   "trace_graph_ready",
            "algorithm_id": self._algorithm_id,
            "delivery_id":  self._delivery_id,
            "graph":        finished_graph,
        })

        # Invoke optional callback registered by RunController
        if self._on_complete_cb:
            self._on_complete_cb(finished_graph)

    # ── private helpers ────────────────────────────────────────────────────────

    def _build_node(self, node_data: dict, step: int, status: str) -> dict:
        """
        Constructs a TraceNode dict from event node data.

        TraceNode is a superset of the event node — it adds "step" for
        playback ordering. The frontend uses step to reconstruct the
        simulation state at any point in time.
        """
        return {
            "id":        node_data["id"],
            "x":         node_data["x"],
            "y":         node_data["y"],
            "cell_type": node_data["cell_type"],
            "g":         node_data["g"],
            "h":         node_data["h"],
            "f":         node_data["f"],
            "depth":     node_data["depth"],
            "parent_id": node_data.get("parent_id"),
            "status":    status,
            "step":      step,
        }

    def _record_edge(self, edge_data: dict) -> None:
        """
        Records a directed edge, respecting the priority hierarchy:
        path > backtrack > expansion.

        Never downgrade a path edge — once an edge is confirmed as part
        of the final path, it stays that way regardless of future events.

        The edge cost is taken from the TraceEvent's edge data, which
        reflects the actual cell traversal cost (from cell_type_registry).
        This cost is used by the 3D graph to size particle density.
        """
        from_id = edge_data["from_id"]
        to_id   = edge_data["to_id"]
        key     = (from_id, to_id)

        # Priority guard: never overwrite a path edge
        existing = self._edges.get(key)
        if existing and existing["edge_type"] == "path":
            return

        self._edges[key] = {
            "from_id":   from_id,
            "to_id":     to_id,
            "edge_type": edge_data["edge_type"],
            "cost":      edge_data["cost"],
        }

    def _update_metadata(self, node_data: dict, step: int) -> None:
        """
        Updates running maximums used in the TraceGraph metadata block.

        The metadata drives the 3D graph's axis scaling:
          max_depth → how tall the Y axis needs to be
          max_g     → how large the largest sphere is (g encodes sphere size)
          max_f     → normalisation for color intensity in heuristic-aware algos

        Doing this incrementally means finalize() is O(1) — no second pass
        over all nodes at the end.
        """
        self._total_steps = max(self._total_steps, step)
        self._max_depth   = max(self._max_depth,   node_data.get("depth", 0))
        self._max_g       = max(self._max_g,        node_data.get("g", 0.0))
        self._max_f       = max(self._max_f,        node_data.get("f", 0.0))
