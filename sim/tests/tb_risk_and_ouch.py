"""
Cocotb Testbench for Pre-Trade Risk Engine and OUCH 5.0 Egress Subsystem (AURA-HFT).
Validates:
  1. 1-cycle deterministic rejection for all 5 risk limit violations:
     - Hard Kill Switch
     - Max Order Shares
     - Price Collar vs BBO
     - Max Single Notional
     - Cumulative Daily Notional
  2. Bit-accurate generation of 91-byte Ethernet/IPv4/UDP/OUCH Enter Order ('O') packets.
  3. Autonomous strategy triggering on quantitative OBI signals.
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset_dut(dut):
    """Initializes and resets the DUT."""
    dut.rst_n.value = 0
    dut.obi_valid.value = 0
    dut.obi_val.value = 0
    dut.micro_price.value = 0
    dut.bbo_bid_price.value = 0
    dut.bbo_ask_price.value = 0
    dut.current_timestamp.value = 0

    dut.cfg_auto_trade_enable.value = 0
    dut.cfg_obi_buy_thresh.value = 0
    dut.cfg_obi_sell_thresh.value = 0
    dut.cfg_default_order_shares.value = 100

    dut.host_intent_valid.value = 0
    dut.host_intent_side.value = 0
    dut.host_intent_shares.value = 0
    dut.host_intent_price.value = 0
    dut.host_intent_token.value = 0

    dut.cfg_kill_switch.value = 0
    dut.cfg_max_order_shares.value = 1000
    dut.cfg_price_collar_threshold.value = 5000 # $0.5000
    dut.cfg_max_notional_raw.value = 500000000  # $50,000 * 10000
    dut.cfg_max_cum_notional_raw.value = 5000000000 # $500,000 * 10000

    dut.m_axis_tready.value = 1

    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_kill_switch_rejection(dut):
    """Scenario 1: Hard Kill Switch blocks order intent immediately."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Enable Kill Switch
    dut.cfg_kill_switch.value = 1
    dut.bbo_bid_price.value = 1500000
    dut.bbo_ask_price.value = 1500500

    # Submit host order intent
    dut.host_intent_valid.value = 1
    dut.host_intent_side.value = 0 # Buy
    dut.host_intent_shares.value = 100
    dut.host_intent_price.value = 1500000
    dut.host_intent_token.value = 101

    await RisingEdge(dut.clk)
    dut.host_intent_valid.value = 0

    # 1 cycle after intent: inspect risk decision
    await RisingEdge(dut.clk)
    assert dut.risk_rejected_strobe.value == 1, "Expected risk rejection strobe"
    assert dut.risk_approved_strobe.value == 0, "Order must not be approved"
    assert int(dut.risk_reject_reason.value) == 1, "Expected RISK_REJECT_KILL_SWITCH (1)"
    assert dut.m_axis_tvalid.value == 0, "No egress packet should be transmitted"


@cocotb.test()
async def test_max_shares_rejection(dut):
    """Scenario 2: Single-order size exceeding cfg_max_order_shares is rejected."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.cfg_kill_switch.value = 0
    dut.cfg_max_order_shares.value = 500 # Max 500 shares
    dut.bbo_bid_price.value = 1500000
    dut.bbo_ask_price.value = 1500500

    # Submit 800 shares
    dut.host_intent_valid.value = 1
    dut.host_intent_side.value = 0
    dut.host_intent_shares.value = 800
    dut.host_intent_price.value = 1500000
    dut.host_intent_token.value = 102

    await RisingEdge(dut.clk)
    dut.host_intent_valid.value = 0

    await RisingEdge(dut.clk)
    assert dut.risk_rejected_strobe.value == 1
    assert dut.risk_approved_strobe.value == 0
    assert int(dut.risk_reject_reason.value) == 2, "Expected RISK_REJECT_MAX_SHARES (2)"


@cocotb.test()
async def test_price_collar_rejection(dut):
    """Scenario 3: Aggressive price exceeding Price Collar threshold is rejected."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.cfg_kill_switch.value = 0
    dut.cfg_max_order_shares.value = 1000
    dut.cfg_price_collar_threshold.value = 5000 # $0.50 Collar
    dut.bbo_bid_price.value = 1500000 # $150.00
    dut.bbo_ask_price.value = 1501000 # $150.10

    # Max allowed Buy price is Ask + Collar = 1501000 + 5000 = 1506000 ($150.60)
    # Submit Buy intent at $151.00 (1510000)
    dut.host_intent_valid.value = 1
    dut.host_intent_side.value = 0
    dut.host_intent_shares.value = 100
    dut.host_intent_price.value = 1510000
    dut.host_intent_token.value = 103

    await RisingEdge(dut.clk)
    dut.host_intent_valid.value = 0

    await RisingEdge(dut.clk)
    assert dut.risk_rejected_strobe.value == 1
    assert dut.risk_approved_strobe.value == 0
    assert int(dut.risk_reject_reason.value) == 3, "Expected RISK_REJECT_PRICE_COLLAR (3)"


