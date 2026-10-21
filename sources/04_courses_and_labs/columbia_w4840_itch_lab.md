# Courses & Labs: Columbia University CSEE W4840

## 1. Course context
* **University:** Columbia University (Department of Computer Science & Electrical Engineering)
* **Course:** CSEE W4840 - Embedded System Design
* **Instructor:** Stephen A. Edwards
* **Course and projects page:** http://www.cs.columbia.edu/~sedwards/classes/

## 2. Reference project: "FPGA NASDAQ ITCH Market Data Feed Handler & Order Book"
Several cohorts of advanced students have designed and publicly documented live market data processors on FPGA.

### Typical architecture implemented in the lab:
```
+------------------+      +-------------------+      +--------------------+
|  1GbE/10GbE PHY  | ---> | Packet Parser FSM | ---> | Order Book Engine  |
|  (RGMII / XGMII) |      | (MoldUDP64 + ITCH)|      | (BRAM Dual-Port)   |
+------------------+      +-------------------+      +--------------------+
                                                        |
                                                        v
                                             +--------------------+
                                             | Video / HDMI Out / |
                                             | PCIe Host Telemetry|
                                             +--------------------+
```

### Key lessons from the lab:
1. **Real-time constraints:**
   * Process a continuous stream without excessive buffering: if the order book cannot process an order at the arrival rate, the FIFOs overflow (*FIFO overrun*).
2. **BRAM address space management:**
   * Concrete examples of dual-port BRAM arbitration that allow reading the best bid/offer while simultaneously writing an update from an order cancel.
3. **Software / hardware partitioning:**
   * The critical path (network decapsulation, ITCH decoding, BBO update) runs 100% in hardwired logic (hardware fabric).
   * Administrative and slow tasks (configuring symbol filters, graphical display, slow statistics) are delegated to an embedded processor (ARM Cortex or a RISC-V/MicroBlaze softcore).
