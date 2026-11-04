"""
Main FastAPI entry point for AURA-HFT backend server.
Serves REST API routes and high-speed WebSocket telemetry replay.
"""

import asyncio
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.staticfiles import StaticFiles

from .db import DatabaseManager, init_db
from .live.manager import get_manager
from .logging_config import configure_logging, get_logger
from .routes import health_payload, router as api_router
from .replay_manager import ReplaySession


log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    log.info("backend started", extra={"live_feed": get_manager().status()["feed"]})
    yield


app = FastAPI(
    title="AURA-HFT Supervision & Telemetry API",
    description="Backend API and WebSocket engine for FPGA hardware-accelerated tick-to-trade trading pipeline.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for development with Vite / React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register REST routes
app.include_router(api_router)


@app.get("/health")
def health() -> Dict[str, Any]:
    """Liveness/readiness probe (same payload as /api/health)."""
    return health_payload()


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket) -> None:
    """Live public crypto book + software OBI signal. Paper only, read-only.
    Streams events: {type: 'live_status'|'live_tick', data: {...}}
    """
    await websocket.accept()
    manager = get_manager()
    queue = manager.subscribe()

    async def drain_client() -> None:
        while True:
            await websocket.receive_text()  # ignore client messages, detect disconnect

    reader = asyncio.create_task(drain_client())
    try:
        while not reader.done():
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({getter, reader}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                await websocket.send_json(getter.result())
            else:
                getter.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        reader.cancel()
        await manager.unsubscribe(queue)


@app.websocket("/ws/replay/{run_id}")
async def websocket_replay_endpoint(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for interactive telemetry replay of a simulation run.
    Accepts commands: {action: 'play'|'pause'|'seek'|'step'|'set_speed', speed?: float, tick_index?: int}
    Streams events: {type: 'tick'|'status'|'completed'|'error', data: {...}}
    """
    await websocket.accept()
    db = DatabaseManager()
    run = db.get_run(run_id)
    if not run:
        await websocket.send_json({"type": "error", "message": f"Run '{run_id}' not found."})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    session = ReplaySession(websocket=websocket, run_id=run_id, db=db)
    await session.run()


# Mount frontend production build after API and WebSocket routes
client_dist = Path(__file__).resolve().parent.parent / "client" / "dist"
if client_dist.exists():
    app.mount("/", StaticFiles(directory=str(client_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="127.0.0.1", port=8000, reload=True)


