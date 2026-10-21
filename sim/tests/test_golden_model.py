"""
Unit Tests for ITCH 5.0 Decoder and Golden Order Book Reference Model.
"""

import struct
import pytest
from sim.golden_model.itch_decoder import ItchDecoder, ItchMessage
from sim.golden_model.golden_order_book import GoldenOrderBook


class TestItchDecoder:
    """Validates binary unpacking for all ITCH 5.0 message types."""

    def test_decode_add_order(self):
        # Type 'A' (36 bytes):
        # 0: 'A'
        # 1-2: stock_locate = 1
        # 3-4: tracking = 42
        # 5-10: timestamp = 36000000000000 ns (6 bytes)
        # 11-18: order_ref = 10001 (8 bytes)
        # 19: side = 'B'
        # 20-23: shares = 200
        # 24-31: stock = "AAPL    "
        # 32-35: price = 1502500 (150.2500)
        ts_bytes = (36000000000000).to_bytes(6, byteorder="big")
        raw = (
            b"A"
            + struct.pack(">HH", 1, 42)
            + ts_bytes
            + struct.pack(">QcI", 10001, b"B", 200)
            + b"AAPL    "
            + struct.pack(">I", 1502500)
        )
        assert len(raw) == 36

        msg = ItchDecoder.decode_message(raw)
        assert msg is not None
        assert msg.msg_type == "A"
        assert msg.stock_locate == 1
        assert msg.tracking_number == 42
        assert msg.timestamp_ns == 36000000000000
        assert msg.order_ref == 10001
        assert msg.side == "B"
        assert msg.shares == 200
        assert msg.stock == "AAPL"
        assert msg.price == 150.25
        assert msg.raw_price == 1502500

    def test_decode_order_executed(self):
        # Type 'E' (31 bytes):
        ts_bytes = (123456789).to_bytes(6, byteorder="big")
        raw = (
            b"E"
            + struct.pack(">HH", 1, 10)
            + ts_bytes
            + struct.pack(">QIQ", 10001, 50, 999999)
        )
        assert len(raw) == 31

        msg = ItchDecoder.decode_message(raw)
        assert msg is not None
        assert msg.msg_type == "E"
        assert msg.order_ref == 10001
        assert msg.shares == 50
        assert msg.match_number == 999999

    def test_decode_order_cancel(self):
        # Type 'X' (23 bytes):
        ts_bytes = (123456789).to_bytes(6, byteorder="big")
        raw = (
            b"X"
            + struct.pack(">HH", 1, 10)
            + ts_bytes
            + struct.pack(">QI", 10001, 30)
        )
        assert len(raw) == 23

        msg = ItchDecoder.decode_message(raw)
        assert msg is not None
        assert msg.msg_type == "X"
        assert msg.order_ref == 10001
        assert msg.shares == 30

    def test_decode_order_delete(self):
        # Type 'D' (19 bytes):
        ts_bytes = (123456789).to_bytes(6, byteorder="big")
        raw = (
            b"D"
            + struct.pack(">HH", 1, 10)
            + ts_bytes
            + struct.pack(">Q", 10001)
        )
        assert len(raw) == 19

        msg = ItchDecoder.decode_message(raw)
        assert msg is not None
        assert msg.msg_type == "D"
        assert msg.order_ref == 10001

    def test_decode_order_replace(self):
        # Type 'U' (35 bytes):
        ts_bytes = (123456789).to_bytes(6, byteorder="big")
        raw = (
            b"U"
            + struct.pack(">HH", 1, 10)
            + ts_bytes
            + struct.pack(">QQII", 10001, 10002, 350, 1510000)
        )
        assert len(raw) == 35

        msg = ItchDecoder.decode_message(raw)
        assert msg is not None
        assert msg.msg_type == "U"
        assert msg.original_order_ref == 10001
        assert msg.new_order_ref == 10002
        assert msg.shares == 350
        assert msg.price == 151.00


