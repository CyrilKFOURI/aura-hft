"""Cross-validate the golden order book against MeatPy on real NASDAQ ITCH 5.0 data.

MeatPy (https://github.com/vgreg/MeatPy) is an independent, peer-reviewed-use
academic library that rebuilds limit order books from ITCH. For each tracked
symbol we feed both books the same message stream and compare:
  * the best bid / best ask (price and size) after every message touching the symbol;
  * the full 5-level depth on both sides every `--depth-every` messages.

Usage:
    python -m sim.validation.compare_meatpy data/cache/<file>.itch \
        --symbols AAPL MSFT QQQ NVDA TSLA --out reports/golden_vs_meatpy.md
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from meatpy.itch50 import ITCH50MarketProcessor, ITCH50MessageReader
from meatpy.lob import ExecutionPriorityExceptionList

from sim.golden_model.golden_order_book import GoldenOrderBook
from sim.golden_model.itch_decoder import ItchDecoder
from sim.validation.itch_file import iter_raw_messages

ADD_TYPES = ("A", "F")
REF_TYPES = ("E", "C", "X", "D")
MAX_EXAMPLES = 10


@dataclass
class SymbolReport:
    symbol: str
    bbo_checks: int = 0
    bbo_mismatches: int = 0
    depth_checks: int = 0
    depth_mismatches: int = 0
    priority_exceptions: int = 0
    examples: list[str] = field(default_factory=list)
    final_bbo: str = ""


def golden_levels(book: GoldenOrderBook, side: str, depth: int) -> list[tuple[int, int]]:
    levels = book.top_bids(depth) if side == "B" else book.top_asks(depth)
    return [(round(p * 10000), v) for p, v in levels]


def meatpy_levels(proc: ITCH50MarketProcessor, side: str, depth: int) -> list[tuple[int, int]]:
    lob = proc.current_lob
    if lob is None:
        return []
    levels = lob.bid_levels if side == "B" else lob.ask_levels
    return [(int(lv.price), int(lv.volume)) for lv in levels[:depth]]


def touches(book: GoldenOrderBook, symbol: str, msg) -> bool:
    if msg.msg_type in ADD_TYPES:
        return (msg.stock or "").strip() == symbol
    if msg.msg_type in REF_TYPES:
        return msg.order_ref in book.orders
    if msg.msg_type == "U":
        return msg.original_order_ref in book.orders
    return False


def run(path: str, symbols: list[str], depth_every: int, limit: int | None, book_date: datetime.datetime):
    books = {s: GoldenOrderBook(target_symbol=s) for s in symbols}
    procs = {s: ITCH50MarketProcessor(s, book_date) for s in symbols}
    reports = {s: SymbolReport(s) for s in symbols}
    decode = ItchDecoder.decode_message
    started = time.time()
    n = 0
    with ITCH50MessageReader(path) as reader:
        for raw, mp_msg in zip(iter_raw_messages(path, limit), reader):
            n += 1
            msg = decode(raw)
            for s in symbols:
                try:
                    procs[s].process_message(mp_msg)
                except ExecutionPriorityExceptionList:
                    # MeatPy applies the execution, then flags it as out of time
                    # priority (normal during auction crosses). Book state is valid.
                    reports[s].priority_exceptions += 1
                if msg is None:
                    continue
                book = books[s]
                hit = touches(book, s, msg)
                if msg.msg_type in ADD_TYPES and not hit:
                    continue
                book.process_message(msg)
                if not hit:
                    continue
                rep = reports[s]
                rep.bbo_checks += 1
                g = (golden_levels(book, "B", 1), golden_levels(book, "S", 1))
                m = (meatpy_levels(procs[s], "B", 1), meatpy_levels(procs[s], "S", 1))
                if g != m:
                    rep.bbo_mismatches += 1
                    if len(rep.examples) < MAX_EXAMPLES:
                        rep.examples.append(f"msg #{n} `{msg.msg_type}` t={msg.timestamp_ns}: golden={g} meatpy={m}")
            if n % depth_every == 0:
                for s in symbols:
                    rep = reports[s]
                    rep.depth_checks += 1
                    for side in ("B", "S"):
                        if golden_levels(books[s], side, 5) != meatpy_levels(procs[s], side, 5):
                            rep.depth_mismatches += 1
                            if len(rep.examples) < MAX_EXAMPLES:
                                rep.examples.append(f"depth@{n} side {side}: golden={golden_levels(books[s], side, 5)} "
                                                    f"meatpy={meatpy_levels(procs[s], side, 5)}")
                            break
            if n % 1_000_000 == 0:
                print(f"  {n:>12,} messages, {n / (time.time() - started):,.0f} msg/s", flush=True)
    for s in symbols:
        reports[s].final_bbo = f"bid {golden_levels(books[s], 'B', 1)} / ask {golden_levels(books[s], 'S', 1)}"
    return n, time.time() - started, reports


def write_report(out: Path, path: str, n: int, elapsed: float, reports: dict[str, SymbolReport], depth_every: int):
    meta_path = Path(path + ".json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    total_mismatch = sum(r.bbo_mismatches + r.depth_mismatches for r in reports.values())
    lines = [
        "# Golden model vs MeatPy — real NASDAQ ITCH 5.0",
        "",
        f"- Data: `{meta.get('source_url', path)}` ({meta.get('mode', 'local')}), "
        f"SHA-256 `{meta.get('sha256', 'n/a')}`",
        f"- Messages replayed: **{n:,}** in {elapsed / 60:.1f} min",
        "- Reference: MeatPy 0.5.0 `ITCH50MarketProcessor` (independent implementation)",
        f"- Checks: BBO after every message touching the symbol; full 5-level depth every {depth_every:,} messages",
        f"- **Result: {'0 divergence' if total_mismatch == 0 else f'{total_mismatch:,} divergences'}**",
        "",
        "| Symbol | BBO checks | BBO mismatches | Depth checks | Depth mismatches | Out-of-priority executions* | Final BBO (raw price ×10⁴, shares) |",
        "| :-- | --: | --: | --: | --: | --: | :-- |",
    ]
    for r in reports.values():
        lines.append(f"| {r.symbol} | {r.bbo_checks:,} | {r.bbo_mismatches:,} | {r.depth_checks:,} | "
                     f"{r.depth_mismatches:,} | {r.priority_exceptions:,} | {r.final_bbo} |")
    lines += ["", r"\* Executions MeatPy flags as not first in time priority (e.g. 09:30 opening cross). "
              "MeatPy still applies them; they are reported for transparency, not counted as divergences."]
    for r in reports.values():
        if r.examples:
            lines += ["", f"### First divergences — {r.symbol}", ""] + [f"- {e}" for e in r.examples]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return total_mismatch


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("itch")
    ap.add_argument("--symbols", nargs="+", default=["AAPL", "MSFT", "QQQ", "NVDA", "TSLA"])
    ap.add_argument("--depth-every", type=int, default=100_000)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default="2019-01-30")
    ap.add_argument("--out", default="reports/golden_vs_meatpy.md")
    args = ap.parse_args()
    book_date = datetime.datetime.strptime(args.date, "%Y-%m-%d")
    n, elapsed, reports = run(args.itch, args.symbols, args.depth_every, args.limit, book_date)
    mismatches = write_report(Path(args.out), args.itch, n, elapsed, reports, args.depth_every)
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
