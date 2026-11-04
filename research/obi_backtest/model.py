"""Pure logic of the backtest: hardware trading rule, risk checks, fill model, costs.

Everything here works on the per-symbol event arrays built by `extract.py`
(one row per book-changing ITCH event, BBO *after* the event). No function
looks at a row whose timestamp is later than the time it is asked about.

Prices are integers in 1/10000 $ (ITCH raw price), times in ns since midnight.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Event kinds
ADD, EXEC, CANCEL = 0, 1, 2
BID, ASK = 1, -1
PRICE_SCALE = 10_000
Q31 = 1 << 31


# --------------------------------------------------------------------------
# Hardware rule (rtl/quant/obi_signal.sv, rtl/risk/risk_ouch_top.sv)
# --------------------------------------------------------------------------

def to_q31(threshold: float) -> int:
    """Signed Q1.31 register value, as written by the host (saturated)."""
    return max(-Q31, min(Q31 - 1, int(round(threshold * Q31))))


def obi_signals(bid_sz: np.ndarray, ask_sz: np.ndarray, buy_q31: int, sell_q31: int):
    """Exact integer replica of obi_signal.sv: buy iff (Vb-Va)*2^31 >= T_buy*(Vb+Va).

    int64 is exact as long as Vb+Va < 2^31 shares (checked), which real
    top-of-book sizes satisfy by many orders of magnitude.
    """
    vb = bid_sz.astype(np.int64)
    va = ask_sz.astype(np.int64)
    total = vb + va
    if total.size and int(total.max()) >= Q31:
        raise ValueError("top-of-book size too large for exact int64 comparison")
    lhs = (vb - va) << 31
    valid = total > 0
    buy = valid & (lhs >= buy_q31 * total)
    sell = valid & (lhs <= sell_q31 * total)
    return buy, sell


@dataclass(frozen=True)
class RiskConfig:
    """Mirror of the pre_trade_risk.sv registers (0 disables a limit, as in RTL)."""

    kill_switch: bool = False
    max_order_shares: int = 1000
    price_collar: int = 5000                # $0.50 in 1/10000 $
    max_notional_raw: int = 500_000_000     # $50k  (shares * raw price)
    max_cum_notional_raw: int = 0           # disabled for the research runs (see report)


def risk_check(cfg: RiskConfig, side: int, shares: int, price: int, bid: int, ask: int,
               cum_notional_raw: int) -> tuple[bool, str]:
    """Same priority order as pre_trade_risk.sv. Returns (approved, reason)."""
    if cfg.kill_switch:
        return False, "KILL_SWITCH"
    if cfg.max_order_shares > 0 and shares > cfg.max_order_shares:
        return False, "MAX_SHARES"
    if cfg.price_collar > 0:
        if side == BID and ask > 0 and price > ask + cfg.price_collar:
            return False, "PRICE_COLLAR"
        if side == ASK and bid > cfg.price_collar and price < bid - cfg.price_collar:
            return False, "PRICE_COLLAR"
    notional = shares * price
    if cfg.max_notional_raw > 0 and notional > cfg.max_notional_raw:
        return False, "MAX_NOTIONAL"
    if cfg.max_cum_notional_raw > 0 and cum_notional_raw + notional > cfg.max_cum_notional_raw:
        return False, "CUMULATIVE_NOTIONAL"
    return True, "PASS"


# --------------------------------------------------------------------------
# Book lookups without look-ahead
# --------------------------------------------------------------------------

def row_at(ts: np.ndarray, t: int) -> int:
    """Index of the last event with ts <= t (-1 if none): the book state known at t."""
    return int(np.searchsorted(ts, t, side="right")) - 1


# --------------------------------------------------------------------------
# Passive fill model (queue position by FIFO age)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Fill:
    filled: int        # shares filled (0 = not filled)
    ts: int            # time of the last fill event (or of arrival if marketable)
    price: int
    maker: bool        # True = passive (rebate), False = took liquidity (take fee)
    reason: str


def passive_fill(ev: dict, side: int, price: int, shares: int, t_arrive: int, t_expire: int) -> Fill:
    """Simulate a virtual limit order joining the back of the queue at t_arrive.

    Rules (conservative, stated in the report):
      * Marketable on arrival (buy with ask <= price, sell with bid >= price):
        immediate fill at the opposite touch, as a taker.
      * Price-time priority: our order sits behind every real order resting at
        `price` that was added before t_arrive. We are filled only by
        executions at `price` on our side against orders *younger* than us
        (FIFO means those would have hit us first), share for share.
      * Trade-through: an execution on our side at a worse price
        (bid < price for a buy) fills the remainder: the aggressor would have
        hit us first.
      * Opposite touch crossing our price (ask <= price for a buy) while we
        rest fills the remainder: that seller would have traded with us.
      * Cancels/deletes of older orders only move us up; they never fill us.
      * Unfilled remainder is cancelled at t_expire (no cancel latency modelled).
    """
    ts = ev["ts"]
    i0 = row_at(ts, t_arrive)
    if i0 >= 0:
        bid, ask = int(ev["bb"][i0]), int(ev["ba"][i0])
        if side == BID and ask > 0 and ask <= price:
            return Fill(shares, t_arrive, ask, False, "marketable")
        if side == ASK and bid > 0 and bid >= price:
            return Fill(shares, t_arrive, bid, False, "marketable")
    lo = i0 + 1
    hi = int(np.searchsorted(ts, t_expire, side="right"))
    if hi <= lo:
        return Fill(0, t_expire, price, True, "expired")
    k = ev["kind"][lo:hi]
    sd = ev["side"][lo:hi]
    px = ev["px"][lo:hi]
    qty = ev["qty"][lo:hi]
    age = ev["add_ts"][lo:hi]
    on_side_exec = (k == EXEC) & (sd == side)
    younger_at_px = on_side_exec & (px == price) & (age > t_arrive)
    if side == BID:
        through = on_side_exec & (px < price)
        cross = (ev["ba"][lo:hi] > 0) & (ev["ba"][lo:hi] <= price)
    else:
        through = on_side_exec & (px > price)
        cross = (ev["bb"][lo:hi] > 0) & (ev["bb"][lo:hi] >= price)
    cum = np.cumsum(np.where(younger_at_px, qty, 0))
    full_by_queue = np.flatnonzero(cum >= shares)
    full_by_sweep = np.flatnonzero(through | cross)
    cands = []
    if full_by_queue.size:
        cands.append((int(full_by_queue[0]), "queue"))
    if full_by_sweep.size:
        cands.append((int(full_by_sweep[0]), "trade_through"))
    if cands:
        j, why = min(cands)
        return Fill(shares, int(ts[lo + j]), price, True, why)
    partial = int(min(cum[-1], shares)) if cum.size else 0
    if partial > 0:
        last = int(np.flatnonzero(younger_at_px)[-1])
        return Fill(partial, int(ts[lo + last]), price, True, "partial")
    return Fill(0, t_expire, price, True, "expired")


# --------------------------------------------------------------------------
# Costs
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Costs:
    """Per-share fees in $. Defaults: labelled assumptions, see obi_backtest.md."""

    take_fee: float = 0.0030        # Nasdaq remove-liquidity fee (Reg NMS cap)
    maker_rebate: float = 0.0020    # Nasdaq add-liquidity rebate (assumed tier)
    sec_fee_rate: float = 13.00e-6  # SEC Section 31, $13.00 / $1M of sales (Jan 2019)
    finra_taf: float = 0.000119     # FINRA TAF per share sold
    finra_taf_cap: float = 5.95     # per trade


def leg_cost(c: Costs, side: int, shares: int, price_raw: int, maker: bool) -> float:
    """Total $ cost of one execution (negative = we receive a rebate)."""
    fee = -c.maker_rebate * shares if maker else c.take_fee * shares
    if side == ASK:  # sale
        fee += c.sec_fee_rate * shares * price_raw / PRICE_SCALE
        fee += min(c.finra_taf * shares, c.finra_taf_cap)
    return fee


def round_trip_pnl(c: Costs, direction: int, shares: int, entry_px: int, entry_maker: bool,
                   exit_px: int, exit_maker: bool) -> tuple[float, float]:
    """(gross $, net $) of a round trip. direction +1 = long (buy then sell)."""
    gross = direction * shares * (exit_px - entry_px) / PRICE_SCALE
    entry_side = BID if direction > 0 else ASK
    exit_side = -entry_side
    cost = leg_cost(c, entry_side, shares, entry_px, entry_maker) + leg_cost(c, exit_side, shares, exit_px, exit_maker)
    return gross, gross - cost