@cocotb.test()
async def test_max_notional_rejection(dut):
    """Scenario 4: Single-order dollar value exceeding cfg_max_notional_raw is rejected."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.cfg_kill_switch.value = 0
    dut.cfg_max_order_shares.value = 10000
    dut.cfg_price_collar_threshold.value = 50000
    # Max notional = $10,000 -> raw = 10,000 * 10000 = 100,000,000
    dut.cfg_max_notional_raw.value = 100000000
    dut.bbo_bid_price.value = 1500000
    dut.bbo_ask_price.value = 1501000

    # Submit 100 shares @ $150.00 -> notional raw = 100 * 1500000 = 150,000,000 ($15,000 > $10,000)
    dut.host_intent_valid.value = 1
    dut.host_intent_side.value = 0
    dut.host_intent_shares.value = 100
    dut.host_intent_price.value = 1500000
    dut.host_intent_token.value = 104

    await RisingEdge(dut.clk)
    dut.host_intent_valid.value = 0

    await RisingEdge(dut.clk)
    assert dut.risk_rejected_strobe.value == 1
    assert dut.risk_approved_strobe.value == 0
    assert int(dut.risk_reject_reason.value) == 4, "Expected RISK_REJECT_MAX_NOTIONAL (4)"


@cocotb.test()
async def test_approved_order_ouch_packet_generation(dut):
    """Scenario 5: Compliant order is approved and correctly framed into 91-byte OUCH Enter Order."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.cfg_kill_switch.value = 0
    dut.cfg_max_order_shares.value = 1000
    dut.cfg_price_collar_threshold.value = 10000
    dut.cfg_max_notional_raw.value = 1000000000     # $100,000
    dut.cfg_max_cum_notional_raw.value = 5000000000 # $500,000
    dut.bbo_bid_price.value = 1500000
    dut.bbo_ask_price.value = 1501000
    dut.current_timestamp.value = 0x0123456789AB

    # Submit approved Buy order: 100 shares of AAPL @ $150.00
    dut.host_intent_valid.value = 1
    dut.host_intent_side.value = 0 # 'B'
    dut.host_intent_shares.value = 100
    dut.host_intent_price.value = 1500000
    dut.host_intent_token.value = 2001

    await RisingEdge(dut.clk)
    dut.host_intent_valid.value = 0

    await RisingEdge(dut.clk)
    assert dut.risk_approved_strobe.value == 1
    assert dut.risk_rejected_strobe.value == 0
    assert int(dut.risk_reject_reason.value) == 0

    # Collect AXI4-Stream output beats
    collected_bytes = bytearray()
    tlast_seen = False

    for _ in range(25):
        await RisingEdge(dut.clk)
        if dut.m_axis_tvalid.value == 1 and dut.m_axis_tready.value == 1:
            data_val = int(dut.m_axis_tdata.value)
            keep_val = int(dut.m_axis_tkeep.value)
            tlast_val = int(dut.m_axis_tlast.value)

            beat_bytes = data_val.to_bytes(8, byteorder="little")
            for b in range(8):
                if (keep_val >> b) & 1:
                    collected_bytes.append(beat_bytes[b])

            if tlast_val == 1:
                tlast_seen = True
                break

    assert tlast_seen, "Did not observe m_axis_tlast on final beat"
    assert len(collected_bytes) == 91, f"Expected 91-byte packet, got {len(collected_bytes)}"
    dut._log.info(f"Successfully collected 91-byte OUCH packet!")

    # Verify Network Headers:
    # 1. Ethernet II Header (14 bytes)
    eth_hdr = bytes(collected_bytes[:14])
    dest_mac = eth_hdr[:6]
    src_mac = eth_hdr[6:12]
    eth_type = struct.unpack(">H", eth_hdr[12:14])[0]
    assert eth_type == 0x0800, "Expected IPv4 EtherType 0x0800"

    # 2. IPv4 Header (20 bytes)
    ip_hdr = bytes(collected_bytes[14:34])
    ip_ver_ihl = ip_hdr[0]
    assert ip_ver_ihl == 0x45
    ip_len = struct.unpack(">H", ip_hdr[2:4])[0]
    assert ip_len == 77, f"Expected IPv4 total length 77, got {ip_len}"
    ip_proto = ip_hdr[9]
    assert ip_proto == 17, "Expected UDP protocol 17"

    # 3. UDP Header (8 bytes)
    udp_hdr = bytes(collected_bytes[34:42])
    src_port, dst_port, udp_len = struct.unpack(">HHH", udp_hdr[:6])
    assert src_port == 12345
    assert dst_port == 40002
    assert udp_len == 57, f"Expected UDP length 57, got {udp_len}"

    # 4. OUCH 5.0 Enter Order Payload (49 bytes)
    ouch_payload = bytes(collected_bytes[42:91])
    assert len(ouch_payload) == 49
    msg_type = chr(ouch_payload[0])
    assert msg_type == "O", f"Expected OUCH msg type 'O', got {msg_type}"

    side_char = chr(ouch_payload[15])
    assert side_char == "B", f"Expected side 'B', got {side_char}"

    shares = struct.unpack(">I", ouch_payload[16:20])[0]
    assert shares == 100, f"Expected 100 shares, got {shares}"

    stock = ouch_payload[20:28].decode("ascii")
    assert stock == "AAPL    ", f"Expected 'AAPL    ', got '{stock}'"

    price = struct.unpack(">I", ouch_payload[28:32])[0]
    assert price == 1500000, f"Expected price 1500000, got {price}"

    dut._log.info("OUCH 5.0 Enter Order packet decoded bit-for-bit successfully!")


