# TRD — AURA-HFT (Technical Requirements Document)

> **Status:** v1.0, technical architecture and engineering specifications.

---

## Stack

### 1. Hardware RTL and hardware design
* **Description language:** synthesizable, portable SystemVerilog (IEEE 1800-2012 / 2017).
* **Hardware target:** AMD Kria KR260 Robotics Starter Kit (AMD Zynq UltraScale+ SoC `xck26-sfvc784-2LV-c`).
* **Core clock frequency:** $156.25\text{ MHz}$ (native 10GbE MAC / PHY 64-bit AXI-Stream clock, period $T = 6.4\text{ ns}$).
* **Synthesis and timing tool:** AMD Vivado ML Standard (Linux / WSL2), `.xdc` constraints.
* **Key target resources:** CLB LUT6, flip-flops, dual-port block RAM (RAMB36E2), DSP48E2 slices.

### 2. Simulation, verification and reference model
* **RTL simulator:** Verilator (v5+), very fast cycle-accurate C++ compilation.
* **Testbench:** Cocotb (Python 3.11+) with the `cocotbext-axi` and `scapy` extensions.
* **Golden model:** pure-Python L2/L3 order book engine used as the cycle-by-cycle reference (scoreboard).
* **Waveform format:** VCD / FST (viewed with GTKWave).

### 3. Web application and telemetry
* **Backend:** Python 3.11+ with **FastAPI** and **Uvicorn**, running Verilator as a subprocess.
* **Run and telemetry storage:** **SQLite** (WAL mode) or **DuckDB** for tick/latency time series.
* **Frontend:** **React 18** + **Vite** + **TypeScript** + **Tailwind CSS**.
* **Charts:** Chart.js / Recharts (latency, OBI curves) + a virtualized table for the order book (price ladder).

---

## Architecture

### 1. FPGA hardware pipeline (datapath ingress → egress)
```
[RX Transceiver 10G SFP+] 
          │ (156.25 MHz / AXI4-Stream 64-bit)
          ▼
┌────────────────────────────────────────────────────────┐
│ 1. Ingress Network Depacketizer                        │
│    - Stripping Ethernet II (14B) + IPv4 (20B) + UDP(8B) │
│    - MoldUDP64 Session Header Parser (20B)             │
│    - Sequence gap detector (Gap Detection)             │
└─────────────────────────┬──────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────┐
│ 2. Streaming Cut-Through ITCH 5.0 Parser               │
│    - Combinational barrel shifter (byte alignment)     │
│    - FSM decoding of messages 'A', 'F', 'E', 'C', 'X', │
│      'D', 'U'                                          │
│    - Immediate endianness swap                         │
└─────────────────────────┬──────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────┐
│ 3. Hardware Limit Order Book (LOB) Engine              │
│    - 64-bit -> 17-bit hash table in dual-port BRAM     │
│    - Fixed-Tick Price Ladder (volume aggregation)      │
│    - Top-of-Book cache (Top 5 bid / ask levels)        │
│    - Constant-time O(1) BBO registers                  │
└────────────┬─────────────────────────────┬─────────────┘
             ▼                             ▼
┌───────────────────────────┐ ┌──────────────────────────┐
│ 4. Queue Position Tracker │ │ 5. DSP Fixed-Point Engine│
│    - Passive volume ahead │ │    - OBI computation     │
│      of test orders       │ │    - Micro-Price         │
│    - Depletion detection  │ └────────────┬─────────────┘
└────────────┬──────────────┘              │
             └──────────────┬──────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│ 6. Strategy Trigger & Pre-Trade Risk Checks            │
│    - Conditional OBI threshold                         │
│    - Max Order Size Check                              │
│    - Price Collar vs BBO Check                         │
│    - Max Notional Exposure Check                       │
│    - Hard Kill Switch                                  │
└─────────────────────────┬──────────────────────────────┘
                          ▼
┌────────────────────────────────────────────────────────┐
│ 7. Egress OUCH 5.0 Generator                           │
│    - Binary formatting of Enter Order ('O')            │
│    - UDP / MAC encapsulation                           │
│    - Cycle-accurate latency measurement (Timestamp)    │
└─────────────────────────┬──────────────────────────────┘
                          ▼
              [TX Transceiver 10G SFP+]
```

### 2. Host system and dashboard architecture
```
┌────────────────────────────────────────────────────────┐
│ Web Frontend (React / TypeScript / Vite / Tailwind)    │
│ - Run configuration (Symbol, OBI thresholds, Risk)     │
│ - Dynamic L2 order book viewer                         │
│ - OBI signal & Micro-Price curve                       │
│ - Queue position gauge (Queue Position Tracker)        │
│ - Blotter of emitted / rejected orders                 │
│ - Latency distribution histogram (p50, p99)            │
└─────────────────────────▲──────────────────────────────┘
                          │ (HTTP REST + WebSocket)
┌─────────────────────────▼──────────────────────────────┐
│ Backend API (FastAPI / Python)                         │
│ - Simulation orchestrator (Verilator subprocess)       │
│ - JSONL / CSV telemetry log parser                     │
│ - Local run database (SQLite)                          │
│ - Step-by-step replay API (Play / Pause / Scrub / 1x-10x)│
└─────────────────────────▲──────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────┐
│ C++ Simulation Engine (Verilator + Harness)            │
│ - Injection of real ITCH traces (.pcap / .bin)         │
│ - Cycle-by-cycle telemetry dump to disk                │
└────────────────────────────────────────────────────────┘
```

---

## External services / APIs

* **Input data:** binary capture files of official NASDAQ TotalView-ITCH 5.0 market data (`.bin` format or `.pcap` extracts).
* **Emulated network protocols:**
  * Ingress: MoldUDP64 over UDP multicast.
  * Egress: OUCH 5.0 over UDP (test mode / emulated exchange).
* **External dependencies:** no paid API or cloud service required; the whole system runs locally and offline.

---

## Security and auth

* **Security context:** local / simulation research project.
* **Secrets management:** no banking secret or production credential. A `.env` file holds the local server port configuration (API port 8000, Vite port 5173).
* **Hardware kill switch:** safety register wired in RTL. As soon as the host or the system sets the `kill_switch_enable` bit to 1, any physical order transmission is masked on the next clock cycle ($< 6.4\text{ ns}$).
* **Pre-trade risk assurance:** the hardware risk checks always run in combinational logic, independently of any order coming from the host.

---

## Constraints

1. **Timing constraints:**
   * Target clock period: $T = 6.4\text{ ns}$ ($F = 156.25\text{ MHz}$).
   * Worst Negative Slack (WNS) $\ge 0\text{ ps}$ under Vivado for the AMD UltraScale+ `xck26` device.
2. **Hardware memory constraints:**
   * Respect the K26 BRAM budget ($144\text{ blocks}$ of $36\text{ Kb}$).
   * Hash table sized for at most $128\text{ K}$ entries for active order tracking, keeping the BRAM footprint $< 30\%$ of the FPGA.
3. **Development constraints:**
   * Runs on Windows via WSL2 (Ubuntu 22.04 LTS).
   * Design model: 100% testable end to end in simulation without a physical board.
