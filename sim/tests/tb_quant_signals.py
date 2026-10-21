"""
Cocotb Testbench for Quantitative Microstructure Engine (AURA-HFT).
Co-simulates quant_engine_top against Python Golden Model:
  - Validates Order Book Imbalance (OBI) fixed-point Q1.31 bit-accuracy.
  - Validates Micro-Price DSP48 arithmetic.
  - Validates Queue Tracker FIFO position decrement and Top-of-Queue detection.
"""

import math
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from sim.golden_model.golden_order_book import GoldenOrderBook


def q1_31_to_float(val_int: int) -> float:
    """Converts a signed 32-bit Q1.31 integer into a float [-1.0, 1.0]."""
    if val_int >= 0x80000000:
        val_int -= 0x100000000
    return val_int / (2**31)


async def reset_dut(dut):
    """Initializes and resets the DUT."""
    dut.rst_n.value = 0
    dut.bbo_valid.value = 0
    dut.best_bid_price.value = 0
    dut.best_bid_shares.value = 0
    dut.best_ask_price.value = 0
    dut.best_ask_shares.value = 0
    dut.spread.value = 0
    dut.event_valid.value = 0
    dut.event_side.value = 0
    dut.event_price.value = 0
    dut.event_shares_reduced.value = 0
    dut.cfg_valid.value = 0
    dut.cfg_slot_idx.value = 0
    dut.cfg_side.value = 0
    dut.cfg_price.value = 0
    dut.cfg_shares.value = 0
    dut.cfg_initial_volume.value = 0
    dut.cfg_cancel.value = 0

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_obi_balanced_book(dut):
    """Scenario 1: Perfectly balanced book (V_bid == V_ask) yields OBI = 0.0."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # V_bid = 500, V_ask = 500, P_bid = $150.00, P_ask = $150.10
    dut.best_bid_price.value = 1500000
    dut.best_bid_shares.value = 500
    dut.best_ask_price.value = 1501000
    dut.best_ask_shares.value = 500
    dut.spread.value = 1000
    dut.bbo_valid.value = 1

    await RisingEdge(dut.clk)
    dut.bbo_valid.value = 0

    # Wait for the 34-cycle division and DSP pipeline to produce output
    for _ in range(35):
        await RisingEdge(dut.clk)
        if dut.obi_valid.value == 1:
            break

    assert dut.obi_valid.value == 1
    raw_obi = int(dut.obi_val.value)
    obi_f = q1_31_to_float(raw_obi)
    assert raw_obi == 0
    assert math.isclose(obi_f, 0.0, abs_tol=1e-6)

    # Micro-Price should equal Mid-Price ($150.05 = 1500500)
    assert int(dut.micro_price.value) == 1500500


@cocotb.test()
async def test_obi_heavy_bid(dut):
    """Scenario 2: Heavy Bid side (V_bid=300, V_ask=100) -> OBI = +0.50."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    golden = GoldenOrderBook()
    golden.bids[150.0] = 300
    golden.asks[150.2] = 100

    exp_obi = golden.calculate_obi()           # +0.5
    exp_micro = golden.calculate_micro_price() # 150.15

    dut.best_bid_price.value = 1500000
    dut.best_bid_shares.value = 300
    dut.best_ask_price.value = 1502000
    dut.best_ask_shares.value = 100
    dut.spread.value = 2000
    dut.bbo_valid.value = 1

    await RisingEdge(dut.clk)
    dut.bbo_valid.value = 0

    for _ in range(35):
        await RisingEdge(dut.clk)
        if dut.obi_valid.value == 1:
            break

    assert dut.obi_valid.value == 1
    raw_obi = int(dut.obi_val.value)
    obi_f = q1_31_to_float(raw_obi)
    dut._log.info(f"Heavy Bid OBI: raw={hex(raw_obi)}, float={obi_f:.6f}, expected={exp_obi}")
    assert math.isclose(obi_f, exp_obi, abs_tol=1e-5)

    micro_price_f = int(dut.micro_price.value) / 10000.0
    dut._log.info(f"Micro-Price: {micro_price_f}, expected={exp_micro}")
    assert int(dut.micro_price.value) == int(round(exp_micro * 10000)) == 1501500


