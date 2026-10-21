# ==============================================================================
# Vivado Batch Synthesis & Implementation Script (AURA-HFT)
# Target Device : AMD Kria KR260 (xck26-sfvc784-2LV-c)
# Top Module    : aura_hft_top
# Usage         : vivado -mode batch -source scripts/synth.tcl
# ==============================================================================

set PROJECT_ROOT [file normalize [file dirname [info script]]/..]
set OUTPUT_DIR   [file normalize $PROJECT_ROOT/reports]
file mkdir $OUTPUT_DIR

puts "=================================================================="
puts "  AURA-HFT: Starting Vivado Synthesis & Timing Closure Run"
puts "  Target Part: xck26-sfvc784-2LV-c (AMD Kria KR260)"
puts "=================================================================="

# 1. Read SystemVerilog Sources
read_verilog -sv [list \
    $PROJECT_ROOT/rtl/include/itch_pkg.sv \
    $PROJECT_ROOT/rtl/include/lob_pkg.sv \
    $PROJECT_ROOT/rtl/include/ouch_pkg.sv \
    $PROJECT_ROOT/rtl/ingress/moldudp64_depacketizer.sv \
    $PROJECT_ROOT/rtl/parser/itch_parser_fsm.sv \
    $PROJECT_ROOT/rtl/parser/speculative_itch_parser.sv \
    $PROJECT_ROOT/rtl/ingress/ingress_pipeline_top.sv \
    $PROJECT_ROOT/rtl/book/top_of_book_cache.sv \
    $PROJECT_ROOT/rtl/book/order_store.sv \
    $PROJECT_ROOT/rtl/book/depth_book.sv \
    $PROJECT_ROOT/rtl/book/lob_engine_top.sv \
    $PROJECT_ROOT/rtl/quant/obi_calculator.sv \
    $PROJECT_ROOT/rtl/quant/queue_tracker.sv \
    $PROJECT_ROOT/rtl/quant/quant_engine_top.sv \
    $PROJECT_ROOT/rtl/risk/pre_trade_risk.sv \
    $PROJECT_ROOT/rtl/risk/pnl_circuit_breaker.sv \
    $PROJECT_ROOT/rtl/egress/ouch_order_gen.sv \
    $PROJECT_ROOT/rtl/quant/obi_signal.sv \
    $PROJECT_ROOT/rtl/risk/risk_ouch_top.sv \
    $PROJECT_ROOT/rtl/metrology/ptp_timer_96b.sv \
    $PROJECT_ROOT/rtl/metrology/axis_eth_fcs_checker.sv \
    $PROJECT_ROOT/rtl/metrology/latency_metrology.sv \
    $PROJECT_ROOT/rtl/top/aura_hft_top.sv \
]

# Set Include Directories
set_property include_dirs [list \
    $PROJECT_ROOT/rtl/include \
    $PROJECT_ROOT/rtl/ingress \
    $PROJECT_ROOT/rtl/parser \
    $PROJECT_ROOT/rtl/metrology \
    $PROJECT_ROOT/rtl/book \
    $PROJECT_ROOT/rtl/quant \
    $PROJECT_ROOT/rtl/risk \
    $PROJECT_ROOT/rtl/egress \
    $PROJECT_ROOT/rtl/top \
] [current_fileset]

# 2. Read Timing & Physical Constraints
read_xdc $PROJECT_ROOT/constraints/kria_kr260.xdc

# 3. Run Out-of-Context Synthesis
puts "--- Running Synthesis (synth_design) ---"
synth_design -top aura_hft_top -part xck26-sfvc784-2LV-c -mode out_of_context -retiming

# 4. Run Optimization & Implementation
puts "--- Running Logic Optimization (opt_design) ---"
opt_design

puts "--- Running Placement (place_design) ---"
place_design

puts "--- Running Physical Optimization (phys_opt_design) ---"
phys_opt_design

puts "--- Running Routing (route_design) ---"
route_design

# 5. Generate Comprehensive Quality of Results (QoR) Reports
puts "--- Generating Reports ---"
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -input_pins -routable_nets -file $OUTPUT_DIR/timing_summary.rpt
report_utilization -hierarchical -file $OUTPUT_DIR/utilization_hierarchical.rpt
report_utilization -file $OUTPUT_DIR/utilization_summary.rpt
report_power -file $OUTPUT_DIR/power_summary.rpt
report_drc -file $OUTPUT_DIR/drc_summary.rpt

# 6. Check Worst Negative Slack (WNS)
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
puts "=================================================================="
puts "  Synthesis & Implementation Completed!"
puts "  Worst Negative Slack (WNS): $wns ns"
if { $wns >= 0.0 } {
    puts "  >>> TIMING MET: Positive Slack Achieved at 156.25 MHz! <<<"
} else {
    puts "  >>> WARNING: Timing Violation Detected! <<<"
}
puts "  Reports saved to: $OUTPUT_DIR"
puts "=================================================================="
