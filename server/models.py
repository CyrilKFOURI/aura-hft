"""
Pydantic data models for AURA-HFT REST API and WebSocket events.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class RunLaunchRequest(BaseModel):
    dataset_name: str = Field(default="AAPL_sample.itch", description="Name of the ITCH stream file")
    symbol: str = Field(default="AAPL", description="Stock ticker symbol to track")
    obi_threshold: float = Field(default=0.65, ge=-1.0, le=1.0, description="Order Book Imbalance trigger threshold")
    max_shares: int = Field(default=1000, gt=0, description="Pre-trade risk: max volume per order")
    price_collar: float = Field(default=0.05, gt=0.0, le=1.0, description="Pre-trade risk: maximum allowed price deviation (e.g., 0.05 = 5%)")
    max_notional: float = Field(default=1000000.0, gt=0.0, description="Pre-trade risk: maximum gross notional")
    kill_switch: bool = Field(default=False, description="Emergency hardware kill switch flag")
    scenario: Optional[str] = Field(default="balanced", description="Market replay scenario: 'balanced', 'bullish_surge', 'bearish_dump', 'risk_violation'")
    tick_limit: int = Field(default=500, gt=0, le=5000, description="Maximum number of ITCH ticks to simulate")


class RunResponse(BaseModel):
    id: str
    created_at: str
    dataset_name: str
    symbol: str
    obi_threshold: float
    max_shares: int
    price_collar: float
    max_notional: float
    kill_switch: bool
    status: str
    total_ticks: int
    total_orders: int
    p50_latency: Optional[float] = None
    p99_latency: Optional[float] = None


class Top5Depth(BaseModel):
    bids: List[List[float]] = Field(default_factory=list, description="List of [price, volume] for top 5 bids")
    asks: List[List[float]] = Field(default_factory=list, description="List of [price, volume] for top 5 asks")


class TickTelemetryResponse(BaseModel):
    id: int
    run_id: str
    timestamp_ns: int
    cycle_count: int
    msg_type: str
    best_bid: float
    best_ask: float
    bid_qty_l1: int
    ask_qty_l1: int
    obi_value: float
    micro_price: float
    queue_pos: Optional[int] = None
    top_5: Optional[Dict[str, Any]] = None


class GeneratedOrderResponse(BaseModel):
    id: int
    run_id: str
    user_ref_num: int
    timestamp_ns: int
    side: str
    shares: int
    price: float
    latency_cycles: int
    latency_ns: float
    status: str
    risk_reason: Optional[str] = None


class DatasetInfo(BaseModel):
    name: str
    symbol: str
    description: str
    tick_count: int
    scenario_type: str


class WsCommand(BaseModel):
    action: str = Field(description="Action: 'play', 'pause', 'seek', 'step', 'set_speed'")
    speed: Optional[float] = Field(default=1.0, description="Replay speed multiplier (e.g., 1.0, 5.0, 20.0)")
    tick_index: Optional[int] = Field(default=None, description="Target tick index for seek")
    direction: Optional[int] = Field(default=1, description="Step direction: 1 (forward) or -1 (backward)")


class AxiLiteTuneRequest(BaseModel):
    kill_switch: Optional[bool] = None
    skew_factor: Optional[int] = Field(default=None, ge=1, le=10)
    half_spread: Optional[int] = Field(default=None, ge=10, le=5000)
    max_inventory: Optional[int] = Field(default=None, ge=100, le=10000)
    max_order_shares: Optional[int] = Field(default=None, ge=10, le=10000)
    strategy_mode: Optional[str] = Field(default="AVELLANEDA_STOIKOV")


class AxiLiteStatusResponse(BaseModel):
    kill_switch: bool
    skew_factor: int
    half_spread: int
    max_inventory: int
    max_order_shares: int
    strategy_mode: str
    active_inventory: int
    reservation_price: float
    best_bid: float
    best_ask: float
    total_orders_approved: int
    total_orders_rejected: int
    arbitrated_orders: int
    collision_count: int
    telemetry_source: str

