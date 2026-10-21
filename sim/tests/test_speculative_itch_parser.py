"""
Pytest integration runner for speculative_itch_parser.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
from cocotb_test.simulator import run


def test_speculative_itch_parser_verilator():
    """Runs the Cocotb test suite against speculative_itch_parser using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "include" / "itch_pkg.sv"),
        str(repo_root / "rtl" / "parser" / "speculative_itch_parser.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "include"),
        str(repo_root / "rtl" / "parser"),
    ]

    build_dir = str(repo_root / "sim" / "build" / "speculative_itch_parser")

    run(
        verilog_sources=verilog_sources,
        toplevel="speculative_itch_parser",
        module="sim.tests.tb_speculative_itch_parser",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
