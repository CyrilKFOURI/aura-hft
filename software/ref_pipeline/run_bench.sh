#!/bin/sh
# Validate then benchmark the software reference path on a raw ITCH file.
# Usage (repo root, Linux / Docker): sh software/ref_pipeline/run_bench.sh <file.itch> [limit] [symbols...]
set -e
ITCH=${1:?usage: run_bench.sh <file.itch> [limit] [symbols...]}
LIMIT=${2:-20000000}
shift 2 2>/dev/null || shift $#
SYMBOLS=${*:-"AAPL MSFT TSLA QQQ"}
OUT=reports/software_latency

make -C software/ref_pipeline all test
PYTHONPATH=. python3 software/ref_pipeline/validate.py "$ITCH" --symbols $SYMBOLS --limit "$LIMIT"
mkdir -p "$OUT"
for sym in $SYMBOLS; do
    software/ref_pipeline/bin/aura_ref bench "$ITCH" --symbol "$sym" --limit "$LIMIT" --cpu 2 --reps 3 \
        --json "$OUT/$sym.json" | grep -v histogram
done
grep -m1 'model name' /proc/cpuinfo || true
