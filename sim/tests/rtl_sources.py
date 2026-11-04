"""Shared RTL source lists for the reference top (aura_hft_top) runners."""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
RTL = REPO / "rtl"

AURA_TOP_SOURCES = [str(RTL / s) for s in [
    "include/itch_pkg.sv", "include/lob_pkg.sv", "include/ouch_pkg.sv",
    "ingress/moldudp64_depacketizer.sv", "parser/itch_parser_fsm.sv", "parser/speculative_itch_parser.sv",
    "ingress/ingress_pipeline_top.sv", "book/top_of_book_cache.sv", "book/order_store.sv", "book/depth_book.sv",
    "book/lob_engine_top.sv", "quant/obi_calculator.sv", "quant/queue_tracker.sv", "quant/quant_engine_top.sv",
    "risk/pre_trade_risk.sv", "risk/pnl_circuit_breaker.sv", "egress/ouch_order_gen.sv", "quant/obi_signal.sv",
    "risk/risk_ouch_top.sv", "control/axi_lite_control_registers.sv", "metrology/ptp_timer_96b.sv",
    "metrology/axis_eth_fcs_checker.sv", "metrology/latency_metrology.sv", "top/aura_hft_top.sv",
]]
AURA_TOP_INCLUDES = [str(RTL / d) for d in
                     ["include", "ingress", "parser", "book", "quant", "risk", "egress", "control", "metrology", "top"]]
RISK_PROPS = [str(RTL / "assertions" / "pre_trade_risk_props.sv"), str(RTL / "assertions" / "pre_trade_risk_bind.sv")]
ITCH_LOB_SOURCES = [str(RTL / s) for s in [
    "include/itch_pkg.sv", "include/lob_pkg.sv", "ingress/moldudp64_depacketizer.sv",
    "parser/itch_parser_fsm.sv", "parser/speculative_itch_parser.sv", "ingress/ingress_pipeline_top.sv",
    "book/top_of_book_cache.sv", "book/order_store.sv", "book/depth_book.sv",
    "book/lob_engine_top.sv", "book/itch_lob_pipeline_top.sv",
]]
