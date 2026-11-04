"""Rebuild per-symbol books with the validated golden model and dump event arrays.

One pass over the raw ITCH file. Messages are pre-filtered on their 2-byte
stock_locate (every order message carries it), mapped from the 'R' stock
directory, then fed to `GoldenOrderBook` (0 divergence vs MeatPy, step P2).

Output: data/cache/<itch>.obi_events.<SYMBOL>.npz with one row per
book-changing event (a replace 'U' gives a cancel row + an add row):
    ts, kind (0 add / 1 exec / 2 cancel-delete), side (+1 bid / -1 ask),
    px (resting price of the order, raw 1/10000 $), qty, add_ts (time the
    touched order entered the book = its queue priority),
    bb, bbq, ba, baq (best bid/ask price and size *after* the event, 0 = empty).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from sim.golden_model.golden_order_book import GoldenOrderBook
from sim.golden_model.itch_decoder import ItchDecoder
from sim.validation.itch_file import iter_raw_messages

from .model import ADD, ASK, BID, CANCEL, EXEC, PRICE_SCALE

FIELDS = ("ts", "kind", "side", "px", "qty", "add_ts", "bb", "bbq", "ba", "baq")
ORDER_TYPES = frozenset(b"AFECXDU")


def out_path(itch: Path, symbol: str) -> Path:
    return itch.with_name(f"{itch.name}.obi_events.{symbol}.npz")


def _raw(p: float) -> int:
    return int(round(p * PRICE_SCALE))


def extract(itch: Path, symbols: list[str], limit: int | None = None) -> dict[str, Path]:
    books = {s: GoldenOrderBook(target_symbol=s) for s in symbols}
    rows: dict[str, list[tuple]] = {s: [] for s in symbols}
    locate: dict[int, str] = {}
    decode = ItchDecoder.decode_message
    started = time.time()
    n = 0
    for raw in iter_raw_messages(itch, limit):
        n += 1
        t = raw[0]
        if t == 0x52:  # 'R' stock directory
            stock = raw[11:19].decode("ascii").strip()
            if stock in books:
                locate[int.from_bytes(raw[1:3], "big")] = stock
            continue
        if t not in ORDER_TYPES:
            continue
        sym = locate.get(int.from_bytes(raw[1:3], "big"))
        if sym is None:
            continue
        msg = decode(raw)
        if msg is None:
            continue
        book = books[sym]
        out = rows[sym]
        pre: list[tuple] = []
        if msg.msg_type in ("E", "C", "X", "D"):
            o = book.orders.get(msg.order_ref)
            if o is None:
                continue
            q = o.shares if msg.msg_type == "D" else min(o.shares, msg.shares)
            kind = EXEC if msg.msg_type in ("E", "C") else CANCEL
            pre.append((kind, BID if o.side == "B" else ASK, _raw(o.price), q, o.timestamp_ns))
        elif msg.msg_type == "U":
            o = book.orders.get(msg.original_order_ref)
            if o is None:
                continue
            side = BID if o.side == "B" else ASK
            pre.append((CANCEL, side, _raw(o.price), o.shares, o.timestamp_ns))
            pre.append((ADD, side, msg.raw_price, msg.shares, msg.timestamp_ns))
        else:  # A / F
            pre.append((ADD, BID if msg.side == "B" else ASK, msg.raw_price, msg.shares, msg.timestamp_ns))
        res = book.process_message(msg)
        bb, ba = res["best_bid"], res["best_ask"]
        top = (_raw(bb[0]) if bb else 0, bb[1] if bb else 0, _raw(ba[0]) if ba else 0, ba[1] if ba else 0)
        for kind, side, px, q, age in pre:
            out.append((msg.timestamp_ns, kind, side, px, q, age) + top)
        if n % 5_000_000 == 0:
            print(f"  {n:>12,} messages, {time.time() - started:,.0f} s", flush=True)
    paths = {}
    for s in symbols:
        arr = np.array(rows[s], dtype=np.int64).reshape(-1, len(FIELDS))
        p = out_path(itch, s)
        np.savez_compressed(p, **{f: arr[:, i] for i, f in enumerate(FIELDS)}, messages_read=n)
        paths[s] = p
        print(f"  {s}: {len(arr):,} events -> {p.name}")
    return paths


def load(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {f: z[f] for f in FIELDS}
