"""Public crypto L2 feeds normalized to the internal book format, plus the OBI signal.

Internal format: price levels as exact `Decimal` -> size, top 5 per side,
sizes converted to integer base units (1e-8, satoshi-like) before the
division-free OBI rule of rtl/quant/obi_signal.sv is applied. Paper only:
these feeds are read-only market data, no order is ever sent.
"""

from __future__ import annotations

import bisect
import json
from decimal import Decimal, InvalidOperation
from typing import Any

Q31 = 1 << 31
SIZE_SCALE = Decimal(100_000_000)
DEPTH = 5


def to_q31(threshold: float) -> int:
    return max(-Q31, min(Q31 - 1, int(round(threshold * Q31))))


def obi_signal(vb: int, va: int, buy_q31: int, sell_q31: int) -> tuple[bool, bool, bool]:
    """(valid, buy, sell): OBI >= T  <=>  (Vb - Va) * 2^31 >= T * (Vb + Va)."""
    total = vb + va
    if total <= 0:
        return False, False, False
    lhs = (vb - va) << 31
    return True, lhs >= buy_q31 * total, lhs <= sell_q31 * total


def size_units(size: Decimal) -> int:
    return int(size * SIZE_SCALE)


class LiveBook:
    """Full-depth L2 book; prices kept sorted (bisect) so the top 5 is O(1) to read."""

    def __init__(self) -> None:
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self._bid_px: list[Decimal] = []  # ascending
        self._ask_px: list[Decimal] = []  # ascending

    def set_level(self, side: str, price: Decimal, size: Decimal) -> None:
        book, keys = (self.bids, self._bid_px) if side == "bid" else (self.asks, self._ask_px)
        if size == 0:
            if book.pop(price, None) is not None:
                del keys[bisect.bisect_left(keys, price)]
        else:
            if price not in book:
                bisect.insort(keys, price)
            book[price] = size

    def replace(self, bids: list[tuple[Decimal, Decimal]], asks: list[tuple[Decimal, Decimal]]) -> None:
        self.bids = {p: s for p, s in bids if s > 0}
        self.asks = {p: s for p, s in asks if s > 0}
        self._bid_px = sorted(self.bids)
        self._ask_px = sorted(self.asks)

    def top(self, depth: int = DEPTH) -> tuple[list[tuple[Decimal, Decimal]], list[tuple[Decimal, Decimal]]]:
        bids = [(p, self.bids[p]) for p in reversed(self._bid_px[-depth:])]
        asks = [(p, self.asks[p]) for p in self._ask_px[:depth]]
        return bids, asks


def _levels(raw: Any) -> list[tuple[Decimal, Decimal]]:
    out = []
    for row in raw or []:
        try:
            out.append((Decimal(str(row[0])), Decimal(str(row[1]))))
        except (InvalidOperation, IndexError, TypeError):
            continue
    return out


class Feed:
    """A public, unauthenticated L2 stream."""

    name = "feed"
    url = ""
    instrument = ""

    def subscribe_message(self) -> str | None:
        return None

    def apply(self, raw: str, book: LiveBook) -> bool:
        """Update `book` from one message; True if the book changed."""
        raise NotImplementedError


class BinanceDepth(Feed):
    """Binance spot partial book depth (top 20, 100 ms snapshots)."""

    def __init__(self, symbol: str = "btcusdt"):
        self.symbol = symbol.lower()
        self.name = f"Binance spot {self.symbol.upper()} depth20@100ms"
        self.instrument = self.symbol.upper()
        self.url = f"wss://stream.binance.com:9443/ws/{self.symbol}@depth20@100ms"

    def apply(self, raw: str, book: LiveBook) -> bool:
        msg = json.loads(raw)
        if "bids" not in msg or "asks" not in msg:
            return False
        book.replace(_levels(msg["bids"]), _levels(msg["asks"]))
        return True


class CoinbaseLevel2Batch(Feed):
    """Coinbase Exchange level2_batch (snapshot then batched l2update)."""

    url = "wss://ws-feed.exchange.coinbase.com"

    def __init__(self, product: str = "BTC-USD"):
        self.product = product.upper()
        self.instrument = self.product
        self.name = f"Coinbase Exchange {self.product} level2_batch"

    def subscribe_message(self) -> str:
        return json.dumps({"type": "subscribe", "product_ids": [self.product], "channels": ["level2_batch"]})

    def apply(self, raw: str, book: LiveBook) -> bool:
        msg = json.loads(raw)
        kind = msg.get("type")
        if kind == "snapshot":
            book.replace(_levels(msg.get("bids")), _levels(msg.get("asks")))
            return True
        if kind == "l2update":
            changed = False
            for side, price, size in msg.get("changes", []):
                book.set_level("bid" if side == "buy" else "ask", Decimal(price), Decimal(size))
                changed = True
            return changed
        if kind == "error":
            raise ConnectionError(f"coinbase error: {msg.get('message')} {msg.get('reason', '')}".strip())
        return False


def make_feed(spec: str) -> Feed:
    """`binance[:btcusdt]` or `coinbase[:BTC-USD]`."""
    venue, _, inst = spec.partition(":")
    venue = venue.strip().lower()
    if venue == "binance":
        return BinanceDepth(inst or "btcusdt")
    if venue == "coinbase":
        return CoinbaseLevel2Batch(inst or "BTC-USD")
    raise ValueError(f"unknown live feed: {spec!r}")
