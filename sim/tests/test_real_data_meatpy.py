"""Real-data cross-validation (skipped when no NASDAQ capture is cached).

Fetch data first:  python data/fetch.py --messages 2000000
"""

import datetime
from pathlib import Path

import pytest

CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"
CAPTURES = sorted(CACHE.glob("*.NASDAQ_ITCH50*.itch"))

pytestmark = pytest.mark.skipif(not CAPTURES, reason="no real ITCH capture in data/cache (run data/fetch.py)")


def test_golden_matches_meatpy_on_real_nasdaq_data():
    pytest.importorskip("meatpy")
    from sim.validation.compare_meatpy import run

    n, _, reports = run(str(CAPTURES[0]), ["AAPL", "QQQ"], 100_000, 500_000, datetime.datetime(2019, 1, 30))
    assert n == 500_000
    for rep in reports.values():
        assert rep.bbo_checks > 0, f"{rep.symbol}: no message touched the book"
        assert rep.bbo_mismatches == 0 and rep.depth_mismatches == 0, rep.examples
