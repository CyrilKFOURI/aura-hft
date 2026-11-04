"""
Cocotb Testbench for Complete End-to-End Tick-to-Trade Hardware Pipeline (AURA-HFT).
DUT: aura_hft_top.
Simulates:
  1. Ethernet II / IPv4 / UDP / MoldUDP64 / ITCH 5.0 streaming packet injection over RX AXI-Stream.
  2. Cut-through depacketization and streaming decoding.
  3. LOB price ladder update and O(1) Top-of-Book BBO update.
  4. Pipelined OBI and Micro-Price signal generation.
  5. Autonomous strategy trigger and 1-cycle Pre-Trade Risk validation.
  6. Line-rate generation of 91-byte OUCH 5.0 Enter Order over TX AXI-Stream.
  7. Exact cycle-accurate tick-to-trade latency measurement.
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from sim.tests.tb_itch_parser import (
    build_eth_ip_udp_frame,
    send_axis_frame,
    encode_itch_a,
    encode_itch_e,
)


async def reset_dut(dut):
    """Initializes and resets the top-level DUT."""
    dut.rst_n.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tkeep.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
    dut.m_axis_tready.value = 1

    dut.cfg_auto_trade_enable.value = 0
    dut.cfg_obi_buy_thresh.value = 0
    dut.cfg_obi_sell_thresh.value = 0
    dut.cfg_default_order_shares.value = 100

    dut.cfg_kill_switch.value = 0
    dut.cfg_max_order_shares.value = 2000
    dut.cfg_price_collar_threshold.value = 10000 # $1.00 collar
    dut.cfg_max_notional_raw.value = 1000000000   # $100,000 * 10000
    dut.cfg_max_cum_notional_raw.value = 5000000000 # $500,000 * 10000

    dut.host_intent_valid.value = 0
    dut.host_intent_side.value = 0
    dut.host_intent_shares.value = 0
    dut.host_intent_price.value = 0
    dut.host_intent_token.value = 0

    dut.cfg_queue_valid.value = 0
    dut.cfg_queue_slot.value = 0
    dut.cfg_queue_side.value = 0
    dut.cfg_queue_price.value = 0
    dut.cfg_queue_shares.value = 0
    dut.cfg_queue_initial_vol.value = 0
    dut.cfg_queue_cancel.value = 0

    # AXI4-Lite Control Slave inputs
    dut.s_axi_awaddr.value = 0
    dut.s_axi_awprot.value = 0
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wdata.value = 0
    dut.s_axi_wstrb.value = 0
    dut.s_axi_wvalid.value = 0
    dut.s_axi_bready.value = 1
    dut.s_axi_araddr.value = 0
    dut.s_axi_arprot.value = 0
    dut.s_axi_arvalid.value = 0
    dut.s_axi_rready.value = 1

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_end_to_end_tick_to_trade_pipeline(dut):
    """
    Scenario 1: Full tick-to-trade autonomous execution.
    Injects market orders, causes high OBI imbalance (+0.60), and observes
    automatic generation of OUCH Enter Order with measured sub-55-cycle latency.
    """
    clock = Clock(dut.clk, 6.4, unit="ns") # 156.25 MHz clock
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Enable autonomous trading with +0.40 Buy threshold (858993459 in Q1.31)
    dut.cfg_auto_trade_enable.value = 1
    dut.cfg_obi_buy_thresh.value = 858993459
    dut.cfg_obi_sell_thresh.value = -858993459
    dut.cfg_default_order_shares.value = 100

    # 1. Packet 1: Initial Book Setup
    # Bid: 100 shares @ $150.00 | Ask: 200 shares @ $150.10
    msg_b1 = encode_itch_a(locate=1, track=1, ts_ns=1000, order_ref=1001, side="B", shares=100, stock="AAPL    ", price_raw=1500000)
    msg_a1 = encode_itch_a(locate=1, track=2, ts_ns=2000, order_ref=1002, side="S", shares=200, stock="AAPL    ", price_raw=1501000)
    frame1 = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=1, msg_payloads=[msg_b1, msg_a1])

    await send_axis_frame(dut, frame1)

    # Wait for LOB to initialize
    for _ in range(40):
        await RisingEdge(dut.clk)

    assert dut.bbo_valid.value == 1
    assert int(dut.best_bid_price.value) == 1500000
    assert int(dut.best_bid_shares.value) == 100
    assert int(dut.best_ask_price.value) == 1501000
    assert int(dut.best_ask_shares.value) == 200
    dut._log.info("LOB initialized successfully: Bid=$150.00 (100) / Ask=$150.10 (200)")

    # 2. Packet 2: High Imbalance Trigger
    # Add large Buy order: 700 shares @ $150.00
    # New Bid volume = 800, Ask volume = 200 -> OBI = (800 - 200) / 1000 = +0.60 (> +0.40)!
    msg_b2 = encode_itch_a(locate=1, track=3, ts_ns=3000, order_ref=1003, side="B", shares=700, stock="AAPL    ", price_raw=1500000)
    frame2 = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=3, msg_payloads=[msg_b2])

    # Monitor TX Egress concurrently
    tx_packet_bytes = bytearray()
    t2t_cycles_recorded = 0

    async def tx_monitor():
        nonlocal t2t_cycles_recorded
        while True:
            await RisingEdge(dut.clk)
            if dut.m_axis_tvalid.value == 1 and dut.m_axis_tready.value == 1:
                data_val = int(dut.m_axis_tdata.value)
                keep_val = int(dut.m_axis_tkeep.value)
                beat_bytes = data_val.to_bytes(8, byteorder="little")
                for b in range(8):
                    if (keep_val >> b) & 1:
                        tx_packet_bytes.append(beat_bytes[b])
                if dut.tick_to_trade_strobe.value == 1:
                    t2t_cycles_recorded = int(dut.last_tick_to_trade_cycles.value)
                if dut.m_axis_tlast.value == 1:
                    break

    mon_task = cocotb.start_soon(tx_monitor())

    # Send trigger packet
    await send_axis_frame(dut, frame2)

    # Wait for the pipeline to compute OBI and emit OUCH order
    for _ in range(60):
        await RisingEdge(dut.clk)
        if len(tx_packet_bytes) >= 91:
            break

    mon_task.cancel()

    # 3. Verify End-to-End Execution
    assert len(tx_packet_bytes) == 91, f"Expected 91-byte OUCH frame, got {len(tx_packet_bytes)}"
    dut._log.info(f"Complete OUCH frame emitted! Length = {len(tx_packet_bytes)} bytes")

    # Decode OUCH payload (bytes 42..91)
    ouch_body = bytes(tx_packet_bytes[42:91])
    msg_type = chr(ouch_body[0])
    side = chr(ouch_body[15])
    shares = struct.unpack(">I", ouch_body[16:20])[0]
    stock = ouch_body[20:28].decode("ascii")
    price = struct.unpack(">I", ouch_body[28:32])[0]

    assert msg_type == "O", f"Expected OUCH 'O', got {msg_type}"
    assert side == "B", f"Expected Buy 'B', got {side}"
    assert shares == 100, f"Expected 100 shares, got {shares}"
    assert stock == "AAPL    ", f"Expected AAPL, got {stock}"
    assert price == 1500000, f"Expected price 1500000, got {price}"

    # Verify measured tick-to-trade latency
    latency_cycles = int(dut.last_tick_to_trade_cycles.value)
    latency_ns = latency_cycles * 6.4
    dut._log.info(f"Hardware Tick-to-Trade Latency: {latency_cycles} clock cycles = {latency_ns:.1f} ns!")
    assert latency_cycles > 0, "Latency cycles must be positive"
    assert latency_cycles < 60, f"Expected sub-60 cycle latency, got {latency_cycles} cycles"


@cocotb.test()
async def test_end_to_end_risk_kill_switch_protection(dut):
    """Scenario 2: Hard Kill Switch immediately suppresses order generation on high OBI."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Activate Hard Kill Switch
    dut.cfg_kill_switch.value = 1
    dut.cfg_auto_trade_enable.value = 1
    dut.cfg_obi_buy_thresh.value = 858993459 # +0.40

    # Send high imbalance trigger
    msg_b = encode_itch_a(locate=1, track=1, ts_ns=1000, order_ref=1001, side="B", shares=800, stock="AAPL    ", price_raw=1500000)
    msg_a = encode_itch_a(locate=1, track=2, ts_ns=2000, order_ref=1002, side="S", shares=200, stock="AAPL    ", price_raw=1501000)
    frame = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=10, msg_payloads=[msg_b, msg_a])

    await send_axis_frame(dut, frame)

    for _ in range(50):
        await RisingEdge(dut.clk)
        # Verify that kill switch completely prevented egress transmission
        assert dut.m_axis_tvalid.value == 0, "Kill switch must prevent any AXI-Stream egress"

    assert int(dut.tx_order_count.value) == 0, "No orders should be transmitted when Kill Switch is active"
    assert int(dut.total_orders_rejected.value) >= 1, "Order must be counted in rejected orders"
    dut._log.info("Kill switch verified: Order successfully intercepted and suppressed!")


