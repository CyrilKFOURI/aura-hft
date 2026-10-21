"""
Cocotb testbench for Avellaneda-Stoikov High-Frequency Market Making Engine.
DUT: avellaneda_stoikov_engine.
Verifies:
  1. Exact 3-cycle fixed deterministic latency on DSP pipeline.
  2. Inventory tracking upon execution fills (Buy/Sell).
  3. Continuous Bit-Exact agreement with Python Golden Model (AvellanedaStoikovModel).
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from sim.golden_model.avellaneda_stoikov_model import AvellanedaStoikovModel


async def reset_dut(dut):
    """Initializes and resets the Avellaneda-Stoikov DUT."""
    dut.rst_n.value = 0
    dut.mid_valid.value = 0
    dut.mid_price.value = 0
    dut.exec_valid.value = 0
    dut.exec_side.value = 0
    dut.exec_shares.value = 0
    dut.cfg_skew_factor.value = 2
    dut.cfg_half_spread.value = 100
    dut.cfg_max_inventory.value = 2000

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_avellaneda_stoikov_zero_inventory(dut):
    """Tests symmetric quoting when inventory is flat (q = 0)."""
    clock = Clock(dut.clk, 6.4, unit="ns")  # 156.25 MHz
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    golden = AvellanedaStoikovModel(skew_factor_raw=2, default_half_spread=100)

    mid = 1500000  # $150.00
    dut.mid_price.value = mid
    dut.mid_valid.value = 1

    # Measure exact pipeline latency
    await RisingEdge(dut.clk)
    dut.mid_valid.value = 0

    cycle_count = 0
    while int(dut.as_valid.value) != 1:
        await RisingEdge(dut.clk)
        cycle_count += 1
        assert cycle_count <= 5, "Timeout waiting for as_valid"

    # Verifies exact 3 cycles pipeline latency after stimulus pulse
    assert cycle_count == 3, f"Expected 3-cycle latency, got {cycle_count}"

    exp_res, exp_bid, exp_ask = golden.compute_quotes(mid, 0)
    assert int(dut.as_reservation_price.value) == exp_res == 1500000
    assert int(dut.as_bid_price.value) == exp_bid == 1499900
    assert int(dut.as_ask_price.value) == exp_ask == 1500100
    assert int(dut.as_inventory.value.signed_integer) == 0
    assert int(dut.as_skew_active.value) == 0


@cocotb.test()
async def test_avellaneda_stoikov_long_skew(dut):
    """Tests downward quote skewing when holding a long position (q > 0)."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    golden = AvellanedaStoikovModel(skew_factor_raw=2, default_half_spread=100)

    # 1. Fill Buy of 300 shares -> q = +300
    dut.exec_valid.value = 1
    dut.exec_side.value = 0  # Buy
    dut.exec_shares.value = 300
    await RisingEdge(dut.clk)
    dut.exec_valid.value = 0
    await RisingEdge(dut.clk)

    golden.apply_execution("BUY", 300)

    # 2. Present Mid-price $150.00
    mid = 1500000
    dut.mid_price.value = mid
    dut.mid_valid.value = 1
    await RisingEdge(dut.clk)

    # Wait for pipeline outputs (3 cycles)
    for _ in range(3):
        await RisingEdge(dut.clk)

    exp_res, exp_bid, exp_ask = golden.compute_quotes(mid, 300)

    # Skew offset = 300 * 2 = 600 -> Res = 1499400 ($149.94)
    assert int(dut.as_reservation_price.value) == exp_res == 1499400
    assert int(dut.as_bid_price.value) == exp_bid == 1499300
    assert int(dut.as_ask_price.value) == exp_ask == 1499500
    assert int(dut.as_inventory.value.signed_integer) == 300
    assert int(dut.as_skew_active.value) == 1


@cocotb.test()
async def test_avellaneda_stoikov_short_skew(dut):
    """Tests upward quote skewing when holding a short position (q < 0)."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    golden = AvellanedaStoikovModel(skew_factor_raw=2, default_half_spread=100)

    # Fill Sell of 400 shares -> q = -400
    dut.exec_valid.value = 1
    dut.exec_side.value = 1  # Sell
    dut.exec_shares.value = 400
    await RisingEdge(dut.clk)
    dut.exec_valid.value = 0
    await RisingEdge(dut.clk)

    golden.apply_execution("SELL", 400)

    # Present Mid-price $150.00
    mid = 1500000
    dut.mid_price.value = mid
    dut.mid_valid.value = 1
    await RisingEdge(dut.clk)

    for _ in range(3):
        await RisingEdge(dut.clk)

    exp_res, exp_bid, exp_ask = golden.compute_quotes(mid, -400)

    # Skew offset = -400 * 2 = -800 -> Res = 1500800 ($150.08)
    assert int(dut.as_reservation_price.value) == exp_res == 1500800
    assert int(dut.as_bid_price.value) == exp_bid == 1500700
    assert int(dut.as_ask_price.value) == exp_ask == 1500900
    assert int(dut.as_inventory.value.signed_integer) == -400
    assert int(dut.as_skew_active.value) == 1
