"""
Pytest integration runner for Quantitative Microstructure Engine & Queue Tracker.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
import pytest
from cocotb_test.simulator import run


def test_quant_engine_verilator():
    """Runs the Cocotb test suite against quant_engine_top using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "include" / "lob_pkg.sv"),
        str(repo_root / "rtl" / "quant" / "obi_calculator.sv"),
        str(repo_root / "rtl" / "quant" / "queue_tracker.sv"),
        str(repo_root / "rtl" / "quant" / "quant_engine_top.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "include"),
        str(repo_root / "rtl" / "quant"),
    ]

    # Build directory
    build_dir = str(repo_root / "sim" / "build" / "quant_top")

    run(
        verilog_sources=verilog_sources,
        toplevel="quant_engine_top",
        module="sim.tests.tb_quant_signals",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
