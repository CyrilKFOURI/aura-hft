# Additional Repositories: FIPO & NASDAQ-ITCH-Processor

## 1. FIPO repository (FPGA ITCH Parser & Order Book)
* **GitHub URL:** https://github.com/wk101/FIPO
* **Author:** wk101
* **Languages:** SystemVerilog / Verilog, Python (testbenches)
* **Key points:**
  * Modular architecture that explicitly separates the ITCH decoder block from the order book (LOB) manager.
  * BRAM-based data structure using a direct lookup table for stock symbols and a simplified price-limit tree.
  * Good reference for a clear academic implementation of a hardware order book's internal data structure.

## 2. NASDAQ-ITCH5.0-Market-Data-Processor
* **GitHub URL:** https://github.com/HIMANK729/NASDAQ-ITCH5.0-Market-Data-Processor
* **Author:** Himank
* **Languages:** Verilog, C++ / Verilator testbenches
* **Key points:**
  * Complete hardware pipeline: Ethernet MAC packet ingestion -> IPv4/UDP decapsulation -> MoldUDP64 demultiplexing -> ITCH 5.0 decoding.
  * Continuous real-time computation of top-of-book / best bid and offer (BBO).
  * Provides cycle-by-cycle latency metrics and testbenches that inject both synthetic and real network frames.

## 3. Clone commands
```bash
git clone https://github.com/wk101/FIPO.git
git clone https://github.com/HIMANK729/NASDAQ-ITCH5.0-Market-Data-Processor.git
```
