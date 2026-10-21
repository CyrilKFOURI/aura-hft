"""Fault-injection bench for the reference ingress + order book (itch_lob_pipeline_top).

Every scenario drives faulty traffic into the RTL, replays the *correct*
interpretation of that traffic into the golden model, and requires the RTL
top-5 book to match it. Telemetry (gap / duplicate pulses, drop counters,
FIFO overflow) is checked against the documented behaviour.

Documented behaviour (see reports/robustness.md):
  * unknown ITCH type          -> message dropped, dropped_msg_count + 1, book unchanged
  * unknown symbol (A/F)       -> ignored by the symbol filter, book unchanged
  * E/C/X/D/U on unknown ref   -> table miss, book unchanged
  * zero-share add             -> no visible level
  * MoldUDP64 gap              -> gap_detected pulse + gap_count, messages still applied
  * MoldUDP64 duplicate        -> duplicate_detected pulse, frame discarded
  * truncated frame            -> partial message discarded, next frame parsed cleanly
  * non IPv4/UDP frame         -> consumed and dropped, sequence state untouched
  * back-to-back burst         -> no request lost: the book FIFO back-pressures the
                                  ingress (s_axis_tready), overflow counter stays 0
"""

import json
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.utils import get_sim_time

from sim.golden_model.golden_order_book import GoldenOrderBook
from sim.golden_model.itch_decoder import ItchDecoder
from sim.tests.tb_itch_parser import (
    build_eth_ip_udp_frame,
    encode_itch_a,
    encode_itch_d,
    encode_itch_e,
    encode_itch_u,
    encode_itch_x,
    send_axis_frame,
)
from sim.tests.tb_order_book import reset_dut

SYM = "AAPL"
SESSION = b"FAULTINJ00"


class Monitor:
    """Counts single-cycle telemetry pulses."""

    def __init__(self, dut):
        self.dut = dut
        self.gaps = self.dups = self.misses = 0
        cocotb.start_soon(self._run())

    async def _run(self):
        while True:
            await RisingEdge(self.dut.clk)
            self.gaps += int(self.dut.gap_detected.value)
            self.dups += int(self.dut.unused_dup_detected.value)
            self.misses += int(self.dut.table_miss.value)


def add(ref, side, shares, price, stock=SYM):
    return encode_itch_a(1, 0, 1000 + ref, ref, side, shares, stock, price)


def rtl_levels(dut, side):
    prices = dut.top5_bid_price if side == "B" else dut.top5_ask_price
    shares = dut.top5_bid_shares if side == "B" else dut.top5_ask_shares
    out = []
    for i in range(5):
        p, s = int(prices[i].value), int(shares[i].value)
        if s == 0:
            break
        out.append((p, s))
    return out


def golden_levels(book, side):
    lv = book.top_bids(10) if side == "B" else book.top_asks(10)
    return [(round(p * 10000), s) for p, s in lv if s > 0][:5]


def apply(book, msgs):
    for raw in msgs:
        msg = ItchDecoder.decode_message(raw)
        if msg is not None and msg.msg_type in "AFECXDU":
            book.process_message(msg)


async def settle(dut, cycles=40):
    lob = dut.u_lob_engine
    for _ in range(cycles):
        await RisingEdge(dut.clk)
    while int(lob.fifo_wr.value) != int(lob.fifo_rd.value):
        await RisingEdge(dut.clk)
    for _ in range(cycles):
        await RisingEdge(dut.clk)


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 6.4, unit="ns").start())
    await reset_dut(dut)
    return Monitor(dut), GoldenOrderBook(SYM)


def assert_book(dut, book, ctx):
    for side in "BS":
        rtl, exp = rtl_levels(dut, side), golden_levels(book, side)
        assert rtl == exp, f"{ctx}: side {side} RTL {rtl} != golden {exp}"


async def send(dut, seq, msgs):
    await send_axis_frame(dut, build_eth_ip_udp_frame(SESSION, seq, msgs))


BASE = [add(1, "B", 100, 1_500_000), add(2, "B", 200, 1_499_900),
        add(3, "S", 300, 1_500_100), add(4, "S", 50, 1_500_200)]


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_unknown_message_types(dut):
    """System event 'S', stock directory 'R' and garbage type '?' are dropped."""
    mon, book = await setup(dut)
    sys_evt = b"S" + bytes(10) + b"O"                    # 12 bytes
    stock_dir = b"R" + bytes(38)                          # 39 bytes
    garbage = b"?" + bytes(20)
    msgs = [BASE[0], sys_evt, BASE[1], stock_dir, BASE[2], garbage, BASE[3]]
    await send(dut, 1, msgs)
    await settle(dut)
    apply(book, msgs)
    assert_book(dut, book, "unknown types")
    assert int(dut.u_ingress.dropped_msg_count.value) == 3
    assert int(dut.parsed_msg_count.value) == 4
    assert mon.gaps == 0 and mon.dups == 0


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_unknown_symbol(dut):
    """Adds for another symbol never reach the book."""
    mon, book = await setup(dut)
    msgs = BASE + [add(10, "B", 999, 1_600_000, "MSFT"), add(11, "S", 999, 1_400_000, "TSLA")]
    await send(dut, 1, msgs)
    await settle(dut)
    apply(book, msgs)
    assert_book(dut, book, "unknown symbol")
    assert int(dut.active_order_count.value) == 4


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_unknown_order_refs(dut):
    """E / X / D / U on refs that were never added (or other symbols) are no-ops."""
    mon, book = await setup(dut)
    await send(dut, 1, BASE + [add(10, "B", 500, 1_499_000, "MSFT")])
    await settle(dut)
    faults = [encode_itch_e(1, 0, 2000, 777, 50, 1), encode_itch_x(1, 0, 2001, 778, 10),
              encode_itch_d(1, 0, 2002, 779), encode_itch_u(1, 0, 2003, 780, 781, 10, 1_500_050),
              encode_itch_e(1, 0, 2004, 10, 100, 2),        # ref 10 belongs to MSFT (filtered)
              encode_itch_d(1, 0, 2005, 10)]
    misses_before = mon.misses
    await send(dut, 6, faults)               # frame 1 carried seq 1..5
    await settle(dut)
    apply(book, BASE + faults)
    assert_book(dut, book, "unknown refs")
    assert int(dut.active_order_count.value) == 4
    assert mon.misses - misses_before == len(faults), f"table_miss pulses {mon.misses - misses_before}"


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_zero_share_orders(dut):
    """A zero-share add (better price) must not create a visible level or hide real ones."""
    mon, book = await setup(dut)
    msgs = BASE + [add(20, "B", 0, 1_500_050), add(21, "S", 0, 1_500_060),
                   encode_itch_e(1, 0, 3000, 1, 0, 9), encode_itch_x(1, 0, 3001, 3, 0)]
    await send(dut, 1, msgs)
    await settle(dut)
    apply(book, msgs)
    assert_book(dut, book, "zero shares")


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_sequence_gap(dut):
    """A forward jump flags the gap (pulse + size) and keeps applying data."""
    mon, book = await setup(dut)
    await send(dut, 1, BASE[:2])            # expects 3 next
    await send(dut, 3, BASE[2:3])           # in order
    await send(dut, 10, BASE[3:])           # gap of 6 (4..9)
    await settle(dut)
    apply(book, BASE)
    assert_book(dut, book, "gap")
    assert mon.gaps == 1
    assert int(dut.unused_gap_count.value) == 6
    assert int(dut.unused_expected_seq.value) == 11


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_sequence_duplicate(dut):
    """A retransmitted frame is flagged and must not be applied twice."""
    mon, book = await setup(dut)
    await send(dut, 1, BASE[:2])
    await send(dut, 3, BASE[2:])
    await send(dut, 1, BASE[:2])            # full duplicate
    await send(dut, 2, BASE[1:2])           # duplicate inside an earlier frame
    await send(dut, 5, [add(5, "B", 10, 1_499_800)])
    await settle(dut)
    apply(book, BASE + [add(5, "B", 10, 1_499_800)])
    assert mon.dups == 2
    assert mon.gaps == 0
    assert_book(dut, book, "duplicate")


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_truncated_frames(dut):
    """A frame cut inside a message must not corrupt the following frames."""
    mon, book = await setup(dut)
    await send(dut, 1, BASE[:2])
    full = build_eth_ip_udp_frame(SESSION, 3, [add(30, "B", 7777, 1_500_090)])
    for cut in (len(full) - 1, len(full) - 13, len(full) - 30, 70):
        await send_axis_frame(dut, full[:cut])
        await settle(dut, 10)
    await send(dut, 4, BASE[2:])
    await settle(dut)
    apply(book, BASE)
    assert_book(dut, book, "truncated")
    assert int(dut.active_order_count.value) == 4
    # Header-only runt frames (shorter than Eth+IP+UDP+Mold) are ignored too.
    await send_axis_frame(dut, full[:30])
    await send(dut, 6, [add(31, "S", 5, 1_500_300)])
    await settle(dut)
    apply(book, [add(31, "S", 5, 1_500_300)])
    assert_book(dut, book, "runt")


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_zero_length_block(dut):
    """A MoldUDP64 block of length 0 must not wedge the parser."""
    mon, book = await setup(dut)
    frame = build_eth_ip_udp_frame(SESSION, 1, [BASE[0]])
    bad = frame + b"\x00\x00"                       # trailing zero-length block
    await send_axis_frame(dut, bad)
    await settle(dut, 20)
    await send(dut, 3, BASE[1:])
    await settle(dut)
    apply(book, BASE)
    assert_book(dut, book, "zero-length block")


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_non_mold_frames(dut):
    """ARP, IPv4 with options and TCP frames are consumed and dropped, without touching the sequence state."""
    mon, book = await setup(dut)
    good = build_eth_ip_udp_frame(SESSION, 1, BASE)
    poison = build_eth_ip_udp_frame(SESSION, 900, [add(50, "B", 999, 1_600_000)])
    arp = poison[:12] + b"" + poison[14:]
    ip_opts = poison[:14] + b"F" + poison[15:]
    tcp = poison[:23] + b"" + poison[24:]
    for f in (arp, ip_opts, tcp):
        await send_axis_frame(dut, f)
    await send_axis_frame(dut, good)
    await settle(dut)
    apply(book, BASE)
    assert_book(dut, book, "non-mold frames")
    assert int(dut.u_ingress.u_depacketizer.dropped_bad_hdr_frames.value) == 3
    assert mon.gaps == 0 and mon.dups == 0
    assert int(dut.unused_expected_seq.value) == 5


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def test_back_to_back_burst(dut):
    """Back-to-back full frames (38 adds/frame, no idle) must not overflow the request FIFO."""
    mon, book = await setup(dut)
    rng = random.Random(29)
    msgs, ref = [], 100
    for _ in range(1200):
        side = rng.choice("BS")
        price = 1_500_000 + (-1 if side == "B" else 1) * rng.randrange(1, 40) * 100
        msgs.append(add(ref, side, rng.randrange(1, 500), price))
        ref += 1
    for _ in range(600):                              # executions / cancels / deletes on live orders
        victim = rng.randrange(100, ref)
        kind = rng.randrange(3)
        msgs.append(encode_itch_e(1, 0, 5000, victim, rng.randrange(1, 100), 1) if kind == 0 else
                    encode_itch_x(1, 0, 5000, victim, rng.randrange(1, 100)) if kind == 1 else
                    encode_itch_d(1, 0, 5000, victim))
    seq = 1
    start = get_sim_time("ns")
    for i in range(0, len(msgs), 38):
        chunk = msgs[i:i + 38]
        await send(dut, seq, chunk)                   # no idle cycle between frames
        seq += len(chunk)
    sent = get_sim_time("ns")
    await settle(dut, 200)
    apply(book, msgs)
    cycles = (sent - start) / 6.4
    stats = {"messages": len(msgs), "frames": (len(msgs) + 37) // 38, "input_cycles": round(cycles),
             "msgs_per_cycle": round(len(msgs) / cycles, 4),
             "msgs_per_s_at_156MHz": round(len(msgs) / cycles * 156.25e6),
             "fifo_overflow": int(dut.u_lob_engine.fifo_overflow_count.value)}
    Path("sim/build").mkdir(parents=True, exist_ok=True)
    Path("sim/build/fault_burst.json").write_text(json.dumps(stats, indent=2))
    overflow = int(dut.u_lob_engine.fifo_overflow_count.value)
    dut._log.info(f"burst: {stats}")
    assert overflow == 0, f"request FIFO overflowed {overflow} times"
    assert_book(dut, book, "burst")
