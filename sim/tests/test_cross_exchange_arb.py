"""
Pytest integration runner for Cross-Exchange Spatial Arbitrage Engine.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
from cocotb_test.simulator import run


def test_cross_exchange_arbiter_verilator():
    """Runs the Cocotb test suite against cross_exchange_arbiter using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "experimental" / "cross_exchange_arbiter.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "arb"),
    ]
    build_dir = str(repo_root / "sim" / "build" / "cross_exchange_arbiter")

    run(
        verilog_sources=verilog_sources,
        toplevel="cross_exchange_arbiter",
        module="sim.tests.tb_cross_exchange_arb",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )


def test_cross_exchange_pipeline_verilator():
    """Runs the full dual-venue end-to-end arbitrage test against cross_exchange_pipeline_top."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "include" / "itch_pkg.sv"),
        str(repo_root / "rtl" / "include" / "lob_pkg.sv"),
        str(repo_root / "rtl" / "include" / "ouch_pkg.sv"),
        str(repo_root / "rtl" / "ingress" / "moldudp64_depacketizer.sv"),
        str(repo_root / "rtl" / "parser" / "itch_parser_fsm.sv"),
        str(repo_root / "rtl" / "parser" / "speculative_itch_parser.sv"),
        str(repo_root / "rtl" / "ingress" / "ingress_pipeline_top.sv"),
        str(repo_root / "rtl" / "experimental" / "order_hash_table.sv"),
        str(repo_root / "rtl" / "experimental" / "price_ladder_l2.sv"),
        str(repo_root / "rtl" / "book" / "top_of_book_cache.sv"),
        str(repo_root / "rtl" / "book" / "order_store.sv"),
        str(repo_root / "rtl" / "book" / "depth_book.sv"),
        str(repo_root / "rtl" / "book" / "lob_engine_top.sv"),
        str(repo_root / "rtl" / "experimental" / "cross_exchange_arbiter.sv"),
        str(repo_root / "rtl" / "experimental" / "cross_exchange_pipeline_top.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "include"),
        str(repo_root / "rtl" / "ingress"),
        str(repo_root / "rtl" / "parser"),
        str(repo_root / "rtl" / "book"),
        str(repo_root / "rtl" / "arb"),
    ]
    build_dir = str(repo_root / "sim" / "build" / "cross_exchange_pipeline")

    run(
        verilog_sources=verilog_sources,
        toplevel="cross_exchange_pipeline_top",
        module="sim.tests.tb_cross_exchange_pipeline",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED", "-Wno-PINCONNECTEMPTY", "-Wno-PINMISSING"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )

