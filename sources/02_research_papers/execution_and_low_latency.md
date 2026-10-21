# Academic Literature: Execution & Ultra-Low Latency (HFT)

This document reviews the main research papers on hardware architectures for order execution, order book (LOB) maintenance and kernel bypass on FPGA.

---

## 1. "Exploring the Potential of Reconfigurable Platforms for Order Book Update"
* **Authors:** Conghui He, Haohuan Fu, Wayne Luk, Weijia Li, Guangwen Yang
* **Conference:** *27th International Conference on Field Programmable Logic and Applications (FPL 2017)*
* **Web link:** [Imperial College](https://www.doc.ic.ac.uk/~wl/papers/17/fpl17ch.pdf)

### Architectural contributions & technical details:
1. **Pointer-free *fixed-tick* data structure:**
   * In software, an order book typically uses red-black trees or doubly linked lists. On an FPGA, sequential pointer chasing destroys parallelism and causes memory pipeline stalls.
   * The authors design a structure where the price space is indexed at fixed tick steps, turning a complex tree search into a simple direct read of Block RAM (BRAM).
2. **Hardware cache hierarchy for the top of book:**
   * Most trading operations modify the first levels of the book (the 5 best bid and ask prices).
   * The design implements a very fast flip-flop/LUT cache for the top 5 price levels, giving combinational access in 1 clock cycle.
3. **HFOBU algorithm (Hardware-Friendly Order Book Update):**
   * Throughput achieved: **1.2 to 1.5 million messages per second** at 10 Gb/s.
   * Guaranteed deterministic latency: between **132 and 288 nanoseconds**.

---

## 2. "Corundum: An Open-Source 100-Gbps NIC"
* **Authors:** Alex Forencich, Alex C. Snoeren, George Porter, George Papen
* **Conference:** *28th IEEE International Symposium on Field-Programmable Custom Computing Machines (FCCM 2020)*
* **Web link:** [UCSD Computer Science](https://www.cse.ucsd.edu/~snoeren/papers/corundum-fccm20.pdf)

### Architectural contributions & technical details:
1. **Modular 100G streaming datapath architecture:**
   * 512-bit AXI-Stream internal datapath at 250/322 MHz, able to ingest and process network frames at line rate with no packet loss.
2. **Scatter-gather DMA engine & queue manager:**
   * Highly optimized PCIe DMA engine that avoids software locks.
   * Can store more than 10,000 hardware queues directly in UltraRAM/BRAM, allowing dedicated queues per trading strategy without a bottleneck.
3. **Sub-nanosecond PTP clock synchronization:**
   * Integrates a hardware PTP IEEE 1588 timestamping core at the MAC/PCS layer, essential for audit and regulatory compliance (MiFID II RTS 25).

---

## 3. "A Low-Latency Library in FPGA Hardware for High-Frequency Trading (HFT)"
* **Authors:** John W. Lockwood, Amit Gupte, Neeraj Mehta, Michaela Blott, Tom English, Kees Vissers
* **Conference / workshop:** *IEEE International Workshop on High Performance Computational Finance (WHPCF / Algo-Logic & Xilinx)*
* **References:** Algo-Logic Systems white paper & IEEE Xplore

### Architectural contributions & technical details:
1. **Fully integrated on-silicon tick-to-trade pipeline:**
   * The authors show that by eliminating any hand-off to the host operating system, overall tick-to-trade latency drops from about $10\text{ }\mu\text{s}$ (optimized C++/Solarflare software) to **under $1\text{ }\mu\text{s}$** (about 600 to 900 ns on FPGA).
2. **Pre-trade risk check module:**
   * Instant parallel hardware verification of compliance rules (maximum order size, cumulative notional exposure, price limits relative to a reference price) before the OUCH packet is allowed out to the exchange gateway.

---

## 4. "Plato: An Architecture for Processing Financial Data Streams on FPGAs"
* **Authors:** Mohammad Sadoghi, H. Javed, N. Tarafdar, P. Singh, R. Singh, Hans-Arno Jacobsen
* **Journal / conference:** *IEEE Transactions on Knowledge and Data Engineering (TKDE) / IEEE FCCM*

### Architectural contributions & technical details:
1. **On-the-fly composite query evaluation engine:**
   * Reconfigurable architecture specialized in evaluating trees of complex Boolean and arithmetic predicates over real-time financial streams.
2. **Massively parallel market filters:**
   * Can monitor thousands of financial instruments at once by deploying dedicated filter units across the FPGA fabric, with a constant response time independent of the number of instruments monitored.
