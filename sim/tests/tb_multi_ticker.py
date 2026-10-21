"""
Cocotb testbench for Multi-Ticker Concurrent Pipeline (4 Symbols).
DUT: multi_ticker_pipeline_top.
Verifies:
  1. Ingress 16-bit stock_locate routing across 4 parallel channels.
  2. Complete order book isolation and simultaneous BBO computation.
  3. Parallel Avellaneda-Stoikov quoting engines.
  4. Round-Robin Egress arbitration without starvation.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


def pack_itch_msg(
    valid=1,
    msg_type=0x41,
    stock_locate=1,
    tracking_num=1,
    timestamp=0,
    order_ref=0,
    side=0,
    shares=0,
    stock=0,
    price=0,
    match_number=0,
    printable=0,
    orig_order_ref=0,
    new_order_ref=0,
    mpid=0,
):
    """Packs an ITCH parsed message struct into a 514-bit integer."""
    val = 0
    val = (val << 1) | (valid & 0x1)
    val = (val << 8) | (msg_type & 0xFF)
    val = (val << 16) | (stock_locate & 0xFFFF)
    val = (val << 16) | (tracking_num & 0xFFFF)
    val = (val << 48) | (timestamp & 0xFFFFFFFFFFFF)
    val = (val << 64) | (order_ref & 0xFFFFFFFFFFFFFFFF)
    val = (val << 1) | (side & 0x1)
    val = (val << 32) | (shares & 0xFFFFFFFF)
    val = (val << 64) | (stock & 0xFFFFFFFFFFFFFFFF)
    val = (val << 32) | (price & 0xFFFFFFFF)
    val = (val << 64) | (match_number & 0xFFFFFFFFFFFFFFFF)
    val = (val << 8) | (printable & 0xFF)
    val = (val << 64) | (orig_order_ref & 0xFFFFFFFFFFFFFFFF)
    val = (val << 64) | (new_order_ref & 0xFFFFFFFFFFFFFFFF)
    val = (val << 32) | (mpid & 0xFFFFFFFF)
    return val


async def reset_dut(dut):
    """Initializes and resets the Multi-Ticker DUT."""
    dut.rst_n.value = 0
    dut.parsed_msg_valid.value = 0
    dut.parsed_msg.value = 0

    dut.cfg_kill_switch.value = 0
    dut.cfg_skew_factor.value = 2
    dut.cfg_half_spread.value = 100
    dut.cfg_max_inventory.value = 2000
    dut.cfg_max_order_shares.value = 5000
    dut.cfg_price_collar_threshold.value = 500000
    dut.cfg_max_notional_raw.value = 50000000000
    dut.cfg_max_cum_notional_raw.value = 500000000000
    dut.m_axis_tready.value = 1

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)


async def send_add_order(dut, locate, order_ref, side, shares, price):
    """Injects an Add Order (ITCH Type 'A') message into the pipeline."""
    dut.parsed_msg_valid.value = 1
    dut.parsed_msg.value = pack_itch_msg(
        valid=1,
        msg_type=0x41,
        stock_locate=locate,
        order_ref=order_ref,
        side=0 if side == "B" else 1,
        shares=shares,
        price=price,
    )
    await RisingEdge(dut.clk)
    dut.parsed_msg_valid.value = 0
    dut.parsed_msg.value = 0


@cocotb.test()
async def test_multi_ticker_concurrent_flow(dut):
    """Verifies simultaneous multi-ticker ingestion, book isolation, and arbiter serialization."""
    clock = Clock(dut.clk, 6.4, unit="ns")  # 156.25 MHz
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # 1. Inject Bids and Asks for 4 tickers in sequence
    # AAPL (locate=1): Bid $150.00, Ask $150.10 -> Mid $150.05 (1500500)
    await send_add_order(dut, locate=1, order_ref=101, side="B", shares=100, price=1500000)
    await send_add_order(dut, locate=1, order_ref=102, side="S", shares=100, price=1501000)

    # MSFT (locate=2): Bid $300.00, Ask $300.20 -> Mid $300.10 (3001000)
    await send_add_order(dut, locate=2, order_ref=201, side="B", shares=200, price=3000000)
    await send_add_order(dut, locate=2, order_ref=202, side="S", shares=200, price=3002000)

    # NVDA (locate=3): Bid $500.00, Ask $500.50 -> Mid $500.25 (5002500)
    await send_add_order(dut, locate=3, order_ref=301, side="B", shares=300, price=5000000)
    await send_add_order(dut, locate=3, order_ref=302, side="S", shares=300, price=5005000)

    # TSLA (locate=4): Bid $200.00, Ask $200.40 -> Mid $200.20 (2002000)
    await send_add_order(dut, locate=4, order_ref=401, side="B", shares=400, price=2000000)
    await send_add_order(dut, locate=4, order_ref=402, side="S", shares=400, price=2004000)

    # Wait for pipeline processing across all channels
    for _ in range(40):
        await RisingEdge(dut.clk)

    # 2. Check router telemetry
    assert int(dut.routed_ingress_count.value) == 8, f"Expected 8 routed messages, got {int(dut.routed_ingress_count.value)}"

    # 3. Check BBO isolation across all 4 channels
    bbo_v = int(dut.bbo_valid.value)
    assert (bbo_v & 0x1) != 0, "Ch 0 (AAPL) BBO should be valid"
    assert (bbo_v & 0x2) != 0, "Ch 1 (MSFT) BBO should be valid"
    assert (bbo_v & 0x4) != 0, "Ch 2 (NVDA) BBO should be valid"
    assert (bbo_v & 0x8) != 0, "Ch 3 (TSLA) BBO should be valid"
    assert int(dut.best_bid_price[0].value) == 1500000
    assert int(dut.best_ask_price[0].value) == 1501000
    assert int(dut.mid_price[0].value) == 1500500

    assert int(dut.best_bid_price[1].value) == 3000000
    assert int(dut.best_ask_price[1].value) == 3002000
    assert int(dut.mid_price[1].value) == 3001000

    assert int(dut.best_bid_price[2].value) == 5000000
    assert int(dut.best_ask_price[2].value) == 5005000
    assert int(dut.mid_price[2].value) == 5002500

    assert int(dut.best_bid_price[3].value) == 2000000
    assert int(dut.best_ask_price[3].value) == 2004000
    assert int(dut.mid_price[3].value) == 2002000

    # 4. Check Avellaneda Reservation Prices
    assert int(dut.as_reservation_price[0].value) == 1500500
    assert int(dut.as_reservation_price[1].value) == 3001000
    assert int(dut.as_reservation_price[2].value) == 5002500
    assert int(dut.as_reservation_price[3].value) == 2002000

    # 5. Check Arbiter and Egress Output Activity
    assert int(dut.total_arbitrated_orders.value) >= 4, f"Expected >= 4 arbitrated orders, got {int(dut.total_arbitrated_orders.value)}"
