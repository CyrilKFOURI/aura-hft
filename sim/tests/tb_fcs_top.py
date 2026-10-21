"""Corrupted Ethernet FCS through the reference top (aura_hft_top).

Frames carry their real 4-byte FCS (CRC-32, as a MAC without FCS stripping
delivers them). A frame whose FCS is wrong must be counted and must not reach
the order book. The reference top instantiates axis_eth_fcs_checker with
CHECK_TRAILING_FCS=0 and no sideband FCS, and forwards cut-through: the check
is expected to FAIL today (runner marks it xfail strict, see spec 029).
"""

import struct
import zlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from sim.tests.tb_itch_parser import build_eth_ip_udp_frame, encode_itch_a, send_axis_frame
from sim.tests.tb_tick_to_trade_top import reset_dut


def with_fcs(frame: bytes, corrupt: bool = False) -> bytes:
    fcs = zlib.crc32(frame) ^ (0xDEADBEEF if corrupt else 0)
    return frame + struct.pack("<I", fcs)


async def settle(dut, n=80):
    for _ in range(n):
        await RisingEdge(dut.clk)


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def test_corrupted_fcs_is_dropped(dut):
    cocotb.start_soon(Clock(dut.clk, 6.4, unit="ns").start())
    await reset_dut(dut)
    good = build_eth_ip_udp_frame(b"FCSTEST001", 1, [encode_itch_a(1, 0, 1, 1, "B", 100, "AAPL", 1_500_000)])
    await send_axis_frame(dut, with_fcs(good))
    await settle(dut)
    assert int(dut.top5_bid_price[0].value) == 1_500_000, "valid frame (with trailing FCS) not applied"
    bad = build_eth_ip_udp_frame(b"FCSTEST001", 2, [encode_itch_a(1, 0, 2, 2, "B", 900, "AAPL", 1_600_000)])
    await send_axis_frame(dut, with_fcs(bad, corrupt=True))
    await settle(dut)
    errors = int(dut.fcs_error_count_out.value)
    best = int(dut.top5_bid_price[0].value)
    dut._log.info(f"fcs_error_count={errors} best_bid={best}")
    assert errors == 1, f"corrupted FCS not counted (fcs_error_count={errors})"
    assert best == 1_500_000, f"corrupted frame reached the book (best bid {best})"
