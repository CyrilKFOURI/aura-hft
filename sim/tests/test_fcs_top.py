"""Corrupted Ethernet FCS through aura_hft_top (step P3b).

Known gap, kept visible: the reference top does not check the FCS (cut-through
checker, CHECK_TRAILING_FCS=0, no sideband), so a corrupted frame reaches the
book. Marked xfail(strict=True): the suite turns red the day it is fixed, so
the marker has to be removed together with the fix.
"""

import pytest
from cocotb_test.simulator import run

from sim.tests.rtl_sources import AURA_TOP_INCLUDES, AURA_TOP_SOURCES, REPO


@pytest.mark.xfail(strict=True, reason="FCS not enforced in aura_hft_top (CHECK_TRAILING_FCS=0, cut-through)")
def test_corrupted_fcs_dropped_by_reference_top():
    run(
        verilog_sources=AURA_TOP_SOURCES,
        toplevel="aura_hft_top",
        module="sim.tests.tb_fcs_top",
        simulator="verilator",
        includes=AURA_TOP_INCLUDES,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED", "-Wno-PINCONNECTEMPTY"],
        sim_build=str(REPO / "sim" / "build" / "aura_top_fcs"),
        extra_env={"PYTHONPATH": str(REPO)},
    )
