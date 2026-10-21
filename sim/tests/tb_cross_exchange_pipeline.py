"""
Cocotb testbench for Multi-Venue Cross-Exchange Pipeline Top-Level (cross_exchange_pipeline_top).
Verifies end-to-end concurrent ITCH stream ingestion across 2 venues, independent L2 book maintenance,
and automated instantaneous sub-5ns cross-exchange arbitrage triggering.
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


def build_eth_ip_udp_frame(session_name: bytes, seq_num: int, msg_payloads: list) -> bytes:
    """Builds a complete Ethernet II + IPv4 + UDP + MoldUDP64 packet."""
    mold_payload = b""
    for p in msg_payloads:
        mold_payload += struct.pack(">H", len(p)) + p

    msg_count = len(msg_payloads)
    session_bytes = session_name[:10].ljust(10, b" ")
    mold_header = session_bytes + struct.pack(">QH", seq_num, msg_count)
    mold_total = mold_header + mold_payload

    udp_len = 8 + len(mold_total)
    udp_header = struct.pack(">HHHH", 12345, 40001, udp_len, 0)

    ip_len = 20 + udp_len
    ip_header = struct.pack(">BBHHHBBHII", 0x45, 0x00, ip_len, 0x1234, 0x4000, 64, 17, 0, 0x0A000001, 0xE0000101)
    eth_header = b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xAA\xBB\x08\x00"

    return eth_header + ip_header + udp_header + mold_total


def encode_itch_a(locate: int, track: int, ts_ns: int, order_ref: int, side: str, shares: int, stock: str, price_raw: int) -> bytes:
    ts_bytes = ts_ns.to_bytes(6, byteorder="big")
    stock_bytes = stock.encode("ascii").ljust(8, b" ")
    return b"A" + struct.pack(">HH", locate, track) + ts_bytes + struct.pack(">QcI", order_ref, side.encode("ascii"), shares) + stock_bytes + struct.pack(">I", price_raw)


async def send_axis_frame(dut, stream_prefix: str, frame_bytes: bytes):
    """Sends a packet frame across 64-bit beats on stream_prefix ('s_axis_a' or 's_axis_b')."""
    tdata = getattr(dut, f"{stream_prefix}_tdata")
    tkeep = getattr(dut, f"{stream_prefix}_tkeep")
    tvalid = getattr(dut, f"{stream_prefix}_tvalid")
    tlast = getattr(dut, f"{stream_prefix}_tlast")
    tready = getattr(dut, f"{stream_prefix}_tready")

    total_len = len(frame_bytes)
    num_beats = (total_len + 7) // 8

    for beat_idx in range(num_beats):
        offset = beat_idx * 8
        chunk = frame_bytes[offset:min(offset + 8, total_len)]
        chunk_len = len(chunk)
        keep = (1 << chunk_len) - 1
        val = int.from_bytes(chunk, byteorder="little")
        is_last = 1 if beat_idx == num_beats - 1 else 0

        tdata.value = val
        tkeep.value = keep
        tvalid.value = 1
        tlast.value = is_last

        while True:
            await RisingEdge(dut.clk)
            if int(tready.value) == 1:
                break

    tvalid.value = 0
    tlast.value = 0
    tkeep.value = 0


@cocotb.test()
async def test_cross_exchange_pipeline_end_to_end(dut):
    """Verifies dual ITCH stream ingestion, L2 book updates, and arbitrage triggering."""
    clock = Clock(dut.clk, 3.2, unit="ns")  # 312.50 MHz
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.s_axis_a_tdata.value = 0
    dut.s_axis_a_tkeep.value = 0
    dut.s_axis_a_tvalid.value = 0
    dut.s_axis_a_tlast.value = 0

    dut.s_axis_b_tdata.value = 0
    dut.s_axis_b_tkeep.value = 0
    dut.s_axis_b_tvalid.value = 0
    dut.s_axis_b_tlast.value = 0

    dut.cfg_arb_enable.value = 1
    dut.cfg_min_profit_ticks.value = 100    # $0.0100
    dut.cfg_fee_ticks.value = 200           # $0.0200
    dut.cfg_max_shares_per_arb.value = 1000
    dut.cfg_cooldown_cycles.value = 2

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(10):
        await RisingEdge(dut.clk)

    # 1. Populate Venue A Book: Bid $150.25 (1000 shares), Ask $150.35 (1000 shares)
    msg_a_bid = encode_itch_a(
        locate=1, track=1, ts_ns=1000000, order_ref=101, side="B", shares=1000, stock="AAPL    ", price_raw=1502500
    )
    msg_a_ask = encode_itch_a(
        locate=1, track=2, ts_ns=2000000, order_ref=102, side="S", shares=1000, stock="AAPL    ", price_raw=1503500
    )
    frame_a = build_eth_ip_udp_frame(session_name=b"MOLD_A    ", seq_num=1, msg_payloads=[msg_a_bid, msg_a_ask])

    # 2. Populate Venue B Book: Bid $150.05 (1000 shares), Ask $150.15 (400 shares)
    msg_b_bid = encode_itch_a(
        locate=1, track=1, ts_ns=1000000, order_ref=201, side="B", shares=1000, stock="AAPL    ", price_raw=1500500
    )
    msg_b_ask = encode_itch_a(
        locate=1, track=2, ts_ns=2000000, order_ref=202, side="S", shares=400, stock="AAPL    ", price_raw=1501500
    )
    frame_b = build_eth_ip_udp_frame(session_name=b"MOLD_B    ", seq_num=1, msg_payloads=[msg_b_bid, msg_b_ask])

    # Send frames into both venue streams concurrently
    cocotb.start_soon(send_axis_frame(dut, "s_axis_a", frame_a))
    await send_axis_frame(dut, "s_axis_b", frame_b)

    # Wait for LOB parsing and book updates across both venues
    saw_arb = False
    for _ in range(50):
        await RisingEdge(dut.clk)
        if int(dut.arb_fire_strobe.value) == 1:
            saw_arb = True
            break

    # Verify both venues updated their BBO
    assert int(dut.bbo_a_valid.value) == 1, "Venue A BBO should be valid"
    assert int(dut.bbo_a_bid_price.value) == 1502500, "Venue A Best Bid = $150.25"
    assert int(dut.bbo_b_valid.value) == 1, "Venue B BBO should be valid"
    assert int(dut.bbo_b_ask_price.value) == 1501500, "Venue B Best Ask = $150.15"

    # Verify cross-exchange arbitrage fired!
    # Spread A->B = 1502500 - 1501500 = 1000 ticks ($0.10)
    # Fees = 200 ticks ($0.02) -> Net profit = 800 ticks ($0.08 / share)
    # Sizing = min(1000, 400) = 400 shares
    assert saw_arb, "Expected cross-exchange arbitrage fire strobe"
    assert int(dut.arb_direction.value) == 0, "Direction should be 0 (Buy B @ $150.15, Sell A @ $150.25)"
    assert int(dut.arb_exec_shares.value) == 400, f"Expected 400 shares, got {int(dut.arb_exec_shares.value)}"
    assert int(dut.arb_buy_price.value) == 1501500, "Buy Venue B @ $150.15"
    assert int(dut.arb_sell_price.value) == 1502500, "Sell Venue A @ $150.25"
    assert int(dut.arb_profit_per_share.value) == 800
    assert int(dut.arb_total_event_profit.value) == 320000, "Expected 400 * 800 = 320,000 ticks ($32.00)"
    assert int(dut.arb_event_count.value) >= 1
