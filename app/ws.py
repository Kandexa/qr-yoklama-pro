from typing import Dict, Set
from fastapi import WebSocket
import asyncio

class ConnectionManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, room: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._rooms.setdefault(room, set()).add(ws)

    async def disconnect(self, room: str, ws: WebSocket):
        async with self._lock:
            if room in self._rooms and ws in self._rooms[room]:
                self._rooms[room].remove(ws)
                if not self._rooms[room]:
                    self._rooms.pop(room, None)

    async def broadcast(self, room: str, message: dict):
        async with self._lock:
            conns = list(self._rooms.get(room, set()))
        dead = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(room, ws)

manager = ConnectionManager()
