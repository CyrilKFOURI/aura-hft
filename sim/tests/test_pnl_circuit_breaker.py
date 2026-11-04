"""
Pytest integration runner for Real-Time PnL Tracker and Circuit Breaker.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
from cocotb_test.simulator import run


def test_pnl_circuit_breaker_verilator():
    """Runs the Cocotb test suite against pnl_circuit_breaker using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "risk" / "pnl_circuit_breaker.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "risk"),
    ]

    build_dir = str(repo_root / "sim" / "build" / "pnl_circuit_breaker")

    run(
        verilog_sources=verilog_sources,
        toplevel="pnl_circuit_breaker",
        module="sim.tests.tb_pnl_circuit_breaker",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
