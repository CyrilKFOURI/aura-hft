"""
Cocotb Testbench for Ingress Network Pipeline & ITCH 5.0 Parser (AURA-HFT).
Co-simulates RTL against Python Golden Reference Model (ItchDecoder).
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from sim.golden_model.itch_decoder import ItchDecoder


def build_eth_ip_udp_frame(session_name: bytes, seq_num: int, msg_payloads: list) -> bytes:
    """Builds a complete Ethernet II + IPv4 + UDP + MoldUDP64 packet."""
    # 1. MoldUDP64 Message blocks
    mold_payload = b""
    for p in msg_payloads:
        mold_payload += struct.pack(">H", len(p)) + p

    msg_count = len(msg_payloads)
    session_bytes = session_name[:10].ljust(10, b" ")
    mold_header = session_bytes + struct.pack(">QH", seq_num, msg_count)
    mold_total = mold_header + mold_payload

    # 2. UDP Header (8 bytes)
    udp_len = 8 + len(mold_total)
    udp_header = struct.pack(">HHHH", 12345, 40001, udp_len, 0)

    # 3. IPv4 Header (20 bytes)
    ip_len = 20 + udp_len
    # IP checksum dummy 0
    ip_header = struct.pack(">BBHHHBBHII", 0x45, 0x00, ip_len, 0x1234, 0x4000, 64, 17, 0, 0x0A000001, 0xE0000101)

    # 4. Ethernet II Header (14 bytes)
    eth_header = b"\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xAA\xBB\x08\x00"

    return eth_header + ip_header + udp_header + mold_total


def encode_itch_a(locate: int, track: int, ts_ns: int, order_ref: int, side: str, shares: int, stock: str, price_raw: int) -> bytes:
    """Encode ITCH 5.0 'A' Add Order message (36 bytes)."""
    ts_bytes = ts_ns.to_bytes(6, byteorder="big")
    stock_bytes = stock.encode("ascii").ljust(8, b" ")
    return b"A" + struct.pack(">HH", locate, track) + ts_bytes + struct.pack(">QcI", order_ref, side.encode("ascii"), shares) + stock_bytes + struct.pack(">I", price_raw)


def encode_itch_f(locate: int, track: int, ts_ns: int, order_ref: int, side: str, shares: int, stock: str, price_raw: int, mpid: str) -> bytes:
    """Encode ITCH 5.0 'F' Add Order with MPID message (40 bytes)."""
    ts_bytes = ts_ns.to_bytes(6, byteorder="big")
    stock_bytes = stock.encode("ascii").ljust(8, b" ")
    mpid_bytes = mpid.encode("ascii").ljust(4, b" ")
    return b"F" + struct.pack(">HH", locate, track) + ts_bytes + struct.pack(">QcI", order_ref, side.encode("ascii"), shares) + stock_bytes + struct.pack(">I", price_raw) + mpid_bytes


def encode_itch_e(locate: int, track: int, ts_ns: int, order_ref: int, shares: int, match_num: int) -> bytes:
    """Encode ITCH 5.0 'E' Executed message (31 bytes)."""
    ts_bytes = ts_ns.to_bytes(6, byteorder="big")
    return b"E" + struct.pack(">HH", locate, track) + ts_bytes + struct.pack(">QIQ", order_ref, shares, match_num)


def encode_itch_c(locate: int, track: int, ts_ns: int, order_ref: int, shares: int, match_num: int, printable: str, price_raw: int) -> bytes:
    """Encode ITCH 5.0 'C' Executed with Price message (36 bytes)."""
    ts_bytes = ts_ns.to_bytes(6, byteorder="big")
    return b"C" + struct.pack(">HH", locate, track) + ts_bytes + struct.pack(">QIQcI", order_ref, shares, match_num, printable.encode("ascii"), price_raw)


def encode_itch_x(locate: int, track: int, ts_ns: int, order_ref: int, shares: int) -> bytes:
    """Encode ITCH 5.0 'X' Order Cancel message (23 bytes)."""
    ts_bytes = ts_ns.to_bytes(6, byteorder="big")
    return b"X" + struct.pack(">HH", locate, track) + ts_bytes + struct.pack(">QI", order_ref, shares)


def encode_itch_d(locate: int, track: int, ts_ns: int, order_ref: int) -> bytes:
    """Encode ITCH 5.0 'D' Order Delete message (19 bytes)."""
    ts_bytes = ts_ns.to_bytes(6, byteorder="big")
    return b"D" + struct.pack(">HH", locate, track) + ts_bytes + struct.pack(">Q", order_ref)


def encode_itch_u(locate: int, track: int, ts_ns: int, orig_ref: int, new_ref: int, shares: int, price_raw: int) -> bytes:
    """Encode ITCH 5.0 'U' Order Replace message (35 bytes)."""
    ts_bytes = ts_ns.to_bytes(6, byteorder="big")
    return b"U" + struct.pack(">HH", locate, track) + ts_bytes + struct.pack(">QQII", orig_ref, new_ref, shares, price_raw)


async def send_axis_frame(dut, frame_bytes: bytes):
    """Sends byte frame over 64-bit AXI4-Stream slave interface."""
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

        await RisingEdge(dut.clk)
        while not dut.s_axis_tready.value:
            await RisingEdge(dut.clk)

    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0


async def reset_dut(dut):
    """Initializes and resets the DUT."""
    dut.rst_n.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tkeep.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_single_add_order(dut):
    """Scenario 1: Single Add Order ('A') message inside MoldUDP64 packet."""
    clock = Clock(dut.clk, 6.4, unit="ns") # 156.25 MHz line rate
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    msg_a = encode_itch_a(
        locate=13,
        track=42,
        ts_ns=34200000000000,
        order_ref=100001,
        side="B",
        shares=500,
        stock="AAPL    ",
        price_raw=1500000, # $150.0000
    )
    frame = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=100, msg_payloads=[msg_a])

    # Monitor coroutine to capture decoded ITCH message and measure latency
    decoded_messages = []
    cycle_count = 0
    valid_cycle = 0
    tlast_cycle = 0

    async def cycle_counter():
        nonlocal cycle_count, valid_cycle
        while True:
            await RisingEdge(dut.clk)
            cycle_count += 1
            if dut.parsed_msg_valid.value == 1:
                valid_cycle = cycle_count
                stock_raw = int(dut.out_stock.value).to_bytes(8, byteorder="big").decode("ascii", errors="replace").strip()
                decoded_messages.append({
                    "msg_type": chr(int(dut.out_msg_type.value)),
                    "locate": int(dut.out_stock_locate.value),
                    "track": int(dut.out_tracking_num.value),
                    "timestamp": int(dut.out_timestamp.value),
                    "order_ref": int(dut.out_order_ref.value),
                    "side": "B" if int(dut.out_side.value) == 0 else "S",
                    "shares": int(dut.out_shares.value),
                    "stock": stock_raw,
                    "price_raw": int(dut.out_price.value),
                    "cycle": cycle_count,
                })

    cocotb.start_soon(cycle_counter())

    # Send frame
    await send_axis_frame(dut, frame)
    tlast_cycle = cycle_count

    # Wait for processing
    for _ in range(15):
        await RisingEdge(dut.clk)

    assert len(decoded_messages) == 1, f"Expected 1 decoded message, got {len(decoded_messages)}"
    rtl_msg = decoded_messages[0]

    # Validate against Golden Reference Model
    ref_msg = ItchDecoder.decode_message(msg_a)
    assert ref_msg is not None
    assert rtl_msg["msg_type"] == ref_msg.msg_type == "A"
    assert rtl_msg["locate"] == ref_msg.stock_locate == 13
    assert rtl_msg["track"] == ref_msg.tracking_number == 42
    assert rtl_msg["timestamp"] == ref_msg.timestamp_ns == 34200000000000
    assert rtl_msg["order_ref"] == ref_msg.order_ref == 100001
    assert rtl_msg["side"] == ref_msg.side == "B"
    assert rtl_msg["shares"] == ref_msg.shares == 500
    assert rtl_msg["stock"] == ref_msg.stock == "AAPL"
    assert rtl_msg["price_raw"] == ref_msg.raw_price == 1500000

    # Latency verification (<= 6 clock cycles from end of input stream)
    latency = valid_cycle - tlast_cycle
    assert latency <= 6, f"Latency was {latency} cycles, expected <= 6"


@cocotb.test()
async def test_back_to_back_all_types(dut):
    """Scenario 2 & 4: Sequence of all 7 ITCH message types ('A', 'F', 'E', 'C', 'X', 'D', 'U') back-to-back."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    msg_a = encode_itch_a(locate=10, track=1, ts_ns=1000, order_ref=101, side="B", shares=100, stock="AAPL    ", price_raw=1500000)
    msg_f = encode_itch_f(locate=10, track=2, ts_ns=2000, order_ref=102, side="S", shares=200, stock="AAPL    ", price_raw=1510000, mpid="GSCO")
    msg_e = encode_itch_e(locate=10, track=3, ts_ns=3000, order_ref=101, shares=50, match_num=999)
    msg_c = encode_itch_c(locate=10, track=4, ts_ns=4000, order_ref=101, shares=50, match_num=1000, printable="Y", price_raw=1505000)
    msg_x = encode_itch_x(locate=10, track=5, ts_ns=5000, order_ref=102, shares=30)
    msg_d = encode_itch_d(locate=10, track=6, ts_ns=6000, order_ref=102)
    msg_u = encode_itch_u(locate=10, track=7, ts_ns=7000, orig_ref=103, new_ref=104, shares=300, price_raw=1490000)

    test_msgs = [msg_a, msg_f, msg_e, msg_c, msg_x, msg_d, msg_u]
    frame = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=200, msg_payloads=test_msgs)

    decoded_messages = []

    async def monitor():
        while True:
            await RisingEdge(dut.clk)
            if dut.parsed_msg_valid.value == 1:
                decoded_messages.append({
                    "msg_type": chr(int(dut.out_msg_type.value)),
                    "locate": int(dut.out_stock_locate.value),
                    "track": int(dut.out_tracking_num.value),
                    "timestamp": int(dut.out_timestamp.value),
                    "order_ref": int(dut.out_order_ref.value),
                    "side": "B" if int(dut.out_side.value) == 0 else "S",
                    "shares": int(dut.out_shares.value),
                    "price_raw": int(dut.out_price.value),
                    "match_num": int(dut.out_match_number.value),
                    "printable": chr(int(dut.out_printable.value)) if int(dut.out_printable.value) > 0 else "",
                    "orig_ref": int(dut.out_orig_order_ref.value),
                    "new_ref": int(dut.out_new_order_ref.value),
                    "mpid": int(dut.out_mpid.value).to_bytes(4, byteorder="big").decode("ascii", errors="replace").strip(),
                })

    monitor_task = cocotb.start_soon(monitor())
    await send_axis_frame(dut, frame)

    # Wait for pipeline to drain
    for _ in range(40):
        await RisingEdge(dut.clk)

    monitor_task.cancel()

    assert len(decoded_messages) == len(test_msgs), f"Expected {len(test_msgs)} messages, got {len(decoded_messages)}"

    expected_types = ["A", "F", "E", "C", "X", "D", "U"]
    for i, (rtl_m, raw_bytes, exp_t) in enumerate(zip(decoded_messages, test_msgs, expected_types)):
        ref_m = ItchDecoder.decode_message(raw_bytes)
        assert rtl_m["msg_type"] == exp_t == ref_m.msg_type, f"Mismatch on msg #{i}"
        assert rtl_m["locate"] == ref_m.stock_locate
        assert rtl_m["track"] == ref_m.tracking_number
        assert rtl_m["timestamp"] == ref_m.timestamp_ns

        if exp_t in ("A", "F"):
            assert rtl_m["order_ref"] == ref_m.order_ref
            assert rtl_m["side"] == ref_m.side
            assert rtl_m["shares"] == ref_m.shares
            assert rtl_m["price_raw"] == ref_m.raw_price
            if exp_t == "F":
                assert rtl_m["mpid"] == ref_m.mpid

        elif exp_t == "E":
            assert rtl_m["order_ref"] == ref_m.order_ref
            assert rtl_m["shares"] == ref_m.shares
            assert rtl_m["match_num"] == ref_m.match_number

        elif exp_t == "C":
            assert rtl_m["order_ref"] == ref_m.order_ref
            assert rtl_m["shares"] == ref_m.shares
            assert rtl_m["match_num"] == ref_m.match_number
            assert rtl_m["printable"] == ref_m.printable
            assert rtl_m["price_raw"] == ref_m.raw_price

        elif exp_t == "X":
            assert rtl_m["order_ref"] == ref_m.order_ref
            assert rtl_m["shares"] == ref_m.shares

        elif exp_t == "D":
            assert rtl_m["order_ref"] == ref_m.order_ref

        elif exp_t == "U":
            assert rtl_m["orig_ref"] == ref_m.original_order_ref
            assert rtl_m["new_ref"] == ref_m.new_order_ref
            assert rtl_m["shares"] == ref_m.shares
            assert rtl_m["price_raw"] == ref_m.raw_price


