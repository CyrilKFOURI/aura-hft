"""
Main FastAPI entry point for AURA-HFT backend server.
Serves REST API routes and high-speed WebSocket telemetry replay.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .db import DatabaseManager, init_db
from .routes import router as api_router
from .replay_manager import ReplaySession


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema on startup
    init_db()
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

from pathlib import Path
from starlette.staticfiles import StaticFiles

# Register REST routes
app.include_router(api_router)


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
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)


