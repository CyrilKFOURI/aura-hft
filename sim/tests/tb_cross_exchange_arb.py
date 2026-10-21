"""
Cocotb testbench for Cross-Exchange Spatial Arbitrage Engine (cross_exchange_arbiter).
Verifies instantaneous sub-5ns cross-spread evaluation, dual-leg routing, fee filtering, and profit accumulation.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


@cocotb.test()
async def test_arbiter_direction_a_to_b(dut):
    """Verifies Venue A Bid > Venue B Ask (Direction 0: Buy B, Sell A)."""
    clock = Clock(dut.clk, 3.2, unit="ns")  # 312.50 MHz
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.bbo_a_valid.value = 0
    dut.bbo_a_bid_price.value = 0
    dut.bbo_a_bid_shares.value = 0
    dut.bbo_a_ask_price.value = 0
    dut.bbo_a_ask_shares.value = 0

    dut.bbo_b_valid.value = 0
    dut.bbo_b_bid_price.value = 0
    dut.bbo_b_bid_shares.value = 0
    dut.bbo_b_ask_price.value = 0
    dut.bbo_b_ask_shares.value = 0

    dut.cfg_arb_enable.value = 1
    dut.cfg_min_profit_ticks.value = 100    # $0.0100 min profit
    dut.cfg_fee_ticks.value = 200           # $0.0200 exchange fees
    dut.cfg_max_shares_per_arb.value = 1000 # 1,000 shares cap
    dut.cfg_cooldown_cycles.value = 2

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Set Venue A: Bid $150.20 (1,502,000 raw) / 500 shares
    dut.bbo_a_valid.value = 1
    dut.bbo_a_bid_price.value = 1502000
    dut.bbo_a_bid_shares.value = 500
    dut.bbo_a_ask_price.value = 1503000
    dut.bbo_a_ask_shares.value = 1000

    # Set Venue B: Ask $150.10 (1,501,000 raw) / 300 shares
    # Spread A->B = 1502000 - 1501000 = 1000 ticks ($0.10)
    # Required = 200 (fees) + 100 (min profit) = 300 ticks
    # Net profit = 1000 - 200 = 800 ticks ($0.08 / share)
    # Exec shares = min(500, 300, 1000) = 300 shares
    # Total event profit = 300 * 800 = 240,000
    dut.bbo_b_valid.value = 1
    dut.bbo_b_bid_price.value = 1500000
    dut.bbo_b_bid_shares.value = 800
    dut.bbo_b_ask_price.value = 1501000
    dut.bbo_b_ask_shares.value = 300

    await RisingEdge(dut.clk)
    await Timer(100, "ps")
    # 1 cycle decision latency
    assert int(dut.arb_fire_strobe.value) == 1, "Expected arb_fire_strobe on cycle 1"
    assert int(dut.arb_direction.value) == 0, "Expected Direction 0 (Buy B / Sell A)"
    assert int(dut.arb_exec_shares.value) == 300, f"Expected 300 shares, got {int(dut.arb_exec_shares.value)}"
    assert int(dut.arb_buy_price.value) == 1501000, "Expected Buy Venue B @ $150.10"
    assert int(dut.arb_sell_price.value) == 1502000, "Expected Sell Venue A @ $150.20"
    assert int(dut.arb_profit_per_share.value) == 800, "Expected 800 ticks profit/share"
    assert int(dut.arb_total_event_profit.value) == 240000, "Expected 240,000 ticks event profit"
    assert int(dut.arb_event_count.value) == 1
    assert int(dut.arb_cum_profit.value) == 240000


@cocotb.test()
async def test_arbiter_direction_b_to_a(dut):
    """Verifies Venue B Bid > Venue A Ask (Direction 1: Buy A, Sell B)."""
    clock = Clock(dut.clk, 3.2, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.bbo_a_valid.value = 0
    dut.bbo_b_valid.value = 0
    dut.cfg_arb_enable.value = 1
    dut.cfg_min_profit_ticks.value = 100
    dut.cfg_fee_ticks.value = 200
    dut.cfg_max_shares_per_arb.value = 500
    dut.cfg_cooldown_cycles.value = 2

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Set Venue A: Ask $150.15 (1,501,500 raw) / 800 shares
    dut.bbo_a_valid.value = 1
    dut.bbo_a_bid_price.value = 1500500
    dut.bbo_a_bid_shares.value = 200
    dut.bbo_a_ask_price.value = 1501500
    dut.bbo_a_ask_shares.value = 800

    # Set Venue B: Bid $150.30 (1,503,000 raw) / 400 shares
    # Spread B->A = 1503000 - 1501500 = 1500 ticks ($0.15)
    # Net profit = 1500 - 200 = 1300 ticks ($0.13 / share)
    # Exec shares = min(400, 800, 500) = 400 shares
    # Total profit = 400 * 1300 = 520,000
    dut.bbo_b_valid.value = 1
    dut.bbo_b_bid_price.value = 1503000
    dut.bbo_b_bid_shares.value = 400
    dut.bbo_b_ask_price.value = 1504000
    dut.bbo_b_ask_shares.value = 1000

    await RisingEdge(dut.clk)
    await Timer(100, "ps")
    assert int(dut.arb_fire_strobe.value) == 1
    assert int(dut.arb_direction.value) == 1, "Expected Direction 1 (Buy A / Sell B)"
    assert int(dut.arb_exec_shares.value) == 400
    assert int(dut.arb_buy_price.value) == 1501500, "Expected Buy Venue A @ $150.15"
    assert int(dut.arb_sell_price.value) == 1503000, "Expected Sell Venue B @ $150.30"
    assert int(dut.arb_profit_per_share.value) == 1300
    assert int(dut.arb_total_event_profit.value) == 520000


@cocotb.test()
async def test_arbiter_fee_rejection(dut):
    """Verifies rejection when gross spread is less than exchange fees + min profit."""
    clock = Clock(dut.clk, 3.2, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.bbo_a_valid.value = 0
    dut.bbo_b_valid.value = 0
    dut.cfg_arb_enable.value = 1
    dut.cfg_min_profit_ticks.value = 100
    dut.cfg_fee_ticks.value = 200           # Total required = 300 ticks
    dut.cfg_max_shares_per_arb.value = 1000
    dut.cfg_cooldown_cycles.value = 2

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Set Venue A Bid = 1500200, Venue B Ask = 1500050 -> Spread = 150 ticks
    # 150 < 300 -> Should NOT fire!
    dut.bbo_a_valid.value = 1
    dut.bbo_a_bid_price.value = 1500200
    dut.bbo_a_bid_shares.value = 500
    dut.bbo_a_ask_price.value = 1501000
    dut.bbo_a_ask_shares.value = 500

    dut.bbo_b_valid.value = 1
    dut.bbo_b_bid_price.value = 1499900
    dut.bbo_b_bid_shares.value = 500
    dut.bbo_b_ask_price.value = 1500050
    dut.bbo_b_ask_shares.value = 500

    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(100, "ps")
        assert int(dut.arb_fire_strobe.value) == 0, "Arbiter must not fire when spread < fees + min_profit"
        assert int(dut.arb_event_count.value) == 0
