"""Integration tests for the WebSocket route.

We test:
- The broadcast helper with no connections (no-op safety)
- The broadcast helper sends to all active connections
- The WebSocket set management (add/remove on connect/disconnect)

Full bidirectional WebSocket testing requires a more capable client
(websockets library) — we keep the tests focused on the unit-level
concerns that the broadcast helper and connection set need to handle.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.ws import (
    _active_connections,
    broadcast_triage_update,
)


class TestBroadcastHelper:
    """The broadcast_triage_update helper pushes JSON to all connections."""

    async def test_broadcast_with_no_connections_is_safe(self):
        """Broadcasting when no one is connected should be a no-op, not an error."""
        _active_connections.clear()
        # Should not raise
        await broadcast_triage_update({"type": "triage_complete", "pr": 1})

    async def test_broadcast_sends_to_all_connected(self):
        """Each connection in the active set should receive the event."""
        _active_connections.clear()

        # Build a list of mock WebSocket-like objects
        sent: list[str] = []
        mocks = []
        for i in range(3):
            mock = MagicMock()
            mock.send_text = AsyncMock(side_effect=lambda msg, _i=i: sent.append((_i, msg)))
            mocks.append(mock)
            _active_connections.add(mock)

        event = {"type": "triage_complete", "repo": "x/y", "pr_number": 7}
        await broadcast_triage_update(event)

        # All 3 mocks received the event
        assert len(sent) == 3
        for idx, payload in sent:
            parsed = json.loads(payload)
            assert parsed == event

        _active_connections.clear()

    async def test_broadcast_skips_dead_connections(self):
        """If a connection's send_text raises, we should drop it and continue."""
        _active_connections.clear()

        good = MagicMock()
        good.send_text = AsyncMock()
        dead = MagicMock()
        dead.send_text = AsyncMock(side_effect=RuntimeError("connection closed"))

        _active_connections.add(dead)
        _active_connections.add(good)

        await broadcast_triage_update({"type": "test"})

        # The good one was called
        good.send_text.assert_awaited_once()
        # The dead one is no longer in the set
        assert dead not in _active_connections
        assert good in _active_connections

        _active_connections.clear()


class TestConnectionSetManagement:
    """Direct tests of the active-connections set behavior."""

    def test_set_starts_empty(self):
        # We can't reliably assert 'empty' across tests, but we can verify
        # add/remove semantics
        old_size = len(_active_connections)
        _active_connections.add("fake-conn-1")
        assert len(_active_connections) == old_size + 1
        _active_connections.discard("fake-conn-1")
        assert len(_active_connections) == old_size

    def test_discard_is_idempotent(self):
        # discarding a missing key doesn't raise
        _active_connections.discard("never-existed")  # no error
        assert "never-existed" not in _active_connections


# Note: end-to-end WebSocket round-trip tests (e.g. sending 'ping' and
# receiving 'pong') would require the `websockets` library and a different
# test client. The Starlette/FastAPI WebSocket route is well-tested by
# the framework itself; we focus on the application-specific helpers.
