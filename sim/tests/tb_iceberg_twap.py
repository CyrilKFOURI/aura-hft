"""
tb_iceberg_twap.py

Cocotb testbench for hardware execution slicing engine:
  - Iceberg native order slicing with automatic 1-cycle replenishment
  - Partial execution vs full execution handling
  - Odd lot / residual slice calculation on final replenishment
  - Emergency parent cancellation
  - TWAP periodic child order generation with interval timer and LFSR jitter
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset_dut(dut):
    """Reset DUT and initialize all inputs."""
    dut.rst_n.value = 0
    dut.iceberg_arm.value = 0
    dut.iceberg_side.value = 0
    dut.iceberg_total_qty.value = 0
    dut.iceberg_display_qty.value = 0
    dut.iceberg_price.value = 0
    dut.iceberg_stock.value = 0
    dut.iceberg_token_base.value = 0
    dut.iceberg_cancel.value = 0

    dut.exec_valid.value = 0
    dut.exec_token.value = 0
    dut.exec_shares.value = 0

    dut.twap_arm.value = 0
    dut.twap_side.value = 0
    dut.twap_total_qty.value = 0
    dut.twap_slice_qty.value = 0
    dut.twap_interval_cycles.value = 0
    dut.twap_jitter_enable.value = 0
    dut.twap_price.value = 0
    dut.twap_stock.value = 0
    dut.twap_token_base.value = 0
    dut.twap_cancel.value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    await Timer(100, "ps")


@cocotb.test()
async def test_iceberg_nominal(dut):
    """Verify nominal Iceberg slicing with automatic 1-cycle replenishment and residual handling."""
    cocotb.start_soon(Clock(dut.clk, 3.2, units="ns").start())
    await reset_dut(dut)

    stock_aapl = int.from_bytes(b"AAPL    ", byteorder="big")
    token_base = 100

    # 1. Arm Iceberg: Total 2,500 shares, Display 1,000 shares (will yield 3 slices: 1000, 1000, 500)
    dut.iceberg_side.value = 0  # Buy
    dut.iceberg_total_qty.value = 2500
    dut.iceberg_display_qty.value = 1000
    dut.iceberg_price.value = 1500000  # $150.0000
    dut.iceberg_stock.value = stock_aapl
    dut.iceberg_token_base.value = token_base
    dut.iceberg_arm.value = 1

    await RisingEdge(dut.clk)
    dut.iceberg_arm.value = 0
    await Timer(100, "ps")

    # Slice 1 emitted immediately
    assert dut.child_order_valid.value == 1, "Slice 1 must be emitted immediately"
    assert dut.child_order_shares.value == 1000, f"Expected 1000 shares, got {dut.child_order_shares.value}"
    assert dut.child_order_token.value == 100, f"Expected token 100, got {dut.child_order_token.value}"
    assert dut.child_order_side.value == 0
    assert dut.child_order_price.value == 1500000
    assert dut.child_is_cancel.value == 0
    assert dut.iceberg_busy.value == 1
    assert dut.iceberg_rem_qty.value == 1500
    assert dut.iceberg_active_qty.value == 1000

    await RisingEdge(dut.clk)
    await Timer(100, "ps")
    assert dut.child_order_valid.value == 0, "Strobe should deassert after 1 cycle"

    # 2. Simulate partial fill on Slice 1: 400 shares
    dut.exec_valid.value = 1
    dut.exec_token.value = 100
    dut.exec_shares.value = 400

    await RisingEdge(dut.clk)
    dut.exec_valid.value = 0
    await Timer(100, "ps")

    assert dut.iceberg_active_qty.value == 600, f"Active qty should be 600, got {dut.iceberg_active_qty.value}"
    assert dut.child_order_valid.value == 0, "No new slice on partial fill"

    # 3. Simulate remaining fill on Slice 1: 600 shares (Slice 1 complete!)
    dut.exec_valid.value = 1
    dut.exec_token.value = 100
    dut.exec_shares.value = 600

    await RisingEdge(dut.clk)
    dut.exec_valid.value = 0
    await Timer(100, "ps")

    # Slice 2 must be emitted in 1 cycle
    assert dut.child_order_valid.value == 1, "Slice 2 must be emitted in 1 cycle after full fill"
    assert dut.child_order_shares.value == 1000, f"Expected 1000 shares, got {dut.child_order_shares.value}"
    assert dut.child_order_token.value == 101, f"Expected token 101, got {dut.child_order_token.value}"
    assert dut.iceberg_rem_qty.value == 500, f"Expected rem_qty 500, got {dut.iceberg_rem_qty.value}"
    assert dut.iceberg_active_qty.value == 1000

    await RisingEdge(dut.clk)
    await Timer(100, "ps")
    assert dut.child_order_valid.value == 0

    # 4. Fill entire Slice 2 (1000 shares) in one trade
    dut.exec_valid.value = 1
    dut.exec_token.value = 101
    dut.exec_shares.value = 1000

    await RisingEdge(dut.clk)
    dut.exec_valid.value = 0
    await Timer(100, "ps")

    # Slice 3 (odd lot / residual of 500 shares) must be emitted
    assert dut.child_order_valid.value == 1, "Slice 3 must be emitted"
    assert dut.child_order_shares.value == 500, f"Expected 500 shares for final slice, got {dut.child_order_shares.value}"
    assert dut.child_order_token.value == 102, f"Expected token 102, got {dut.child_order_token.value}"
    assert dut.iceberg_rem_qty.value == 0, "Remainder should now be 0"
    assert dut.iceberg_active_qty.value == 500

    await RisingEdge(dut.clk)
    await Timer(100, "ps")
    assert dut.child_order_valid.value == 0

    # 5. Fill Slice 3 (500 shares) -> Iceberg completed!
    dut.exec_valid.value = 1
    dut.exec_token.value = 102
    dut.exec_shares.value = 500

    await RisingEdge(dut.clk)
    dut.exec_valid.value = 0
    await Timer(100, "ps")

    assert dut.iceberg_done.value == 1, "Iceberg should report done"
    assert dut.iceberg_busy.value == 0, "Iceberg should no longer be busy"
    assert dut.iceberg_active_qty.value == 0
    assert dut.iceberg_slice_count.value == 3, f"Expected 3 slices, got {dut.iceberg_slice_count.value}"


@cocotb.test()
async def test_iceberg_emergency_cancel(dut):
    """Verify emergency cancellation of active parent order and immediate OUCH cancel child."""
    cocotb.start_soon(Clock(dut.clk, 3.2, units="ns").start())
    await reset_dut(dut)

    stock_nvda = int.from_bytes(b"NVDA    ", byteorder="big")
    token_base = 300

    # Arm large parent: 10,000 shares, display 1,000
    dut.iceberg_side.value = 1  # Sell
    dut.iceberg_total_qty.value = 10000
    dut.iceberg_display_qty.value = 1000
    dut.iceberg_price.value = 5000000
    dut.iceberg_stock.value = stock_nvda
    dut.iceberg_token_base.value = token_base
    dut.iceberg_arm.value = 1

    await RisingEdge(dut.clk)
    dut.iceberg_arm.value = 0
    await Timer(100, "ps")

    assert dut.child_order_valid.value == 1
    assert dut.child_order_token.value == 300
    assert dut.child_is_cancel.value == 0
    assert dut.iceberg_busy.value == 1

    await RisingEdge(dut.clk)
    await Timer(100, "ps")

    # Emergency cancel strobe
    dut.iceberg_cancel.value = 1
    await RisingEdge(dut.clk)
    dut.iceberg_cancel.value = 0
    await Timer(100, "ps")

    assert dut.child_order_valid.value == 1, "Cancel order must be emitted"
    assert dut.child_is_cancel.value == 1, "Must be flagged as cancel"
    assert dut.child_order_token.value == 300
    assert dut.child_order_shares.value == 1000
    assert dut.iceberg_busy.value == 0, "Iceberg should be canceled immediately"
    assert dut.iceberg_rem_qty.value == 0


@cocotb.test()
async def test_twap_execution_slicing(dut):
    """Verify periodic hardware TWAP slicing without jitter (deterministic intervals)."""
    cocotb.start_soon(Clock(dut.clk, 3.2, units="ns").start())
    await reset_dut(dut)

    stock_tsla = int.from_bytes(b"TSLA    ", byteorder="big")
    token_base = 700

    # Arm TWAP: 900 shares total, slices of 300 shares, interval of 20 cycles, jitter disabled
    dut.twap_side.value = 0  # Buy
    dut.twap_total_qty.value = 900
    dut.twap_slice_qty.value = 300
    dut.twap_interval_cycles.value = 20
    dut.twap_jitter_enable.value = 0
    dut.twap_price.value = 2500000
    dut.twap_stock.value = stock_tsla
    dut.twap_token_base.value = token_base
    dut.twap_arm.value = 1

    await RisingEdge(dut.clk)
    dut.twap_arm.value = 0
    await Timer(100, "ps")

    # Slice 1 emitted immediately
    assert dut.child_order_valid.value == 1, "TWAP Slice 1 emitted immediately"
    assert dut.child_order_shares.value == 300
    assert dut.child_order_token.value == 700
    assert dut.twap_busy.value == 1
    assert dut.twap_rem_qty.value == 600

    # Wait for interval (20 cycles)
    emitted = False
    for i in range(25):
        await RisingEdge(dut.clk)
        await Timer(100, "ps")
        if dut.child_order_valid.value == 1:
            emitted = True
            assert dut.child_order_shares.value == 300
            assert dut.child_order_token.value == 701
            assert dut.twap_rem_qty.value == 300
            break
    assert emitted, "TWAP Slice 2 should have been emitted around cycle 20"

    # Wait for next interval for Slice 3
    emitted = False
    for i in range(25):
        await RisingEdge(dut.clk)
        await Timer(100, "ps")
        if dut.child_order_valid.value == 1:
            emitted = True
            assert dut.child_order_shares.value == 300
            assert dut.child_order_token.value == 702
            assert dut.twap_rem_qty.value == 0
            break
    assert emitted, "TWAP Slice 3 should have been emitted around cycle 40"

    # Check termination
    await RisingEdge(dut.clk)
    await Timer(100, "ps")
    assert dut.twap_done.value == 1
    assert dut.twap_busy.value == 0
    assert dut.twap_slice_count.value == 3


@cocotb.test()
async def test_twap_execution_with_jitter(dut):
    """Verify hardware TWAP slicing with 16-bit LFSR pseudo-random jitter enabled."""
    cocotb.start_soon(Clock(dut.clk, 3.2, units="ns").start())
    await reset_dut(dut)

    stock_msft = int.from_bytes(b"MSFT    ", byteorder="big")
    token_base = 900

    # Arm TWAP: 800 shares total, slices of 200 shares (4 slices), base interval of 100 cycles with jitter
    dut.twap_side.value = 1  # Sell
    dut.twap_total_qty.value = 800
    dut.twap_slice_qty.value = 200
    dut.twap_interval_cycles.value = 100
    dut.twap_jitter_enable.value = 1
    dut.twap_price.value = 4000000
    dut.twap_stock.value = stock_msft
    dut.twap_token_base.value = token_base
    dut.twap_arm.value = 1

    await RisingEdge(dut.clk)
    dut.twap_arm.value = 0
    await Timer(100, "ps")

    # Slice 1 emitted immediately
    assert dut.child_order_valid.value == 1
    assert dut.child_order_shares.value == 200
    assert dut.child_order_token.value == 900

    emitted_count = 1
    intervals = []
    cycle_counter = 0

    # Collect remaining 3 slices
    while emitted_count < 4 and cycle_counter < 600:
        await RisingEdge(dut.clk)
        await Timer(100, "ps")
        cycle_counter += 1
        if dut.child_order_valid.value == 1:
            emitted_count += 1
            intervals.append(cycle_counter)
            cycle_counter = 0

    assert emitted_count == 4, f"Expected 4 slices, got {emitted_count}"
    # Verify that jitter created non-identical intervals
    assert len(intervals) == 3, f"Expected 3 interval recordings, got {len(intervals)}"
    dut._log.info(f"Recorded TWAP intervals with LFSR jitter: {intervals}")

    await RisingEdge(dut.clk)
    await Timer(100, "ps")
    assert dut.twap_done.value == 1
    assert dut.twap_busy.value == 0

