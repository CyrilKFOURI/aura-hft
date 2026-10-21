# ==============================================================================
# Xilinx Design Constraints (XDC) - AURA-HFT v4.0
# Target Hardware : AMD Kria KR260 Robotics Starter Kit / K26 SOM
# Target FPGA     : xck26-sfvc784-2LV-c (Zynq UltraScale+ MPSoC)
# Top-Level       : aura_hft_dual_clock_top
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Primary Clock Definitions
# ------------------------------------------------------------------------------
# Network Clock: 156.25 MHz (6.400 ns period, 10GbE / XGMII line rate)
create_clock -period 6.400 -name clk_net -waveform {0.000 3.200} [get_ports clk_net]

# Core Accelerator Clock: 312.50 MHz (3.200 ns period, High-Speed LOB & Arbiter)
create_clock -period 3.200 -name clk_core -waveform {0.000 1.600} [get_ports clk_core]

# ------------------------------------------------------------------------------
# 2. Clock Domain Crossing (CDC) Constraints
# ------------------------------------------------------------------------------
# Declare clk_net and clk_core as asynchronous domains (isolated via Gray-code FIFO)
set_clock_groups -asynchronous \
    -group [get_clocks -include_generated_clocks clk_net] \
    -group [get_clocks -include_generated_clocks clk_core]

# ------------------------------------------------------------------------------
# 3. False Paths on Quasi-Static Configuration & Telemetry
# ------------------------------------------------------------------------------
# AXI4-Lite Control registers updated by host CPU (quasi-static during trading)
set_false_path -from [get_cells -hierarchical -filter {NAME =~ *axi_ctrl* && NAME =~ *reg_control*}]
set_false_path -from [get_cells -hierarchical -filter {NAME =~ *axi_ctrl* && NAME =~ *reg_obi_threshold*}]
set_false_path -from [get_cells -hierarchical -filter {NAME =~ *axi_ctrl* && NAME =~ *reg_risk_*}]
set_false_path -from [get_cells -hierarchical -filter {NAME =~ *axi_ctrl* && NAME =~ *reg_mm_*}]

# Telemetry status registers read by host (slow read-only monitoring)
set_false_path -to [get_cells -hierarchical -filter {NAME =~ *axi_ctrl* && NAME =~ *s_axi_rdata*}]

# ------------------------------------------------------------------------------
# 4. Input / Output Delay Constraints (Board Boundary & Transceivers)
# ------------------------------------------------------------------------------
# Ingress AXI4-Stream (from 10GbE PCS/PMA Subsystem)
set_input_delay -clock [get_clocks clk_net] -max 2.000 [get_ports {s_axis_net_tdata* s_axis_net_tvalid s_axis_net_tlast}]
set_input_delay -clock [get_clocks clk_net] -min 0.500 [get_ports {s_axis_net_tdata* s_axis_net_tvalid s_axis_net_tlast}]

# Egress AXI4-Stream (to 10GbE MAC Subsystem)
set_output_delay -clock [get_clocks clk_net] -max 2.000 [get_ports {m_axis_net_tdata* m_axis_net_tvalid m_axis_net_tlast}]
set_output_delay -clock [get_clocks clk_net] -min 0.500 [get_ports {m_axis_net_tdata* m_axis_net_tvalid m_axis_net_tlast}]
