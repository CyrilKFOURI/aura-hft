"""
Pytest integration runner for Ingress Network Pipeline & ITCH 5.0 Parser.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
from cocotb_test.simulator import run


def test_ingress_pipeline_verilator():
    """Runs the Cocotb test suite against ingress_pipeline_top using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "include" / "itch_pkg.sv"),
        str(repo_root / "rtl" / "ingress" / "moldudp64_depacketizer.sv"),
        str(repo_root / "rtl" / "parser" / "itch_parser_fsm.sv"),
        str(repo_root / "rtl" / "parser" / "speculative_itch_parser.sv"),
        str(repo_root / "rtl" / "ingress" / "ingress_pipeline_top.sv"),
    ]
    includes = [str(repo_root / "rtl" / "include")]

    # Build directory
    build_dir = str(repo_root / "sim" / "build" / "ingress_top")

    run(
        verilog_sources=verilog_sources,
        toplevel="ingress_pipeline_top",
        module="sim.tests.tb_itch_parser",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
