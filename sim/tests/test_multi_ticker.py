"""
Pytest integration runner for Multi-Ticker Concurrent Pipeline.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
from cocotb_test.simulator import run


def test_multi_ticker_pipeline_verilator():
    """Runs the Cocotb test suite against multi_ticker_pipeline_top using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "include" / "itch_pkg.sv"),
        str(repo_root / "rtl" / "include" / "lob_pkg.sv"),
        str(repo_root / "rtl" / "include" / "ouch_pkg.sv"),
        str(repo_root / "rtl" / "experimental" / "multi_symbol_router.sv"),
        str(repo_root / "rtl" / "experimental" / "order_hash_table.sv"),
        str(repo_root / "rtl" / "experimental" / "price_ladder_l2.sv"),
        str(repo_root / "rtl" / "book" / "top_of_book_cache.sv"),
        str(repo_root / "rtl" / "book" / "order_store.sv"),
        str(repo_root / "rtl" / "book" / "depth_book.sv"),
        str(repo_root / "rtl" / "book" / "lob_engine_top.sv"),
        str(repo_root / "rtl" / "experimental" / "avellaneda_stoikov_engine.sv"),
        str(repo_root / "rtl" / "experimental" / "egress_arbiter.sv"),
        str(repo_root / "rtl" / "egress" / "ouch_order_gen.sv"),
        str(repo_root / "rtl" / "risk" / "pre_trade_risk.sv"),
        str(repo_root / "rtl" / "quant" / "obi_signal.sv"),
        str(repo_root / "rtl" / "risk" / "risk_ouch_top.sv"),
        str(repo_root / "rtl" / "experimental" / "multi_ticker_pipeline_top.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "include"),
        str(repo_root / "rtl" / "ingress"),
        str(repo_root / "rtl" / "book"),
        str(repo_root / "rtl" / "quant"),
        str(repo_root / "rtl" / "egress"),
        str(repo_root / "rtl" / "risk"),
        str(repo_root / "rtl" / "top"),
    ]

    build_dir = str(repo_root / "sim" / "build" / "multi_ticker")

    run(
        verilog_sources=verilog_sources,
        toplevel="multi_ticker_pipeline_top",
        module="sim.tests.tb_multi_ticker",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED", "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "-Wno-PINCONNECTEMPTY", "-Wno-PINMISSING"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
