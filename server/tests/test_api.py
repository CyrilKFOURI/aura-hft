"""
Integration tests for AURA-HFT FastAPI backend and WebSocket telemetry replay.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.db import init_db


@pytest.fixture(scope="module")
def test_client():
    # Use temporary database for isolation
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = tmp_db.name

    os.environ["AURA_DB_PATH"] = db_path
    init_db(db_path)

    with TestClient(app) as client:
        yield client

    if os.path.exists(db_path):
        os.remove(db_path)


def test_health_check(test_client):
    response = test_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "aura-hft-backend" in data["service"]


def test_list_datasets(test_client):
    response = test_client.get("/api/datasets")
    assert response.status_code == 200
    datasets = response.json()
    assert len(datasets) >= 4
    scenario_types = [d["scenario_type"] for d in datasets]
    assert "balanced" in scenario_types
    assert "bullish_surge" in scenario_types
    assert "bearish_dump" in scenario_types
    assert "risk_violation" in scenario_types


def test_launch_and_query_run(test_client):
    # Launch standard run
    payload = {
        "dataset_name": "AAPL_sample_balanced.itch",
        "symbol": "AAPL",
        "obi_threshold": 0.60,
        "max_shares": 1000,
        "price_collar": 0.05,
        "max_notional": 1000000.0,
        "kill_switch": False,
        "scenario": "balanced",
        "tick_limit": 100,
    }
    response = test_client.post("/api/runs/launch", json=payload)
    assert response.status_code == 201
    run = response.json()
    run_id = run["id"]
    assert run["status"] == "COMPLETED"
    assert run["total_ticks"] > 50
    assert run["p50_latency"] is not None

    # Get single run
    get_res = test_client.get(f"/api/runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id

    # List runs
    list_res = test_client.get("/api/runs")
    assert list_res.status_code == 200
    runs = list_res.json()
    assert any(r["id"] == run_id for r in runs)

    # Get ticks telemetry
    ticks_res = test_client.get(f"/api/runs/{run_id}/ticks?limit=20")
    assert ticks_res.status_code == 200
    ticks = ticks_res.json()
    assert len(ticks) == 20
    first_tick = ticks[0]
    assert "best_bid" in first_tick
    assert "best_ask" in first_tick
    assert "obi_value" in first_tick
    assert "top_5" in first_tick
    assert "bids" in first_tick["top_5"]
    assert "asks" in first_tick["top_5"]

    # Get orders
    orders_res = test_client.get(f"/api/runs/{run_id}/orders")
    assert orders_res.status_code == 200
    orders = orders_res.json()
    assert isinstance(orders, list)


def test_pre_trade_risk_rejection(test_client):
    # Launch run specifically targeting risk rules
    payload = {
        "dataset_name": "AAPL_sample_risk_test.itch",
        "symbol": "AAPL",
        "obi_threshold": 0.50,
        "max_shares": 100,  # Strict threshold to trigger MAX_SHARES_EXCEEDED
        "price_collar": 0.01,
        "max_notional": 100000.0,
        "kill_switch": False,
        "scenario": "risk_violation",
        "tick_limit": 80,
    }
    response = test_client.post("/api/runs/launch", json=payload)
    assert response.status_code == 201
    run_id = response.json()["id"]

    orders_res = test_client.get(f"/api/runs/{run_id}/orders")
    assert orders_res.status_code == 200
    orders = orders_res.json()
    assert len(orders) > 0

    # Verify that at least one rejected order was caught by pre-trade risk
    rejected_orders = [o for o in orders if o["status"] == "REJECTED"]
    assert len(rejected_orders) > 0
    reasons = [o["risk_reason"] for o in rejected_orders]
    assert any("MAX_SHARES_EXCEEDED" in r or "PRICE_COLLAR_EXCEEDED" in r for r in reasons)


def test_kill_switch_protection(test_client):
    # Launch run with Kill Switch enabled
    payload = {
        "dataset_name": "AAPL_sample_risk_test.itch",
        "symbol": "AAPL",
        "obi_threshold": 0.50,
        "max_shares": 1000,
        "price_collar": 0.05,
        "max_notional": 1000000.0,
        "kill_switch": True,  # Hard lock
        "scenario": "risk_violation",
        "tick_limit": 80,
    }
    response = test_client.post("/api/runs/launch", json=payload)
    assert response.status_code == 201
    run_id = response.json()["id"]

    orders_res = test_client.get(f"/api/runs/{run_id}/orders")
    orders = orders_res.json()
    assert len(orders) > 0
    # Every single generated order MUST be rejected with RISK_KILL_SWITCH
    for o in orders:
        assert o["status"] == "REJECTED"
        assert o["risk_reason"] == "RISK_KILL_SWITCH"


def test_websocket_replay_flow(test_client):
    # Launch a quick run to generate data for replay
    payload = {
        "dataset_name": "AAPL_sample_balanced.itch",
        "symbol": "AAPL",
        "obi_threshold": 0.60,
        "max_shares": 1000,
        "price_collar": 0.05,
        "max_notional": 1000000.0,
        "kill_switch": False,
        "scenario": "balanced",
        "tick_limit": 50,
    }
    run = test_client.post("/api/runs/launch", json=payload).json()
    run_id = run["id"]

    # Connect to WebSocket
    with test_client.websocket_connect(f"/ws/replay/{run_id}") as websocket:
        # First event is initial tick
        initial_tick = websocket.receive_json()
        assert initial_tick["type"] == "tick"
        assert initial_tick["data"]["index"] == 0

        # Second event is status
        status_msg = websocket.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["data"]["state"] == "PAUSED"

        # Send step command
        websocket.send_json({"action": "step", "direction": 1})
        step_tick = websocket.receive_json()
        assert step_tick["type"] == "tick"
        assert step_tick["data"]["index"] == 1

        step_status = websocket.receive_json()
        assert step_status["type"] == "status"

        # Send seek command
        websocket.send_json({"action": "seek", "tick_index": 10})
        seek_tick = websocket.receive_json()
        assert seek_tick["type"] == "tick"
        assert seek_tick["data"]["index"] == 10

        seek_status = websocket.receive_json()
        assert seek_status["type"] == "status"


def test_axi_lite_live_tuning_and_status(test_client):
    """Verifies live runtime tuning of AXI-Lite registers and status readout."""
    # 1. Query initial status
    resp = test_client.get("/api/axi-lite/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy_mode"] == "AVELLANEDA_STOIKOV"
    assert data["skew_factor"] == 2
    assert data["kill_switch"] is False

    # 2. Modify registers on-the-fly (Live Tuning)
    tune_payload = {
        "kill_switch": True,
        "skew_factor": 5,
        "half_spread": 250,
        "max_inventory": 3500,
        "strategy_mode": "AVELLANEDA_STOIKOV",
    }
    tune_resp = test_client.post("/api/axi-lite/tune", json=tune_payload)
    assert tune_resp.status_code == 200
    tuned_data = tune_resp.json()
    assert tuned_data["kill_switch"] is True
    assert tuned_data["skew_factor"] == 5
    assert tuned_data["half_spread"] == 250
    assert tuned_data["max_inventory"] == 3500

    # 3. Disengage kill switch
    restore_resp = test_client.post("/api/axi-lite/tune", json={"kill_switch": False})
    assert restore_resp.status_code == 200
    assert restore_resp.json()["kill_switch"] is False

