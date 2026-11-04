"""Hand-made scenarios for the fill model, the costs and the hardware rule."""

import numpy as np
import pytest

from research.obi_backtest.backtest import Config, block_bootstrap_ci, max_drawdown, run_strategy
from research.obi_backtest.model import (ADD, ASK, BID, CANCEL, EXEC, Costs, RiskConfig, leg_cost,
                                         obi_signals, passive_fill, risk_check, round_trip_pnl, to_q31)

P = 1_000_000  # $100.0000


def events(rows):
    """rows: (ts, kind, side, px, qty, add_ts, bb, bbq, ba, baq)."""
    a = np.array(rows, dtype=np.int64)
    keys = ("ts", "kind", "side", "px", "qty", "add_ts", "bb", "bbq", "ba", "baq")
    return {k: a[:, i] for i, k in enumerate(keys)}


# Book at t=10: bid 100.00 x 300 (order added at t=1), ask 100.01 x 200
BASE = [
    (1, ADD, BID, P, 300, 1, P, 300, 0, 0),
    (2, ADD, ASK, P + 100, 200, 2, P, 300, P + 100, 200),
]


def test_older_queue_executions_do_not_fill_us():
    ev = events(BASE + [(20, EXEC, BID, P, 300, 1, 0, 0, P + 100, 200)])
    f = passive_fill(ev, BID, P, 100, t_arrive=10, t_expire=100)
    assert f.filled == 0 and f.reason == "expired"


def test_execution_of_younger_order_fills_us_share_for_share():
    ev = events(BASE + [
        (15, ADD, BID, P, 500, 15, P, 800, P + 100, 200),       # joins behind us
        (20, EXEC, BID, P, 300, 1, P, 500, P + 100, 200),       # consumes the queue ahead
        (21, EXEC, BID, P, 60, 15, P, 440, P + 100, 200),       # would have hit us: 60
        (22, EXEC, BID, P, 60, 15, P, 380, P + 100, 200),       # 40 more -> full
    ])
    f = passive_fill(ev, BID, P, 100, t_arrive=10, t_expire=100)
    assert (f.filled, f.ts, f.price, f.maker, f.reason) == (100, 22, P, True, "queue")


def test_partial_fill_then_expiry():
    ev = events(BASE + [(15, ADD, BID, P, 500, 15, P, 800, P + 100, 200),
                        (21, EXEC, BID, P, 30, 15, P, 770, P + 100, 200)])
    f = passive_fill(ev, BID, P, 100, t_arrive=10, t_expire=100)
    assert (f.filled, f.reason) == (30, "partial")


def test_cancels_ahead_never_fill():
    ev = events(BASE + [(20, CANCEL, BID, P, 300, 1, 0, 0, P + 100, 200)])
    assert passive_fill(ev, BID, P, 100, 10, 100).filled == 0


def test_trade_through_fills_everything():
    ev = events(BASE + [(15, ADD, BID, P - 100, 400, 15, P, 300, P + 100, 200),
                        (30, EXEC, BID, P - 100, 10, 15, P, 300, P + 100, 200)])
    f = passive_fill(ev, BID, P, 100, 10, 100)
    assert (f.filled, f.ts, f.reason) == (100, 30, "trade_through")


def test_opposite_side_crossing_our_price_fills():
    ev = events(BASE + [(25, ADD, ASK, P, 100, 25, P, 300, P, 100)])
    f = passive_fill(ev, BID, P, 100, 10, 100)
    assert (f.filled, f.ts, f.reason) == (100, 25, "trade_through")


def test_marketable_on_arrival_is_a_taker_fill():
    ev = events(BASE + [(5, ADD, ASK, P, 100, 5, P, 300, P, 100)])
    f = passive_fill(ev, BID, P, 100, 10, 100)
    assert (f.filled, f.price, f.maker, f.reason) == (100, P, False, "marketable")


def test_events_after_expiry_are_ignored():
    ev = events(BASE + [(15, ADD, BID, P, 500, 15, P, 800, P + 100, 200),
                        (200, EXEC, BID, P, 500, 15, P, 300, P + 100, 200)])
    assert passive_fill(ev, BID, P, 100, 10, 100).filled == 0


def test_sell_side_mirror():
    ev = events(BASE + [(15, ADD, ASK, P + 100, 50, 15, P, 300, P + 100, 250),
                        (20, EXEC, ASK, P + 100, 200, 2, P, 300, P + 100, 50),
                        (21, EXEC, ASK, P + 100, 50, 15, P, 300, 0, 0)])
    f = passive_fill(ev, ASK, P + 100, 100, 10, 100)
    assert (f.filled, f.reason) == (50, "partial")


