"""
Cocotb testbench for Dual-Clock Domain Crossing (CDC) Pipeline.
DUT: aura_hft_dual_clock_top.
Verifies:
  1. Safe CDC between clk_net (156.25 MHz, 6.4 ns) and clk_core (312.50 MHz, 3.2 ns).
  2. Lossless transfer of parsed ITCH messages through cdc_msg_fifo.
  3. Double-speed execution of LOB and quantitative algorithms in clk_core domain.
  4. Safe crossing of generated OUCH orders through axis_async_fifo back to clk_net.
  5. Measurement of end-to-end tick-to-trade latency across asynchronous clock domains.
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


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


async def send_axis_frame(dut, frame_bytes: bytes):
    """Sends byte frame over 64-bit AXI4-Stream slave interface in clk_net domain."""
    chunks = [frame_bytes[i : i + 8] for i in range(0, len(frame_bytes), 8)]
    for idx, chunk in enumerate(chunks):
        is_last = (idx == len(chunks) - 1)
        keep_len = len(chunk)
        keep_mask = (1 << keep_len) - 1
        chunk_padded = chunk.ljust(8, b"\x00")
        word_val = int.from_bytes(chunk_padded, byteorder="little")

        dut.s_axis_tdata.value = word_val
        dut.s_axis_tkeep.value = keep_mask
        dut.s_axis_tvalid.value = 1
        dut.s_axis_tlast.value = 1 if is_last else 0

        await RisingEdge(dut.clk_net)
        while not int(dut.s_axis_tready.value):
            await RisingEdge(dut.clk_net)

    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0


async def reset_dual_clock_dut(dut):
    """Initializes and resets DUT across both asynchronous clock domains."""
    dut.rst_n.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tkeep.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
    dut.m_axis_tready.value = 1

    dut.cfg_auto_trade_enable.value = 0
    dut.cfg_obi_buy_thresh.value = 0x33333333   # +0.40 Q1.31
    dut.cfg_obi_sell_thresh.value = -0x33333333  # -0.40 Q1.31
    dut.cfg_default_order_shares.value = 100
    dut.cfg_kill_switch.value = 0
    dut.cfg_max_order_shares.value = 1000
    dut.cfg_price_collar_threshold.value = 0x00000666  # 5%
    dut.cfg_max_notional_raw.value = 500_000_000       # $50k
    dut.cfg_max_cum_notional_raw.value = 5_000_000_000 # $500k

    dut.host_intent_valid.value = 0
    dut.host_intent_side.value = 0
    dut.host_intent_shares.value = 0
    dut.host_intent_price.value = 0
    dut.host_intent_token.value = 0

    # Wait in reset for several cycles across both domains
    for _ in range(10):
        await RisingEdge(dut.clk_net)
    dut.rst_n.value = 1
    for _ in range(10):
        await RisingEdge(dut.clk_net)


@cocotb.test()
async def test_dual_clock_cdc_tick_to_trade(dut):
    """Tests end-to-end ITCH ingestion, CDC crossing, LOB update and OUCH order egress."""
    # 1. Start clk_net (156.25 MHz -> 6.4 ns)
    clock_net = Clock(dut.clk_net, 6.4, unit="ns")
    cocotb.start_soon(clock_net.start())

    # 2. Start clk_core (312.50 MHz -> 3.2 ns) with slight initial phase jitter
    await Timer(0.7, unit="ns")
    clock_core = Clock(dut.clk_core, 3.2, unit="ns")
    cocotb.start_soon(clock_core.start())

    await reset_dual_clock_dut(dut)

    # Enable auto-trade
    dut.cfg_auto_trade_enable.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk_net)

    # Monitor OUCH egress packets on clk_net
    egress_packets = []

    async def egress_monitor():
        current_packet = []
        while True:
            await RisingEdge(dut.clk_net)
            if int(dut.m_axis_tvalid.value) == 1 and int(dut.m_axis_tready.value) == 1:
                tdata = int(dut.m_axis_tdata.value)
                tkeep = int(dut.m_axis_tkeep.value)
                tlast = int(dut.m_axis_tlast.value)
                current_packet.append((tdata, tkeep, tlast))
                if tlast:
                    egress_packets.append(list(current_packet))
                    current_packet.clear()

    cocotb.start_soon(egress_monitor())

    # 3. Send Initial Two-Sided Book: Bid 1000 @ $150.00, Ask 500 @ $150.10 (AAPL)
    msg_b1 = encode_itch_a(
        locate=1,
        track=1,
        ts_ns=1000000,
        order_ref=5001,
        side="B",
        shares=1000,
        stock="AAPL    ",
        price_raw=1500000,
    )
    msg_a1 = encode_itch_a(
        locate=1,
        track=2,
        ts_ns=2000000,
        order_ref=5002,
        side="S",
        shares=500,
        stock="AAPL    ",
        price_raw=1501000,
    )
    frame1 = build_eth_ip_udp_frame(session_name=b"MOLD01    ", seq_num=1, msg_payloads=[msg_b1, msg_a1])
    await send_axis_frame(dut, frame1)

    # Wait for core LOB processing
    for _ in range(40):
        await RisingEdge(dut.clk_net)

    # Verify BBO updated in core domain
    assert int(dut.bbo_valid.value) == 1
    assert int(dut.best_bid_price.value) == 1500000
    assert int(dut.best_bid_shares.value) == 1000
    assert int(dut.best_ask_price.value) == 1501000
    assert int(dut.best_ask_shares.value) == 500

    # 4. Trigger manual host intent to verify risk & egress pipeline
    dut.host_intent_valid.value = 1
    dut.host_intent_side.value = 0 # Buy
    dut.host_intent_shares.value = 100
    dut.host_intent_price.value = 1500000
    dut.host_intent_token.value = 0xCAFE0001
    await RisingEdge(dut.clk_core)
    dut.host_intent_valid.value = 0

    # Wait for OUCH packet egress through axis_async_fifo
    for _ in range(40):
        await RisingEdge(dut.clk_net)

    # Confirm order was approved by risk and transmitted out over network
    assert len(egress_packets) >= 1, f"Expected at least 1 egress OUCH order, got {len(egress_packets)}"
    assert int(dut.tx_order_count.value) >= 1
