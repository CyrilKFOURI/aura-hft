"""
Pytest integration runner for Hardware Limit Order Book (LOB) Engine.
Invokes Cocotb + Verilator co-simulation of itch_lob_pipeline_top.
"""

from pathlib import Path
import pytest
from cocotb_test.simulator import run


def test_order_book_pipeline_verilator():
    """Runs the Cocotb test suite against itch_lob_pipeline_top using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "include" / "itch_pkg.sv"),
        str(repo_root / "rtl" / "include" / "lob_pkg.sv"),
        str(repo_root / "rtl" / "ingress" / "moldudp64_depacketizer.sv"),
        str(repo_root / "rtl" / "parser" / "itch_parser_fsm.sv"),
        str(repo_root / "rtl" / "parser" / "speculative_itch_parser.sv"),
        str(repo_root / "rtl" / "ingress" / "ingress_pipeline_top.sv"),
        str(repo_root / "rtl" / "book" / "order_hash_table.sv"),
        str(repo_root / "rtl" / "book" / "price_ladder_l2.sv"),
        str(repo_root / "rtl" / "book" / "top_of_book_cache.sv"),
        str(repo_root / "rtl" / "book" / "lob_engine_top.sv"),
        str(repo_root / "rtl" / "book" / "itch_lob_pipeline_top.sv"),
    ]
    includes = [str(repo_root / "rtl" / "include")]

    # Build directory
    build_dir = str(repo_root / "sim" / "build" / "lob_top")

    run(
        verilog_sources=verilog_sources,
        toplevel="itch_lob_pipeline_top",
        module="sim.tests.tb_order_book",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
