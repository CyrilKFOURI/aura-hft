"""
tb_moldudp64_resilience.py

Cocotb testbench for MoldUDP64 Network Resilience, Gap Detection & Snapshot Recovery:
  - In-order nominal sequential processing (book in-sync)
  - Ultra-fast 1-cycle sequence gap detection and instant halt assertion
  - Autonomous Unicast re-request strobe generation
  - Infill reconciliation restoring book in-sync state
  - DMA snapshot state recovery
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset_dut(dut):
    """Reset DUT and initialize all inputs."""
    dut.rst_n.value = 0
    dut.pkt_header_valid.value = 0
    dut.pkt_session.value = 0
    dut.pkt_seq_num.value = 0
    dut.pkt_msg_count.value = 0

    dut.infill_valid.value = 0
    dut.infill_seq_num.value = 0
    dut.infill_msg_count.value = 0

    dut.snap_load_en.value = 0
    dut.snap_target_seq.value = 0
    dut.manual_resync_req.value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    await Timer(100, "ps")


@cocotb.test()
async def test_in_order_streaming(dut):
    """Verify in-order MoldUDP64 packet reception maintains IN_SYNC state without gap events."""
    cocotb.start_soon(Clock(dut.clk, 3.2, units="ns").start())
    await reset_dut(dut)

    session_id = int.from_bytes(b"NASDAQ0001", byteorder="big")

    # Packet 1: seq=1, count=3 -> expected advances to 4
    dut.pkt_header_valid.value = 1
    dut.pkt_session.value = session_id
    dut.pkt_seq_num.value = 1
    dut.pkt_msg_count.value = 3

    await RisingEdge(dut.clk)
    dut.pkt_header_valid.value = 0
    await Timer(100, "ps")

    assert dut.book_out_of_sync.value == 0, "Book must be in sync"
    assert dut.expected_seq_num.value == 4, f"Expected seq 4, got {dut.expected_seq_num.value}"
    assert dut.gap_event_counter.value == 0

    # Packet 2: seq=4, count=5 -> expected advances to 9
    dut.pkt_header_valid.value = 1
    dut.pkt_session.value = session_id
    dut.pkt_seq_num.value = 4
    dut.pkt_msg_count.value = 5

    await RisingEdge(dut.clk)
    dut.pkt_header_valid.value = 0
    await Timer(100, "ps")

    assert dut.book_out_of_sync.value == 0
    assert dut.expected_seq_num.value == 9
    assert dut.gap_event_counter.value == 0
    assert dut.rerequest_valid.value == 0


@cocotb.test()
async def test_gap_detection_and_re_request(dut):
    """Verify 1-cycle sequence gap detection, trading halt assertion, and Unicast re-request strobe."""
    cocotb.start_soon(Clock(dut.clk, 3.2, units="ns").start())
    await reset_dut(dut)

    session_id = int.from_bytes(b"NASDAQ0001", byteorder="big")

    # Baseline Packet: seq=1, count=5 -> expected advances to 6
    dut.pkt_header_valid.value = 1
    dut.pkt_session.value = session_id
    dut.pkt_seq_num.value = 1
    dut.pkt_msg_count.value = 5

    await RisingEdge(dut.clk)
    dut.pkt_header_valid.value = 0
    await Timer(100, "ps")

    assert dut.expected_seq_num.value == 6
    assert dut.book_out_of_sync.value == 0

    # Gap Packet: seq=10 arrives (missing 6, 7, 8, 9; count=4), count=2
    dut.pkt_header_valid.value = 1
    dut.pkt_session.value = session_id
    dut.pkt_seq_num.value = 10
    dut.pkt_msg_count.value = 2

    await RisingEdge(dut.clk)
    dut.pkt_header_valid.value = 0
    await Timer(100, "ps")

    # Check 1-cycle reaction!
    assert dut.book_out_of_sync.value == 1, "Book must immediately switch to OUT_OF_SYNC"
    assert dut.gap_detected_strobe.value == 1, "Gap strobe must be asserted"
    assert dut.rerequest_valid.value == 1, "Re-request strobe must be asserted"
    assert dut.rerequest_seq_num.value == 6, f"Expected re-request seq 6, got {dut.rerequest_seq_num.value}"
    assert dut.rerequest_count.value == 4, f"Expected re-request count 4, got {dut.rerequest_count.value}"
    assert dut.gap_event_counter.value == 1
    assert dut.total_lost_messages.value == 4

    await RisingEdge(dut.clk)
    await Timer(100, "ps")
    assert dut.gap_detected_strobe.value == 0, "Strobe must deassert after 1 cycle"
    assert dut.rerequest_valid.value == 0, "Strobe must deassert after 1 cycle"
    assert dut.book_out_of_sync.value == 1, "Book must stay OUT_OF_SYNC until reconciled"


@cocotb.test()
async def test_infill_reconciliation(dut):
    """Verify infill packet stream reconciles gap and restores book to IN_SYNC state."""
    cocotb.start_soon(Clock(dut.clk, 3.2, units="ns").start())
    await reset_dut(dut)

    session_id = int.from_bytes(b"NASDAQ0001", byteorder="big")

    # Packet 1: seq=1, count=10 -> expected advances to 11
    dut.pkt_header_valid.value = 1
    dut.pkt_session.value = session_id
    dut.pkt_seq_num.value = 1
    dut.pkt_msg_count.value = 10

    await RisingEdge(dut.clk)
    dut.pkt_header_valid.value = 0
    await Timer(100, "ps")

    # Gap packet: seq=20, count=5 -> target head becomes 25
    dut.pkt_header_valid.value = 1
    dut.pkt_session.value = session_id
    dut.pkt_seq_num.value = 20
    dut.pkt_msg_count.value = 5

    await RisingEdge(dut.clk)
    dut.pkt_header_valid.value = 0
    await Timer(100, "ps")

    assert dut.book_out_of_sync.value == 1

    # Infill batch 1: seq=11, count=4 -> advances expected to 15 (still missing 15..19)
    dut.infill_valid.value = 1
    dut.infill_seq_num.value = 11
    dut.infill_msg_count.value = 4

    await RisingEdge(dut.clk)
    dut.infill_valid.value = 0
    await Timer(100, "ps")

    assert dut.expected_seq_num.value == 15
    assert dut.book_out_of_sync.value == 1, "Still missing 15..19, book must remain halted"

    # Infill batch 2: seq=15, count=10 -> covers up to 25 (head of stream caught up!)
    dut.infill_valid.value = 1
    dut.infill_seq_num.value = 15
    dut.infill_msg_count.value = 10

    await RisingEdge(dut.clk)
    dut.infill_valid.value = 0
    await Timer(100, "ps")

    assert dut.book_out_of_sync.value == 0, "Book must be restored to IN_SYNC"
    assert dut.expected_seq_num.value == 25


@cocotb.test()
async def test_snapshot_recovery(dut):
    """Verify hot snapshot restoration immediately resynchronizes book and unhalts trading."""
    cocotb.start_soon(Clock(dut.clk, 3.2, units="ns").start())
    await reset_dut(dut)

    session_id = int.from_bytes(b"NASDAQ0001", byteorder="big")

    # Baseline packet
    dut.pkt_header_valid.value = 1
    dut.pkt_session.value = session_id
    dut.pkt_seq_num.value = 1
    dut.pkt_msg_count.value = 5
    await RisingEdge(dut.clk)
    dut.pkt_header_valid.value = 0
    await Timer(100, "ps")

    # Massive gap: seq=500
    dut.pkt_header_valid.value = 1
    dut.pkt_session.value = session_id
    dut.pkt_seq_num.value = 500
    dut.pkt_msg_count.value = 10
    await RisingEdge(dut.clk)
    dut.pkt_header_valid.value = 0
    await Timer(100, "ps")

    assert dut.book_out_of_sync.value == 1

    # Load complete snapshot state at seq=510 via DMA
    dut.snap_load_en.value = 1
    dut.snap_target_seq.value = 510

    await RisingEdge(dut.clk)
    dut.snap_load_en.value = 0
    await Timer(100, "ps")

    assert dut.book_out_of_sync.value == 0, "Snapshot must restore book to IN_SYNC"
    assert dut.expected_seq_num.value == 510
