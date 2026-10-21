# Sub-25ns NASDAQ ITCH 5.0 FPGA Parser

## 1. General information
* **Repository:** `mbattyani/sub-25-ns-nasdaq-itch-fpga-parser`
* **GitHub URL:** https://github.com/mbattyani/sub-25-ns-nasdaq-itch-fpga-parser
* **Author:** Marc Battyani
* **License:** Open source
* **Hardware language:** Verilog
* **Target architecture:** Xilinx / AMD UltraScale+, Kintex UltraScale, Virtex UltraScale+

## 2. Specifications & performance metrics
* **Decode latency:** **< 25 nanoseconds** (from the first valid frame fragment to the decoded order fields being available).
* **Input interface:** 64-bit / 128-bit AXI4-Stream from the MAC/IP/UDP controller.
* **Output interface:** Decoded order structure in parallel (Order Reference Number, Order Type, Shares, Price, Buy/Sell Indicator, Timestamp).
* **Target frequency:** > 300 MHz on UltraScale+ FPGAs (typically 322.26 MHz to match the 25G/40G network clock, or 156.25 MHz for 10G).

## 3. Internal architecture & pipelining
The core of the challenge in the NASDAQ ITCH protocol is:
1. **Variable byte alignment:** ITCH messages are not aligned on 64-bit or 128-bit word boundaries. A 36-byte message can start in the middle of an AXI-Stream word.
2. **Big-endian format:** Integers and prices must be byte-swapped to match the FPGA's internal arithmetic.
3. **Multiple messages per packet:** A single MoldUDP64 UDP packet often contains 5 to 15 consecutive ITCH messages.

```
AXI-Stream (64-bit) 
       |
       v
+-----------------------------------------------------------+
| Sliding Window Barrel Shifter & Byte Alignment            |
+-----------------------------------------------------------+
       |
       +---> Message Type Detection (Byte 0: 'A', 'E', 'X', 'D')
       |
+-----------------------------------------------------------+
| Pipeline Stage 1: Field Extraction & Endianness Swap      |
| - Order Reference Number (64-bit)                         |
| - Stock Locate / Tracking (16-bit)                        |
| - Shares (32-bit integer)                                 |
| - Price (32-bit fixed point, 4 decimals)                  |
| - Buy/Sell Indicator (1-bit)                              |
+-----------------------------------------------------------+
       |
       v
Validated order fields passed to the Order Book (LOB) engine
```

## 4. Key points to study in the code
* The clever use of a combinational *barrel shifter* coupled with a compact one- or two-state finite state machine (FSM) to avoid inserting unnecessary latency cycles.
* How the AXI-Stream `tready` signal is driven without introducing a stall on the critical network path.

## 5. Cloning
```bash
git clone https://github.com/mbattyani/sub-25-ns-nasdaq-itch-fpga-parser.git
```
