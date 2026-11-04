"""
Pytest integration runner for Avellaneda-Stoikov Market Making Engine.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
import pytest
from cocotb_test.simulator import run


def test_avellaneda_stoikov_verilator():
    """Runs the Cocotb test suite against avellaneda_stoikov_engine using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "quant" / "avellaneda_stoikov_engine.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "quant"),
    ]

    build_dir = str(repo_root / "sim" / "build" / "avellaneda_stoikov")

    run(
        verilog_sources=verilog_sources,
        toplevel="avellaneda_stoikov_engine",
        module="sim.tests.tb_avellaneda_stoikov",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
