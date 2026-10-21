# FPGA NASDAQ ITCH 5.0 Order Book (Hugo Brosse / BRH Engineering)

## 1. General information
* **Author / blog:** Hugo Brosse (BRH Engineering)
* **Related technical blog:** https://hugobrh.dev
* **Hardware language:** SystemVerilog (IEEE 1800-2012 / 2017)
* **Test & verification environment:** Python, **Cocotb**, **Verilator**, Icarus Verilog
* **Test data:** Real market capture files (`.pcap`) and raw NASDAQ TotalView ITCH market streams

## 2. Modular breakdown of the project
This project is both a teaching and an industry-grade reference for building a complete tick-to-trade pipeline from scratch:

```
                  +----------------------------------------------+
Raw Ethernet      | Part 1: MoldUDP64 Parser (AXI-Stream)        |
Packet (.pcap) -> | - UDP decapsulation & payload extraction     |
                  +----------------------------------------------+
                                         |
                                         v
                  +----------------------------------------------+
                  | Part 2: ITCH 5.0 FSM Parser                  |
                  | - Decodes messages A, E, C, X, D, P          |
                  +----------------------------------------------+
                                         |
                                         v
                  +----------------------------------------------+
                  | Part 3: Order Tracking & Hashing (BRAM)      |
                  | - OrderRef compression 64-bit -> 17-bit BRAM |
                  | - Collision handling & hash table            |
                  +----------------------------------------------+
                                         |
                                         v
                  +----------------------------------------------+
                  | Part 4 & 5: Price Ladder & AXI-Lite Engine   |
                  | - L2 Bid/Ask price levels                    |
                  | - Best Bid and Offer (BBO) computation       |
                  | - Book exposed through AXI-Lite registers    |
                  +----------------------------------------------+
```

### Major components:
1. **MoldUDP64 parser:**
   * Strips the NASDAQ network wrapper that guarantees ordered delivery of UDP packets.
   * Handles packet sequence gaps and extracts variable-size message blocks.
2. **ITCH 5.0 FSM parser:**
   * Pipelined state machine that decodes cycle by cycle without stalling the AXI-Stream input.
   * Extracts the key message types:
     * `'A'`: Add Order (displayed order with Order Reference Number, Buy/Sell, Shares, Price).
     * `'E'`: Order Executed (partial or full execution of an existing order).
     * `'C'`: Order Executed with Price.
     * `'X'`: Order Cancel (partial cancellation of volume).
     * `'D'`: Order Delete (full removal of the order).
3. **BRAM hash table (solving the memory bottleneck):**
   * *Problem:* NASDAQ assigns 64-bit `order_reference_number` values ($2^{64}$ possible values), which cannot be indexed directly in FPGA BRAM.
   * *Hardware solution:* A compact hardware hash function (e.g. multiplicative hash or polynomial CRC) maps the 64 bits onto a 17-bit BRAM address ($128\text{ K}$ entries), with auxiliary memory for collision resolution.
4. **Price ladder & Best Bid/Offer (BBO):**
   * Maintains aggregate volumes per price level.
   * Instantly updates `best_bid_price`, `best_bid_qty`, `best_ask_price`, `best_ask_qty` and `spread`.

## 3. Verification strategy with Cocotb
* Instead of writing tedious, rigid Verilog testbenches, the project uses **Cocotb** (Python coroutine-based testbench).
* A reference order book model is written in Python.
* Packets captured on a real exchange network are injected into the RTL model emulated under Verilator.
* On every clock cycle, a scoreboard checks that the internal BRAM state and the hardware BBO outputs are strictly identical to those of the software model.

## 4. Relevance as a starting point
This repository and its article series form the most complete engineering guide for building a Level 1 and Level 2 project that can be fully simulated on a PC, without owning a physical FPGA board costing 10,000 EUR.
