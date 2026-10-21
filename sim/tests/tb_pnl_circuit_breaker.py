"""
Cocotb testbench for Real-Time PnL Tracker and Autonomous Circuit Breaker.
DUT: pnl_circuit_breaker.
Verifies:
  1. Cash Flow accumulation on Buy and Sell executions.
  2. Mark-to-Market (MtM) continuous valuation on incoming Mid-Price ticks.
  3. Peak historical PnL tracking and peak-to-trough Drawdown calculation.
  4. Instantaneous 1-cycle ($6.4 ns) reflex circuit breaker tripping when Drawdown > Limit.
  5. Manual reset clearance via AXI-Lite command.
  6. Bit-exact agreement with Python Golden Model (PnlTrackerModel).
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from sim.golden_model.pnl_tracker_model import PnlTrackerModel


def to_signed(val):
    """Helper to convert Cocotb LogicArray to signed int without deprecation warnings."""
    if hasattr(val, "to_signed"):
        return int(val.to_signed())
    return int(val.signed_integer)


async def reset_dut(dut):
    """Initializes and resets the PnL Circuit Breaker DUT."""
    dut.rst_n.value = 0
    dut.exec_valid.value = 0
    dut.exec_side.value = 0
    dut.exec_shares.value = 0
    dut.exec_price.value = 0
    dut.mid_valid.value = 0
    dut.mid_price.value = 0
    dut.cfg_max_drawdown_limit.value = 50_000_000  # $5,000.0000 max drawdown limit
    dut.cfg_breaker_manual_reset.value = 0

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_pnl_accumulation_and_mtm(dut):
    """Tests normal trading with inventory gain, price appreciation and MtM tracking."""
    clock = Clock(dut.clk, 6.4, unit="ns")  # 156.25 MHz
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    golden = PnlTrackerModel(max_drawdown_limit=50_000_000)

    # 1. Fill Buy 100 shares @ $150.00 (1500000 raw)
    # Cash decreases by 100 * 1500000 = 150,000,000
    dut.exec_valid.value = 1
    dut.exec_side.value = 0  # Buy
    dut.exec_shares.value = 100
    dut.exec_price.value = 1500000
    await RisingEdge(dut.clk)
    dut.exec_valid.value = 0
    await RisingEdge(dut.clk)

    golden.apply_execution("B", 100, 1500000)

    # 2. Present mid-price tick @ $150.00 -> MtM PnL should be exactly 0
    dut.mid_valid.value = 1
    dut.mid_price.value = 1500000
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    snap = golden.evaluate_mid_price(1500000)
    assert to_signed(dut.telemetry_cash_flow.value) == snap.cash_flow == -150000000
    assert to_signed(dut.telemetry_inventory.value) == snap.inventory == 100
    assert to_signed(dut.telemetry_mtm_pnl.value) == snap.mtm_pnl == 0
    assert int(dut.breaker_tripped.value) == 0
    assert int(dut.allow_tx.value) == 1

    # 3. Market appreciates to $155.00 (1550000 raw) -> MtM PnL = -150M + 100 * 155M = +$500.00 (+5,000,000 raw)
    dut.mid_price.value = 1550000
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    snap2 = golden.evaluate_mid_price(1550000)
    assert to_signed(dut.telemetry_mtm_pnl.value) == snap2.mtm_pnl == 5000000
    assert to_signed(dut.telemetry_peak_pnl.value) == snap2.peak_pnl == 5000000
    assert int(dut.telemetry_drawdown.value) == snap2.drawdown == 0
    assert int(dut.allow_tx.value) == 1


@cocotb.test()
async def test_circuit_breaker_drawdown_trip(dut):
    """Tests violent market flash crash tripping the hardware circuit breaker in 1 cycle."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Max Drawdown configured at $5,000.0000 (50,000,000 raw)
    golden = PnlTrackerModel(max_drawdown_limit=50_000_000)

    # 1. Fill Buy 1000 shares @ $150.00 (1500000 raw) -> Cash = -1,500,000,000, q = +1000
    dut.exec_valid.value = 1
    dut.exec_side.value = 0
    dut.exec_shares.value = 1000
    dut.exec_price.value = 1500000
    await RisingEdge(dut.clk)
    dut.exec_valid.value = 0
    await RisingEdge(dut.clk)

    golden.apply_execution("B", 1000, 1500000)

    # Peak reached at $150.00 -> MtM = 0, Peak = 0
    dut.mid_valid.value = 1
    dut.mid_price.value = 1500000
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # 2. Flash Crash: Mid-Price drops violently from $150.00 to $90.00 (900000 raw)
    # Loss = 1000 shares * $60 drop = $60,000.0000 loss (600,000,000 raw)
    # Exceeds max allowed drawdown of 50,000,000!
    dut.mid_price.value = 900000
    await RisingEdge(dut.clk)

    # Evaluate circuit breaker trigger
    await RisingEdge(dut.clk)

    snap = golden.evaluate_mid_price(900000)
    assert snap.breaker_tripped is True
    assert int(dut.breaker_tripped.value) == 1, "Circuit Breaker must be tripped"
    assert int(dut.allow_tx.value) == 0, "Transmission must be shut down immediately"
    assert int(dut.total_trip_events.value) == 1

    # 3. Test Authorized Manual Reset
    dut.cfg_breaker_manual_reset.value = 1
    await RisingEdge(dut.clk)
    dut.cfg_breaker_manual_reset.value = 0
    await RisingEdge(dut.clk)

    golden.reset_breaker(current_mid_price=900000)

    # Bring price back to safe level
    dut.mid_price.value = 1500000
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    snap_recov = golden.evaluate_mid_price(1500000)
    assert snap_recov.breaker_tripped is False
    assert int(dut.breaker_tripped.value) == 0, "Breaker should be cleared after authorized reset"
    assert int(dut.allow_tx.value) == 1, "Transmission re-enabled"
