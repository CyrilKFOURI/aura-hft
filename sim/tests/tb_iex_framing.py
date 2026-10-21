"""Real-world framing: real IEX Ethernet/IPv4/UDP headers around real NASDAQ ITCH payloads.

IEX HIST frames are IEX-TP, not ITCH, so their payload cannot drive the ITCH
parser. Each real IEX frame keeps its Ethernet header (real MACs, EtherType),
its IPv4 header (real TOS, ID, flags, TTL, addresses; total length and header
checksum recomputed) and its UDP ports; its UDP payload is replaced by one
MoldUDP64 packet holding as many consecutive real NASDAQ AAPL messages as fit
in the ORIGINAL payload size, so the real frame-size distribution (up to
1 500-byte frames, i.e. ~40 messages back-to-back) is preserved. After each
frame the RTL top-5 is compared with the golden expectation recorded in the
AAPL stream (sim.validation.extract_symbol_stream).

Environment:
    IEX_PCAP     classic pcap written by data/fetch_iex.py (required)
    REAL_STREAM  <capture>.AAPL.stream.json (required)
    IEX_FRAMES   max frames to replay (default: all)
    IEX_REPORT   JSON results path
"""

import json
import os
import struct
import time
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from sim.tests.tb_itch_parser import send_axis_frame
from sim.tests.tb_order_book import reset_dut
from sim.tests.tb_real_data_cosim import rtl_levels


def read_pcap(path: Path) -> list:
    data = path.read_bytes()
    endian = "<" if data[:4] in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
    frames, off = [], 24
    while off + 16 <= len(data):
        caplen = struct.unpack(endian + "I", data[off + 8:off + 12])[0]
        frames.append(data[off + 16:off + 16 + caplen])
        off += 16 + caplen
    return frames


def ip_checksum(hdr: bytes) -> int:
    total = sum(struct.unpack(">10H", hdr))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def rewrap(frame: bytes, mold: bytes) -> bytes:
    """Real Eth + IPv4 + UDP headers of `frame` around a new UDP payload."""
    eth, ip, udp = frame[:14], bytearray(frame[14:34]), bytearray(frame[34:42])
    ip[2:4] = struct.pack(">H", 20 + 8 + len(mold))
    ip[10:12] = b"\x00\x00"
    ip[10:12] = struct.pack(">H", ip_checksum(bytes(ip)))
    udp[4:6] = struct.pack(">H", 8 + len(mold))
    udp[6:8] = b"\x00\x00"                     # UDP checksum optional over IPv4
    return eth + bytes(ip) + bytes(udp) + mold


def framing_stats(frames: list) -> dict:
    sizes = [len(f) for f in frames]
    plain = [f for f in frames if f[12:14] == b"\x08\x00" and f[14] == 0x45 and f[23] == 17]
    return {
        "frames": len(frames), "plain_ipv4_udp": len(plain),
        "vlan_tagged": sum(f[12:14] == b"\x81\x00" for f in frames),
        "src_macs": sorted({f[6:12].hex(":") for f in frames}),
        "dst_macs": sorted({f[:6].hex(":") for f in frames}),
        "ip_pairs": sorted({".".join(map(str, f[26:30])) + " -> " + ".".join(map(str, f[30:34])) for f in plain}),
        "udp_ports": sorted({f"{struct.unpack('>H', f[34:36])[0]}->{struct.unpack('>H', f[36:38])[0]}" for f in plain}),
        "frame_bytes_min": min(sizes), "frame_bytes_max": max(sizes),
        "frame_bytes_mean": round(sum(sizes) / len(sizes), 1),
    }


@cocotb.test()
async def test_iex_framing_real_itch(dut):
    frames = read_pcap(Path(os.environ["IEX_PCAP"]))
    data = json.loads(Path(os.environ["REAL_STREAM"]).read_text())
    stream = [(bytes.fromhex(h), [tuple(x) for x in b], [tuple(x) for x in a]) for h, b, a in data["stream"]]
    limit = int(os.environ.get("IEX_FRAMES") or len(frames))
    report_path = Path(os.environ["IEX_REPORT"])
    stats = framing_stats(frames[:limit])

    cocotb.start_soon(Clock(dut.clk, 6.4, unit="ns").start())
    await reset_dut(dut)
    lob = dut.u_lob_engine

    pos, seq, sent, mism, examples, msgs_per_frame = 0, 1, 0, 0, [], []
    started = time.time()
    for frame in frames[:limit]:
        if not (frame[12:14] == b"\x08\x00" and frame[14] == 0x45 and frame[23] == 17) or pos >= len(stream):
            continue
        budget = len(frame) - 42 - 20            # original UDP payload minus the MoldUDP64 header
        blocks, n = b"", 0
        while pos + n < len(stream):
            raw = stream[pos + n][0]
            if n and len(blocks) + 2 + len(raw) > budget:
                break
            blocks += struct.pack(">H", len(raw)) + raw
            n += 1
        mold = b"NASDAQREAL" + struct.pack(">QH", seq, n) + blocks
        await send_axis_frame(dut, rewrap(frame, mold))
        for _ in range(8):
            await RisingEdge(dut.clk)
        while int(lob.fifo_wr.value) != int(lob.fifo_rd.value):
            await RisingEdge(dut.clk)
        for _ in range(24):
            await RisingEdge(dut.clk)
        pos += n
        seq += n
        sent += 1
        msgs_per_frame.append(n)
        _, exp_bids, exp_asks = stream[pos - 1]
        bids, asks = rtl_levels(dut, "B"), rtl_levels(dut, "S")
        if bids != exp_bids or asks != exp_asks:
            mism += 1
            if len(examples) < 10:
                examples.append({"frame": sent, "msgs": n, "rtl_bids": bids, "exp_bids": exp_bids,
                                 "rtl_asks": asks, "exp_asks": exp_asks})

    result = {
        "iex_capture": Path(os.environ["IEX_PCAP"]).name,
        "itch_stream": Path(os.environ["REAL_STREAM"]).name,
        "iex_framing": stats,
        "frames_replayed": sent,
        "itch_messages_replayed": pos,
        "msgs_per_frame_max": max(msgs_per_frame, default=0),
        "msgs_per_frame_mean": round(sum(msgs_per_frame) / max(1, len(msgs_per_frame)), 2),
        "top5_mismatches_after_frame": mism,
        "gap_count_end": int(dut.unused_gap_count.value),
        "dropped_dup_frames": int(dut.u_ingress.u_depacketizer.dropped_dup_frames.value),
        "dropped_bad_hdr_frames": int(dut.u_ingress.u_depacketizer.dropped_bad_hdr_frames.value),
        "parser_truncated": int(dut.u_ingress.gen_speculative_parser.u_itch_parser.truncated_msg_count.value),
        "fifo_overflow": int(lob.fifo_overflow_count.value),
        "parsed_msg_count_end": int(dut.parsed_msg_count.value),
        "wall_seconds": round(time.time() - started, 1),
        "examples": examples,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2))
    dut._log.info(json.dumps({k: v for k, v in result.items() if k != "examples"}))
    assert sent > 0, "no frame replayed"
    assert mism == 0, f"{mism} frames with a top-5 divergence, e.g. {examples[:2]}"
    assert result["fifo_overflow"] == 0 and result["dropped_bad_hdr_frames"] == 0
    assert result["parser_truncated"] == 0 and result["gap_count_end"] == 0
