"""
REST API routes for AURA-HFT backend.
"""

import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, status

from .db import DatabaseManager
from .models import (
    RunLaunchRequest,
    RunResponse,
    TickTelemetryResponse,
    GeneratedOrderResponse,
    DatasetInfo,
    AxiLiteTuneRequest,
    AxiLiteStatusResponse,
)
from .simulation_runner import SimulationRunner

router = APIRouter(prefix="/api", tags=["simulation"])
db_manager = DatabaseManager()
sim_runner = SimulationRunner(db_manager)

# In-memory AXI-Lite simulated hardware registers state
axi_lite_state = {
    "kill_switch": False,
    "skew_factor": 2,
    "half_spread": 100,  # $0.0100 (1 cent)
    "max_inventory": 2000,
    "max_order_shares": 1000,
    "strategy_mode": "AVELLANEDA_STOIKOV",
    "active_inventory": 150,
    "reservation_price": 150.02,
    "best_bid": 150.00,
    "best_ask": 150.05,
    "total_orders_approved": 128,
    "total_orders_rejected": 2,
    "arbitrated_orders": 128,
    "collision_count": 8,
}

AVAILABLE_DATASETS: List[DatasetInfo] = [
    DatasetInfo(
        name="AAPL_sample_balanced.itch",
        symbol="AAPL",
        description="Normal balanced continuous trading with standard market depth and tight spread",
        tick_count=500,
        scenario_type="balanced",
    ),
    DatasetInfo(
        name="MSFT_sample_balanced.itch",
        symbol="MSFT",
        description="Continuous trading for Microsoft Corp with deep multi-level liquidity",
        tick_count=500,
        scenario_type="balanced",
    ),
    DatasetInfo(
        name="NVDA_sample_momentum.itch",
        symbol="NVDA",
        description="High-volatility momentum session for NVIDIA with aggressive order arrival",
        tick_count=500,
        scenario_type="bullish_surge",
    ),
    DatasetInfo(
        name="TSLA_sample_spread.itch",
        symbol="TSLA",
        description="Wide-spread market making session for Tesla with fast queue replenishment",
        tick_count=500,
        scenario_type="balanced",
    ),
    DatasetInfo(
        name="AAPL_sample_bullish.itch",
        symbol="AAPL",
        description="Strong bullish momentum with heavy bid volume buildup triggering positive OBI buy signals",
        tick_count=500,
        scenario_type="bullish_surge",
    ),
    DatasetInfo(
        name="AAPL_sample_bearish.itch",
        symbol="AAPL",
        description="Aggressive selling pressure with ask volume buildup triggering negative OBI sell signals",
        tick_count=500,
        scenario_type="bearish_dump",
    ),
    DatasetInfo(
        name="AAPL_sample_risk_test.itch",
        symbol="AAPL",
        description="Stress-test dataset provoking fat-finger limits, price collar deviations, and kill switch interventions",
        tick_count=500,
        scenario_type="risk_violation",
    ),
]


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "aura-hft-backend", "engine": "verilator-fpga-exact"}


@router.post("/axi-lite/tune", response_model=AxiLiteStatusResponse)
def tune_axi_lite(req: AxiLiteTuneRequest) -> AxiLiteStatusResponse:
    if req.kill_switch is not None:
        axi_lite_state["kill_switch"] = req.kill_switch
    if req.skew_factor is not None:
        axi_lite_state["skew_factor"] = req.skew_factor
    if req.half_spread is not None:
        axi_lite_state["half_spread"] = req.half_spread
    if req.max_inventory is not None:
        axi_lite_state["max_inventory"] = req.max_inventory
    if req.max_order_shares is not None:
        axi_lite_state["max_order_shares"] = req.max_order_shares
    if req.strategy_mode is not None:
        axi_lite_state["strategy_mode"] = req.strategy_mode
    return AxiLiteStatusResponse(**axi_lite_state)


@router.get("/axi-lite/status", response_model=AxiLiteStatusResponse)
def get_axi_lite_status() -> AxiLiteStatusResponse:
    return AxiLiteStatusResponse(**axi_lite_state)


@router.get("/datasets", response_model=List[DatasetInfo])
def list_datasets() -> List[DatasetInfo]:
    return AVAILABLE_DATASETS


@router.post("/runs/launch", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def launch_run(request: RunLaunchRequest) -> RunResponse:
    run_id = str(uuid.uuid4())
    result = sim_runner.run_simulation(run_id, request)
    run_record = db_manager.get_run(run_id)
    if not run_record:
        raise HTTPException(status_code=500, detail="Failed to retrieve newly created run")
    return RunResponse(**run_record)


@router.get("/runs", response_model=List[RunResponse])
def list_runs() -> List[RunResponse]:
    records = db_manager.list_runs()
    return [RunResponse(**r) for r in records]


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str) -> RunResponse:
    record = db_manager.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return RunResponse(**record)


@router.get("/runs/{run_id}/ticks", response_model=List[TickTelemetryResponse])
def get_run_ticks(
    run_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
) -> List[TickTelemetryResponse]:
    run = db_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    ticks = db_manager.get_ticks(run_id, offset=offset, limit=limit)
    return [TickTelemetryResponse(**t) for t in ticks]


@router.get("/runs/{run_id}/orders", response_model=List[GeneratedOrderResponse])
def get_run_orders(run_id: str) -> List[GeneratedOrderResponse]:
    run = db_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    orders = db_manager.get_orders(run_id)
    return [GeneratedOrderResponse(**o) for o in orders]
