"""RTL co-simulation on real NASDAQ data (skipped unless a symbol stream is cached).

Prepare: python data/fetch.py && python -m sim.validation.extract_symbol_stream <capture> --symbol AAPL
Run:     REAL_STREAM=<capture>.AAPL.stream.json pytest sim/tests/test_real_data_rtl.py
"""

import os
from pathlib import Path

import pytest
from cocotb_test.simulator import run

REPO = Path(__file__).resolve().parent.parent.parent
STREAM = os.environ.get("REAL_STREAM")

pytestmark = pytest.mark.skipif(not STREAM or not Path(STREAM).exists(),
                                reason="set REAL_STREAM to a cached *.stream.json")


def test_rtl_lob_on_real_nasdaq_stream():
    symbol = Path(STREAM).name.split(".")[-3]
    target_stock = "64'h" + symbol.ljust(8).encode("ascii").hex()
    sources = ["include/itch_pkg.sv", "include/lob_pkg.sv", "ingress/moldudp64_depacketizer.sv",
               "parser/itch_parser_fsm.sv", "parser/speculative_itch_parser.sv", "ingress/ingress_pipeline_top.sv",
               "experimental/order_hash_table.sv", "experimental/price_ladder_l2.sv", "book/top_of_book_cache.sv",
               "book/order_store.sv", "book/depth_book.sv", "book/lob_engine_top.sv", "book/itch_lob_pipeline_top.sv"]
    run(
        verilog_sources=[str(REPO / "rtl" / s) for s in sources],
        toplevel="itch_lob_pipeline_top",
        module="sim.tests.tb_real_data_cosim",
        simulator="verilator",
        includes=[str(REPO / "rtl" / "include")],
        parameters={"TARGET_STOCK": target_stock},
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED", "-O3"],
        sim_build=str(REPO / "sim" / "build" / f"lob_real_{symbol}"),
        extra_env={"PYTHONPATH": str(REPO), "REAL_STREAM": str(Path(STREAM).resolve()),
                   "REAL_LIMIT": os.environ.get("REAL_LIMIT", ""), "SETTLE": os.environ.get("SETTLE", "24"),
                   "REAL_REPORT": str(REPO / os.environ.get("REAL_REPORT", "reports/rtl_real_cosim.json"))},
    )
