"""Fault-injection runner for itch_lob_pipeline_top (step P3b).

Each scenario runs in its own simulator process (fresh BRAM state) on a shared build.
Set RTL_COVERAGE=1 to build with Verilator line/toggle coverage (see reports/coverage_itch_lob.md).
"""

import os
import pytest
from cocotb_test.simulator import run

from sim.tests.rtl_sources import ITCH_LOB_SOURCES, REPO

CASES = ["test_unknown_message_types", "test_unknown_symbol", "test_unknown_order_refs",
         "test_zero_share_orders", "test_sequence_gap", "test_sequence_duplicate",
         "test_truncated_frames", "test_zero_length_block", "test_non_mold_frames", "test_back_to_back_burst"]
COVERAGE = os.environ.get("RTL_COVERAGE") == "1"


@pytest.mark.parametrize("case", CASES)
def test_fault_injection(case):
    args = ["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED"]
    if COVERAGE:
        args += ["--coverage-line", "--coverage-toggle", "--coverage-underscore", "-Wno-SIDEEFFECT"]  # coverage instrumentation only
    build = REPO / "sim" / "build" / ("fault_cov" if COVERAGE else "fault")
    run(
        verilog_sources=ITCH_LOB_SOURCES,
        toplevel="itch_lob_pipeline_top",
        module="sim.tests.tb_fault_injection",
        testcase=case,
        simulator="verilator",
        includes=[str(REPO / "rtl" / "include")],
        compile_args=args,
        sim_build=str(build),
        extra_env={"PYTHONPATH": str(REPO)},
        plus_args=[f"+verilator+coverage+file+{build}/coverage_{case}.dat"] if COVERAGE else [],
    )
