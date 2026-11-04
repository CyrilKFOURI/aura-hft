"""
Pytest integration runner for Pre-Trade Risk Engine & OUCH 5.0 Packet Generator.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
import pytest
from cocotb_test.simulator import run


def test_risk_and_ouch_verilator():
    """Runs the Cocotb test suite against risk_ouch_top using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "include" / "ouch_pkg.sv"),
        str(repo_root / "rtl" / "risk" / "pre_trade_risk.sv"),
        str(repo_root / "rtl" / "egress" / "ouch_order_gen.sv"),
        str(repo_root / "rtl" / "risk" / "risk_ouch_top.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "include"),
        str(repo_root / "rtl" / "risk"),
        str(repo_root / "rtl" / "egress"),
    ]

    # Build directory
    build_dir = str(repo_root / "sim" / "build" / "risk_top")

    run(
        verilog_sources=verilog_sources,
        toplevel="risk_ouch_top",
        module="sim.tests.tb_risk_and_ouch",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
