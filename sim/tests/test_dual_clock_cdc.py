"""
Pytest integration runner for Dual-Clock Domain Crossing (CDC) Pipeline.
Invokes Cocotb + Verilator co-simulation.
"""

from pathlib import Path
from cocotb_test.simulator import run


def test_dual_clock_cdc_verilator():
    """Runs the Cocotb test suite against aura_hft_dual_clock_top using Verilator."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    verilog_sources = [
        str(repo_root / "rtl" / "include" / "itch_pkg.sv"),
        str(repo_root / "rtl" / "include" / "lob_pkg.sv"),
        str(repo_root / "rtl" / "include" / "ouch_pkg.sv"),
        str(repo_root / "rtl" / "ingress" / "moldudp64_depacketizer.sv"),
        str(repo_root / "rtl" / "parser" / "itch_parser_fsm.sv"),
        str(repo_root / "rtl" / "parser" / "speculative_itch_parser.sv"),
        str(repo_root / "rtl" / "ingress" / "ingress_pipeline_top.sv"),
        str(repo_root / "rtl" / "experimental" / "order_hash_table.sv"),
        str(repo_root / "rtl" / "experimental" / "price_ladder_l2.sv"),
        str(repo_root / "rtl" / "book" / "top_of_book_cache.sv"),
        str(repo_root / "rtl" / "book" / "order_store.sv"),
        str(repo_root / "rtl" / "book" / "depth_book.sv"),
        str(repo_root / "rtl" / "book" / "lob_engine_top.sv"),
        str(repo_root / "rtl" / "quant" / "obi_calculator.sv"),
        str(repo_root / "rtl" / "quant" / "queue_tracker.sv"),
        str(repo_root / "rtl" / "quant" / "quant_engine_top.sv"),
        str(repo_root / "rtl" / "risk" / "pre_trade_risk.sv"),
        str(repo_root / "rtl" / "risk" / "pnl_circuit_breaker.sv"),
        str(repo_root / "rtl" / "experimental" / "cdc_sync_bit.sv"),
        str(repo_root / "rtl" / "experimental" / "axis_async_fifo.sv"),
        str(repo_root / "rtl" / "experimental" / "cdc_msg_fifo.sv"),
        str(repo_root / "rtl" / "egress" / "ouch_order_gen.sv"),
        str(repo_root / "rtl" / "quant" / "obi_signal.sv"),
        str(repo_root / "rtl" / "risk" / "risk_ouch_top.sv"),
        str(repo_root / "rtl" / "metrology" / "ptp_timer_96b.sv"),
        str(repo_root / "rtl" / "metrology" / "axis_eth_fcs_checker.sv"),
        str(repo_root / "rtl" / "metrology" / "latency_metrology.sv"),
        str(repo_root / "rtl" / "experimental" / "aura_hft_dual_clock_top.sv"),
    ]
    includes = [
        str(repo_root / "rtl" / "include"),
        str(repo_root / "rtl" / "ingress"),
        str(repo_root / "rtl" / "parser"),
        str(repo_root / "rtl" / "cdc"),
        str(repo_root / "rtl" / "metrology"),
        str(repo_root / "rtl" / "book"),
        str(repo_root / "rtl" / "quant"),
        str(repo_root / "rtl" / "risk"),
        str(repo_root / "rtl" / "egress"),
        str(repo_root / "rtl" / "top"),
    ]

    build_dir = str(repo_root / "sim" / "build" / "dual_clock_cdc")

    run(
        verilog_sources=verilog_sources,
        toplevel="aura_hft_dual_clock_top",
        module="sim.tests.tb_dual_clock_cdc",
        simulator="verilator",
        includes=includes,
        compile_args=["-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSED", "-Wno-PINCONNECTEMPTY"],
        sim_build=build_dir,
        extra_env={"PYTHONPATH": str(repo_root)},
    )
