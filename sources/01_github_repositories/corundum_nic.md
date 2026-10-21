# Corundum: Open-Source 100-Gbps FPGA NIC Platform

## 1. General information
* **Repository:** `corundum/corundum`
* **GitHub URL:** https://github.com/corundum/corundum
* **Author / organization:** Alex Forencich, Alex C. Snoeren, George Porter, George Papen (University of California San Diego - UCSD)
* **License:** MIT / BSD 2-Clause
* **Hardware languages:** Verilog, SystemVerilog
* **Simulation environment:** Python, Cocotb, MyHDL / Icarus Verilog / Verilator

## 2. Target architectures & boards
* **AMD / Xilinx UltraScale & UltraScale+:**
  * AMD Alveo U50, U200, U250, U280
  * Xilinx VCU108, VCU118, VCU1525, KCU105
  * BittWare XUP-P3R, 250-SoC
* **Intel:**
  * Intel Stratix 10 MX / DX (e.g. Intel PAC D5005)

## 3. Hardware architecture & key modules
Corundum is a high-performance, modular network interface card (NIC) platform designed for 10G, 25G and 100G. It is a natural host for placing an order book or a hardware trading strategy between the MAC layer and the PCIe host bus.

```
       +-------------------------------------------------------------+
       |                         Corundum NIC                        |
       |                                                             |
QSFP   |  +------------+   AXI-S   +-----------------+   AXI-S       | PCIe
-----> |  | Ethernet   | --------> |  User App Space | --------+     | ====>
(100G) |  | 100G MAC   |           | (HFT Pipeline)  |         |     | Host
<----- |  | (CMAC/XGEM)| <-------- | (ITCH/LOB/OUCH) | <-----+ |     | (DMA)
       |  +------------+   AXI-S   +-----------------+       | |     |
       |                                                     v v     |
       |           +---------------------------------------------+   |
       |           |     Scatter-Gather DMA & Queue Manager      |   |
       |           +---------------------------------------------+   |
       +-------------------------------------------------------------+
```

* **MAC subsystem:** Supports XGMII (10GbE), 25GMII (25GbE) and CMAC AXI-Stream (100GbE).
* **High-performance PCIe DMA engine:**
  * PCIe Gen 3 x16 or PCIe Gen 4 x8/x16 host interface.
  * Highly parallel scatter-gather DMA.
  * Hardware management of more than 10,000 queues (transmit, receive, completion, event queues) stored in BRAM/URAM.
* **PTP IEEE 1588 time synchronization:**
  * PTP hardware clock with sub-nanosecond resolution, integrated at the MAC layer.
  * Hardware timestamping of RX and TX packets (essential for measuring physical tick-to-trade).
* **Integrated Linux driver:**
  * Native kernel driver supporting high-rate streaming and MSI-X interrupts.

## 4. Relevance for the FPGA HFT project
1. **No reinventing the wheel:** Provides the complex and tedious infrastructure (PCIe Gen3/Gen4, DMA, 10G/100G PHY/MAC, PTP).
2. **User injection zone (bump-in-the-wire):** An ITCH parsing module and an order book can be inserted directly on a standard 64, 128 or 512-bit AXI-Stream interface.
3. **Dual data path:** The FPGA can inspect the stream and trigger an OUCH order directly on the outgoing Ethernet port (sub-microsecond latency), while log metadata is transferred to host memory over DMA in the background without blocking the critical path.

## 5. Clone commands and getting started
```bash
git clone --recursive https://github.com/corundum/corundum.git
cd corundum
# To explore the Alveo designs:
ls fpga/mqnic/AU50/
ls fpga/mqnic/AU280/
```