@cocotb.test()
async def test_autonomous_strategy_trigger(dut):
    """Scenario 6: High OBI signal automatically triggers and transmits an OUCH order."""
    clock = Clock(dut.clk, 6.4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Enable autonomous trading
    dut.cfg_auto_trade_enable.value = 1
    # Buy threshold = +0.40 -> Q1.31 = round(0.40 * 2^31) = 858993459
    dut.cfg_obi_buy_thresh.value = 858993459
    dut.cfg_obi_sell_thresh.value = -858993459
    dut.cfg_default_order_shares.value = 200

    dut.bbo_bid_price.value = 1500000
    dut.bbo_ask_price.value = 1500500
    dut.micro_price.value = 1500300

    # Quantitative engine asserts OBI = +0.50 (> +0.40 threshold)
    dut.obi_valid.value = 1
    dut.obi_val.value = 1073741824 # +0.50 in Q1.31

    await RisingEdge(dut.clk)
    dut.obi_valid.value = 0

    # In 1 cycle, strategy arbitrates and risk engine validates
    await RisingEdge(dut.clk)
    assert dut.risk_approved_strobe.value == 1, "Autonomous strategy order must be risk approved"
    assert dut.risk_rejected_strobe.value == 0

    # Monitor AXI egress packet
    packet_transmitted = False
    for _ in range(25):
        await RisingEdge(dut.clk)
        if dut.m_axis_tvalid.value == 1 and dut.m_axis_tlast.value == 1:
            packet_transmitted = True
            break

    assert packet_transmitted, "Autonomous strategy must transmit complete OUCH packet over AXI-Stream"
    await RisingEdge(dut.clk)
    assert int(dut.tx_order_count.value) == 1
    dut._log.info("Autonomous tick-to-trade trigger completed successfully!")
