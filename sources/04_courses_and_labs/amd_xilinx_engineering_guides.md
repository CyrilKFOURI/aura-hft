# Vendor Manuals & Guides: AMD / Xilinx FinTech

This document lists the official design guides needed for timing closure, HLS acceleration and hardware architecture on AMD/Xilinx UltraScale+ FPGAs.

---

## 1. UG1399: Vitis High-Level Synthesis User Guide
* **Publisher:** AMD (Xilinx)
* **Main topics:**
  * Optimization directives for financial computing:
    * `#pragma HLS pipeline II=1`: Ensures one loop iteration or one price sample is ingested every clock cycle.
    * `#pragma HLS array_partition variable=... complete`: Partitions arrays into individual registers to eliminate multi-port read/write memory access conflicts.
    * `#pragma HLS dataflow`: Enables concurrent pipelined execution of sequential C++ functions through ping-pong buffers in BRAM.

---

## 2. UG901: Vivado Design Suite User Guide - Synthesis
* **Publisher:** AMD (Xilinx)
* **Main topics:**
  * Clean hardware inference: how to write SystemVerilog that automatically infers synchronous dual-port block RAMs (`RAMB36E2`), DSP48E2 blocks or UltraRAM memories (`URAM288`).
  * Optimal finite state machine (FSM) coding: one-hot encoding to favor clock speed vs Gray/binary to save flip-flops.

---

## 3. WP401: Developing Low Latency Trading Systems on Xilinx Platforms
* **Publisher:** Xilinx white paper
* **Main topics:**
  * Best practices for tick-to-trade architecture:
    * Avoid long combinational logic chains on wide network data buses (> 64 bits).
    * Clock domain crossing (CDC) between the GTY/GTH serial transceivers and the internal logic.
    * Use UltraRAM on UltraScale+ to store very deep order books without saturating external DDR memory bandwidth.
