import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect


class ProgressManager:
    """Manages active WebSocket connections for progress broadcasting."""

    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, event: str, data: dict):
        dead = []
        message = json.dumps({"event": event, **data})
        for ws in self.connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ProgressManager()


async def progress_callback(stage: str, percent: int):
    """Called by ota_core during long operations."""
    await manager.broadcast("progress", {"stage": stage, "percent": percent})


async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
