"""
Golden reference model for Hardware PnL Tracker and Autonomous Circuit Breaker.
Conforms to SEC Rule 15c3-5 and MiFID II RTS 25 pre-trade risk mandates.

Tracks:
  1. Cash Flow from execution fills (Buy = cash out, Sell = cash in).
  2. Inventory net position q.
  3. Continuous Mark-to-Market (MtM) PnL: CashFlow + (q * MidPrice).
  4. Peak-to-Trough Drawdown: Peak_MtM - Current_MtM.
  5. Reflex Circuit Breaker trip signal when Drawdown > MaxDrawdownLimit.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class PnlSnapshot:
    cash_flow: int              # Signed cumulative cash flow (cents * 100 or 4-decimal currency units)
    inventory: int              # Net position in shares
    mtm_pnl: int                # Mark-to-Market PnL
    peak_pnl: int               # Historical highest MtM PnL
    drawdown: int               # Current peak-to-trough drawdown
    breaker_tripped: bool       # Hardware breaker status (latched)


class PnlTrackerModel:
    def __init__(self, max_drawdown_limit: int = 100000000, initial_cash: int = 0):
        """
        Args:
            max_drawdown_limit: Maximum allowed peak-to-trough drawdown before hard trip.
            initial_cash: Starting cash balance in raw 4-decimal fixed point currency.
        """
        self.max_drawdown_limit = max_drawdown_limit
        self.cash_flow = initial_cash
        self.inventory = 0
        self.peak_pnl = 0
        self.breaker_tripped = False
        self.trip_count = 0

    def apply_execution(self, side: str, shares: int, price_raw: int) -> PnlSnapshot:
        """
        Applies a local trade fill (Buy / Sell).
        Buy (side == 'B'): Cash decreases, inventory increases.
        Sell (side == 'S'): Cash increases, inventory decreases.
        """
        notional = shares * price_raw
        if side.upper() == 'B' or side == 0:
            self.cash_flow -= notional
            self.inventory += shares
        else:
            self.cash_flow += notional
            self.inventory -= shares

        return self.get_snapshot(last_mid_price=price_raw)

    def evaluate_mid_price(self, mid_price_raw: int) -> PnlSnapshot:
        """
        Updates Mark-to-Market PnL upon arrival of a new BBO Mid-Price tick.
        """
        return self.get_snapshot(last_mid_price=mid_price_raw)

    def get_snapshot(self, last_mid_price: int) -> PnlSnapshot:
        inventory_value = self.inventory * last_mid_price
        mtm_pnl = self.cash_flow + inventory_value

        # Update historical peak PnL
        if mtm_pnl > self.peak_pnl:
            self.peak_pnl = mtm_pnl

        # Calculate peak-to-trough drawdown
        drawdown = max(0, self.peak_pnl - mtm_pnl)

        # Evaluate autonomous circuit breaker condition
        if drawdown > self.max_drawdown_limit:
            if not self.breaker_tripped:
                self.breaker_tripped = True
                self.trip_count += 1

        return PnlSnapshot(
            cash_flow=self.cash_flow,
            inventory=self.inventory,
            mtm_pnl=mtm_pnl,
            peak_pnl=self.peak_pnl,
            drawdown=drawdown,
            breaker_tripped=self.breaker_tripped,
        )

    def reset_breaker(self, current_mid_price: int = None):
        """Manual authorized clearance of the circuit breaker."""
        self.breaker_tripped = False
        if current_mid_price is not None:
            self.peak_pnl = self.cash_flow + (self.inventory * current_mid_price)
