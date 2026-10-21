"""
Database module for AURA-HFT: SQLite in WAL mode.
Provides thread-safe connections, schema initialization, and high-performance batch operations.
"""

import sqlite3
import json
import os
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

DEFAULT_DB_PATH = os.environ.get(
    "AURA_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "aura_hft.db"),
)


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return an SQLite connection configured with WAL mode and row factory."""
    path = db_path or DEFAULT_DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Idempotently initialize all database tables and indexes."""
    conn = get_db_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                dataset_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                obi_threshold REAL NOT NULL,
                max_shares INTEGER NOT NULL,
                price_collar REAL NOT NULL,
                max_notional REAL NOT NULL,
                kill_switch INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                total_ticks INTEGER DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                p50_latency REAL,
                p99_latency REAL
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticks_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp_ns INTEGER NOT NULL,
                cycle_count INTEGER NOT NULL,
                msg_type TEXT NOT NULL,
                best_bid REAL NOT NULL,
                best_ask REAL NOT NULL,
                bid_qty_l1 INTEGER NOT NULL,
                ask_qty_l1 INTEGER NOT NULL,
                obi_value REAL NOT NULL,
                micro_price REAL NOT NULL,
                queue_pos INTEGER,
                top_5_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS generated_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                user_ref_num INTEGER NOT NULL,
                timestamp_ns INTEGER NOT NULL,
                side TEXT NOT NULL,
                shares INTEGER NOT NULL,
                price REAL NOT NULL,
                latency_cycles INTEGER NOT NULL,
                latency_ns REAL NOT NULL,
                status TEXT NOT NULL,
                risk_reason TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_run ON ticks_telemetry(run_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_run_cycle ON ticks_telemetry(run_id, cycle_count);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_run ON generated_orders(run_id);")
    conn.close()


class DatabaseManager:
    """Helper wrapper for database queries and batch transactions."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        init_db(self.db_path)

    def get_connection(self) -> sqlite3.Connection:
        return get_db_connection(self.db_path)

    def create_run(self, run_data: Dict[str, Any]) -> None:
        conn = self.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, created_at, dataset_name, symbol,
                    obi_threshold, max_shares, price_collar, max_notional,
                    kill_switch, status, total_ticks, total_orders, p50_latency, p99_latency
                ) VALUES (
                    :id, :created_at, :dataset_name, :symbol,
                    :obi_threshold, :max_shares, :price_collar, :max_notional,
                    :kill_switch, :status, :total_ticks, :total_orders, :p50_latency, :p99_latency
                );
                """,
                run_data,
            )
        conn.close()

    def update_run_completion(
        self,
        run_id: str,
        status: str,
        total_ticks: int,
        total_orders: int,
        p50_latency: Optional[float] = None,
        p99_latency: Optional[float] = None,
    ) -> None:
        conn = self.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, total_ticks = ?, total_orders = ?, p50_latency = ?, p99_latency = ?
                WHERE id = ?;
                """,
                (status, total_ticks, total_orders, p50_latency, p99_latency, run_id),
            )
        conn.close()

    def list_runs(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.execute("SELECT * FROM runs ORDER BY created_at DESC;")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.execute("SELECT * FROM runs WHERE id = ?;", (run_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def insert_ticks_batch(self, ticks: List[Tuple]) -> None:
        if not ticks:
            return
        conn = self.get_connection()
        with conn:
            conn.executemany(
                """
                INSERT INTO ticks_telemetry (
                    run_id, timestamp_ns, cycle_count, msg_type,
                    best_bid, best_ask, bid_qty_l1, ask_qty_l1,
                    obi_value, micro_price, queue_pos, top_5_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                ticks,
            )
        conn.close()

    def insert_orders_batch(self, orders: List[Tuple]) -> None:
        if not orders:
            return
        conn = self.get_connection()
        with conn:
            conn.executemany(
                """
                INSERT INTO generated_orders (
                    run_id, user_ref_num, timestamp_ns, side,
                    shares, price, latency_cycles, latency_ns, status, risk_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                orders,
            )
        conn.close()

    def get_ticks(self, run_id: str, offset: int = 0, limit: int = 500) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM ticks_telemetry
            WHERE run_id = ?
            ORDER BY id ASC
            LIMIT ? OFFSET ?;
            """,
            (run_id, limit, offset),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        # Parse top_5_json
        for r in rows:
            if isinstance(r.get("top_5_json"), str):
                try:
                    r["top_5"] = json.loads(r["top_5_json"])
                except Exception:
                    r["top_5"] = {}
        return rows

    def get_orders(self, run_id: str) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM generated_orders
            WHERE run_id = ?
            ORDER BY id ASC;
            """,
            (run_id,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
