"""Strategy loop, statistics and report tables for the OBI backtest."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .model import (ASK, BID, Costs, RiskConfig, passive_fill, risk_check, round_trip_pnl,
                    row_at, obi_signals, to_q31)

NS = 1_000_000_000
OPEN_NS = 9 * 3600 * NS + 30 * 60 * NS     # 09:30:00 ET
PREMARKET_NS = 4 * 3600 * NS               # 04:00:00 ET, first time Nasdaq accepts orders
MINUTE_NS = 60 * NS


@dataclass(frozen=True)
class Config:
    threshold: float      # buy if OBI >= +T, sell if OBI <= -T
    horizon_ns: int       # holding time after the entry fill; also entry order lifetime
    latency_ns: int       # reaction delay: decision -> order at the exchange (also on exit)
    shares: int = 100     # cfg_default_order_shares


@dataclass
class Trade:
    symbol: str
    t_decision: int
    direction: int
    shares: int
    entry_px: int
    entry_maker: bool
    fill_reason: str
    exit_px: int
    t_exit: int
    gross: float
    net: float

    @property
    def session(self) -> str:
        return "regular" if self.t_decision >= OPEN_NS else "pre"


def signal_rows(ev: dict, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """Rows where the hardware would emit an order, and the side (+1 buy / -1 sell).

    Research filter on top of the RTL rule: both sides present and book not
    locked/crossed (the RTL would also fire on a one-sided book).
    """
    buy, sell = obi_signals(ev["bbq"], ev["baq"], to_q31(threshold), to_q31(-threshold))
    ok = (ev["bb"] > 0) & (ev["ba"] > 0) & (ev["bb"] < ev["ba"]) & (ev["ts"] >= PREMARKET_NS)
    fire = ok & (buy | sell)
    idx = np.flatnonzero(fire)
    side = np.where(buy[idx], BID, ASK)
    return idx, side


def run_strategy(symbol: str, ev: dict, cfg: Config, costs: Costs, risk: RiskConfig) -> tuple[list[Trade], dict]:
    """One position at a time: passive entry at the touch, taker exit after the horizon."""
    ts = ev["ts"]
    idx, side = signal_rows(ev, cfg.threshold)
    sig_ts = ts[idx]
    t_end = int(ts[-1])
    trades: list[Trade] = []
    attempts = rejected = 0
    cum_notional = 0
    t_free = 0
    while True:
        k = int(np.searchsorted(sig_ts, t_free, side="left"))
        if k >= len(idx):
            break
        i, d = int(idx[k]), int(side[k])
        t_dec = int(ts[i])
        px = int(ev["bb"][i]) if d == BID else int(ev["ba"][i])
        ok, _ = risk_check(risk, d, cfg.shares, px, int(ev["bb"][i]), int(ev["ba"][i]), cum_notional)
        if not ok:
            rejected += 1
            t_free = t_dec + 1
            continue
        cum_notional += cfg.shares * px
        attempts += 1
        t_arr = t_dec + cfg.latency_ns
        t_exp = t_arr + cfg.horizon_ns
        if t_exp > t_end:
            break
        f = passive_fill(ev, d, px, cfg.shares, t_arr, t_exp)
        if f.filled == 0:
            t_free = t_exp
            continue
        t_x = f.ts + cfg.horizon_ns + cfg.latency_ns
        if t_x > t_end:
            break
        j = row_at(ts, t_x)
        exit_px = int(ev["bb"][j]) if d == BID else int(ev["ba"][j])
        if exit_px == 0:
            t_free = t_x
            continue
        gross, net = round_trip_pnl(costs, d, f.filled, f.price, f.maker, exit_px, False)
        trades.append(Trade(symbol, t_dec, d, f.filled, f.price, f.maker, f.reason, exit_px, t_x, gross, net))
        t_free = t_x
    return trades, {"attempts": attempts, "rejected": rejected}


def run_mid_to_mid(ev: dict, cfg: Config) -> list[tuple[int, float]]:
    """Naive upper bound: instant fill at mid on the decision, exit at mid after H, no costs.

    Returns (t_decision, $ PnL per share) for non-overlapping signals.
    """
    ts = ev["ts"]
    mid2 = ev["bb"] + ev["ba"]  # 2*mid, raw
    idx, side = signal_rows(ev, cfg.threshold)
    sig_ts = ts[idx]
    out = []
    t_free = 0
    while True:
        k = int(np.searchsorted(sig_ts, t_free, side="left"))
        if k >= len(idx):
            break
        i, d = int(idx[k]), int(side[k])
        t_dec = int(ts[i])
        t_x = t_dec + cfg.horizon_ns
        if t_x > ts[-1]:
            break
        j = row_at(ts, t_x)
        if ev["bb"][j] == 0 or ev["ba"][j] == 0:
            t_free = t_x
            continue
        out.append((t_dec, d * (int(mid2[j]) - int(mid2[i])) / 2 / 10_000))
        t_free = t_x
    return out


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def max_drawdown(pnl: np.ndarray) -> float:
    if pnl.size == 0:
        return 0.0
    curve = np.concatenate([[0.0], np.cumsum(pnl)])
    return float(np.max(np.maximum.accumulate(curve) - curve))


def block_bootstrap_ci(t: np.ndarray, pnl: np.ndarray, block_minutes: int = 5, n_boot: int = 2000,
                       seed: int = 0) -> tuple[float, float]:
    """95% CI of the total PnL by a moving-block bootstrap on 1-minute buckets.

    Buckets without trades count as 0, so the resampled day keeps the same
    length; blocks of `block_minutes` keep short-range autocorrelation.
    """
    if pnl.size == 0:
        return 0.0, 0.0
    m = ((t - t.min()) // MINUTE_NS).astype(np.int64)
    buckets = np.bincount(m, weights=pnl)
    n = buckets.size
    b = min(block_minutes, n)
    starts_max = n - b + 1
    n_blocks = int(np.ceil(n / b))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, starts_max, size=(n_boot, n_blocks))
    csum = np.concatenate([[0.0], np.cumsum(buckets)])
    totals = (csum[starts + b] - csum[starts]).sum(axis=1) * (n / (n_blocks * b))
    lo, hi = np.percentile(totals, [2.5, 97.5])
    return float(lo), float(hi)


def summarize(trades: list[Trade]) -> dict:
    if not trades:
        return {"trades": 0, "shares": 0, "hit_rate": float("nan"), "gross": 0.0, "net": 0.0,
                "net_per_share": float("nan"), "gross_per_share": float("nan"), "max_dd": 0.0,
                "ci_lo": 0.0, "ci_hi": 0.0, "maker_share": float("nan")}
    net = np.array([x.net for x in trades])
    gross = np.array([x.gross for x in trades])
    sh = np.array([x.shares for x in trades], dtype=float)
    t = np.array([x.t_decision for x in trades], dtype=np.int64)
    lo, hi = block_bootstrap_ci(t, net)
    return {
        "trades": len(trades),
        "shares": int(sh.sum()),
        "hit_rate": float(np.mean(net > 0)),
        "gross": float(gross.sum()),
        "net": float(net.sum()),
        "gross_per_share": float(gross.sum() / sh.sum()),
        "net_per_share": float(net.sum() / sh.sum()),
        "max_dd": max_drawdown(net),
        "ci_lo": lo,
        "ci_hi": hi,
        "maker_share": float(np.mean([x.entry_maker for x in trades])),
    }


def summarize_mid(points: list[tuple[int, float]], shares: int) -> dict:
    if not points:
        return {"signals": 0, "hit_rate": float("nan"), "per_share": float("nan"), "total": 0.0,
                "ci_lo": 0.0, "ci_hi": 0.0}
    t = np.array([p[0] for p in points], dtype=np.int64)
    v = np.array([p[1] for p in points]) * shares
    lo, hi = block_bootstrap_ci(t, v)
    return {"signals": len(points), "hit_rate": float(np.mean(v > 0)), "per_share": float(v.sum() / (shares * len(v))),
            "total": float(v.sum()), "ci_lo": lo, "ci_hi": hi}


def literal_hardware_orders(ev: dict, threshold: float, shares: int, risk: RiskConfig,
                            tx_busy_ns: float = 12 * 6.4) -> dict:
    """What the RTL does as written: one order per BBO update while the signal holds.

    The only throttle is tx_busy (the OUCH frame takes ~12 beats at 156.25 MHz)
    and the cumulative-notional limit, which never decrements.
    """
    idx, side = signal_rows(ev, threshold)
    ts = ev["ts"][idx]
    keep = []
    last = -1e30
    for i, t in enumerate(ts):
        if t - last >= tx_busy_ns:
            keep.append(i)
            last = t
    keep_a = np.array(keep, dtype=np.int64)
    px = np.where(side[keep_a] == BID, ev["bb"][idx[keep_a]], ev["ba"][idx[keep_a]]).astype(np.int64)
    cum = np.cumsum(px * shares)
    trip = int(np.searchsorted(cum, risk.max_cum_notional_raw, side="right")) if risk.max_cum_notional_raw else len(cum)
    return {"orders_emitted": len(keep_a), "approved_before_cum_limit": trip,
            "t_cum_limit_ns": int(ts[keep_a[trip]]) if trip < len(keep_a) else None}


def config_dict(cfg: Config) -> dict:
    return asdict(cfg)