@cocotb.test()
async def test_sequence_gap_detection(dut):
    """Scenario 3: Sequence gap detection in MoldUDP64 depacketizer."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    msg_a = encode_itch_a(locate=1, track=1, ts_ns=100, order_ref=1, side="B", shares=10, stock="AAPL    ", price_raw=10000)
    pkt1 = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=100, msg_payloads=[msg_a, msg_a]) # 2 msgs -> next expected = 102
    await send_axis_frame(dut, pkt1)

    for _ in range(10):
        await RisingEdge(dut.clk)

    assert int(dut.expected_seq_out.value) == 102
    assert dut.gap_detected.value == 0

    # Inject Packet 2 with Gap: Seq = 105 (gap of 3)
    gap_detected_events = []

    async def monitor_gap():
        while True:
            await RisingEdge(dut.clk)
            if dut.gap_detected.value == 1:
                gap_detected_events.append(int(dut.gap_count.value))

    gap_task = cocotb.start_soon(monitor_gap())
    pkt2 = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=105, msg_payloads=[msg_a])
    await send_axis_frame(dut, pkt2)

    for _ in range(15):
        await RisingEdge(dut.clk)

    gap_task.cancel()

    assert len(gap_detected_events) == 1, f"Expected 1 gap event, got {len(gap_detected_events)}"
    assert gap_detected_events[0] == 3, f"Expected gap_count=3, got {gap_detected_events[0]}"
    assert int(dut.expected_seq_out.value) == 106


@cocotb.test()
async def test_unsupported_message_drop(dut):
    """Scenario 5: Handling unsupported message type without pipeline stall."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # ITCH System Event 'S' (12 bytes)
    msg_s = b"S" + struct.pack(">HH", 0, 0) + (1000).to_bytes(6, "big") + b"O"
    msg_a = encode_itch_a(locate=10, track=1, ts_ns=2000, order_ref=555, side="B", shares=20, stock="AAPL    ", price_raw=1450000)

    frame = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=500, msg_payloads=[msg_s, msg_a])

    dropped_events = []
    valid_events = []

    async def monitor():
        while True:
            await RisingEdge(dut.clk)
            if dut.msg_drop.value == 1:
                dropped_events.append(int(dut.unsupported_type_code.value))
            if dut.parsed_msg_valid.value == 1:
                valid_events.append(int(dut.out_order_ref.value))

    mon_task = cocotb.start_soon(monitor())
    await send_axis_frame(dut, frame)

    for _ in range(25):
        await RisingEdge(dut.clk)

    mon_task.cancel()

    assert len(dropped_events) == 1, f"Expected 1 dropped event, got {len(dropped_events)}"
    assert dropped_events[0] == ord("S"), f"Expected drop code 'S' (83), got {dropped_events[0]}"
    assert len(valid_events) == 1, f"Expected valid 'A' message to be decoded, got {len(valid_events)}"
    assert valid_events[0] == 555
