# PRD — AURA-HFT

> **Status:** v0.2, scoping complete, pending validation.
> **Legend:** ✅ decided · ❓ to be settled · → TRD: technical decision deferred to the TRD.

---

## Problem

**Market context.** On an electronic order-book market, the value of a piece of information (an order added, cancelled, executed) decays within microseconds. A conventional software stack reacts in 15–50 µs, a C++ kernel-bypass stack in ~1–2 µs; a cut-through FPGA pipeline reacts in tens of nanoseconds, deterministically (no OS, no cache misses).

**State of open-source work.** Public projects cover **fragments**: an ITCH parser here, an order book there, a NIC somewhere else. What is missing is a project that is all of:
1. **end to end**: from the incoming market packet to the outgoing order;
2. **grounded in microstructure**: a signal derived from theory (imbalance, queue dynamics), not an arbitrary threshold;
3. **rigorously verified**: compared against a reference software model on a real trading day;
4. **honestly measured**: latency reported in cycles, with the clock frequency and the measurement scope stated;
5. **observable**: an application that makes visible what happens in the hardware.

**What AURA-HFT is.** ✅ A complete tick-to-trade pipeline on FPGA (target: **AMD Kria KR260**) that ingests a NASDAQ ITCH 5.0 feed, maintains an order book in hardware, computes a microstructure signal, tracks the position of virtual orders in the queue, applies pre-trade risk controls and emits OUCH orders. It comes with a verification bench and a web dashboard.

**Goal.** ✅ A **portfolio** project. Each choice is judged on what it demonstrates to a technical reviewer.

---

## Target users

| User | What they do with AURA-HFT | What they must be able to verify |
| :--- | :--- | :--- |
| **The operator** (the author) | Launches a simulation run from the dashboard, sets risk thresholds, replays the run, inspects the book and the emitted orders | The system is correct, fast and controllable |
| **The technical reviewer** (hardware / quant hiring manager, interviewer) | Reads the README, watches the demo, browses the code and the verification and timing reports | Latency is substantiated, verification is serious, the architecture is clean |

---

## MVP features

✅ **The MVP is entirely in simulation**, with synthesis and timing targeting the KR260 device. It is delivered in **small, publishable slices** (constraint: less than 5 h/week). The first visible slice is parser + order book + verification against the reference model.

| ID | Feature | Detail |
| :--- | :--- | :--- |
| F1 | **Network ingress** | Ethernet → IPv4 → UDP → MoldUDP64; sequence gap detection |
| F2 | **ITCH 5.0 parser** | The 7 messages that modify the book: `A`, `F`, `E`, `C`, `X`, `D`, `U` (needed to stay exact over a real trading day) |
| F3 | **Hardware order book** | **A single symbol**, chosen by configuration (e.g. AAPL); active order table, price levels, best-price cache (BBO / top 5) |
| F4 | **Microstructure signal** | Imbalance (OBI) + micro-price, threshold trigger |
| F5 | **Queue position tracking** | **Virtual orders**: an order is assumed to be placed at a given instant, and the FPGA tracks the volume ahead of it (executions, cancellations of older orders). No simulated exchange |
| F6 | **Pre-trade risk** | Max quantity, price band around the BBO, max exposure, kill switch |
| F7 | **OUCH 5.0 order generation** | `O` message (Enter Order) encapsulated in UDP, emitted at the pipeline output |
| F8 | **Verification** | Python reference model; cocotb + Verilator benches; cycle-accurate latency measurement; generated reports |
| F9 | **Web dashboard** | Launches a run with its parameters (risk thresholds, kill switch, symbol), then **replays the recorded run**: order book, signal, queue, emitted and rejected orders, latency histogram |

---

## Out of scope

**Excluded from the project:**
- Connection to a real exchange, real money.
- TCP / SoupBinTCP in hardware. In production OUCH runs over TCP; here the orders leave over UDP.
- A simulated exchange that executes our orders.
- Other protocols and markets (CME MDP 3.0, FIX, Euronext).
- PCIe cards (Alveo) and GPUs.
- Any promise of profitability: the signal demonstrates the architecture, not an alpha.

**Deferred to V2:**
- Deployment on the KR260 with a real 10G feed.
- Live control from the dashboard (thresholds, kill switch during execution).
- Several symbols in parallel.
- Avellaneda-Stoikov style market making.
- Option pricing on FPGA (Monte Carlo / Heston).

---

## Success criteria

| Criterion | Measure | Target |
| :--- | :--- | :--- |
| **Parser correctness** | Messages decoded by the RTL vs the Python reference decoder, on a full NASDAQ ITCH file | 100% identical |
| **Order book correctness** | FPGA (simulated) BBO and top 5 vs the reference model, after every message of the chosen symbol, over a full day | 0 divergence |
| **Queue correctness** | Volume ahead of each virtual order vs the reference model | 0 divergence |
| **Risk** | Each rule has a test proving the rejection; the kill switch blocks all orders | 100% of tests pass |
| **Core latency** | Cycles between the arrival of the last useful byte of a message and the first byte of the emitted order; published distribution (p50 / p99 / max) | → TRD (target value and frequency) |
| **Timing** | Timing closure on the KR260 device (WNS ≥ 0), published resource report | → TRD (target frequency) |
| **Throughput** | Back-to-back packets at 10G line rate in simulation, without loss | 100% |
| **Reproducibility** | All verification runs from one command | ✅ |
| **Demonstration** | README (architecture, quantified results) + dashboard video | ✅ |
| **Publication** | Private repository until the first clean slice, then public | ✅ |

> ⚠️ **Correction of an earlier estimate.** The figure of "~40 ns at 322 MHz" assumed a 25G-class clock. The KR260 SFP+ port is **10G**, whose natural clock is **156.25 MHz** (64-bit bus, 6.4 ns per cycle). Also, "wire-to-wire" latency includes the transceivers and the MAC, which add tens of ns outside our core. The figure quoted will be that of the core, with its frequency and scope. → TRD.
