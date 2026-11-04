"""
NASDAQ TotalView-ITCH 5.0 Binary Protocol Decoder (Golden Reference).

Format Specs:
- All binary integers are Big-Endian (Network Byte Order).
- Prices are 32-bit unsigned integers representing price * 10,000 (4 decimals).
- Timestamps are 48-bit unsigned integers (nanoseconds since midnight).
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any
import struct


@dataclass(frozen=True)
class ItchMessage:
    msg_type: str
    stock_locate: int
    tracking_number: int
    timestamp_ns: int
    order_ref: Optional[int] = None
    side: Optional[str] = None
    shares: Optional[int] = None
    stock: Optional[str] = None
    price: Optional[float] = None
    raw_price: Optional[int] = None
    match_number: Optional[int] = None
    printable: Optional[str] = None
    original_order_ref: Optional[int] = None
    new_order_ref: Optional[int] = None
    mpid: Optional[str] = None


class ItchDecoder:
    """Decodes raw NASDAQ ITCH 5.0 binary messages."""

    @staticmethod
    def decode_timestamp(ts_bytes: bytes) -> int:
        """Unpack 6-byte big-endian unsigned integer (48 bits)."""
        return int.from_bytes(ts_bytes, byteorder="big", signed=False)

    @classmethod
    def decode_message(cls, data: bytes) -> Optional[ItchMessage]:
        if not data:
            return None

        msg_type = chr(data[0])

        if msg_type == "A":  # Add Order (no MPID) - 36 bytes
            if len(data) < 36:
                return None
            stock_locate, tracking_num = struct.unpack(">HH", data[1:5])
            ts_ns = cls.decode_timestamp(data[5:11])
            order_ref, side_byte, shares = struct.unpack(">QcI", data[11:24])
            stock = data[24:32].decode("ascii", errors="replace").strip()
            raw_price = struct.unpack(">I", data[32:36])[0]
            price = raw_price / 10000.0

            return ItchMessage(
                msg_type="A",
                stock_locate=stock_locate,
                tracking_number=tracking_num,
                timestamp_ns=ts_ns,
                order_ref=order_ref,
                side=side_byte.decode("ascii"),
                shares=shares,
                stock=stock,
                price=price,
                raw_price=raw_price,
            )

        elif msg_type == "F":  # Add Order with MPID - 40 bytes
            if len(data) < 40:
                return None
            stock_locate, tracking_num = struct.unpack(">HH", data[1:5])
            ts_ns = cls.decode_timestamp(data[5:11])
            order_ref, side_byte, shares = struct.unpack(">QcI", data[11:24])
            stock = data[24:32].decode("ascii", errors="replace").strip()
            raw_price = struct.unpack(">I", data[32:36])[0]
            price = raw_price / 10000.0
            mpid = data[36:40].decode("ascii", errors="replace").strip()

            return ItchMessage(
                msg_type="F",
                stock_locate=stock_locate,
                tracking_number=tracking_num,
                timestamp_ns=ts_ns,
                order_ref=order_ref,
                side=side_byte.decode("ascii"),
                shares=shares,
                stock=stock,
                price=price,
                raw_price=raw_price,
                mpid=mpid,
            )

        elif msg_type == "E":  # Order Executed - 31 bytes
            if len(data) < 31:
                return None
            stock_locate, tracking_num = struct.unpack(">HH", data[1:5])
            ts_ns = cls.decode_timestamp(data[5:11])
            order_ref, exec_shares, match_number = struct.unpack(">QIQ", data[11:31])

            return ItchMessage(
                msg_type="E",
                stock_locate=stock_locate,
                tracking_number=tracking_num,
                timestamp_ns=ts_ns,
                order_ref=order_ref,
                shares=exec_shares,
                match_number=match_number,
            )

        elif msg_type == "C":  # Order Executed with Price - 36 bytes
            if len(data) < 36:
                return None
            stock_locate, tracking_num = struct.unpack(">HH", data[1:5])
            ts_ns = cls.decode_timestamp(data[5:11])
            order_ref, exec_shares, match_num, printable, raw_price = struct.unpack(">QIQcI", data[11:36])

            return ItchMessage(
                msg_type="C",
                stock_locate=stock_locate,
                tracking_number=tracking_num,
                timestamp_ns=ts_ns,
                order_ref=order_ref,
                shares=exec_shares,
                match_number=match_num,
                printable=printable.decode("ascii"),
                raw_price=raw_price,
                price=raw_price / 10000.0,
            )

        elif msg_type == "X":  # Order Cancel - 23 bytes
            if len(data) < 23:
                return None
            stock_locate, tracking_num = struct.unpack(">HH", data[1:5])
            ts_ns = cls.decode_timestamp(data[5:11])
            order_ref, canceled_shares = struct.unpack(">QI", data[11:23])

            return ItchMessage(
                msg_type="X",
                stock_locate=stock_locate,
                tracking_number=tracking_num,
                timestamp_ns=ts_ns,
                order_ref=order_ref,
                shares=canceled_shares,
            )

        elif msg_type == "D":  # Order Delete - 19 bytes
            if len(data) < 19:
                return None
            stock_locate, tracking_num = struct.unpack(">HH", data[1:5])
            ts_ns = cls.decode_timestamp(data[5:11])
            order_ref = struct.unpack(">Q", data[11:19])[0]

            return ItchMessage(
                msg_type="D",
                stock_locate=stock_locate,
                tracking_number=tracking_num,
                timestamp_ns=ts_ns,
                order_ref=order_ref,
            )

        elif msg_type == "U":  # Order Replace - 35 bytes
            if len(data) < 35:
                return None
            stock_locate, tracking_num = struct.unpack(">HH", data[1:5])
            ts_ns = cls.decode_timestamp(data[5:11])
            orig_ref, new_ref, shares, raw_price = struct.unpack(">QQII", data[11:35])

            return ItchMessage(
                msg_type="U",
                stock_locate=stock_locate,
                tracking_number=tracking_num,
                timestamp_ns=ts_ns,
                original_order_ref=orig_ref,
                new_order_ref=new_ref,
                shares=shares,
                raw_price=raw_price,
                price=raw_price / 10000.0,
            )

        return None
