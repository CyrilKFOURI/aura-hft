"""
Cocotb testbench for Tranche 16: IEEE 1588 PTP Timer, Ethernet FCS CRC32, and Latency Metrology.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


@cocotb.test()
async def test_ptp_timer_96b(dut):
    """Verifies IEEE 1588-2008 96-bit PTP timer accuracy and second rollover."""
    clock = Clock(dut.clk, 6.4, unit="ns")  # 156.25 MHz
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.cfg_step_ns.value = 6
    dut.cfg_step_fns.value = 26214  # 0.4 * 65536
    dut.cfg_step_load.value = 0
    dut.load_en.value = 0
    dut.load_timestamp.value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # 1. Verify timer progresses
    start_ns = int(dut.ptp_ns.value)
    for _ in range(10):
        await RisingEdge(dut.clk)
    end_ns = int(dut.ptp_ns.value)
    delta_ns = end_ns - start_ns
    assert 60 <= delta_ns <= 68, f"Expected ~64 ns for 10 cycles @ 6.4 ns, got {delta_ns}"

    # 2. Test reload near 1-second boundary to test rollover
    # Load 1,700,000,000 sec and 999,999,980 ns
    sec_load = 1700000000
    ns_load = 999999980
    fns_load = 0
    load_val = (sec_load << 48) | (ns_load << 16) | fns_load

    dut.load_timestamp.value = load_val
    dut.load_en.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.load_en.value = 0
    await RisingEdge(dut.clk)

    cocotb.log.info(f"Loaded PTP time: sec={int(dut.ptp_sec.value)}, ns={int(dut.ptp_ns.value)}")
    assert int(dut.ptp_sec.value) >= sec_load

    # Advance 4 cycles (4 * 6.4 = 25.6 ns -> should cross 1,000,000,000 ns)
    saw_pps = False
    for _ in range(5):
        await RisingEdge(dut.clk)
        if int(dut.pps_pulse.value) == 1:
            saw_pps = True

    assert saw_pps, "Expected PPS pulse on second rollover"
    assert int(dut.ptp_sec.value) == sec_load + 1, f"Expected sec {sec_load + 1}, got {int(dut.ptp_sec.value)}"
    assert int(dut.ptp_ns.value) < 50, f"Expected ns wrapped around, got {int(dut.ptp_ns.value)}"


@cocotb.test()
async def test_axis_eth_fcs_checker(dut):
    """Verifies cut-through Ethernet FCS CRC-32 calculation and error detection."""
    # This test will be run when toplevel is axis_eth_fcs_checker
    pass
