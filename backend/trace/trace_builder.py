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
    The builder registers once with subscribe_all(). Because RunController
    executes algorithms sequentially, only one builder is ever alive on the
    bus at a time — the algorithm_id filter in _handle_event is therefore
    not currently load-bearing, but is kept as an explicit documentation of
    which algorithm this builder belongs to.

    ── design: node storage ───────────────────────────────────────────────
    Nodes are stored in a dict keyed by cell id ("x,y"). The same cell
    cannot appear twice in the output — the last status wins. This is
    intentional: we show "what happened to each cell" not "every time a
    cell was pushed onto the frontier".

    The status lifecycle is: open → closed → path (path is terminal,
    never downgraded). The 3D renderer renders one sphere per unique cell,
    coloured by its final status.

    ── design: edge history ───────────────────────────────────────────────
    Edges are keyed by (from_id, to_id) tuple. Each edge stores its full
    visit history — every time the algorithm traversed that directed pair,
    the step number and cost are recorded.

    This matters most for UCS and A*. When A* relaxes a node (finds a
    cheaper path to it), it re-pushes the node and re-generates the edge
    from its new parent. Without history, that relaxation event is silently
    lost. With history, the Node Inspector Panel can show exactly when and
    by how much each edge was relaxed — making A*'s behaviour inspectable.

    The "current" cost and edge_type exposed to the renderer always reflect
    the most recent visit (or "path" if the edge is on the final path).
    Line thickness and particle density use visit_count so heavily-traversed
    edges are visually prominent.

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
        #
        # Each entry holds:
        #   from_id, to_id    — the directed pair
        #   edge_type         — current type ("expansion" | "backtrack" | "path")
        #   cost              — cost of the most recent visit
        #   visit_count       — how many times this edge was traversed
        #   history           — list of every visit: [{step, cost, edge_type}, ...]
        #
        # "current" values (edge_type, cost) reflect the most recent visit,
        # except when edge_type is "path" — that is terminal and never changes.
        # history is append-only and is frozen once edge_type becomes "path".
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

        Each edge in the output has this shape:
            {
                "from_id":     "2,4",
                "to_id":       "3,4",
                "edge_type":   "path",        # current / final type
                "cost":        2,             # cost of most recent visit
                "visit_count": 3,             # how many times traversed
                "history": [                  # every visit in order
                    {"step": 4,  "cost": 5, "edge_type": "expansion"},
                    {"step": 11, "cost": 3, "edge_type": "expansion"},
                    {"step": 19, "cost": 2, "edge_type": "expansion"},
                ]
            }

        The renderer uses edge_type for line style, visit_count for line
        thickness, cost for particle density, and history for the inspector.

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
        self._bus.unsubscribe("*", self._handle_event)

    # ── event dispatch ─────────────────────────────────────────────────────────

    def _handle_event(self, event: dict) -> None:
        """
        Single entry point for all EventBus events.

        Filters to our algorithm_id first. RunController guarantees sequential
        execution so this filter is not currently load-bearing — only one
        builder is alive at a time and the bus only carries events from the
        running algorithm. The filter is kept as explicit documentation: this
        builder belongs to self._algorithm_id and only that algorithm.

        After filtering, dispatches by event_type using a dict table.

        Why dispatch table instead of if/elif?
        Adding a new event type = one dict line. With if/elif = editing
        existing logic, risking unintended side effects. The dispatch table
        also makes it immediately obvious which event types this builder
        cares about — everything not in the table is silently ignored
        (e.g. algorithm_start, simulation_complete).
        """
        if event.get("algorithm_id") != self._algorithm_id:
            return

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

        We add the node if unseen. If already present (e.g. re-queued in
        UCS/A* with a lower g), we do NOT change its status — status
        upgrades only happen in _on_node_expand and _on_path_step.
        The edge is always recorded via _record_edge, which appends
        the new visit to the edge's history rather than overwriting.
        """
        node_data = event.get("node")
        if not node_data:
            return

        node_id = node_data["id"]
        step    = event.get("step", 0)

        if node_id not in self._nodes:
            self._nodes[node_id] = self._build_node(node_data, step, "open")

        self._update_metadata(node_data, step)

        # Always record the edge — _record_edge appends to history
        # rather than overwriting, so re-queuing events are preserved
        edge_data = event.get("edge")
        if edge_data:
            self._record_edge(edge_data, step)

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
            # Never downgrade from path — path is the terminal status
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

        We also mark the incoming edge for this node as "path" type.
        _mark_incoming_edge_as_path() loops over self._edges to find edges
        whose to_id matches this node, then sets their edge_type to "path".
        This is O(edges) but the path is at most ~30 nodes long so the
        total cost across all path_step calls is O(30 × edges) = O(edges).
        Once marked as "path", the edge's history is frozen — _record_edge
        will not append further visits to a path edge.
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

        # Upgrade the incoming edge to "path" type
        self._mark_incoming_edge_as_path(node_id)

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

    def _record_edge(self, edge_data: dict, step: int) -> None:
        """
        Records one traversal of a directed edge into its history.

        ── what changed from the original design ─────────────────────────
        The original implementation used last-write-wins: the second call
        for the same (from_id, to_id) pair silently overwrote the first.
        This lost relaxation events — the moments where UCS or A* found a
        cheaper path to an already-queued node and re-traversed the edge
        with a lower cost. Those events are analytically the most interesting
        part of understanding why A* outperforms UCS.

        The new design keeps a history list. Every traversal of the edge
        is appended regardless of whether it was seen before. The "current"
        cost and edge_type on the edge reflect the most recent non-path
        visit — these are what the renderer uses for particle density and
        line style. The full history is available to the Node Inspector Panel.

        ── path edges are frozen ──────────────────────────────────────────
        Once edge_type is "path", the edge is on the final solution route.
        No further visits are appended. This prevents a stray late-arriving
        visit event from corrupting the path record.

        ── visit_count ────────────────────────────────────────────────────
        visit_count increments on every call, including after path marking
        is complete — wait, no. After path marking, we return early so
        visit_count correctly reflects only pre-path traversals. In practice
        on this simulator, path marking happens in a dedicated path_step
        event pass after the algorithm finishes — no new visit events arrive
        for path edges after that point.

        Parameters:
            edge_data — the "edge" dict from a node_visit TraceEvent
            step      — the global step counter at the time of this visit
        """
        from_id = edge_data["from_id"]
        to_id   = edge_data["to_id"]
        key     = (from_id, to_id)

        existing = self._edges.get(key)

        # Path edges are frozen — never append further history to them.
        # _mark_incoming_edge_as_path() sets edge_type to "path" and that
        # is the terminal state. Any visit event arriving after path marking
        # (which should not happen in normal operation) is silently discarded.
        if existing and existing["edge_type"] == "path":
            return

        # Build this visit's history entry
        visit_entry = {
            "step":      step,
            "cost":      edge_data["cost"],
            "edge_type": edge_data["edge_type"],
        }

        if existing is None:
            # First time we see this edge — create the full record
            self._edges[key] = {
                "from_id":     from_id,
                "to_id":       to_id,
                "edge_type":   edge_data["edge_type"],  # current type
                "cost":        edge_data["cost"],        # current cost
                "visit_count": 1,
                "history":     [visit_entry],
            }
        else:
            # Edge seen before — append to history, update current values.
            #
            # Why update "current" cost on each visit?
            # In A*, re-queuing happens because a cheaper path was found.
            # The most recent cost is the best (lowest) cost seen so far.
            # Particle density in the 3D graph should reflect this best cost,
            # not the original (possibly much higher) first-visit cost.
            #
            # Why update "current" edge_type?
            # DFS uses "backtrack" — if DFS re-visits an edge (which it can
            # on a cyclic path), the type is consistently "backtrack". For
            # expansion edges, the type is always "expansion" so updating
            # it is a no-op. There is no meaningful "downgrade" case here
            # because we already guard against overwriting "path" above.
            existing["cost"]        = edge_data["cost"]
            existing["edge_type"]   = edge_data["edge_type"]
            existing["visit_count"] += 1
            existing["history"].append(visit_entry)

    def _mark_incoming_edge_as_path(self, node_id: str) -> None:
        """
        Marks the edge leading into node_id as edge_type="path".

        Called from _on_path_step once we know a node is on the final route.
        The edge_type upgrade makes path edges visually dominant in the 3D
        graph — thick line, fast green particles.

        Once marked as "path", _record_edge will discard any further visits
        to that edge (the path is final, no re-traversal is meaningful).

        We do NOT freeze the history list here — the history already contains
        all the pre-path visits, which is exactly what the inspector wants to
        show ("this edge was relaxed twice before ending up on the path").

        Why loop over all edges instead of a reverse index?
        On a 15×15 grid there are at most ~225 edges. Looping over them once
        per path node (at most ~30 nodes) is O(30 × 225) = O(6750) operations
        total — negligible. A reverse index (to_id → edge key) would be an
        optimisation only worth adding if the grid were orders of magnitude
        larger.
        """
        for edge in self._edges.values():
            if edge["to_id"] == node_id and edge["edge_type"] != "path":
                edge["edge_type"] = "path"

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
