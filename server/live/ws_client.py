"""Minimal RFC 6455 WebSocket client on asyncio + ssl (stdlib only).

Enough for public market-data streams: text/binary messages, fragmentation,
ping/pong, close. No extensions (no permessage-deflate), no proxy support.
Written to avoid adding a runtime dependency (step P6); swap for a maintained
library if the project ever accepts one.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import ssl
import struct
from typing import AsyncIterator
from urllib.parse import urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
MAX_MESSAGE = 8 << 20


class WebSocketError(Exception):
    pass


def encode_frame(opcode: int, payload: bytes, mask_key: bytes | None = None) -> bytes:
    """Client frame (always masked, per RFC 6455 section 5.3)."""
    key = mask_key if mask_key is not None else os.urandom(4)
    head = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head.append(0x80 | n)
    elif n < 1 << 16:
        head.append(0x80 | 126)
        head += struct.pack(">H", n)
    else:
        head.append(0x80 | 127)
        head += struct.pack(">Q", n)
    masked = bytes(b ^ key[i & 3] for i, b in enumerate(payload))
    return bytes(head) + key + masked


async def read_frame(reader: asyncio.StreamReader) -> tuple[bool, int, bytes]:
    b0, b1 = await reader.readexactly(2)
    fin, opcode = bool(b0 & 0x80), b0 & 0x0F
    n = b1 & 0x7F
    if n == 126:
        (n,) = struct.unpack(">H", await reader.readexactly(2))
    elif n == 127:
        (n,) = struct.unpack(">Q", await reader.readexactly(8))
    if n > MAX_MESSAGE:
        raise WebSocketError(f"frame too large: {n}")
    key = await reader.readexactly(4) if b1 & 0x80 else None
    data = await reader.readexactly(n)
    if key:
        data = bytes(b ^ key[i & 3] for i, b in enumerate(data))
    return fin, opcode, data


class WebSocketClient:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._reader = reader
        self._writer = writer

    @classmethod
    async def connect(cls, url: str, timeout: float = 10.0) -> "WebSocketClient":
        parts = urlsplit(url)
        if parts.scheme not in ("ws", "wss") or not parts.hostname:
            raise WebSocketError(f"bad url: {url}")
        secure = parts.scheme == "wss"
        port = parts.port or (443 if secure else 80)
        ctx = ssl.create_default_context() if secure else None
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(parts.hostname, port, ssl=ctx,
                                    server_hostname=parts.hostname if secure else None),
            timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        host = parts.hostname if parts.port is None else f"{parts.hostname}:{parts.port}"
        request = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                   "User-Agent: aura-hft-paper/1.0\r\n\r\n")
        writer.write(request.encode())
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in f"{lines[0]} ":
            writer.close()
            raise WebSocketError(f"handshake refused: {lines[0]}")
        headers = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in lines[1:] if ln)}
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if headers.get("sec-websocket-accept") != expected:
            writer.close()
            raise WebSocketError("bad Sec-WebSocket-Accept")
        return cls(reader, writer)

    async def send_text(self, text: str) -> None:
        self._writer.write(encode_frame(OP_TEXT, text.encode()))
        await self._writer.drain()

    async def messages(self) -> AsyncIterator[str]:
        """Yield complete text messages until the server closes."""
        parts: list[bytes] = []
        while True:
            fin, op, data = await read_frame(self._reader)
            if op == OP_PING:
                self._writer.write(encode_frame(OP_PONG, data))
                await self._writer.drain()
                continue
            if op == OP_PONG:
                continue
            if op == OP_CLOSE:
                self._writer.write(encode_frame(OP_CLOSE, data[:2]))
                return
            if op in (OP_TEXT, OP_BIN, OP_CONT):
                parts.append(data)
                if fin:
                    yield b"".join(parts).decode("utf-8", errors="replace")
                    parts = []

    async def close(self) -> None:
        try:
            self._writer.write(encode_frame(OP_CLOSE, struct.pack(">H", 1000)))
            await self._writer.drain()
        except (ConnectionError, RuntimeError):
            pass
        self._writer.close()
