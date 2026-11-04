"""
Interactive WebSocket Replay Manager for AURA-HFT.
Enables fine-grained client-side control: Play, Pause, Step, Seek, and Speed adjustments (1x-20x).
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect

from .db import DatabaseManager


class ReplaySession:
    """Manages playback state for a single connected client session."""

    def __init__(self, websocket: WebSocket, run_id: str, db: DatabaseManager):
        self.ws = websocket
        self.run_id = run_id
        self.db = db
        self.ticks: List[Dict[str, Any]] = []
        self.orders: List[Dict[str, Any]] = []
        self.orders_by_cycle: Dict[int, Dict[str, Any]] = {}
        self.current_index: int = 0
        self.is_playing: bool = False
        self.speed: float = 1.0
        self.base_delay_sec: float = 0.05  # 50ms at 1.0x

    def load_data(self) -> bool:
        """Fetch all recorded telemetry ticks and orders for the run."""
        self.ticks = self.db.get_ticks(self.run_id, offset=0, limit=10000)
        raw_orders = self.db.get_orders(self.run_id)
        self.orders = raw_orders
        # Index orders by timestamp or cycle for matching
        self.orders_by_cycle = {o["timestamp_ns"]: o for o in self.orders}
        return len(self.ticks) > 0

    async def send_status(self) -> None:
        """Send current player status."""
        total = len(self.ticks)
        await self.ws.send_json({
            "type": "status",
            "data": {
                "run_id": self.run_id,
                "state": "PLAYING" if self.is_playing else "PAUSED",
                "current_index": self.current_index,
                "total_ticks": total,
                "speed": self.speed,
                "progress_pct": round((self.current_index / total * 100), 1) if total > 0 else 0.0,
            },
        })

    async def emit_tick(self, index: int) -> None:
        """Send a single tick telemetry frame to the client."""
        if 0 <= index < len(self.ticks):
            tick = self.ticks[index]
            # Check if there is an associated order at this timestamp
            matched_order = self.orders_by_cycle.get(tick["timestamp_ns"])

            payload = {
                "type": "tick",
                "data": {
                    "index": index,
                    "tick": tick,
                    "order": matched_order,
                },
            }
            await self.ws.send_json(payload)

    async def handle_command(self, cmd: Dict[str, Any]) -> None:
        """Handle incoming command from the client UI."""
        action = cmd.get("action")

        if action == "play":
            self.is_playing = True
            if "speed" in cmd and cmd["speed"]:
                self.speed = max(0.2, min(50.0, float(cmd["speed"])))
            await self.send_status()

        elif action == "pause":
            self.is_playing = False
            await self.send_status()

        elif action == "seek":
            target = cmd.get("tick_index", 0)
            self.current_index = max(0, min(len(self.ticks) - 1, int(target)))
            await self.emit_tick(self.current_index)
            await self.send_status()

        elif action == "step":
            direction = int(cmd.get("direction", 1))
            self.is_playing = False
            new_idx = self.current_index + direction
            self.current_index = max(0, min(len(self.ticks) - 1, new_idx))
            await self.emit_tick(self.current_index)
            await self.send_status()

        elif action == "set_speed":
            new_speed = float(cmd.get("speed", 1.0))
            self.speed = max(0.2, min(50.0, new_speed))
            await self.send_status()

    async def run(self) -> None:
        """Main event loop managing both WebSocket reception and continuous playback."""
        if not self.load_data():
            await self.ws.send_json({"type": "error", "message": f"Run '{self.run_id}' not found or empty."})
            return

        # Emit initial tick and status
        await self.emit_tick(0)
        await self.send_status()

        async def playback_loop():
            while True:
                if self.is_playing and self.current_index < len(self.ticks) - 1:
                    self.current_index += 1
                    await self.emit_tick(self.current_index)
                    if self.current_index % 20 == 0:
                        await self.send_status()

                    delay = max(0.005, self.base_delay_sec / self.speed)
                    await asyncio.sleep(delay)
                elif self.is_playing and self.current_index >= len(self.ticks) - 1:
                    self.is_playing = False
                    await self.send_status()
                    await self.ws.send_json({"type": "completed", "message": "Replay finished."})
                else:
                    await asyncio.sleep(0.05)

        playback_task = asyncio.create_task(playback_loop())

        try:
            while True:
                data_text = await self.ws.receive_text()
                try:
                    cmd = json.loads(data_text)
                    await self.handle_command(cmd)
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            playback_task.cancel()