class TestGoldenOrderBook:
    """Validates L2/L3 state transitions, OBI, micro-price and queue tracking."""

    @pytest.fixture
    def book(self):
        return GoldenOrderBook(target_symbol="AAPL")

    def test_empty_book(self, book):
        assert book.best_bid() is None
        assert book.best_ask() is None
        assert book.spread() is None
        assert book.calculate_obi() == 0.0
        assert book.calculate_micro_price() is None

    def test_add_orders_and_bbo(self, book):
        # Add Bid 1: 100 shares @ 150.00
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=1, timestamp_ns=1000,
            order_ref=1, side="B", shares=100, stock="AAPL", price=150.00, raw_price=1500000
        ))
        # Add Bid 2: 200 shares @ 150.05 (Higher bid becomes Best Bid)
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=2, timestamp_ns=2000,
            order_ref=2, side="B", shares=200, stock="AAPL", price=150.05, raw_price=1500500
        ))
        # Add Ask 1: 150 shares @ 150.10
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=3, timestamp_ns=3000,
            order_ref=3, side="S", shares=150, stock="AAPL", price=150.10, raw_price=1501000
        ))
        # Add Ask 2: 300 shares @ 150.20
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=4, timestamp_ns=4000,
            order_ref=4, side="S", shares=300, stock="AAPL", price=150.20, raw_price=1502000
        ))

        assert book.best_bid() == (150.05, 200)
        assert book.best_ask() == (150.10, 150)
        assert book.spread() == 0.05

        top_bids = book.top_bids(depth=5)
        assert top_bids == [(150.05, 200), (150.00, 100)]

        top_asks = book.top_asks(depth=5)
        assert top_asks == [(150.10, 150), (150.20, 300)]

    def test_order_execution_and_cancellation(self, book):
        # Add Bid: 200 shares @ 100.00
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=1, timestamp_ns=1000,
            order_ref=10, side="B", shares=200, stock="AAPL", price=100.00, raw_price=1000000
        ))
        assert book.best_bid() == (100.00, 200)

        # Partial execution of 50 shares
        book.process_message(ItchMessage(
            msg_type="E", stock_locate=1, tracking_number=2, timestamp_ns=2000,
            order_ref=10, shares=50, match_number=123
        ))
        assert book.best_bid() == (100.00, 150)

        # Partial cancel of 30 shares
        book.process_message(ItchMessage(
            msg_type="X", stock_locate=1, tracking_number=3, timestamp_ns=3000,
            order_ref=10, shares=30
        ))
        assert book.best_bid() == (100.00, 120)

        # Delete remaining 120 shares
        book.process_message(ItchMessage(
            msg_type="D", stock_locate=1, tracking_number=4, timestamp_ns=4000,
            order_ref=10
        ))
        assert book.best_bid() is None

    def test_order_replace(self, book):
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=1, timestamp_ns=1000,
            order_ref=100, side="B", shares=100, stock="AAPL", price=50.00, raw_price=500000
        ))
        assert book.best_bid() == (50.00, 100)

        # Replace order 100 with order 101: 250 shares @ 50.50
        book.process_message(ItchMessage(
            msg_type="U", stock_locate=1, tracking_number=2, timestamp_ns=2000,
            original_order_ref=100, new_order_ref=101, shares=250, price=50.50, raw_price=505000
        ))
        assert 100 not in book.orders
        assert 101 in book.orders
        assert book.best_bid() == (50.50, 250)

    def test_replace_of_unknown_order_is_ignored(self, book):
        # 'U' has no symbol field: a replace of an order this book never saw
        # belongs to another instrument and must not create a phantom order.
        book.process_message(ItchMessage(
            msg_type="U", stock_locate=99, tracking_number=1, timestamp_ns=1000,
            original_order_ref=555, new_order_ref=556, shares=300, price=12.34, raw_price=123400
        ))
        assert book.orders == {}
        assert book.best_bid() is None and book.best_ask() is None

    def test_obi_and_micro_price(self, book):
        # Best Bid: 300 shares @ 100.00
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=1, timestamp_ns=1000,
            order_ref=1, side="B", shares=300, stock="AAPL", price=100.00, raw_price=1000000
        ))
        # Best Ask: 100 shares @ 101.00
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=2, timestamp_ns=2000,
            order_ref=2, side="S", shares=100, stock="AAPL", price=101.00, raw_price=1010000
        ))

        # OBI = (300 - 100) / (300 + 100) = 200 / 400 = +0.5
        assert book.calculate_obi() == 0.5

        # Micro-Price = (300 * 101.00 + 100 * 100.00) / 400 = (30300 + 10000) / 400 = 40300 / 400 = 100.75
        assert book.calculate_micro_price() == 100.75

        # Symmetrical book test: Add 200 more to ask (now 300 vs 300)
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=3, timestamp_ns=3000,
            order_ref=3, side="S", shares=200, stock="AAPL", price=101.00, raw_price=1010000
        ))
        assert book.calculate_obi() == 0.0
        assert book.calculate_micro_price() == 100.50

    def test_queue_tracker_virtual_order(self, book):
        # Existing queue at 150.00:
        # Order 1: 200 shares
        # Order 2: 300 shares
        # Total volume ahead = 500 shares
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=1, timestamp_ns=1000,
            order_ref=1, side="B", shares=200, stock="AAPL", price=150.00, raw_price=1500000
        ))
        book.process_message(ItchMessage(
            msg_type="A", stock_locate=1, tracking_number=2, timestamp_ns=2000,
            order_ref=2, side="B", shares=300, stock="AAPL", price=150.00, raw_price=1500000
        ))

        # Register our virtual order (id=999) at price 150.00
        vo = book.register_virtual_order(order_id=999, side="B", price=150.00, shares=50)
        assert vo.volume_ahead == 500
        assert vo.status == "PENDING"

        # Partial execution of Order 1: 150 shares executed
        book.process_message(ItchMessage(
            msg_type="E", stock_locate=1, tracking_number=3, timestamp_ns=3000,
            order_ref=1, shares=150, match_number=501
        ))
        assert vo.volume_ahead == 350

        # Full deletion of Order 2: 300 shares canceled
        book.process_message(ItchMessage(
            msg_type="D", stock_locate=1, tracking_number=4, timestamp_ns=4000,
            order_ref=2
        ))
        assert vo.volume_ahead == 50

        # Remaining 50 shares of Order 1 executed -> Volume ahead drops to 0!
        book.process_message(ItchMessage(
            msg_type="E", stock_locate=1, tracking_number=5, timestamp_ns=5000,
            order_ref=1, shares=50, match_number=502
        ))
        assert vo.volume_ahead == 0
        assert vo.status == "AT_FRONT_OF_QUEUE"
