"""Descriptive statistics of a real ITCH 5.0 capture (message mix, time span, busiest symbols).

Usage: python -m sim.validation.itch_stats data/cache/<file>.itch [--out reports/itch_stats.md]
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from sim.validation.itch_file import iter_raw_messages

ORDER_TYPES = set(b"AFECXDU")


def ns_to_hms(ns: int) -> str:
    s = ns / 1e9
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"


def main() -> None:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("itch")
    ap.add_argument("--out", default="reports/itch_stats.md")
    args = ap.parse_args()

    by_type: collections.Counter[str] = collections.Counter()
    adds_by_locate: collections.Counter[int] = collections.Counter()
    locate_to_symbol: dict[int, str] = {}
    per_second: collections.Counter[int] = collections.Counter()
    first_ts = last_ts = None
    total = 0
    for m in iter_raw_messages(args.itch):
        total += 1
        t = m[0]
        by_type[chr(t)] += 1
        ts = int.from_bytes(m[5:11], "big")
        first_ts = ts if first_ts is None else first_ts
        last_ts = ts
        if t in ORDER_TYPES:
            per_second[ts // 1_000_000_000] += 1
        if t == ord("R"):
            locate_to_symbol[int.from_bytes(m[1:3], "big")] = m[11:19].decode("ascii").strip()
        elif t in (ord("A"), ord("F")):
            adds_by_locate[int.from_bytes(m[1:3], "big")] += 1

    peak_sec, peak = per_second.most_common(1)[0] if per_second else (0, 0)
    meta_path = Path(args.itch + ".json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    lines = [
        "# ITCH capture statistics",
        "",
        f"- Source: `{meta.get('source_url', args.itch)}` ({meta.get('mode', 'local')})",
        f"- SHA-256 of extract: `{meta.get('sha256', 'n/a')}`",
        f"- Messages: **{total:,}**",
        f"- Time span: {ns_to_hms(first_ts or 0)} → {ns_to_hms(last_ts or 0)} (Eastern, ns since midnight)",
        f"- Peak order-message rate: **{peak:,} msg/s** at {ns_to_hms(peak_sec * 1_000_000_000)}",
        f"- Symbols in directory: {len(locate_to_symbol):,}",
        "",
        "## Message mix",
        "",
        "| Type | Count | Share |",
        "| :-- | --: | --: |",
    ]
    lines += [f"| `{k}` | {v:,} | {100 * v / total:.2f} % |" for k, v in by_type.most_common()]
    lines += ["", "## Busiest symbols (add orders)", "", "| Symbol | Locate | Adds |", "| :-- | --: | --: |"]
    lines += [f"| {locate_to_symbol.get(loc, '?')} | {loc} | {n:,} |" for loc, n in adds_by_locate.most_common(15)]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
