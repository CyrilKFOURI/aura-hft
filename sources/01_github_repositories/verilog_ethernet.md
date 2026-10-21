# Verilog-Ethernet & Verilog-AXIS: Network and Streaming Components

## 1. General information
* **Repositories:** 
  * `alexforencich/verilog-ethernet` (https://github.com/alexforencich/verilog-ethernet)
  * `alexforencich/verilog-axis` (https://github.com/alexforencich/verilog-axis)
* **Author:** Alex Forencich
* **License:** MIT
* **Languages:** Verilog-2001, Python (Cocotb) testbenches
* **Target architecture:** Vendor independent (AMD/Xilinx, Intel, Lattice, Microchip). 100% synthesizable and simulatable with Icarus Verilog and Verilator.

## 2. Key modules & features

### A. verilog-ethernet
* **Physical MAC cores:**
  * `eth_mac_1g.v` / `eth_mac_10g.v` (64-bit XGMII interface at 156.25 MHz) / `eth_mac_25g.v`
* **Streaming decapsulation / encapsulation:**
  * `ip_complete.v`: Full IPv4 stack with hardware ARP resolution.
  * `udp_complete.v`: UDP stack with port filtering, checksum computation/verification and on-the-fly encapsulation on an AXI-Stream bus.
* **CRC32 / FCS generation and verification:**
  * Ethernet CRC computed in 1 cycle on 64/128/512-bit buses.

### B. verilog-axis
* **Asynchronous and synchronous FIFOs:**
  * `axis_fifo.v`: AXI-Stream FIFO with careful `tready`/`tvalid`/`tlast` handling, no loss and no deadlock.
  * `axis_async_fifo.v`: Safe clock domain crossing (CDC) (e.g. from the MAC network clock 156.25/322.26 MHz to the internal compute clock 250/400 MHz).
* **Mux / demux & arbiters:**
  * `axis_arb_mux.v`: Round-robin or strict-priority arbitration to steer several streams into a single Ethernet transmitter.
* **Bus width converters:**
  * `axis_adapter.v`: Transparent bus conversion (e.g. 64-bit to 128-bit or 512-bit to 64-bit), needed to match packets to the word widths of compute blocks.

## 3. Relevance for the HFT project
In a tick-to-trade system, latency suffers if the software network stack is involved. `verilog-ethernet` and `verilog-axis` provide the basic building blocks to:
1. Extract the UDP payload (carrying the MoldUDP64/ITCH quote streams) directly at the Ethernet PHY output in a few clock cycles.
2. Build Ethernet/IP/UDP or TCP frames in the transmit direction to send OUCH orders without ever leaving the hardware domain.
3. Separate the optical transceiver clock (e.g. 156.25 MHz for 10GbE) from the order book engine clock (which can run faster, e.g. 250 MHz or 322 MHz on UltraScale+).

## 4. Clone commands
```bash
git clone https://github.com/alexforencich/verilog-ethernet.git
git clone https://github.com/alexforencich/verilog-axis.git
```
