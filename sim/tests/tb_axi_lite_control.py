"""
Cocotb testbench for AXI4-Lite Control Registers.
DUT: axi_lite_control_registers.
Verifies memory-mapped read/write transactions, default values, and status readouts.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset_dut(dut):
    """Initializes and resets the AXI-Lite DUT."""
    dut.rst_n.value = 0
    dut.s_axi_awaddr.value = 0
    dut.s_axi_awprot.value = 0
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wdata.value = 0
    dut.s_axi_wstrb.value = 0
    dut.s_axi_wvalid.value = 0
    dut.s_axi_bready.value = 0
    dut.s_axi_araddr.value = 0
    dut.s_axi_arprot.value = 0
    dut.s_axi_arvalid.value = 0
    dut.s_axi_rready.value = 0

    dut.status_pipeline_ready.value = 1
    dut.status_bbo_valid.value = 1
    dut.status_risk_reject.value = 0
    dut.status_ingress_count.value = 1234
    dut.status_egress_count.value = 42
    dut.status_last_latency.value = 49
    dut.status_current_inventory.value = -100

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)


async def axi_write(dut, addr: int, data: int):
    """Executes an AXI4-Lite 32-bit single write transaction."""
    # Present Address and Data
    dut.s_axi_awaddr.value = addr
    dut.s_axi_awvalid.value = 1
    dut.s_axi_wdata.value = data
    dut.s_axi_wstrb.value = 0xF
    dut.s_axi_wvalid.value = 1
    dut.s_axi_bready.value = 1

    # Wait for write acceptance
    while True:
        await RisingEdge(dut.clk)
        if int(dut.s_axi_awready.value) == 1 and int(dut.s_axi_wready.value) == 1:
            break

    dut.s_axi_awvalid.value = 0
    dut.s_axi_wvalid.value = 0

    # Wait for write response
    while int(dut.s_axi_bvalid.value) != 1:
        await RisingEdge(dut.clk)

    assert int(dut.s_axi_bresp.value) == 0, f"Write to {hex(addr)} failed with bresp={dut.s_axi_bresp.value}"
    await RisingEdge(dut.clk)
    dut.s_axi_bready.value = 0


async def axi_read(dut, addr: int) -> int:
    """Executes an AXI4-Lite 32-bit single read transaction."""
    dut.s_axi_araddr.value = addr
    dut.s_axi_arvalid.value = 1
    dut.s_axi_rready.value = 1

    # Wait for address acceptance
    while True:
        await RisingEdge(dut.clk)
        if int(dut.s_axi_arready.value) == 1:
            break

    dut.s_axi_arvalid.value = 0

    # Wait for read data valid
    while int(dut.s_axi_rvalid.value) != 1:
        await RisingEdge(dut.clk)

    data = int(dut.s_axi_rdata.value)
    assert int(dut.s_axi_rresp.value) == 0, f"Read from {hex(addr)} failed with rresp={dut.s_axi_rresp.value}"
    await RisingEdge(dut.clk)
    dut.s_axi_rready.value = 0
    return data


@cocotb.test()
async def test_axi_lite_defaults(dut):
    """Verifies default reset values of all configuration registers."""
    clock = Clock(dut.clk, 6.4, units="ns")  # 156.25 MHz
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Check hardware signal defaults
    assert int(dut.cfg_pipeline_enable.value) == 1
    assert int(dut.cfg_hard_kill_switch.value) == 0
    assert int(dut.cfg_risk_max_shares.value) == 1000
    assert int(dut.cfg_risk_max_notional.value) == 1000000

    # Read back through AXI
    ctrl = await axi_read(dut, 0x00)
    assert ctrl == 0x00000001, f"Default ctrl expected 1, got {hex(ctrl)}"

    max_shares = await axi_read(dut, 0x08)
    assert max_shares == 1000, f"Default max shares expected 1000, got {max_shares}"


@cocotb.test()
async def test_axi_lite_write_read_roundtrip(dut):
    """Verifies write and read roundtrip for all configuration registers."""
    clock = Clock(dut.clk, 6.4, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # 1. Engage Kill Switch (bit 2) and enable auto trade (bit 0)
    await axi_write(dut, 0x00, 0x00000005)
    ctrl = await axi_read(dut, 0x00)
    assert ctrl == 0x00000005
    assert int(dut.cfg_hard_kill_switch.value) == 1
    assert int(dut.cfg_pipeline_enable.value) == 1

    # 2. Modify OBI Threshold to +0.80 (0x66666666)
    await axi_write(dut, 0x04, 0x66666666)
    thresh = await axi_read(dut, 0x04)
    assert thresh == 0x66666666
    assert int(dut.cfg_obi_threshold.value) == 0x66666666

    # 3. Modify Max Shares to 500
    await axi_write(dut, 0x08, 500)
    shares = await axi_read(dut, 0x08)
    assert shares == 500
    assert int(dut.cfg_risk_max_shares.value) == 500

    # 4. Modify Price Collar to 2.0% (0x028F)
    await axi_write(dut, 0x0C, 0x0000028F)
    collar = await axi_read(dut, 0x0C)
    assert collar == 0x0000028F

    # 5. Modify Max Notional to $2,000,000
    await axi_write(dut, 0x10, 2000000)
    notional = await axi_read(dut, 0x10)
    assert notional == 2000000


@cocotb.test()
async def test_axi_lite_read_telemetry_registers(dut):
    """Verifies reading read-only status and telemetry registers."""
    clock = Clock(dut.clk, 6.4, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Read status register (0x1C): bits [1:0] = bbo_valid (1), pipeline_ready (1) -> 3
    status = await axi_read(dut, 0x1C)
    assert status & 0x03 == 0x03

    # Read ingress count (0x20)
    ingress = await axi_read(dut, 0x20)
    assert ingress == 1234

    # Read egress count (0x24)
    egress = await axi_read(dut, 0x24)
    assert egress == 42

    # Read last latency (0x28)
    lat = await axi_read(dut, 0x28)
    assert lat == 49

    # Read unmapped address -> returns 0xDEADBEEF
    unmapped = await axi_read(dut, 0xFC)
    assert unmapped == 0xDEADBEEF