@cocotb.test()
async def test_end_to_end_queue_tracker_integration(dut):
    """Scenario 3: Virtual order queue tracking integrated with ITCH market executions."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # 1. Register virtual passive buy order in slot 0 at $150.00 with 400 shares ahead
    dut.cfg_queue_valid.value = 1
    dut.cfg_queue_slot.value = 0
    dut.cfg_queue_side.value = 0 # 'B'
    dut.cfg_queue_price.value = 1500000
    dut.cfg_queue_shares.value = 100
    dut.cfg_queue_initial_vol.value = 400
    dut.cfg_queue_cancel.value = 0

    await RisingEdge(dut.clk)
    dut.cfg_queue_valid.value = 0

    await RisingEdge(dut.clk)
    assert int(dut.slot_volume_ahead[0].value) == 400
    assert (int(dut.slot_is_top_of_queue.value) & 1) == 0

    # 2. Add real order 1001 at $150.00 (500 shares)
    msg_add = encode_itch_a(locate=1, track=1, ts_ns=1000, order_ref=5001, side="B", shares=500, stock="AAPL    ", price_raw=1500000)
    # 3. Market execution: execute 300 shares of order 5001
    msg_exec = encode_itch_e(locate=1, track=2, ts_ns=2000, order_ref=5001, shares=300, match_num=999)

    frame = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=20, msg_payloads=[msg_add, msg_exec])
    await send_axis_frame(dut, frame)

    # Wait for pipeline processing
    for _ in range(40):
        await RisingEdge(dut.clk)

    # Volume ahead should be reduced from 400 by 300 -> 100 shares remaining!
    vol_ahead = int(dut.slot_volume_ahead[0].value)
    dut._log.info(f"Queue volume ahead after execution: {vol_ahead}")
    assert vol_ahead == 100, f"Expected 100 shares ahead, got {vol_ahead}"
    assert (int(dut.slot_is_top_of_queue.value) & 1) == 0

    # 4. Another execution of 100 shares
    msg_exec2 = encode_itch_e(locate=1, track=3, ts_ns=3000, order_ref=5001, shares=100, match_num=1000)
    frame2 = build_eth_ip_udp_frame(session_name=b"SESSION001", seq_num=22, msg_payloads=[msg_exec2])
    await send_axis_frame(dut, frame2)

    for _ in range(40):
        await RisingEdge(dut.clk)

    # Now volume ahead reaches 0 -> top of queue!
    assert int(dut.slot_volume_ahead[0].value) == 0
    assert (int(dut.slot_is_top_of_queue.value) & 1) == 1
    dut._log.info("Integrated Queue Tracker reached Top-of-Queue successfully!")
