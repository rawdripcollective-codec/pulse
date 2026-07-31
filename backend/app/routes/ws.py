"""WebSocket endpoint for real-time triage updates.

The dashboard subscribes to `/ws/triage-updates` and receives a JSON
event every time a triage status changes (started, awaiting approval,
posted, etc.). Implementation uses an in-process broadcast set; for
multi-worker deployments, swap to Redis pub/sub.
"""

import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger()
router = APIRouter()

# Active WebSocket connections
_active_connections: set[WebSocket] = set()


@router.websocket("/triage-updates")
async def triage_updates(websocket: WebSocket) -> None:
    """WebSocket for real-time triage progress updates."""
    await websocket.accept()
    _active_connections.add(websocket)

    try:
        while True:
            # Keep connection alive; actual updates are pushed by the service
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        _active_connections.discard(websocket)
    except Exception as exc:
        logger.warning("WebSocket disconnected with error", error=str(exc))
        _active_connections.discard(websocket)


async def broadcast_triage_update(event: dict) -> None:
    """Broadcast a triage status update to all connected dashboards."""
    disconnected: set[WebSocket] = set()
    payload = json.dumps(event)
    for ws in _active_connections:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)
    _active_connections.difference_update(disconnected)
