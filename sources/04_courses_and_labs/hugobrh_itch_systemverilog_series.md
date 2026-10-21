# Practical Engineering Guide: Hugo Brosse Series (BRH Engineering)

## 1. Overview
* **Author:** Hugo Brosse (embedded systems & FPGA engineer)
* **Blog URL:** https://hugobrh.dev
* **Series:** *Building an FPGA High-Frequency Trading Order Book in SystemVerilog*

## 2. Methodological breakdown of the articles & code

### Article 1: The MoldUDP64 Parser
* **Goal:** Decode the MoldUDP64 transport protocol used by NASDAQ.
* **Key concepts:**
  * Packet structure: Session ID (10 bytes), Sequence Number (8 bytes), Message Count (2 bytes), followed by message blocks each preceded by a 2-byte length field.
  * Reception on an AXI4-Stream interface with a 64-bit data bus.
  * Header-stripping state machine that does not break the data flow.

### Article 2: The NASDAQ ITCH 5.0 Parser
* **Goal:** Turn the raw byte stream into typed order structures in SystemVerilog.
* **Key concepts:**
  * Misalignment handling: extracting a message that starts on an arbitrary byte within the 64-bit word.
  * Endianness extraction and swap (network byte order to little endian / native internal format).
  * Deterministic-cycle FSM.

### Article 3: Verification with Cocotb and Real Market Data
* **Goal:** Set up a modern testbench based on Python coroutines.
* **Tools:** `cocotb`, `cocotbext-eth`, `scapy`, `verilator`.
* **Methodology:**
  * Read a standard `.pcap` network capture of a real market session.
  * Inject it packet by packet into the RTL simulator.
  * A Python reference model maintains its own book to validate every simulation cycle.

### Article 4: Order Tracking in BRAM
* **Goal:** Solve the memory footprint problem for order indexing.
* **Constraint:** The `order_reference_number` is 64 bits wide. $2^{64}$ BRAM entries cannot be allocated.
* **Solution:** A hardware hash function maps the 64 bits onto 17 bits (131,072 BRAM addresses), with hardware collision handling by chaining or direct probing.

### Article 5: Price Ladder & Integration
* **Goal:** Assemble the full pipeline up to the best bid / offer (BBO) computation and expose it over an AXI-Lite bus for software readout.
