"""Fetch real NASDAQ TotalView-ITCH 5.0 data from NASDAQ's public sample server.

The full sample days are ~5 GB compressed. By default this script *streams*
the gzip file and keeps only the first N messages, so you get real market
data in minutes without storing the whole day. Use --full to download the
entire file (checked against NASDAQ's published MD5).

Output (never committed, see .gitignore):
    data/cache/<DATE>.NASDAQ_ITCH50[.first<N>].itch   raw ITCH file (2-byte length-prefixed messages)
    data/cache/<DATE>...itch.json                     provenance: URL, message count, SHA-256

Usage:
    python data/fetch.py                       # 01302019, first 20M messages
    python data/fetch.py --messages 5000000
    python data/fetch.py --date 01302020 --full
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
import time
import urllib.request
import zlib
from pathlib import Path

BASE_URL = "https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
CHUNK = 1 << 20
USER_AGENT = "aura-hft-data-fetch/1.0"


def open_url(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=60)


def published_md5(date: str) -> str:
    with open_url(f"{BASE_URL}{date}.NASDAQ_ITCH50.gz.md5sum") as resp:
        return resp.read().decode("ascii").split()[0].lower()


def stream_first_messages(date: str, max_messages: int, out_path: Path) -> dict:
    """Stream-decompress the remote gzip and write the first `max_messages` ITCH messages."""
    url = f"{BASE_URL}{date}.NASDAQ_ITCH50.gz"
    inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    sha = hashlib.sha256()
    pending = b""
    count = 0
    compressed_read = 0
    started = time.time()
    with open_url(url) as resp, open(out_path, "wb") as out:
        while count < max_messages:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            compressed_read += len(chunk)
            pending += inflater.decompress(chunk)
            offset = 0
            while count < max_messages and offset + 2 <= len(pending):
                length = int.from_bytes(pending[offset:offset + 2], "big")
                end = offset + 2 + length
                if end > len(pending):
                    break
                record = pending[offset:end]
                out.write(record)
                sha.update(record)
                offset = end
                count += 1
            pending = pending[offset:]
            if count and count % 1_000_000 < 50_000:
                rate = count / max(1e-9, time.time() - started)
                print(f"  {count:>12,} messages  ({compressed_read / 1e6:,.0f} MB compressed, {rate:,.0f} msg/s)",
                      flush=True)
    return {
        "source_url": url,
        "mode": "stream-prefix",
        "messages": count,
        "compressed_bytes_read": compressed_read,
        "sha256": sha.hexdigest(),
    }


def download_full(date: str, gz_path: Path, out_path: Path) -> dict:
    url = f"{BASE_URL}{date}.NASDAQ_ITCH50.gz"
    md5 = hashlib.md5()
    with open_url(url) as resp, open(gz_path, "wb") as out:
        while chunk := resp.read(CHUNK):
            out.write(chunk)
            md5.update(chunk)
    expected = published_md5(date)
    if md5.hexdigest() != expected:
        gz_path.unlink()
        raise SystemExit(f"MD5 mismatch: got {md5.hexdigest()}, NASDAQ publishes {expected}")
    sha = hashlib.sha256()
    with gzip.open(gz_path, "rb") as src, open(out_path, "wb") as dst:
        while chunk := src.read(CHUNK):
            dst.write(chunk)
            sha.update(chunk)
    return {"source_url": url, "mode": "full", "md5_verified": expected, "sha256": sha.hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default="01302019", help="NASDAQ sample date MMDDYYYY (default: 01302019)")
    parser.add_argument("--messages", type=int, default=20_000_000, help="messages to keep in stream mode")
    parser.add_argument("--full", action="store_true", help="download and verify the whole day (~5 GB)")
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if args.full:
        out_path = CACHE_DIR / f"{args.date}.NASDAQ_ITCH50.itch"
        meta = download_full(args.date, CACHE_DIR / f"{args.date}.NASDAQ_ITCH50.gz", out_path)
    else:
        out_path = CACHE_DIR / f"{args.date}.NASDAQ_ITCH50.first{args.messages}.itch"
        meta = stream_first_messages(args.date, args.messages, out_path)

    meta.update({"date": args.date, "file": out_path.name, "bytes": out_path.stat().st_size,
                 "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    out_path.with_suffix(out_path.suffix + ".json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    shutil.disk_usage(CACHE_DIR.parent)  # fail early if the data dir is unreachable
    sys.exit(main())
