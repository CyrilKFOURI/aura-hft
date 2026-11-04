"""Summarise a Verilator coverage.dat (line / branch / toggle) per RTL file.

Usage: python -m sim.validation.coverage_summary merged.dat --out reports/coverage_itch_lob.md
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

RECORD = re.compile(r"^C '(.*)' (\d+)$")


def parse(path: Path) -> list:
    points = []
    for line in path.read_text(errors="replace").splitlines():
        m = RECORD.match(line)
        if not m:
            continue
        fields = {}
        for item in m.group(1).split("\x01"):
            if "\x02" in item:
                k, v = item.split("\x02", 1)
                fields[k] = v
        page = fields.get("page", "")
        kind = page.split("/")[0].replace("v_", "")          # line, branch, toggle, expr, user
        points.append({"kind": kind, "file": Path(fields.get("f", "?")).name, "line": int(fields.get("l", 0)),
                       "name": fields.get("o", ""), "hier": fields.get("h", ""), "count": int(m.group(2))})
    return points


def pct(c: int, t: int) -> str:
    return f"{100 * c / t:.1f} %" if t else "—"


def summarise(points: list) -> tuple:
    per = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for p in points:
        cell = per[p["file"]][p["kind"]]
        cell[1] += 1
        cell[0] += p["count"] > 0
    totals = defaultdict(lambda: [0, 0])
    for kinds in per.values():
        for k, (c, t) in kinds.items():
            totals[k][0] += c
            totals[k][1] += t
    return per, totals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dat")
    ap.add_argument("--out")
    args = ap.parse_args()
    points = parse(Path(args.dat))
    per, totals = summarise(points)
    kinds = [k for k in ("line", "branch", "toggle") if k in totals] + sorted(set(totals) - {"line", "branch", "toggle"})
    out = ["| Fichier | " + " | ".join(kinds) + " |", "| :-- | " + " | ".join("--:" for _ in kinds) + " |"]
    for f in sorted(per):
        out.append(f"| `{f}` | " + " | ".join(
            f"{pct(*per[f][k])} ({per[f][k][0]}/{per[f][k][1]})" if k in per[f] else "—" for k in kinds) + " |")
    out.append("| **Total** | " + " | ".join(f"**{pct(*totals[k])}** ({totals[k][0]}/{totals[k][1]})" for k in kinds) + " |")
    missed = sorted({(p["file"], p["line"]) for p in points if p["kind"] in ("line", "branch") and p["count"] == 0})
    out += ["", f"Points ligne/branche jamais atteints ({len(missed)}) :", ""]
    by_file = defaultdict(list)
    for f, ln in missed:
        by_file[f].append(ln)
    for f in sorted(by_file):
        out.append(f"- `{f}` : lignes {', '.join(map(str, by_file[f]))}")
    text = "\n".join(out) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
