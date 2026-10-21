"""Bit-exact check of the C++ reference path against the Python golden model.

Runs `aura_ref trace` and an independent Python pipeline (sim/golden_model book
+ research/obi_backtest rule and risk model) on the same raw ITCH file, then
compares every applied book event: timestamp, type, top 5 per side, OBI signal
bits, risk decision, reject reason and cumulative notional.

    PYTHONPATH=. python software/ref_pipeline/validate.py data/cache/<file>.itch \
        --symbols AAPL MSFT TSLA --limit 2000000
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

from research.obi_backtest.model import ASK, BID, RiskConfig, risk_check
from sim.golden_model.golden_order_book import GoldenOrderBook
from sim.golden_model.itch_decoder import ItchDecoder
from sim.validation.itch_file import iter_raw_messages

REASON = {"PASS": 0, "KILL_SWITCH": 1, "MAX_SHARES": 2, "PRICE_COLLAR": 3, "MAX_NOTIONAL": 4,
          "CUMULATIVE_NOTIONAL": 5}
U64_MAX = (1 << 64) - 1
BOOK_TYPES = frozenset(b"AFECXDU")
BIN = Path(__file__).resolve().parent / "bin" / "aura_ref"


def _raw(p: float) -> int:
    return int(round(p * 10_000))


def obi_bits(vb: int, va: int, buy_q31: int, sell_q31: int) -> tuple[int, int, int]:
    """obi_signal.sv with Python integers (no width limit)."""
    total = vb + va
    if total == 0:
        return 0, 0, 0
    lhs = (vb - va) << 31
    return 1, int(lhs >= buy_q31 * total), int(lhs <= sell_q31 * total)


def golden_trace(itch: Path, symbol: str, limit: int, buy_q31: int, sell_q31: int, shares: int,
                 risk: RiskConfig) -> list[str]:
    book = GoldenOrderBook(target_symbol=symbol)
    locate: int | None = None
    cum = 0
    lines: list[str] = []
    for raw in iter_raw_messages(itch, limit):
        t = raw[0]
        if t == 0x52 and len(raw) >= 39:
            if raw[11:19].decode("ascii").strip() == symbol:
                locate = int.from_bytes(raw[1:3], "big")
            continue
        if t not in BOOK_TYPES or locate is None or int.from_bytes(raw[1:3], "big") != locate:
            continue
        msg = ItchDecoder.decode_message(raw)
        if msg is None:
            continue
        if msg.msg_type in ("E", "C", "X", "D") and msg.order_ref not in book.orders:
            continue
        if msg.msg_type == "U" and msg.original_order_ref not in book.orders:
            continue
        book.process_message(msg)
        bids = [(_raw(p), q) for p, q in book.top_bids(5)] + [(0, 0)] * 5
        asks = [(_raw(p), q) for p, q in book.top_asks(5)] + [(0, 0)] * 5
        bb, ba = bids[0], asks[0]
        valid, buy, sell = obi_bits(bb[1], ba[1], buy_q31, sell_q31)
        decision, reason = 0, 0
        if buy or sell:
            side = BID if buy else ASK
            px = bb[0] if buy else ba[0]
            ok, why = risk_check(risk, side, shares, px, bb[0], ba[0], cum)
            reason = REASON[why]
            decision = 1 if ok else 2
            if ok:
                cum = min(cum + shares * px, U64_MAX)  # saturating accumulator
        levels = ",".join(f"{p},{q}" for p, q in bids[:5] + asks[:5])
        lines.append(f"{msg.timestamp_ns},{msg.msg_type},{levels},{valid},{buy},{sell},{decision},{reason},{cum}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("itch", type=Path)
    ap.add_argument("--symbols", nargs="+", default=["AAPL"])
    ap.add_argument("--limit", type=int, default=2_000_000)
    ap.add_argument("--buy-q31", type=int, default=858_993_459)     # +0.40
    ap.add_argument("--sell-q31", type=int, default=-858_993_459)   # -0.40
    ap.add_argument("--shares", type=int, default=100)
    ap.add_argument("--max-cum", type=int, default=20_000_000_000)  # $2M: trips on real data
    args = ap.parse_args()
    if not BIN.exists():
        print(f"build first: make -C {BIN.parent.parent}", file=sys.stderr)
        return 2

    risk = RiskConfig(max_cum_notional_raw=args.max_cum)
    failed = 0
    for sym in args.symbols:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "trace.csv"
            cmd = [str(BIN), "trace", str(args.itch), "--symbol", sym, "--limit", str(args.limit),
                   "--out", str(out), "--buy-q31", str(args.buy_q31), "--sell-q31", str(args.sell_q31),
                   "--shares", str(args.shares), "--max-shares", str(risk.max_order_shares),
                   "--collar", str(risk.price_collar), "--max-notional", str(risk.max_notional_raw),
                   "--max-cum", str(args.max_cum)]
            summary = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
            cpp = out.read_text().splitlines()
        py = golden_trace(args.itch, sym, args.limit, args.buy_q31, args.sell_q31, args.shares, risk)
        first = next((i for i, (a, b) in enumerate(zip(cpp, py)) if a != b), None)
        if first is None and len(cpp) != len(py):
            first = min(len(cpp), len(py))
        digest = hashlib.sha256("\n".join(cpp).encode()).hexdigest()[:16]
        orders = sum(1 for line in py if line.split(",")[-3] != "0")
        rejects = {r: sum(1 for line in py if line.split(",")[-2] == str(v)) for r, v in REASON.items() if v}
        status = "OK" if first is None else f"DIVERGENCE at event {first}"
        print(f"{sym}: {len(cpp)} C++ events / {len(py)} golden events, {orders} intents, "
              f"rejects {rejects}, sha256 {digest} -> {status}   [{summary}]")
        if first is not None:
            failed += 1
            print("  C++   :", cpp[first] if first < len(cpp) else "<end>")
            print("  golden:", py[first] if first < len(py) else "<end>")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
