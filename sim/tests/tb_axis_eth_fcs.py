"""
Cocotb testbench for Cut-Through Ethernet FCS CRC-32 Checker (axis_eth_fcs_checker).
Verifies standard IEEE 802.3 CRC-32 matching Python binascii.crc32, cut-through forwarding, and error detection.
"""

import binascii
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


async def send_axis_packet(dut, data: bytes, expected_crc: int = None, provide_expected: bool = False):
    """Sends an AXI-Stream packet across 64-bit beats."""
    total_len = len(data)
    num_beats = (total_len + 7) // 8

    for beat_idx in range(num_beats):
        offset = beat_idx * 8
        chunk = data[offset:min(offset + 8, total_len)]
        chunk_len = len(chunk)
        keep = (1 << chunk_len) - 1
        val = int.from_bytes(chunk, byteorder="little")
        is_last = 1 if beat_idx == num_beats - 1 else 0

        dut.s_axis_tdata.value = val
        dut.s_axis_tkeep.value = keep
        dut.s_axis_tvalid.value = 1
        dut.s_axis_tlast.value = is_last

        if is_last and provide_expected and expected_crc is not None:
            dut.expected_fcs_valid.value = 1
            dut.expected_fcs.value = expected_crc
        else:
            dut.expected_fcs_valid.value = 0

        # Verify zero-latency cut-through combinational forwarding
        await cocotb.triggers.ReadOnly()
        assert int(dut.m_axis_tdata.value) == val, "Cut-through data mismatch"
        assert int(dut.m_axis_tkeep.value) == keep, "Cut-through keep mismatch"
        assert int(dut.m_axis_tvalid.value) == 1, "Cut-through valid mismatch"
        assert int(dut.m_axis_tlast.value) == is_last, "Cut-through last mismatch"

        await RisingEdge(dut.clk)

    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
    dut.s_axis_tkeep.value = 0
    dut.expected_fcs_valid.value = 0


@cocotb.test()
async def test_axis_eth_fcs_checker_basic(dut):
    """Verifies CRC32 calculation on various packet sizes and payloads."""
    clock = Clock(dut.clk, 6.4, unit="ns")  # 156.25 MHz
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tkeep.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
    dut.m_axis_tready.value = 1
    dut.expected_fcs_valid.value = 0
    dut.expected_fcs.value = 0

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Test Packet 1: Standard ASCII test string
    payload1 = b"123456789"
    expected1 = binascii.crc32(payload1)  # 0xcbf43926
    await send_axis_packet(dut, payload1, expected_crc=expected1, provide_expected=True)

    await RisingEdge(dut.clk)
    assert int(dut.fcs_calculated.value) == expected1, f"Expected {hex(expected1)}, got {hex(int(dut.fcs_calculated.value))}"
    assert int(dut.fcs_error.value) == 0
    assert int(dut.fcs_error_count.value) == 0

    # Test Packet 2: 64-byte Ethernet Header + MoldUDP64 frame
    payload2 = b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb\x08\x00" + b"MOLD01    " + b"\x00" * 30
    expected2 = binascii.crc32(payload2)
    await send_axis_packet(dut, payload2, expected_crc=expected2, provide_expected=True)

    await RisingEdge(dut.clk)
    assert int(dut.fcs_calculated.value) == expected2, f"Expected {hex(expected2)}, got {hex(int(dut.fcs_calculated.value))}"
    assert int(dut.fcs_error.value) == 0
    assert int(dut.fcs_error_count.value) == 0

    # Test Packet 3: Corrupted Packet (Expect FCS Error)
    payload3 = b"AURAHFT_ETH_PACKET_TEST"
    wrong_expected = expected2  # Intentionally wrong expected CRC
    await send_axis_packet(dut, payload3, expected_crc=wrong_expected, provide_expected=True)

    await RisingEdge(dut.clk)
    assert int(dut.fcs_error.value) == 1, "Expected fcs_error to pulse on CRC mismatch"
    assert int(dut.fcs_error_count.value) == 1, f"Expected 1 error, got {int(dut.fcs_error_count.value)}"
