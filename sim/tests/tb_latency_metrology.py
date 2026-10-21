"""
Cocotb testbench for Wire-to-Wire Hardware Latency Metrology Unit (latency_metrology).
Verifies timestamp FIFO matching, Delta-t nanosecond computation, min/max tracking, and telemetry registers.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


@cocotb.test()
async def test_latency_metrology_basic(dut):
    """Tests hardware wire-to-wire latency tracking, min/max, and accumulation."""
    clock = Clock(dut.clk, 6.4, unit="ns")  # 156.25 MHz
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.ptp_timestamp.value = 0
    dut.rx_sop.value = 0
    dut.tx_sop.value = 0
    dut.stats_clear.value = 0

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Helper function to construct PTP 96-bit word
    def make_ptp(sec: int, ns: int, fns: int = 0) -> int:
        return (sec << 48) | (ns << 16) | fns

    # Event 1: RX at 1,000,000 ns, TX at 1,000,320 ns -> Delta = 320 ns
    dut.ptp_timestamp.value = make_ptp(sec=100, ns=1_000_000)
    dut.rx_sop.value = 1
    await RisingEdge(dut.clk)
    dut.rx_sop.value = 0

    for _ in range(10):
        await RisingEdge(dut.clk)

    dut.ptp_timestamp.value = make_ptp(sec=100, ns=1_000_320)
    dut.tx_sop.value = 1
    await RisingEdge(dut.clk)
    dut.tx_sop.value = 0

    await RisingEdge(dut.clk)
    assert int(dut.latency_valid.value) == 1
    assert int(dut.last_latency_ns.value) == 320, f"Expected 320 ns, got {int(dut.last_latency_ns.value)}"
    assert int(dut.min_latency_ns.value) == 320
    assert int(dut.max_latency_ns.value) == 320
    assert int(dut.event_count.value) == 1
    assert int(dut.cum_latency_ns.value) == 320

    # Event 2: RX at 2,000,000 ns, TX at 2,000,200 ns -> Delta = 200 ns (new min!)
    dut.ptp_timestamp.value = make_ptp(sec=100, ns=2_000_000)
    dut.rx_sop.value = 1
    await RisingEdge(dut.clk)
    dut.rx_sop.value = 0

    for _ in range(5):
        await RisingEdge(dut.clk)

    dut.ptp_timestamp.value = make_ptp(sec=100, ns=2_000_200)
    dut.tx_sop.value = 1
    await RisingEdge(dut.clk)
    dut.tx_sop.value = 0

    await RisingEdge(dut.clk)
    assert int(dut.latency_valid.value) == 1
    assert int(dut.last_latency_ns.value) == 200, f"Expected 200 ns, got {int(dut.last_latency_ns.value)}"
    assert int(dut.min_latency_ns.value) == 200, "Expected min latency updated to 200 ns"
    assert int(dut.max_latency_ns.value) == 320, "Expected max latency to remain 320 ns"
    assert int(dut.event_count.value) == 2
    assert int(dut.cum_latency_ns.value) == 520

    # Event 3: Cross-Second Rollover
    # RX at sec 100, ns 999,999,800
    # TX at sec 101, ns 100 -> Delta = 200 + 100 = 300 ns
    dut.ptp_timestamp.value = make_ptp(sec=100, ns=999_999_800)
    dut.rx_sop.value = 1
    await RisingEdge(dut.clk)
    dut.rx_sop.value = 0

    dut.ptp_timestamp.value = make_ptp(sec=101, ns=100)
    dut.tx_sop.value = 1
    await RisingEdge(dut.clk)
    dut.tx_sop.value = 0

    await RisingEdge(dut.clk)
    assert int(dut.latency_valid.value) == 1
    assert int(dut.last_latency_ns.value) == 300, f"Expected 300 ns on cross-second, got {int(dut.last_latency_ns.value)}"
    assert int(dut.event_count.value) == 3
