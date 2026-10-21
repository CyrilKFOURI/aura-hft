# AMD / Xilinx OpenNIC: 100GbE FPGA SmartNIC Platform

## 1. General information
* **Repository:** `Xilinx/open-nic`
* **GitHub URL:** https://github.com/Xilinx/open-nic
* **Author / organization:** AMD (Xilinx Adaptive and Embedded Computing Group)
* **License:** Apache 2.0
* **Languages:** SystemVerilog, C/C++ (Linux drivers and host tools), Vivado Tcl scripts
* **Target architectures:**
  * AMD Alveo U50, U200, U250, U280

## 2. Architecture & key features
OpenNIC provides a ready-to-use 100GbE hardware infrastructure with a modular structure that separates the "Shell" (fixed infrastructure) from the user application "Box":

```
             +-------------------------------------------------------------+
             |                         AMD OpenNIC                         |
             |                                                             |
100GbE QSFP  |  +------------+             +-----------------+             | PCIe Gen3/Gen4
-----------> |  | CMAC 100G  | --AXI-S---> | User Logic Box  | --AXI-S---> | QDMA Subsystem
             |  | Subsystem  |             | (Custom HFT /   |             | (Host Memory)
<----------- |  |            | <--AXI-S--- |  Trading Engine)| <--AXI-S--- |
             |  +------------+             +-----------------+             |
             +-------------------------------------------------------------+
```

* **100G network subsystem (CMAC):**
  * Implements the UltraScale+ 100G Ethernet MAC controller.
  * 512-bit AXI4-Stream bus clocked at 322.265 MHz ($512 \times 322.265\text{ MHz} \approx 165\text{ Gbps}$ raw internal bandwidth).
* **PCIe QDMA engine (queue-based DMA):**
  * Supports up to 2048 virtual queues.
  * Direct zero-copy transfers between the card and host memory.
* **User application box (`box_250mhz` or `box_322mhz`):**
  * Standard slot reserved for user code.
  * Receives raw Ethernet frames directly over AXI-Stream.
  * Can modify frames, inject new ones, or route them to the CPU with no overhead.

## 3. Relevance for the HFT project
1. **Deployment on Alveo cards:** The most direct and reliable way to deploy physical HFT logic on industrial cards such as the Alveo U50 (a compact card popular in trading).
2. **DPDK support:** OpenNIC includes an official DPDK PMD (poll mode driver), letting a C++ software application talk to the FPGA with sub-microsecond latency.
3. **Dual RX/TX pipeline:** The logic can be programmed to send a buy/sell order directly on the 100G port as soon as a tick is received, while sending a report to the host CPU through QDMA.

## 4. Cloning and building
```bash
git clone --recursive https://github.com/Xilinx/open-nic.git
cd open-nic
# Generate the Vivado project for Alveo U50:
./build.sh -t au50
```
