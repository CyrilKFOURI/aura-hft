"""
High-performance simulation runner for AURA-HFT.
Simulates market feeds, feeds the Golden Reference Model, computes microstructure signals,
evaluates 1-cycle pre-trade risk controls, and emits OUCH orders with hardware cycle-accurate latency.
"""

import json
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from sim.golden_model.golden_order_book import GoldenOrderBook
from sim.golden_model.itch_decoder import ItchMessage
from .db import DatabaseManager
from .latency_sources import FPGA_CLOCK_MHZ, FPGA_SIM_CYCLES
from .models import RunLaunchRequest


class SimulationRunner:
    """Executes market scenario replay, computes hardware telemetry, and saves to database."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def generate_synthetic_scenario(
        self,
        symbol: str,
        scenario: str,
        num_ticks: int = 500,
        base_price: float = 150.00,
    ) -> List[ItchMessage]:
        """
        Generates realistic ITCH 5.0 messages tailored to the chosen scenario:
        - 'balanced': normal two-sided continuous book with balanced liquidity.
        - 'bullish_surge': heavy bid influx leading to OBI > +0.70.
        - 'bearish_dump': heavy ask influx leading to OBI < -0.70.
        - 'risk_violation': injects conditions triggering fat-finger, collar, and kill switch rules.
        """
        random.seed(42)  # Deterministic seed for reproducible testing
        messages: List[ItchMessage] = []
        current_time_ns = 34_200_000_000_000  # 09:30:00.000 in nanoseconds since midnight
        order_ref_counter = 1000

        # Initial seed orders to establish a clean BBO
        init_orders = [
            ("B", 1000, base_price - 0.05),
            ("B", 800, base_price - 0.04),
            ("B", 600, base_price - 0.03),
            ("B", 500, base_price - 0.02),
            ("B", 400, base_price - 0.01),
            ("S", 400, base_price + 0.01),
            ("S", 500, base_price + 0.02),
            ("S", 600, base_price + 0.03),
            ("S", 800, base_price + 0.04),
            ("S", 1000, base_price + 0.05),
        ]

        active_bid_refs: List[int] = []
        active_ask_refs: List[int] = []

        for side, shares, price in init_orders:
            order_ref_counter += 1
            current_time_ns += 500
            msg = ItchMessage(
                msg_type="A",
                stock_locate=1,
                tracking_number=1,
                timestamp_ns=current_time_ns,
                order_ref=order_ref_counter,
                side=side,
                shares=shares,
                stock=symbol,
                price=round(price, 2),
                raw_price=int(round(price * 10000)),
            )
            messages.append(msg)
            if side == "B":
                active_bid_refs.append(order_ref_counter)
            else:
                active_ask_refs.append(order_ref_counter)

        # Generate subsequent ticks according to scenario
        mid = base_price
        for i in range(num_ticks):
            current_time_ns += random.randint(100, 2000)
            roll = random.random()

            if scenario == "bullish_surge":
                # 75% bids, 25% asks, drift upward
                side = "B" if roll < 0.75 else "S"
                shares = random.randint(300, 1500) if side == "B" else random.randint(50, 300)
                if i % 20 == 0:
                    mid += 0.01
            elif scenario == "bearish_dump":
                # 75% asks, 25% bids, drift downward
                side = "S" if roll < 0.75 else "B"
                shares = random.randint(300, 1500) if side == "S" else random.randint(50, 300)
                if i % 20 == 0:
                    mid -= 0.01
            else:  # balanced or risk_violation
                side = "B" if roll < 0.50 else "S"
                shares = random.randint(100, 800)

            # Choose message type: Add (A), Execute (E), Cancel (X), Delete (D)
            msg_choice = random.random()
            if msg_choice < 0.65 or not active_bid_refs or not active_ask_refs:
                # Add order
                order_ref_counter += 1
                offset = random.choice([0.01, 0.02, 0.03, 0.04])
                price = round(mid - offset if side == "B" else mid + offset, 2)
                msg = ItchMessage(
                    msg_type="A",
                    stock_locate=1,
                    tracking_number=1,
                    timestamp_ns=current_time_ns,
                    order_ref=order_ref_counter,
                    side=side,
                    shares=shares,
                    stock=symbol,
                    price=price,
                    raw_price=int(round(price * 10000)),
                )
                messages.append(msg)
                if side == "B":
                    active_bid_refs.append(order_ref_counter)
                else:
                    active_ask_refs.append(order_ref_counter)
            elif msg_choice < 0.85:
                # Execute order (E)
                target_list = active_bid_refs if side == "B" else active_ask_refs
                if target_list:
                    ref = random.choice(target_list)
                    exec_shares = min(shares, 200)
                    msg = ItchMessage(
                        msg_type="E",
                        stock_locate=1,
                        tracking_number=1,
                        timestamp_ns=current_time_ns,
                        order_ref=ref,
                        shares=exec_shares,
                        match_number=i,
                        printable="Y",
                    )
                    messages.append(msg)
            else:
                # Cancel or Delete (X / D)
                target_list = active_bid_refs if side == "B" else active_ask_refs
                if target_list:
                    ref = target_list.pop(random.randrange(len(target_list)))
                    msg = ItchMessage(
                        msg_type="D",
                        stock_locate=1,
                        tracking_number=1,
                        timestamp_ns=current_time_ns,
                        order_ref=ref,
                    )
                    messages.append(msg)

        return messages

    def run_simulation(self, run_id: str, request: RunLaunchRequest) -> Dict[str, Any]:
        """
        Runs full end-to-end pipeline simulation, recording telemetry and generated orders.
        """
        created_at = datetime.now(timezone.utc).isoformat()
        self.db.create_run({
            "id": run_id,
            "created_at": created_at,
            "dataset_name": request.dataset_name,
            "symbol": request.symbol,
            "obi_threshold": request.obi_threshold,
            "max_shares": request.max_shares,
            "price_collar": request.price_collar,
            "max_notional": request.max_notional,
            "kill_switch": 1 if request.kill_switch else 0,
            "status": "RUNNING",
            "total_ticks": 0,
            "total_orders": 0,
            "p50_latency": None,
            "p99_latency": None,
        })

        book = GoldenOrderBook(target_symbol=request.symbol)
        messages = self.generate_synthetic_scenario(
            symbol=request.symbol,
            scenario=request.scenario or "balanced",
            num_ticks=request.tick_limit,
        )

        ticks_records: List[Tuple] = []
        orders_records: List[Tuple] = []
        latencies: List[float] = []

        clock_cycle = 0
        virtual_order_registered = False
        user_ref_counter = 50000

        # Cumulative notional tracker
        cumulative_notional = 0.0

        for msg in messages:
            clock_cycle += random.randint(3, 8)
            book.process_message(msg)

            bb = book.best_bid()
            ba = book.best_ask()

            # If book is empty on either side, skip quant eval
            if bb is None or ba is None:
                continue

            best_bid, bid_qty_l1 = bb
            best_ask, ask_qty_l1 = ba
            obi = book.calculate_obi()
            calc_micro = book.calculate_micro_price()
            micro_price = calc_micro if calc_micro is not None else ((best_bid + best_ask) / 2.0)

            # Register a virtual passive order at best_bid once established
            if not virtual_order_registered and best_bid is not None:
                book.register_virtual_order(
                    order_id=1,
                    side="B",
                    price=best_bid,
                    shares=100,
                )
                virtual_order_registered = True

            vo = book.virtual_orders.get(1)
            queue_pos = vo.volume_ahead if vo else None

            # Top 5 levels JSON
            top_bids = book.top_bids(5)
            top_asks = book.top_asks(5)
            top_5_json = json.dumps({
                "bids": [[p, s] for p, s in top_bids],
                "asks": [[p, s] for p, s in top_asks],
            })

            ticks_records.append((
                run_id,
                msg.timestamp_ns,
                clock_cycle,
                msg.msg_type,
                best_bid,
                best_ask,
                bid_qty_l1,
                ask_qty_l1,
                obi,
                round(micro_price, 4),
                queue_pos,
                top_5_json,
            ))

            # Strategy trigger check:
            # Trigger order when OBI breaches threshold
            trigger_order = False
            order_side = "B"
            order_price = best_ask
            order_shares = 200

            # In risk_violation scenario, periodically craft violating orders
            if request.scenario == "risk_violation" and len(orders_records) < 3:
                trigger_order = True
                if len(orders_records) == 0:
                    # Violate max_shares
                    order_shares = request.max_shares + 500
                    order_price = best_bid
                elif len(orders_records) == 1:
                    # Violate price collar
                    order_shares = 100
                    order_price = round(best_bid * (1.0 + request.price_collar + 0.05), 2)
                else:
                    order_shares = 100
                    order_price = best_bid
            elif abs(obi) >= request.obi_threshold and (len(orders_records) == 0 or clock_cycle - orders_records[-1][6] > 30):
                # Throttle orders at least 30 cycles apart
                trigger_order = True
                if obi > 0:
                    order_side = "B"
                    order_price = best_ask
                else:
                    order_side = "S"
                    order_price = best_bid

            if trigger_order:
                user_ref_counter += 1
                # Synthetic demo runner (not Verilator): it reports the tick-to-trade
                # latency simulated for the RTL (docs/CLAIMS.md C1), no invented jitter.
                latency_cycles = FPGA_SIM_CYCLES
                latency_ns = round(latency_cycles * 1000.0 / FPGA_CLOCK_MHZ, 2)
                latencies.append(latency_ns)

                order_notional = order_shares * order_price
                mid_price = (best_bid + best_ask) / 2.0

                # Pre-trade risk evaluation (1-cycle combinational check)
                status = "EXECUTED"
                risk_reason = None

                if request.kill_switch:
                    status = "REJECTED"
                    risk_reason = "RISK_KILL_SWITCH"
                elif order_shares > request.max_shares:
                    status = "REJECTED"
                    risk_reason = "MAX_SHARES_EXCEEDED"
                elif abs(order_price - mid_price) / mid_price > request.price_collar:
                    status = "REJECTED"
                    risk_reason = "PRICE_COLLAR_EXCEEDED"
                elif order_notional > request.max_notional:
                    status = "REJECTED"
                    risk_reason = "NOTIONAL_EXCEEDED"
                elif cumulative_notional + order_notional > request.max_notional * 5:
                    status = "REJECTED"
                    risk_reason = "CUMULATIVE_NOTIONAL_EXCEEDED"
                else:
                    cumulative_notional += order_notional

                orders_records.append((
                    run_id,
                    user_ref_counter,
                    msg.timestamp_ns,
                    order_side,
                    order_shares,
                    order_price,
                    latency_cycles,
                    latency_ns,
                    status,
                    risk_reason,
                ))

        # Save all batches
        self.db.insert_ticks_batch(ticks_records)
        self.db.insert_orders_batch(orders_records)

        p50 = float(np.percentile(latencies, 50)) if latencies else None
        p99 = float(np.percentile(latencies, 99)) if latencies else None

        self.db.update_run_completion(
            run_id=run_id,
            status="COMPLETED",
            total_ticks=len(ticks_records),
            total_orders=len(orders_records),
            p50_latency=p50,
            p99_latency=p99,
        )

        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "total_ticks": len(ticks_records),
            "total_orders": len(orders_records),
            "p50_latency": p50,
            "p99_latency": p99,
        }
