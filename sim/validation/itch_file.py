"""Iterate raw NASDAQ ITCH 5.0 files (2-byte big-endian length prefix per message)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

CHUNK = 1 << 22


def iter_raw_messages(path: Path | str, limit: int | None = None) -> Iterator[bytes]:
    """Yield each message payload (without its length prefix)."""
    count = 0
    buf = b""
    with open(path, "rb") as f:
        while True:
            data = f.read(CHUNK)
            if not data:
                break
            buf += data
            offset = 0
            n = len(buf)
            while offset + 2 <= n:
                length = (buf[offset] << 8) | buf[offset + 1]
                end = offset + 2 + length
                if end > n:
                    break
                yield buf[offset + 2:end]
                count += 1
                if limit is not None and count >= limit:
                    return
                offset = end
            buf = buf[offset:]
