# backend/tests/test_event_bus.py

import asyncio

import pytest

from backend.engine.event_bus import EventBus

# ── helpers ────────────────────────────────────────────────────────────────────


def make_event(event_type: str, **kwargs) -> dict:
    """Builds a minimal valid event dict for testing."""
    return {"event_type": event_type, **kwargs}


# ── basic subscribe / publish ───────────────────────────────────────────────────


def test_subscriber_receives_event():
    bus = EventBus()
    received = []

    bus.subscribe("node_visit", lambda e: received.append(e))
    bus.publish(make_event("node_visit", step=1))

    assert len(received) == 1
    assert received[0]["step"] == 1


def test_subscriber_only_receives_its_type():
    bus = EventBus()
    received = []

    bus.subscribe("node_visit", lambda e: received.append(e))
    bus.publish(make_event("delivery_complete"))  # different type

    assert len(received) == 0


def test_multiple_subscribers_same_type():
    bus = EventBus()
    log_a, log_b = [], []

    bus.subscribe("node_visit", lambda e: log_a.append(e))
    bus.subscribe("node_visit", lambda e: log_b.append(e))
    bus.publish(make_event("node_visit", step=1))

    assert len(log_a) == 1
    assert len(log_b) == 1


def test_wildcard_subscriber_receives_all():
    bus = EventBus()
    received = []

    bus.subscribe_all(lambda e: received.append(e))
    bus.publish(make_event("node_visit"))
    bus.publish(make_event("delivery_complete"))
    bus.publish(make_event("algorithm_start"))

    assert len(received) == 3


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    received = []

    handler = lambda e: received.append(e)
    bus.subscribe("node_visit", handler)
    bus.publish(make_event("node_visit", step=1))

    bus.unsubscribe("node_visit", handler)
    bus.publish(make_event("node_visit", step=2))

    # Only the first event should have been received
    assert len(received) == 1


# ── buffer ──────────────────────────────────────────────────────────────────────


def test_buffer_stores_all_events():
    bus = EventBus()
    bus.publish(make_event("node_visit", step=1))
    bus.publish(make_event("node_visit", step=2))
    bus.publish(make_event("delivery_complete"))

    assert bus.buffer_size() == 3


def test_buffer_returns_copy():
    bus = EventBus()
    bus.publish(make_event("node_visit"))

    buffer = bus.get_buffer()
    buffer.clear()  # mutate the copy

    # Original buffer should be untouched
    assert bus.buffer_size() == 1


def test_clear_buffer():
    bus = EventBus()
    bus.publish(make_event("node_visit"))
    bus.publish(make_event("node_visit"))
    bus.clear_buffer()

    assert bus.buffer_size() == 0


def test_buffer_slice():
    bus = EventBus()
    for i in range(10):
        bus.publish(make_event("node_visit", step=i))

    sliced = bus.get_buffer_slice(2, 5)
    assert len(sliced) == 3
    assert sliced[0]["step"] == 2
    assert sliced[2]["step"] == 4


# ── replay ──────────────────────────────────────────────────────────────────────


def test_replay_all_events():
    bus = EventBus()
    bus.publish(make_event("node_visit", step=1))
    bus.publish(make_event("delivery_complete"))

    replayed = []
    bus.replay(lambda e: replayed.append(e))

    assert len(replayed) == 2


def test_replay_filtered_by_type():
    bus = EventBus()
    bus.publish(make_event("node_visit", step=1))
    bus.publish(make_event("node_visit", step=2))
    bus.publish(make_event("delivery_complete"))

    replayed = []
    bus.replay(lambda e: replayed.append(e), event_type="node_visit")

    assert len(replayed) == 2


# ── missing event_type ──────────────────────────────────────────────────────────


def test_publish_without_event_type_raises():
    bus = EventBus()
    with pytest.raises(ValueError, match="event_type"):
        bus.publish({"step": 1})  # missing event_type key


# ── async handler ───────────────────────────────────────────────────────────────


def test_async_handler_receives_event():
    bus = EventBus()
    received = []

    async def async_handler(event):
        received.append(event)

    async def run():
        bus.subscribe("node_visit", async_handler)
        bus.publish(make_event("node_visit", step=1))
        # Give the event loop a moment to run the scheduled coroutine
        await asyncio.sleep(0)

    asyncio.run(run())
    assert len(received) == 1
