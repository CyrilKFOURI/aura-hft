"""
Pytest integration runner for Hardware Iceberg & TWAP Execution Engine.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
from cocotb_test.simulator import run


def test_iceberg_twap_engine_verilator():
    """Runs the Cocotb test suite against iceberg_twap_engine using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "experimental" / "iceberg_twap_engine.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "exec"),
    ]
    build_dir = str(repo_root / "sim" / "build" / "iceberg_twap_engine")

    run(
        verilog_sources=verilog_sources,
        toplevel="iceberg_twap_engine",
        module="sim.tests.tb_iceberg_twap",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
