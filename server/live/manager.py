"""Live crypto feed manager: one upstream connection shared by all dashboard clients.

The upstream task starts with the first subscriber and stops with the last one,
so the backend never opens a network connection unless the dashboard asks for
it. Offline or refused connections are retried with exponential backoff and
reported as `offline` status messages; nothing crashes. Paper only.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable

from ..logging_config import get_logger
from .feeds import Feed, LiveBook, make_feed, obi_signal, size_units, to_q31
from .ws_client import WebSocketClient

log = get_logger("live")

Source = Callable[[Feed], AsyncIterator[str]]
QUEUE_SIZE = 64
LATENCY_WINDOW = 10_000
STATUS_INTERVAL_S = 1.0


async def websocket_source(feed: Feed) -> AsyncIterator[str]:
    ws = await WebSocketClient.connect(feed.url)
    try:
        sub = feed.subscribe_message()
        if sub:
            await ws.send_text(sub)
        async for msg in ws.messages():
            yield msg
    finally:
        await ws.close()


def _pct(sorted_vals: list[int], q: float) -> int | None:
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(q * (len(sorted_vals) - 1) + 0.5))]


class LiveFeedManager:
    def __init__(self, feed: Feed | None, source: Source = websocket_source,
                 buy_threshold: float = 0.4, sell_threshold: float = -0.4,
                 backoff_initial: float = 1.0, backoff_max: float = 30.0, min_interval_s: float = 0.1):
        self.feed = feed
        self.source = source
        self.buy_q31 = to_q31(buy_threshold)
        self.sell_q31 = to_q31(sell_threshold)
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.min_interval_s = min_interval_s
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._task: asyncio.Task[None] | None = None
        self._latency: deque[int] = deque(maxlen=LATENCY_WINDOW)
        self.state = "disabled" if feed is None else "idle"
        self.last_error: str | None = None
        self.updates = 0
        self.reconnects = 0
        self.last_update: str | None = None
        self.signals = {"buy": 0, "sell": 0}

    # ------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        lat = sorted(self._latency)
        return {
            "state": self.state,
            "feed": self.feed.name if self.feed else None,
            "url": self.feed.url if self.feed else None,
            "instrument": self.feed.instrument if self.feed else None,
            "mode": "paper (read-only market data, no order is ever sent)",
            "subscribers": len(self._subscribers),
            "updates": self.updates,
            "reconnects": self.reconnects,
            "last_update": self.last_update,
            "last_error": self.last_error,
            "signals": dict(self.signals),
            "thresholds_q31": {"buy": self.buy_q31, "sell": self.sell_q31},
            "software_latency_ns": {
                "kind": "measured (Python, normalize + book + OBI, time.perf_counter_ns)",
                "samples": len(lat), "p50": _pct(lat, 0.5), "p99": _pct(lat, 0.99), "p999": _pct(lat, 0.999),
            },
        }

    # ------------------------------------------------------------ subscribers
    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(q)
        q.put_nowait({"type": "live_status", "data": self.status()})
        if self.feed is not None and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._run())
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)
        if not self._subscribers and self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            self.state = "idle"

    def _broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            if q.full():  # slow client: drop its oldest event, never block the feed
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)

    def _set_state(self, state: str, error: str | None = None) -> None:
        self.state = state
        self.last_error = error
        self._broadcast({"type": "live_status", "data": self.status()})

    # ------------------------------------------------------------ upstream loop
    async def _run(self) -> None:
        assert self.feed is not None
        delay = self.backoff_initial
        while True:
            self._set_state("connecting", self.last_error)
            try:
                await self._consume(self.feed)
                error = "upstream closed the connection"
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # network down, DNS, TLS, refused, bad payload
                error = f"{type(exc).__name__}: {exc}"
            self.reconnects += 1
            log.warning("live feed offline", extra={"feed": self.feed.name, "error": error, "retry_s": delay})
            self._set_state("offline", error)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.backoff_max)

    async def _consume(self, feed: Feed) -> None:
        book = LiveBook()
        last_sent = 0.0
        last_status = time.monotonic()
        async for raw in self.source(feed):
            t0 = time.perf_counter_ns()
            if not feed.apply(raw, book):
                continue
            bids, asks = book.top()
            vb = size_units(bids[0][1]) if bids else 0
            va = size_units(asks[0][1]) if asks else 0
            valid, buy, sell = obi_signal(vb, va, self.buy_q31, self.sell_q31)
            self._latency.append(time.perf_counter_ns() - t0)
            if self.state != "live":
                self._set_state("live")
                log.info("live feed connected", extra={"feed": feed.name})
            self.updates += 1
            self.signals["buy"] += int(buy)
            self.signals["sell"] += int(sell)
            now = time.monotonic()
            if now - last_sent < self.min_interval_s and not (buy or sell):
                continue
            last_sent = now
            self.last_update = datetime.now(timezone.utc).isoformat()
            self._broadcast({"type": "live_tick", "data": {
                "source": feed.name,
                "instrument": feed.instrument,
                "ts": self.last_update,
                "bids": [[float(p), float(s)] for p, s in bids],
                "asks": [[float(p), float(s)] for p, s in asks],
                "obi": round((vb - va) / (vb + va), 6) if valid else None,
                "signal": {"valid": valid, "buy": buy, "sell": sell},
                "sw_latency_ns": self._latency[-1],
                "updates": self.updates,
            }})
            if now - last_status >= STATUS_INTERVAL_S:  # counters + latency percentiles
                last_status = now
                self._broadcast({"type": "live_status", "data": self.status()})


_manager: LiveFeedManager | None = None


def get_manager() -> LiveFeedManager:
    """Process-wide manager; AURA_LIVE_FEED=coinbase[:BTC-USD] | binance[:btcusdt] | off."""
    global _manager
    if _manager is None:
        spec = os.environ.get("AURA_LIVE_FEED", "coinbase:BTC-USD")
        _manager = LiveFeedManager(None if spec.lower() == "off" else make_feed(spec))
    return _manager


def set_manager(manager: LiveFeedManager | None) -> None:
    """Test hook."""
    global _manager
    _manager = manager
