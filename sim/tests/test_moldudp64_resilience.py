"""
Pytest integration runner for MoldUDP64 Network Resilience & Snapshot Recovery Engine.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
import pytest
from cocotb_test.simulator import run


def test_moldudp64_resilience_verilator():
    """Runs the Cocotb test suite against moldudp64_resilience_engine using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "ingress" / "moldudp64_resilience_engine.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "ingress"),
    ]
    build_dir = str(repo_root / "sim" / "build" / "moldudp64_resilience_engine")

    run(
        verilog_sources=verilog_sources,
        toplevel="moldudp64_resilience_engine",
        module="sim.tests.tb_moldudp64_resilience",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
