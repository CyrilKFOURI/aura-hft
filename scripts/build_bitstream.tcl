# ==============================================================================
# Vivado Automated Bitstream Generation & Implementation Script (AURA-HFT v4.0)
# Target Hardware : AMD Kria KR260 / K26 SOM
# Target Device   : xck26-sfvc784-2LV-c
# Top Module      : aura_hft_top
# Usage           : vivado -mode batch -source scripts/build_bitstream.tcl
# ==============================================================================

set PROJECT_ROOT [file normalize [file dirname [info script]]/..]
set OUTPUT_DIR   [file normalize $PROJECT_ROOT/reports/impl]
file mkdir $OUTPUT_DIR

puts "=================================================================="
puts "  AURA-HFT v4.0: Complete Bitstream & Implementation Pipeline"
puts "  Target SOM  : AMD Kria KR260 (xck26-sfvc784-2LV-c)"
puts "  Top Module  : aura_hft_top"
puts "=================================================================="

# 1. Read SystemVerilog RTL Sources
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
    $PROJECT_ROOT/rtl/control/axi_lite_control_registers.sv \
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
    $PROJECT_ROOT/rtl/control \
    $PROJECT_ROOT/rtl/book \
    $PROJECT_ROOT/rtl/quant \
    $PROJECT_ROOT/rtl/risk \
    $PROJECT_ROOT/rtl/egress \
] [current_fileset]

# 2. Read Physical and Timing Constraints
read_xdc $PROJECT_ROOT/constraints/kria_kr260.xdc

# 3. Out-Of-Context Synthesis for Top Module
puts "\n--> Running RTL Synthesis (synth_design)..."
synth_design -top aura_hft_top -part xck26-sfvc784-2LV-c -mode out_of_context

# 4. Optimization & Physical Implementation
puts "\n--> Running Logic Optimization (opt_design)..."
opt_design -directive Explore

puts "\n--> Running Placement (place_design)..."
place_design -directive Explore

puts "\n--> Running Physical Optimization (phys_opt_design)..."
phys_opt_design -directive AggressiveExplore

puts "\n--> Running Routing (route_design)..."
route_design -directive Explore

# 5. Timing Closure & Resource Verification Reports
puts "\n--> Generating Implementation Reports..."
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -nworst 3 -file $OUTPUT_DIR/timing_summary.rpt
report_utilization -file $OUTPUT_DIR/utilization_summary.rpt
report_clock_interaction -delay_type min_max -file $OUTPUT_DIR/clock_interaction.rpt
report_cdc -details -file $OUTPUT_DIR/cdc_report.rpt

# 6. Save Checkpoint, Bitstream & Hardware Export
puts "\n--> Writing Design Checkpoint & Bitstream..."
write_checkpoint -force $OUTPUT_DIR/post_route.dcp
write_bitstream -force $OUTPUT_DIR/aura_hft_top.bit
write_hw_platform -fixed -force $OUTPUT_DIR/aura_hft_top.xsa

puts "\n=================================================================="
puts "  AURA-HFT v4.0: Bitstream Generation Completed Successfully!"
puts "  Output files stored in: $OUTPUT_DIR"
puts "=================================================================="
