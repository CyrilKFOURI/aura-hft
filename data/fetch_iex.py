"""Fetch a prefix of a real IEX HIST capture (DEEP / TOPS pcap) for ingress framing tests.

IEX publishes each trading day as a gzip'd capture of ~1.2-1.3 GB. This script
*streams* it and keeps only the first N Ethernet frames, reading at most
--max-mb of compressed data, so nothing large is ever stored.

The frames are IEX-TP over UDP (not NASDAQ ITCH): the bench keeps their real
Ethernet / IPv4 / UDP layers and re-wraps real NASDAQ ITCH payloads inside.

Output (never committed, see .gitignore):
    data/cache/iex_<DATE>_<FEED>.first<N>.pcap   classic pcap (LINKTYPE_ETHERNET)
    data/cache/iex_<DATE>_<FEED>.first<N>.pcap.json   provenance: URL, frames, SHA-256

Usage:
    python data/fetch_iex.py                          # 20190130 DEEP, first 5000 frames
    python data/fetch_iex.py --date 20190130 --feed TOPS --packets 20000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
import urllib.request
import zlib
from pathlib import Path

HIST_API = "https://iextrading.com/api/1.0/hist?date={date}"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
CHUNK = 1 << 18
USER_AGENT = "aura-hft-data-fetch/1.0"


def open_url(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=60)


def hist_link(date: str, feed: str) -> dict:
    with open_url(HIST_API.format(date=date)) as resp:
        entries = json.loads(resp.read())
    for entry in entries:
        if entry["feed"] == feed:
            return entry
    raise SystemExit(f"no {feed} capture listed for {date}: {[e['feed'] for e in entries]}")


class CaptureReader:
    """Incremental pcap / pcapng parser yielding (ts_ns, linktype, frame bytes)."""

    def __init__(self):
        self.buf = b""
        self.fmt = None
        self.endian = "<"
        self.linktypes: list = []
        self.pcap_linktype = 1
        self.ts_div = 1000

    def feed(self, data: bytes):
        self.buf += data
        out = []
        while True:
            rec = self._next()
            if rec is None:
                break
            if rec is not ...:
                out.append(rec)
        return out

    def _next(self):
        b = self.buf
        if self.fmt is None:
            if len(b) < 24:
                return None
            magic = b[:4]
            if magic == b"\x0a\x0d\x0d\x0a":
                self.fmt = "pcapng"
            elif magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
                self.fmt, self.endian = "pcap", "<"
                self.ts_div = 1000 if magic == b"\xd4\xc3\xb2\xa1" else 1
                self.pcap_linktype = struct.unpack("<I", b[20:24])[0]
                self.buf = b[24:]
                return ...
            elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
                self.fmt, self.endian = "pcap", ">"
                self.ts_div = 1000 if magic == b"\xa1\xb2\xc3\xd4" else 1
                self.pcap_linktype = struct.unpack(">I", b[20:24])[0]
                self.buf = b[24:]
                return ...
            else:
                raise SystemExit(f"unknown capture magic {magic.hex()}")
        e = self.endian
        if self.fmt == "pcap":
            if len(b) < 16:
                return None
            sec, frac, caplen, _ = struct.unpack(e + "IIII", b[:16])
            if len(b) < 16 + caplen:
                return None
            self.buf = b[16 + caplen:]
            return (sec * 1_000_000_000 + frac * (1_000_000_000 // (1_000_000 if self.ts_div == 1000 else 1_000_000_000)),
                    self.pcap_linktype, b[16:16 + caplen])
        # pcapng
        if len(b) < 12:
            return None
        btype = struct.unpack(e + "I", b[:4])[0]
        if btype == 0x0A0D0D0A:
            bom = b[8:12]
            e = self.endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
        blen = struct.unpack(e + "I", b[4:8])[0]
        if len(b) < blen:
            return None
        body = b[8:blen - 4]
        self.buf = b[blen:]
        if btype == 0x00000001:                               # Interface Description Block
            self.linktypes.append(struct.unpack(e + "H", body[:2])[0])
            return ...
        if btype == 0x00000006:                               # Enhanced Packet Block
            ifid, ts_hi, ts_lo, caplen, _ = struct.unpack(e + "IIIII", body[:20])
            lt = self.linktypes[ifid] if ifid < len(self.linktypes) else 1
            return ((ts_hi << 32 | ts_lo) * 1000, lt, body[20:20 + caplen])   # default µs resolution
        return ...


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default="20190130", help="trading day YYYYMMDD (default: 20190130, same day as the NASDAQ sample)")
    ap.add_argument("--feed", default="DEEP", choices=["DEEP", "TOPS"])
    ap.add_argument("--packets", type=int, default=5000, help="Ethernet frames to keep")
    ap.add_argument("--max-mb", type=float, default=64.0, help="hard cap on compressed bytes read")
    args = ap.parse_args()

    entry = hist_link(args.date, args.feed)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CACHE_DIR / f"iex_{args.date}_{args.feed}.first{args.packets}.pcap"
    inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    reader = CaptureReader()
    sha = hashlib.sha256()
    kept = read = 0
    linktypes = set()
    with open_url(entry["link"]) as resp, open(out_path, "wb") as out:
        out.write(struct.pack("<IHHiIII", 0xA1B23C4D, 2, 4, 0, 0, 65535, 1))   # ns-resolution pcap, Ethernet
        while kept < args.packets and read < args.max_mb * 1e6:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            read += len(chunk)
            for ts_ns, lt, frame in reader.feed(inflater.decompress(chunk)):
                linktypes.add(lt)
                if lt != 1 or kept >= args.packets:
                    continue
                out.write(struct.pack("<IIII", ts_ns // 1_000_000_000, ts_ns % 1_000_000_000, len(frame), len(frame)))
                out.write(frame)
                sha.update(frame)
                kept += 1
    meta = {"source_url": entry["link"], "feed": args.feed, "protocol": entry.get("protocol"),
            "version": entry.get("version"), "published_size_bytes": int(entry["size"]), "date": args.date,
            "capture_format": reader.fmt, "linktypes_seen": sorted(linktypes), "frames": kept,
            "compressed_bytes_read": read, "sha256_frames": sha.hexdigest(), "file": out_path.name,
            "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    out_path.with_suffix(".pcap.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
