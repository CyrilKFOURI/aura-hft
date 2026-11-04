"""
Pytest integration runner for IEEE 1588 PTP, Ethernet FCS CRC32, and Latency Metrology.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
import pytest
from cocotb_test.simulator import run


def test_ptp_timer_verilator():
    """Runs the Cocotb test suite against ptp_timer_96b using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "metrology" / "ptp_timer_96b.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "metrology"),
    ]
    build_dir = str(repo_root / "sim" / "build" / "ptp_timer")

    run(
        verilog_sources=verilog_sources,
        toplevel="ptp_timer_96b",
        module="sim.tests.tb_ptp_fcs_metrology",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )


def test_axis_eth_fcs_verilator():
    """Runs the Cocotb test suite against axis_eth_fcs_checker using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "metrology" / "axis_eth_fcs_checker.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "metrology"),
    ]
    build_dir = str(repo_root / "sim" / "build" / "axis_eth_fcs")

    run(
        verilog_sources=verilog_sources,
        toplevel="axis_eth_fcs_checker",
        module="sim.tests.tb_axis_eth_fcs",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )


def test_latency_metrology_verilator():
    """Runs the Cocotb test suite against latency_metrology using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "metrology" / "latency_metrology.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "metrology"),
    ]
    build_dir = str(repo_root / "sim" / "build" / "latency_metrology")

    run(
        verilog_sources=verilog_sources,
        toplevel="latency_metrology",
        module="sim.tests.tb_latency_metrology",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
