"""Extract the real ITCH messages that touch one symbol, with golden-model expectations.

For RTL co-simulation we replay only the messages that can change the symbol's
book (its adds, and executions / cancels / deletes / replaces of its orders).
Messages for other symbols are no-ops for a single-symbol book, so dropping
them keeps simulation time reasonable without changing the expected state.

Also reports the real sizing the hardware must handle (live orders, price
levels per side), to compare with the RTL capacity.

Usage:
    python -m sim.validation.extract_symbol_stream data/cache/<file>.itch --symbol AAPL [--limit N]
Writes data/cache/<file>.<SYMBOL>.stream.json (derived from licensed data, never committed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sim.golden_model.golden_order_book import GoldenOrderBook
from sim.golden_model.itch_decoder import ItchDecoder
from sim.validation.compare_meatpy import touches
from sim.validation.itch_file import iter_raw_messages


def levels(book: GoldenOrderBook, side: str) -> list[tuple[int, int]]:
    lv = book.top_bids(5) if side == "B" else book.top_asks(5)
    return [(round(p * 10000), v) for p, v in lv]


def extract(path: str, symbol: str, limit: int | None):
    book = GoldenOrderBook(target_symbol=symbol)
    stream: list[tuple[bytes, list, list]] = []
    max_orders = max_bid_levels = max_ask_levels = 0
    for raw in iter_raw_messages(path, limit):
        msg = ItchDecoder.decode_message(raw)
        if msg is None or not touches(book, symbol, msg):
            continue
        book.process_message(msg)
        stream.append((raw, levels(book, "B"), levels(book, "S")))
        max_orders = max(max_orders, len(book.orders))
        max_bid_levels = max(max_bid_levels, len(book.bids))
        max_ask_levels = max(max_ask_levels, len(book.asks))
    sizing = {"symbol": symbol, "messages": len(stream), "max_live_orders": max_orders,
              "max_bid_levels": max_bid_levels, "max_ask_levels": max_ask_levels}
    return stream, sizing


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser()
    ap.add_argument("itch")
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    stream, sizing = extract(args.itch, args.symbol, args.limit)
    out = Path(f"{args.itch}.{args.symbol}.stream.json")
    payload = {"sizing": sizing, "stream": [[raw.hex(), bids, asks] for raw, bids, asks in stream]}
    out.write_text(json.dumps(payload))
    print(json.dumps(sizing, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
