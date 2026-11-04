"""
Golden Reference Limit Order Book (L2/L3 Engine + Quant Signals + Queue Tracker).

Matches exact hardware state behavior on FPGA:
- Tracks individual active orders (L3).
- Maintains price ladder aggregated depths (L2).
- Computes Top-of-Book / BBO in O(1).
- Computes Order Book Imbalance (OBI) & Micro-Price (Rosenbaum / DEA El Karoui).
- Tracks FIFO Queue Depletion for virtual test orders.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from .itch_decoder import ItchMessage


@dataclass
class Order:
    order_ref: int
    side: str  # 'B' or 'S'
    shares: int
    price: float
    stock: str
    timestamp_ns: int


@dataclass
class VirtualOrder:
    order_id: int
    side: str
    price: float
    shares: int
    volume_ahead: int
    status: str = "PENDING"  # PENDING, EXECUTED, CANCELLED


class GoldenOrderBook:
    """Cycle-accurate software reference model of the hardware order book."""

    def __init__(self, target_symbol: str = "AAPL"):
        self.target_symbol = target_symbol.strip()
        # Active orders table: order_ref -> Order
        self.orders: Dict[int, Order] = {}
        # Price levels (Price -> Total Shares)
        self.bids: Dict[float, int] = {}
        self.asks: Dict[float, int] = {}
        # Queue Tracker: virtual_order_id -> VirtualOrder
        self.virtual_orders: Dict[int, VirtualOrder] = {}
        # Order entry FIFO sequence per price level: price -> list of order_refs
        self.order_queues: Dict[float, List[int]] = {}

    def clear(self):
        self.orders.clear()
        self.bids.clear()
        self.asks.clear()
        self.virtual_orders.clear()
        self.order_queues.clear()

    # --- Level 1 & Level 2 State Queries ---

    def best_bid(self) -> Optional[Tuple[float, int]]:
        """Returns (best_bid_price, best_bid_shares) or None."""
        if not self.bids:
            return None
        max_p = max(self.bids.keys())
        return (max_p, self.bids[max_p])

    def best_ask(self) -> Optional[Tuple[float, int]]:
        """Returns (best_ask_price, best_ask_shares) or None."""
        if not self.asks:
            return None
        min_p = min(self.asks.keys())
        return (min_p, self.asks[min_p])

    def spread(self) -> Optional[float]:
        """Returns current bid-ask spread."""
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is not None and ba is not None:
            return round(ba[0] - bb[0], 4)
        return None

    def top_bids(self, depth: int = 5) -> List[Tuple[float, int]]:
        """Returns top N sorted bid levels (highest price first)."""
        sorted_prices = sorted(self.bids.keys(), reverse=True)[:depth]
        return [(p, self.bids[p]) for p in sorted_prices]

    def top_asks(self, depth: int = 5) -> List[Tuple[float, int]]:
        """Returns top N sorted ask levels (lowest price first)."""
        sorted_prices = sorted(self.asks.keys())[:depth]
        return [(p, self.asks[p]) for p in sorted_prices]

    # --- Quantitative Microstructure Signals (DEA El Karoui) ---

    def calculate_obi(self) -> float:
        """
        Calculates Order Book Imbalance (OBI) at Best Bid/Ask:
        OBI = (V_bid - V_ask) / (V_bid + V_ask)
        Returns a float in [-1.0, 1.0]. Returns 0.0 if empty.
        """
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return 0.0
        v_bid = bb[1]
        v_ask = ba[1]
        total_vol = v_bid + v_ask
        if total_vol == 0:
            return 0.0
        return round((v_bid - v_ask) / total_vol, 6)

    def calculate_micro_price(self) -> Optional[float]:
        """
        Calculates Micro-Price:
        P_micro = (V_bid * P_ask + V_ask * P_bid) / (V_bid + V_ask)
        """
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is None or ba is None:
            return None
        p_bid, v_bid = bb
        p_ask, v_ask = ba
        total_vol = v_bid + v_ask
        if total_vol == 0:
            return None
        return round((v_bid * p_ask + v_ask * p_bid) / total_vol, 4)

    # --- Queue Tracking for Virtual Orders ---

    def register_virtual_order(self, order_id: int, side: str, price: float, shares: int) -> VirtualOrder:
        """
        Places a virtual passive order at `price` and computes the initial
        volume ahead of it in the current queue.
        """
        price = round(price, 4)
        vol_ahead = 0
        if side == "B":
            vol_ahead = self.bids.get(price, 0)
        else:
            vol_ahead = self.asks.get(price, 0)

        vo = VirtualOrder(
            order_id=order_id,
            side=side,
            price=price,
            shares=shares,
            volume_ahead=vol_ahead,
        )
        self.virtual_orders[order_id] = vo
        return vo

    def _update_queue_depletion(self, order: Order, volume_reduced: int):
        """When an existing order is executed or canceled, update volume ahead for virtual orders."""
        price = order.price
        side = order.side
        for vo in self.virtual_orders.values():
            if vo.status == "PENDING" and vo.side == side and vo.price == price:
                # Check if the reduced order was ahead of our virtual order in queue
                queue = self.order_queues.get(price, [])
                if order.order_ref in queue:
                    vo.volume_ahead = max(0, vo.volume_ahead - volume_reduced)
                    if vo.volume_ahead == 0:
                        vo.status = "AT_FRONT_OF_QUEUE"

    # --- Core ITCH Message Dispatcher ---

    def process_message(self, msg: ItchMessage) -> Dict[str, Any]:
        """
        Processes an ITCH 5.0 message, updates LOB state and signals.
        Returns a dict with state transition metrics.
        """
        # If stock is explicitly provided, filter on target symbol
        if msg.stock and msg.stock.strip() != self.target_symbol:
            return {"action": "IGNORED_SYMBOL", "stock": msg.stock}

        res = {"msg_type": msg.msg_type, "order_ref": msg.order_ref}

        if msg.msg_type in ("A", "F"):  # Add Order
            self._handle_add(msg)
            res["action"] = "ADDED"

        elif msg.msg_type == "E":  # Order Executed
            self._handle_executed(msg)
            res["action"] = "EXECUTED"

        elif msg.msg_type == "C":  # Order Executed with Price
            self._handle_executed_price(msg)
            res["action"] = "EXECUTED_WITH_PRICE"

        elif msg.msg_type == "X":  # Order Cancel
            self._handle_cancel(msg)
            res["action"] = "CANCELED"

        elif msg.msg_type == "D":  # Order Delete
            self._handle_delete(msg)
            res["action"] = "DELETED"

        elif msg.msg_type == "U":  # Order Replace
            self._handle_replace(msg)
            res["action"] = "REPLACED"

        # Attach real-time computed microstructure signals
        res["best_bid"] = self.best_bid()
        res["best_ask"] = self.best_ask()
        res["spread"] = self.spread()
        res["obi"] = self.calculate_obi()
        res["micro_price"] = self.calculate_micro_price()

        return res

    # --- Private Handlers ---

    def _handle_add(self, msg: ItchMessage):
        price = round(msg.price, 4)
        order = Order(
            order_ref=msg.order_ref,
            side=msg.side,
            shares=msg.shares,
            price=price,
            stock=msg.stock or self.target_symbol,
            timestamp_ns=msg.timestamp_ns,
        )
        self.orders[msg.order_ref] = order

        # Update Level 2 price aggregated book
        if msg.side == "B":
            self.bids[price] = self.bids.get(price, 0) + msg.shares
        else:
            self.asks[price] = self.asks.get(price, 0) + msg.shares

        # Update FIFO queue sequence
        if price not in self.order_queues:
            self.order_queues[price] = []
        self.order_queues[price].append(msg.order_ref)

    def _handle_executed(self, msg: ItchMessage):
        if msg.order_ref not in self.orders:
            return
        order = self.orders[msg.order_ref]
        exec_shares = min(order.shares, msg.shares)
        price = order.price

        self._update_queue_depletion(order, exec_shares)

        order.shares -= exec_shares
        if order.side == "B":
            self.bids[price] -= exec_shares
            if self.bids[price] <= 0:
                del self.bids[price]
        else:
            self.asks[price] -= exec_shares
            if self.asks[price] <= 0:
                del self.asks[price]

        if order.shares == 0:
            del self.orders[msg.order_ref]
            if price in self.order_queues and msg.order_ref in self.order_queues[price]:
                self.order_queues[price].remove(msg.order_ref)

    def _handle_executed_price(self, msg: ItchMessage):
        # Structurally identical to 'E' for book tracking
        self._handle_executed(msg)

    def _handle_cancel(self, msg: ItchMessage):
        if msg.order_ref not in self.orders:
            return
        order = self.orders[msg.order_ref]
        cancel_shares = min(order.shares, msg.shares)
        price = order.price

        self._update_queue_depletion(order, cancel_shares)

        order.shares -= cancel_shares
        if order.side == "B":
            self.bids[price] -= cancel_shares
            if self.bids[price] <= 0:
                del self.bids[price]
        else:
            self.asks[price] -= cancel_shares
            if self.asks[price] <= 0:
                del self.asks[price]

        if order.shares == 0:
            del self.orders[msg.order_ref]
            if price in self.order_queues and msg.order_ref in self.order_queues[price]:
                self.order_queues[price].remove(msg.order_ref)

    def _handle_delete(self, msg: ItchMessage):
        if msg.order_ref not in self.orders:
            return
        order = self.orders[msg.order_ref]
        price = order.price
        remaining_shares = order.shares

        self._update_queue_depletion(order, remaining_shares)

        if order.side == "B":
            self.bids[price] -= remaining_shares
            if self.bids[price] <= 0:
                del self.bids[price]
        else:
            self.asks[price] -= remaining_shares
            if self.asks[price] <= 0:
                del self.asks[price]

        del self.orders[msg.order_ref]
        if price in self.order_queues and msg.order_ref in self.order_queues[price]:
            self.order_queues[price].remove(msg.order_ref)

    def _handle_replace(self, msg: ItchMessage):
        # 1. Delete original order
        # 'U' carries no symbol: an unknown original ref belongs to another
        # instrument (or predates this book) and must not create an order.
        orig_ref = msg.original_order_ref
        if orig_ref not in self.orders:
            return
        orig_order = self.orders[orig_ref]
        orig_side = orig_order.side
        orig_stock = orig_order.stock
        del_msg = ItchMessage(
            msg_type="D",
            stock_locate=msg.stock_locate,
            tracking_number=msg.tracking_number,
            timestamp_ns=msg.timestamp_ns,
            order_ref=orig_ref,
        )
        self._handle_delete(del_msg)

        # 2. Add new order
        new_msg = ItchMessage(
            msg_type="A",
            stock_locate=msg.stock_locate,
            tracking_number=msg.tracking_number,
            timestamp_ns=msg.timestamp_ns,
            order_ref=msg.new_order_ref,
            side=orig_side,
            shares=msg.shares,
            stock=orig_stock,
            price=msg.price,
            raw_price=msg.raw_price,
        )
        self._handle_add(new_msg)
