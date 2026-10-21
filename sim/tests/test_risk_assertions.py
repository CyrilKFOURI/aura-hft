"""Risk safety properties as simulation-time assertions (Verilator --assert).

The same checker (rtl/assertions/pre_trade_risk_props.sv) is proved formally by
formal/run_risk_formal.sh; here it is bound into pre_trade_risk and must never
fire while the existing risk and tick-to-trade benches run.
"""

from cocotb_test.simulator import run

from sim.tests.rtl_sources import AURA_TOP_INCLUDES, AURA_TOP_SOURCES, REPO, RISK_PROPS, RTL

ARGS = ["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED", "-Wno-PINCONNECTEMPTY", "--assert"]


def test_risk_props_in_risk_bench():
    run(
        verilog_sources=[str(RTL / s) for s in ["include/ouch_pkg.sv", "risk/pre_trade_risk.sv",
                                                 "egress/ouch_order_gen.sv", "quant/obi_signal.sv",
                                                 "risk/risk_ouch_top.sv"]] + RISK_PROPS,
        toplevel="risk_ouch_top",
        module="sim.tests.tb_risk_and_ouch",
        simulator="verilator",
        includes=[str(RTL / d) for d in ["include", "risk", "egress"]],
        compile_args=ARGS,
        sim_build=str(REPO / "sim" / "build" / "risk_top_sva"),
        extra_env={"PYTHONPATH": str(REPO)},
    )


def test_risk_props_in_tick_to_trade_bench():
    run(
        verilog_sources=AURA_TOP_SOURCES + RISK_PROPS,
        toplevel="aura_hft_top",
        module="sim.tests.tb_tick_to_trade_top",
        simulator="verilator",
        includes=AURA_TOP_INCLUDES,
        compile_args=ARGS,
        sim_build=str(REPO / "sim" / "build" / "aura_top_sva"),
        extra_env={"PYTHONPATH": str(REPO)},
    )