def test_costs_buy_maker_sell_taker():
    c = Costs()
    assert leg_cost(c, BID, 100, P, maker=True) == pytest.approx(-0.20)
    # 100 shares sold at $100: take 0.30 + SEC 13e-6 * 10000 = 0.13 + TAF 0.0119
    assert leg_cost(c, ASK, 100, P, maker=False) == pytest.approx(0.30 + 0.13 + 0.0119)
    assert leg_cost(c, ASK, 100_000, P, maker=False) == pytest.approx(300 + 130 + 5.95)  # TAF cap


def test_round_trip_long_and_short():
    c = Costs()
    gross, net = round_trip_pnl(c, +1, 100, P, True, P + 100, False)  # +1 cent
    assert gross == pytest.approx(1.00)
    assert net == pytest.approx(1.00 + 0.20 - (0.30 + 0.130013 + 0.0119), abs=1e-4)
    gross, net = round_trip_pnl(c, -1, 100, P + 100, True, P, False)  # short: sell maker, buy taker
    assert gross == pytest.approx(1.00)
    assert net == pytest.approx(1.00 + 0.20 - 0.130013 - 0.0119 - 0.30, abs=1e-4)


def test_obi_rule_matches_rtl_q31_comparison():
    vb = np.array([700, 300, 0, 500, 0])
    va = np.array([300, 700, 100, 500, 0])
    buy, sell = obi_signals(vb, va, to_q31(0.4), to_q31(-0.4))
    assert buy.tolist() == [True, False, False, False, False]      # OBI = +0.4 exactly -> >=
    assert sell.tolist() == [False, True, True, False, False]      # empty book -> no signal
    assert to_q31(1.0) == (1 << 31) - 1


def test_risk_priority_and_limits():
    r = RiskConfig(max_cum_notional_raw=2 * 100 * P)
    assert risk_check(r, BID, 100, P, P, P + 100, 0) == (True, "PASS")
    assert risk_check(r, BID, 1001, P, P, P + 100, 0)[1] == "MAX_SHARES"
    assert risk_check(r, BID, 100, P + 6000, P, P + 100, 0)[1] == "PRICE_COLLAR"
    assert risk_check(r, BID, 100, P, P, P + 100, 2 * 100 * P)[1] == "CUMULATIVE_NOTIONAL"
    assert risk_check(RiskConfig(kill_switch=True), BID, 1001, P, P, P + 100, 0)[1] == "KILL_SWITCH"


def test_strategy_end_to_end_no_lookahead():
    # Buy signal at t=10 (bid 700 vs ask 300). Younger order executes at t=30 -> filled.
    # Exit 1000 ns later at the best bid known then (100.01): +1 cent gross per share.
    rows = [
        (1, ADD, BID, P, 700, 1, P, 700, 0, 0),
        (10, ADD, ASK, P + 200, 300, 10, P, 700, P + 200, 300),
        (20, ADD, BID, P, 100, 20, P, 800, P + 200, 300),
        (25, EXEC, BID, P, 700, 1, P, 100, P + 200, 300),
        (30, EXEC, BID, P, 100, 20, 0, 0, P + 200, 300),
        (40, ADD, BID, P + 100, 500, 40, P + 100, 500, P + 200, 300),
        (2000, ADD, BID, P + 150, 10, 2000, P + 150, 10, P + 200, 300),  # after exit: must not be used
        (5000, ADD, ASK, P + 300, 10, 5000, P + 150, 10, P + 200, 300),
    ]
    rows = [(r[0] + 10**14, *r[1:5], r[5] + 10**14, *r[6:]) for r in rows]  # move into the session
    cfg = Config(threshold=0.4, horizon_ns=1000, latency_ns=5)
    trades, _ = run_strategy("TEST", events(rows), cfg, Costs(), RiskConfig())
    t = trades[0]
    assert (t.direction, t.shares, t.entry_px, t.entry_maker, t.exit_px) == (BID, 100, P, True, P + 100)
    assert t.gross == pytest.approx(1.00)


def test_stats_helpers():
    assert max_drawdown(np.array([1.0, -2.0, -1.0, 5.0])) == pytest.approx(3.0)
    t = np.arange(100, dtype=np.int64) * 60_000_000_000
    lo, hi = block_bootstrap_ci(t, np.ones(100))
    assert lo == pytest.approx(100) and hi == pytest.approx(100)