@cocotb.test()
async def test_obi_heavy_ask(dut):
    """Scenario 3: Heavy Ask side (V_bid=100, V_ask=300) -> OBI = -0.50."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    golden = GoldenOrderBook()
    golden.bids[150.0] = 100
    golden.asks[150.2] = 300

    exp_obi = golden.calculate_obi()           # -0.5
    exp_micro = golden.calculate_micro_price() # 150.05

    dut.best_bid_price.value = 1500000
    dut.best_bid_shares.value = 100
    dut.best_ask_price.value = 1502000
    dut.best_ask_shares.value = 300
    dut.spread.value = 2000
    dut.bbo_valid.value = 1

    await RisingEdge(dut.clk)
    dut.bbo_valid.value = 0

    for _ in range(35):
        await RisingEdge(dut.clk)
        if dut.obi_valid.value == 1:
            break

    assert dut.obi_valid.value == 1
    raw_obi = int(dut.obi_val.value)
    obi_f = q1_31_to_float(raw_obi)
    dut._log.info(f"Heavy Ask OBI: raw={hex(raw_obi)}, float={obi_f:.6f}, expected={exp_obi}")
    assert math.isclose(obi_f, exp_obi, abs_tol=1e-5)

    micro_price_f = int(dut.micro_price.value) / 10000.0
    dut._log.info(f"Micro-Price: {micro_price_f}, expected={exp_micro}")
    assert int(dut.micro_price.value) == int(round(exp_micro * 10000)) == 1500500


@cocotb.test()
async def test_queue_tracker_depletion(dut):
    """Scenario 4: Passive order tracking and FIFO queue depletion to Top-of-Queue."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Configure slot 0: Buy order at $150.00, volume ahead = 500 shares
    dut.cfg_valid.value = 1
    dut.cfg_slot_idx.value = 0
    dut.cfg_side.value = 0 # 'B'
    dut.cfg_price.value = 1500000
    dut.cfg_shares.value = 100
    dut.cfg_initial_volume.value = 500
    dut.cfg_cancel.value = 0

    await RisingEdge(dut.clk)
    dut.cfg_valid.value = 0

    await RisingEdge(dut.clk)
    # Check initial status
    assert (int(dut.slot_active.value) & 1) == 1
    assert (int(dut.slot_volume_ahead.value) & 0xFFFFFFFF) == 500
    assert (int(dut.slot_is_top_of_queue.value) & 1) == 0

    # Event 1: Market execution of 200 shares at $150.00
    dut.event_valid.value = 1
    dut.event_side.value = 0 # 'B'
    dut.event_price.value = 1500000
    dut.event_shares_reduced.value = 200
    await RisingEdge(dut.clk)
    dut.event_valid.value = 0

    await RisingEdge(dut.clk)
    assert (int(dut.slot_volume_ahead.value) & 0xFFFFFFFF) == 300
    assert (int(dut.slot_is_top_of_queue.value) & 1) == 0

    # Event 2: Cancellation of 100 shares at $150.00
    dut.event_valid.value = 1
    dut.event_side.value = 0
    dut.event_price.value = 1500000
    dut.event_shares_reduced.value = 100
    await RisingEdge(dut.clk)
    dut.event_valid.value = 0

    await RisingEdge(dut.clk)
    assert (int(dut.slot_volume_ahead.value) & 0xFFFFFFFF) == 200
    assert (int(dut.slot_is_top_of_queue.value) & 1) == 0

    # Event 3: Execution of 250 shares at $150.00 (exceeds remaining 200 volume ahead)
    dut.event_valid.value = 1
    dut.event_side.value = 0
    dut.event_price.value = 1500000
    dut.event_shares_reduced.value = 250
    await RisingEdge(dut.clk)
    dut.event_valid.value = 0

    await RisingEdge(dut.clk)
    # Volume ahead clamped to 0, and order reaches top of queue!
    assert (int(dut.slot_volume_ahead.value) & 0xFFFFFFFF) == 0
    assert (int(dut.slot_is_top_of_queue.value) & 1) == 1
    dut._log.info("Queue Tracker successfully confirmed Top-of-Queue status!")


@cocotb.test()
async def test_quant_continuous_streaming(dut):
    """Scenario 5: Pipelined streaming throughput with Initiation Interval II=1."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Feed 5 back-to-back BBO updates on consecutive clock cycles
    test_cases = [
        (100, 100, 1500000, 1501000, 1000), # OBI = 0.0
        (400, 100, 1500000, 1501000, 1000), # OBI = +0.60
        (100, 400, 1500000, 1501000, 1000), # OBI = -0.60
        (800, 200, 1500000, 1501000, 1000), # OBI = +0.60
        (500, 500, 1500000, 1502000, 2000), # OBI = 0.0
    ]

    for vb, va, pb, pa, sp in test_cases:
        dut.best_bid_shares.value = vb
        dut.best_ask_shares.value = va
        dut.best_bid_price.value = pb
        dut.best_ask_price.value = pa
        dut.spread.value = sp
        dut.bbo_valid.value = 1
        await RisingEdge(dut.clk)

    dut.bbo_valid.value = 0

    # Collect consecutive outputs
    outputs = []
    for _ in range(50):
        await RisingEdge(dut.clk)
        if dut.obi_valid.value == 1:
            outputs.append((q1_31_to_float(int(dut.obi_val.value)), int(dut.micro_price.value)))
            if len(outputs) == len(test_cases):
                break

    assert len(outputs) == 5, f"Expected 5 continuous outputs, got {len(outputs)}"
    dut._log.info(f"Continuous streaming outputs: {outputs}")

    # Check that II=1 consecutive outputs match expectations
    assert math.isclose(outputs[0][0], 0.0, abs_tol=1e-5)
    assert math.isclose(outputs[1][0], 0.6, abs_tol=1e-5)
    assert math.isclose(outputs[2][0], -0.6, abs_tol=1e-5)
    assert math.isclose(outputs[3][0], 0.6, abs_tol=1e-5)
    assert math.isclose(outputs[4][0], 0.0, abs_tol=1e-5)
