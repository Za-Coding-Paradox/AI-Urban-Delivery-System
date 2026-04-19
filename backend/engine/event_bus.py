# backend/engine/event_bus.py

import asyncio
import inspect
from collections import defaultdict
from typing import Any, Callable

# ── types ──────────────────────────────────────────────────────────────────────
# A handler is any function that accepts one argument: the event dict
Handler = Callable[[dict], Any]


class EventBus:
    """
    The central message broker of the simulation.

    Any component can publish an event to the bus.
    Any component can subscribe to one or more event types.
    Publishers and subscribers never talk to each other directly.

    The bus also maintains a buffer of every event it has ever seen.
    This buffer powers the playback bar — the frontend can replay
    any point in the simulation by replaying the buffer.

    Design: synchronous-first with async support.
    Synchronous handlers are called immediately and directly.
    Async handlers are scheduled onto the running event loop.
    """

    def __init__(self):
        # handlers is a dict where:
        #   key   = event type string e.g. "node_visit"
        #   value = list of handler functions subscribed to that type
        #
        # defaultdict(list) means if you access a key that doesn't exist yet,
        # it automatically creates an empty list for you instead of crashing.
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

        # The buffer stores every single event in the order it was published.
        # This is the complete history of the simulation.
        # Index 0 = first event, index N = latest event.
        self._buffer: list[dict] = []

        # WebSocket connections that want to receive events in real time.
        # When an event is published, it gets sent to all active connections.
        self._websocket_connections: list[Any] = []

    # ── subscribe ───────────────────────────────────────────────────────────────

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """
        Register a handler function to be called whenever
        an event of event_type is published.

        Example:
            bus.subscribe("node_visit", my_function)
            # now every time a node_visit event is published,
            # my_function(event) is called automatically
        """
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """
        Remove a previously registered handler.
        Silent if the handler was never registered.
        """
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def subscribe_all(self, handler: Handler) -> None:
        """
        Register a handler that receives EVERY event regardless of type.
        Useful for the trace builder and metrics collector which need everything.

        We use the special key "*" to mean "all events".
        """
        self._handlers["*"].append(handler)

    # ── publish ─────────────────────────────────────────────────────────────────

    def publish(self, event: dict) -> None:
        """
        Publish one event to the bus.

        Steps:
          1. Store in buffer (always — every event is remembered)
          2. Call all handlers subscribed to this specific event type
          3. Call all handlers subscribed to "*" (everything)
          4. Send to all active WebSocket connections

        The event must have an "event_type" key.
        Everything else is up to the publisher.
        """
        if "event_type" not in event:
            raise ValueError(f"Every event must have an 'event_type' key. Got: {event}")

        # Step 1 — buffer it
        self._buffer.append(event)

        event_type = event["event_type"]

        # Step 2 — notify specific subscribers
        for handler in self._handlers[event_type]:
            self._call(handler, event)

        # Step 3 — notify wildcard subscribers
        for handler in self._handlers["*"]:
            self._call(handler, event)

        # Step 4 — send to WebSocket connections
        for connection in self._websocket_connections:
            self._send_to_websocket(connection, event)

    # ── buffer / playback ───────────────────────────────────────────────────────

    def get_buffer(self) -> list[dict]:
        """
        Returns the complete event history.
        Used by the playback bar to replay the simulation.
        Returns a copy so callers can't accidentally mutate the internal buffer.
        """
        return list(self._buffer)

    def get_buffer_slice(self, start: int, end: int) -> list[dict]:
        """
        Returns a slice of the event buffer by index.
        Useful for the frontend requesting "events 100 to 200".
        """
        return self._buffer[start:end]

    def clear_buffer(self) -> None:
        """
        Clears the event history.
        Call this between simulation runs to start fresh.
        """
        self._buffer.clear()

    def buffer_size(self) -> int:
        """How many events are currently stored."""
        return len(self._buffer)

    def replay(self, handler: Handler, event_type: str = "*") -> None:
        """
        Replays the entire buffer through a handler.
        Used by the playback bar to reconstruct simulation state at any point.

        event_type="*" replays everything.
        event_type="node_visit" replays only node visits.
        """
        for event in self._buffer:
            if event_type == "*" or event["event_type"] == event_type:
                self._call(handler, event)

    # ── websocket management ────────────────────────────────────────────────────

    def register_connection(self, connection: Any) -> None:
        """Add a WebSocket connection to receive live events."""
        if connection not in self._websocket_connections:
            self._websocket_connections.append(connection)

    def unregister_connection(self, connection: Any) -> None:
        """Remove a WebSocket connection (e.g. client disconnected)."""
        if connection in self._websocket_connections:
            self._websocket_connections.remove(connection)

    def connection_count(self) -> int:
        """How many WebSocket connections are currently active."""
        return len(self._websocket_connections)

    # ── internal helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _call(handler: Handler, event: dict) -> None:
        """
        Calls a handler with an event.

        If the handler is an async function, it needs special treatment.
        We check for this and schedule it on the event loop if needed.

        Why does this matter?
        Python has two worlds — synchronous (normal) and asynchronous (async/await).
        A normal function can't directly call an async function.
        This method bridges that gap.
        """
        if inspect.iscoroutinefunction(handler):
            # Handler is async — try to schedule it on the running event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(handler(event))
            except RuntimeError:
                # No event loop running — run it directly
                asyncio.run(handler(event))
        else:
            # Handler is a normal function — call it directly
            handler(event)

    @staticmethod
    def _send_to_websocket(connection: Any, event: dict) -> None:
        """
        Sends an event to one WebSocket connection.
        Silently ignores errors — a broken connection shouldn't crash the simulation.

        Why silently? Because the simulation is the source of truth.
        If the frontend disconnects mid-run, the simulation keeps going.
        The frontend can reconnect and replay the buffer to catch up.
        """
        import json

        try:
            # WebSocket connections have a send_json or send method
            # We check which one exists and use it
            if hasattr(connection, "send_json"):
                asyncio.ensure_future(connection.send_json(event))
            elif hasattr(connection, "send"):
                asyncio.ensure_future(connection.send(json.dumps(event)))
        except Exception:
            # Connection is broken — ignore it
            # It will be cleaned up when the client formally disconnects
            pass
