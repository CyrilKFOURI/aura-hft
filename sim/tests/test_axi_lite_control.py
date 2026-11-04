"""
Pytest integration runner for AXI4-Lite Control Registers.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
from cocotb_test.simulator import run


def test_axi_lite_control_verilator():
    """Runs the Cocotb test suite against axi_lite_control_registers using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "control" / "axi_lite_control_registers.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "control"),
    ]

    build_dir = str(repo_root / "sim" / "build" / "axi_lite_control")

    run(
        verilog_sources=verilog_sources,
        toplevel="axi_lite_control_registers",
        module="sim.tests.tb_axi_lite_control",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
