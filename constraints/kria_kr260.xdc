# ==============================================================================
# AMD Kria KR260 Robotics Starter Kit Constraints (AURA-HFT)
# Target Device: xck26-sfvc784-2LV-c
# Design: aura_hft_top
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Primary Network & Core Clock Definition (156.25 MHz / 6.400 ns period)
# ------------------------------------------------------------------------------
create_clock -period 6.400 -name clk_156mhz -waveform {0.000 3.200} [get_ports clk]

# Clock Uncertainty / Jitter specification
set_clock_uncertainty -setup 0.200 [get_clocks clk_156mhz]
set_clock_uncertainty -hold 0.100 [get_clocks clk_156mhz]

# ------------------------------------------------------------------------------
# 2. Asynchronous / False Paths
# ------------------------------------------------------------------------------
# Reset path is asynchronously asserted, synchronously de-asserted
set_false_path -from [get_ports rst_n] -to [all_registers]

# Configuration registers set by slow host/AXI-Lite interface
set_false_path -from [get_ports cfg_*] -to [all_registers]
set_false_path -from [get_ports host_intent_*] -to [all_registers]

# ------------------------------------------------------------------------------
# 3. I/O Timing Constraints for 64-bit Ingress & Egress AXI4-Stream
# ------------------------------------------------------------------------------
set_input_delay -clock clk_156mhz -max 2.000 [get_ports {s_axis_tdata[*] s_axis_tkeep[*] s_axis_tvalid s_axis_tlast}]
set_input_delay -clock clk_156mhz -min 0.500 [get_ports {s_axis_tdata[*] s_axis_tkeep[*] s_axis_tvalid s_axis_tlast}]

set_output_delay -clock clk_156mhz -max 2.000 [get_ports s_axis_tready]
set_output_delay -clock clk_156mhz -min 0.500 [get_ports s_axis_tready]

set_output_delay -clock clk_156mhz -max 2.000 [get_ports {m_axis_tdata[*] m_axis_tkeep[*] m_axis_tvalid m_axis_tlast}]
set_output_delay -clock clk_156mhz -min 0.500 [get_ports {m_axis_tdata[*] m_axis_tkeep[*] m_axis_tvalid m_axis_tlast}]

set_input_delay -clock clk_156mhz -max 2.000 [get_ports m_axis_tready]
set_input_delay -clock clk_156mhz -min 0.500 [get_ports m_axis_tready]

# ------------------------------------------------------------------------------
# 4. Physical Synthesis & Implementation Directives
# ------------------------------------------------------------------------------
# RAM and DSP Placement Optimizations
set_property BLOCK_SYNTH.RETIMING 1 [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ ADVANCED.RAM.*}]
