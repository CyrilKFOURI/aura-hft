"""Co-simulation of itch_lob_pipeline_top on real NASDAQ ITCH 5.0 messages.

Each real message is sent in its own Ethernet/IPv4/UDP/MoldUDP64 frame. After
the pipeline settles, the RTL best bid/ask and top-5 depth are compared with
the golden-model expectation recorded by sim.validation.extract_symbol_stream.

Environment:
    REAL_STREAM  path to <capture>.<SYMBOL>.stream.json (required)
    REAL_LIMIT   max messages to replay (default: all)
    REAL_REPORT  JSON results path (default: reports/rtl_real_cosim.json)
    SETTLE       cycles to wait after each frame (default: 24)
"""

import json
import os
import time
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from sim.tests.tb_itch_parser import build_eth_ip_udp_frame, send_axis_frame
from sim.tests.tb_order_book import reset_dut

MAX_EXAMPLES = 20


def rtl_levels(dut, side: str) -> list:
    prices = dut.top5_bid_price if side == "B" else dut.top5_ask_price
    shares = dut.top5_bid_shares if side == "B" else dut.top5_ask_shares
    out = []
    for i in range(5):
        p, s = int(prices[i].value), int(shares[i].value)
        if s == 0:
            break
        out.append((p, s))
    return out


@cocotb.test()
async def test_real_nasdaq_stream(dut):
    """Replay a real per-symbol NASDAQ stream and count BBO / top-5 divergences."""
    data = json.loads(Path(os.environ["REAL_STREAM"]).read_text())
    stream = [(bytes.fromhex(h), [tuple(x) for x in b], [tuple(x) for x in a]) for h, b, a in data["stream"]]
    limit = int(os.environ.get("REAL_LIMIT") or len(stream))
    settle = int(os.environ.get("SETTLE", "24"))
    report_path = Path(os.environ.get("REAL_REPORT", "reports/rtl_real_cosim.json"))

    cocotb.start_soon(Clock(dut.clk, 6.4, unit="ns").start())
    await reset_dut(dut)

    bbo_mismatch = depth_mismatch = 0
    first_bbo_mismatch = None
    examples = []
    started = time.time()
    for n, (raw, exp_bids, exp_asks) in enumerate(stream[:limit], start=1):
        frame = build_eth_ip_udp_frame(session_name=b"NASDAQREAL", seq_num=n, msg_payloads=[raw])
        await send_axis_frame(dut, frame)
        for _ in range(settle):
            await RisingEdge(dut.clk)

        bids, asks = rtl_levels(dut, "B"), rtl_levels(dut, "S")
        if bids[:1] != exp_bids[:1] or asks[:1] != exp_asks[:1]:
            bbo_mismatch += 1
            first_bbo_mismatch = first_bbo_mismatch or n
        if bids != exp_bids or asks != exp_asks:
            depth_mismatch += 1
            if len(examples) < MAX_EXAMPLES:
                examples.append({"msg": n, "type": chr(raw[0]), "rtl_bids": bids, "exp_bids": exp_bids,
                                 "rtl_asks": asks, "exp_asks": exp_asks})
        if n % 5000 == 0:
            dut._log.info(f"{n:,} msgs, BBO mismatches {bbo_mismatch:,}, depth mismatches {depth_mismatch:,}")

    result = {
        "symbol": data["sizing"]["symbol"],
        "messages_replayed": min(limit, len(stream)),
        "bbo_mismatches": bbo_mismatch,
        "top5_mismatches": depth_mismatch,
        "first_bbo_mismatch_msg": first_bbo_mismatch,
        "active_order_count_end": int(dut.active_order_count.value),
        "parsed_msg_count_end": int(dut.parsed_msg_count.value),
        "real_sizing": data["sizing"],
        "settle_cycles": settle,
        "wall_seconds": round(time.time() - started, 1),
        "examples": examples,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2))
    dut._log.info(json.dumps({k: v for k, v in result.items() if k != "examples"}))
