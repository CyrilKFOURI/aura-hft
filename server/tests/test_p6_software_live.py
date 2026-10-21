"""Step P6: health, latency provenance, honest AXI-Lite state, live feed (mocked, no network)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from research.obi_backtest.model import obi_signals
from server.db import init_db
from server.latency_sources import FPGA_SIM_CYCLES, latency_summary
from server.live import manager as live_manager
from server.live.feeds import (BinanceDepth, CoinbaseLevel2Batch, Feed, LiveBook, make_feed, obi_signal,
                               to_q31)
from server.live.manager import LiveFeedManager
from server.live.ws_client import OP_TEXT, encode_frame, read_frame
from server.logging_config import JsonFormatter
from server.main import app

COINBASE_SNAPSHOT = json.dumps({"type": "snapshot", "product_id": "BTC-USD",
                                "bids": [["100.00", "3.0"], ["99.50", "1.0"]],
                                "asks": [["100.50", "1.0"], ["101.00", "2.0"]]})
COINBASE_UPDATE = json.dumps({"type": "l2update", "product_id": "BTC-USD",
                              "changes": [["sell", "100.50", "0"], ["sell", "100.75", "0.5"]]})


async def fake_source(_feed: Feed) -> AsyncIterator[str]:
    yield json.dumps({"type": "subscriptions"})
    yield COINBASE_SNAPSHOT
    yield COINBASE_UPDATE
    await asyncio.sleep(3600)  # stay connected until cancelled


async def offline_source(_feed: Feed) -> AsyncIterator[str]:
    raise OSError("network unreachable (simulated)")
    yield ""  # pragma: no cover


@pytest.fixture(scope="module")
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    os.environ["AURA_DB_PATH"] = path
    init_db(path)
    with TestClient(app) as c:
        yield c
    os.remove(path)


@pytest.fixture
def mocked_feed():
    mgr = LiveFeedManager(CoinbaseLevel2Batch("BTC-USD"), source=fake_source, min_interval_s=0.0)
    live_manager.set_manager(mgr)
    yield mgr
    live_manager.set_manager(None)


# ------------------------------------------------------------------ REST
def test_health_endpoints(client, mocked_feed):
    for url in ("/health", "/api/health"):
        r = client.get(url)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["live_feed"] == "idle"  # no subscriber -> no network


def test_latency_endpoint_reports_simulated_and_measured(client, tmp_path: Path):
    r = client.get("/api/latency")
    assert r.status_code == 200
    fpga = r.json()["fpga"]
    assert fpga["kind"] == "simulated" and fpga["cycles"] == FPGA_SIM_CYCLES
    assert fpga["ns"] == pytest.approx(FPGA_SIM_CYCLES * 6.4, abs=0.05)
    (tmp_path / "AAPL.json").write_text(json.dumps({
        "symbol": "AAPL", "events": 10, "messages": 100, "throughput_msgs_per_s": 5,
        "latency_ns": {"p50": 100, "p99": 200, "p999": 300, "mean": 120, "max": 400},
        "histogram": [[96, 104, 10]]}))
    sw = latency_summary(tmp_path)["software"]
    assert sw[0]["kind"] == "measured" and sw[0]["p999_ns"] == 300
    assert sw[0]["data_source"]["date"] == "2019-01-30"
    assert latency_summary(tmp_path / "missing")["software"] == []


def test_axi_lite_state_has_no_invented_telemetry(client):
    body = client.get("/api/axi-lite/status").json()
    for key in ("total_orders_approved", "total_orders_rejected", "arbitrated_orders", "collision_count",
                "active_inventory"):
        assert body[key] == 0
    assert "demo" in body["telemetry_source"]


def test_simulation_runner_uses_simulated_cycles(client):
    run = client.post("/api/runs/launch", json={"dataset_name": "AAPL_sample_bullish.itch", "symbol": "AAPL",
                                                "obi_threshold": 0.3, "scenario": "bullish_surge"}).json()
    orders = client.get(f"/api/runs/{run['id']}/orders").json()
    assert orders, "bullish scenario must trigger orders"
    assert {o["latency_cycles"] for o in orders} == {FPGA_SIM_CYCLES}


# ------------------------------------------------------------------ OBI + feeds
@pytest.mark.parametrize("vb,va", [(70, 30), (69, 31), (30, 70), (0, 0), (1, 0), (123456789, 98765)])
def test_obi_signal_matches_research_model(vb, va):
    import numpy as np
    t = to_q31(0.4)
    buy, sell = obi_signals(np.array([vb]), np.array([va]), t, -t)
    valid, b, s = obi_signal(vb, va, t, -t)
    assert (b, s) == (bool(buy[0]), bool(sell[0]))
    assert valid == (vb + va > 0)


def test_coinbase_normalization():
    feed, book = CoinbaseLevel2Batch(), LiveBook()
    assert not feed.apply(json.dumps({"type": "heartbeat"}), book)
    assert feed.apply(COINBASE_SNAPSHOT, book)
    assert feed.apply(COINBASE_UPDATE, book)
    bids, asks = book.top()
    assert bids[0] == (Decimal("100.00"), Decimal("3.0"))
    assert asks[0] == (Decimal("100.75"), Decimal("0.5"))
    with pytest.raises(ConnectionError):
        feed.apply(json.dumps({"type": "error", "message": "denied"}), book)


def test_binance_normalization_and_factory():
    feed, book = BinanceDepth("btcusdt"), LiveBook()
    msg = {"lastUpdateId": 1, "bids": [["10.0", "2.0"], ["9.0", "0"]], "asks": [["11.0", "1.0"]]}
    assert feed.apply(json.dumps(msg), book)
    assert book.top() == ([(Decimal("10.0"), Decimal("2.0"))], [(Decimal("11.0"), Decimal("1.0"))])
    assert isinstance(make_feed("binance:ethusdt"), BinanceDepth)
    assert make_feed("coinbase").instrument == "BTC-USD"
    with pytest.raises(ValueError):
        make_feed("kraken")


def test_ws_frame_roundtrip():
    frame = encode_frame(OP_TEXT, b"hello" * 40, mask_key=b"\x01\x02\x03\x04")

    async def go():
        reader = asyncio.StreamReader()
        reader.feed_data(frame)
        reader.feed_eof()
        return await read_frame(reader)

    fin, op, data = asyncio.run(go())
    assert fin and op == OP_TEXT and data == b"hello" * 40


# ------------------------------------------------------------------ live WebSocket
def test_live_websocket_streams_mocked_feed(client, mocked_feed):
    with client.websocket_connect("/ws/live") as ws:
        first = ws.receive_json()
        assert first["type"] == "live_status" and "paper" in first["data"]["mode"]
        ticks = []
        while len(ticks) < 2:
            ev = ws.receive_json()
            if ev["type"] == "live_tick":
                ticks.append(ev["data"])
    last = ticks[-1]
    assert last["source"].startswith("Coinbase")
    assert last["asks"][0] == [100.75, 0.5]
    # Vb = 3.0, Va = 0.5 -> OBI = 2.5/3.5 = 0.714 >= 0.4 -> buy
    assert last["signal"] == {"valid": True, "buy": True, "sell": False}
    assert last["obi"] == pytest.approx(0.714286, abs=1e-6)
    assert last["sw_latency_ns"] > 0


def test_live_feed_offline_degrades_gracefully():
    async def go():
        mgr = LiveFeedManager(CoinbaseLevel2Batch(), source=offline_source, backoff_initial=0.01,
                              backoff_max=0.02)
        q = mgr.subscribe()
        states = []
        while "offline" not in states:
            ev = await asyncio.wait_for(q.get(), 2)
            states.append(ev["data"]["state"])
        status = mgr.status()
        await mgr.unsubscribe(q)
        return status, mgr.state

    status, final = asyncio.run(go())
    assert status["state"] == "offline" and "network unreachable" in status["last_error"]
    assert final == "idle"


def test_live_feed_disabled():
    mgr = LiveFeedManager(None)

    async def go():
        q = mgr.subscribe()
        return (await q.get())["data"]["state"]

    assert asyncio.run(go()) == "disabled"


def test_json_log_format():
    rec = logging.LogRecord("aura.test", logging.INFO, __file__, 1, "hello", None, None)
    rec.feed = "x"
    out = json.loads(JsonFormatter().format(rec))
    assert out["msg"] == "hello" and out["feed"] == "x" and out["level"] == "INFO"
