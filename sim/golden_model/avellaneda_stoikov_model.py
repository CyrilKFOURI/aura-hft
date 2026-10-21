"""
Avellaneda & Stoikov (2008) High-Frequency Market Making Golden Reference Model.

Mathematical Formulation:
  r(s, q) = s - q * gamma * sigma^2 * tau
  r_bid   = round_down(r(s, q) - delta)
  r_ask   = round_up(r(s, q) + delta)

All prices and inventory quantities use fixed-point arithmetic matching the FPGA DSP48 pipeline:
  - Prices: 32-bit unsigned integers (price * 10,000, i.e., 4 decimal places).
  - Inventory q: Signed 16-bit integer [-32768, +32767].
  - Skew penalty factor: Q8.8 or Q1.15 fixed-point.
"""

from typing import Tuple


class AvellanedaStoikovModel:
    """Cycle-accurate mathematical model of the hardware Avellaneda-Stoikov quoting engine."""

    def __init__(
        self,
        skew_factor_raw: int = 2,  # Raw penalty per share (e.g. 2 units = 0.0002 $ / share)
        default_half_spread: int = 100,  # 100 raw units = 0.0100 $ (1 cent)
        max_inventory: int = 2000,
    ):
        self.skew_factor_raw = skew_factor_raw
        self.default_half_spread = default_half_spread
        self.max_inventory = max_inventory
        self.current_inventory = 0

    def reset_inventory(self):
        self.current_inventory = 0

    def apply_execution(self, side: str, shares: int) -> int:
        """Update inventory upon order execution: +shares for Buy, -shares for Sell."""
        if side.upper() in ("B", "BUY"):
            self.current_inventory = min(self.max_inventory, self.current_inventory + shares)
        elif side.upper() in ("S", "SELL"):
            self.current_inventory = max(-self.max_inventory, self.current_inventory - shares)
        return self.current_inventory

    def compute_reservation_price(self, mid_price: int, inventory: int) -> int:
        """
        Calculates the Reservation Price:
          r = mid_price - (inventory * skew_factor)
        Clamped to positive price.
        """
        skew_offset = inventory * self.skew_factor_raw
        res_price = mid_price - skew_offset
        return max(1, res_price)

    def compute_quotes(self, mid_price: int, inventory: int) -> Tuple[int, int, int]:
        """
        Computes the optimal dual-sided bid and ask quote prices:
          r = compute_reservation_price(mid_price, inventory)
          bid_quote = r - default_half_spread
          ask_quote = r + default_half_spread
        Returns (reservation_price, bid_quote, ask_quote).
        """
        res_price = self.compute_reservation_price(mid_price, inventory)
        bid_quote = max(1, res_price - self.default_half_spread)
        ask_quote = res_price + self.default_half_spread
        return res_price, bid_quote, ask_quote
