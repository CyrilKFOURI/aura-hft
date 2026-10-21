# HFT Course Notes (Master 2 El Karoui) & FPGA Hardware Mapping

This document links the direct connections between the Econometrics and High-Frequency Trading course of the **Master 2 DEA El Karoui (Sorbonne Université / École Polytechnique)** and FPGA hardware architecture.

---

## 1. Hardware background notes

### A. HFT hardware architecture note
* **Key content:**
  * Tick-to-trade latency comparison:
    * Standard Linux stack (TCP/IP): $15\text{--}50\text{ }\mu\text{s}$ (high jitter due to interrupts and context switches).
    * Kernel bypass (DPDK / Solarflare OpenOnload in C++): $800\text{ ns}\text{--}2.5\text{ }\mu\text{s}$ (jitter due to L1/L2 cache misses and branch prediction).
    * **FPGA cut-through pipeline (10GbE / 25GbE PHY):** **$12\text{--}45\text{ ns}$** (deterministic cycle-by-cycle execution, no OS, no instructions).
  * Internal silicon blocks: LUT6, flip-flops, BRAM (dual-port $36\text{ Kb}$), DSP48, GTY/GTM SerDes (64-bit AXI-Stream at $322.265\text{ MHz}$, i.e. $1\text{ cycle} = 3.1\text{ ns}$).
  * VHDL RTL design for cut-through (on-the-fly) parsing before the FCS checksum has finished arriving.
  * Timing closure formulas (WNS, setup/hold slack) and clock domain crossing (CDC).

### B. Hardware practice in VHDL / FPGA
* **Project done:** Hardware synthesis on an **Intel MAX 10 DE10-Lite** board (Cyclone / MAX 10).
* **Core skills:** Finite state machines (Moore/Mealy FSMs), synchronous frequency dividers, pin assignment and the Quartus Prime / TimeQuest flow.

---

## 2. Analysis of the El Karoui course: Econometrics & High-Frequency Trading

* **Instructor:** Mathieu Rosenbaum (holder of the "Analytics and Models for Regulation" chair at École Polytechnique).

### A. Session breakdown and course sheets
1. **Session 1 (`HFT_slides_seance1.pdf`): Microstructure & market organization**
   * Market types (order-driven vs quote-driven).
   * Order types: limit orders (liquidity provision) vs market orders (liquidity consumption).
   * Role of the matching engine and the impact of co-locating trading servers at exchanges.
2. **Session 1.2 (`HFT_slides_seance1.2.pdf`): Optimal execution (Almgren-Chriss)**
   * Temporary market impact $\eta v_t$ vs permanent impact $\gamma (x_t - x_0)$.
   * Minimizing expected execution cost and capture variance (optimal liquidation frontier).
3. **Session 2 (`HFT_slides_seance2.pdf`): Intraday statistical properties**
   * Microstructure noise, realized volatility estimators (Garman-Klass, Parkinson).
   * Signature plots and the Epps effect (drop in measured correlation at very high frequency).
4. **Session 3 (`HFT_slides_seance3.pdf`): Order book queue dynamics**
   * **79 mentions of "order book" and 87 mentions of "queue":** this is the theoretical core for our hardware order book.
   * Markovian queue models (Cont-Stoikov-Talreja): cancellation probability vs execution probability.
   * Derivation of the fill rate as a function of the order's position in the queue (FIFO time priority).
5. **Session 4 (`HFT_slides_seance4.pdf`): Tick value theory (optimal tick size)**
   * Key distinction between "large tick" assets (the spread is almost always 1 tick, and the game is queue priority) and "small tick" assets (the spread constantly oscillates over several ticks).
   * Modeling microstructure in the high-frequency regime.
6. **Session 5 (`HFT_slides_seance5.pdf`): Point processes & Hawkes processes**
   * Self-exciting conditional stochastic intensity:
     $$\lambda_t = \mu + \int_0^t \alpha e^{-\beta(t - s)} \mathrm{d}N_s$$
   * Models the cascading arrival of limit orders and cancellations.
7. **Summary sheets (`HFT_fiche.pdf` & `econometrie_HFT_fiche2.pdf`):**
   * 45 pages of summary sheets condensing all the mathematical formulas for market impact, information asymmetry (Glosten-Milgrom, Kyle) and market making.

### B. Raw high-frequency data available in the course
The course material includes 10 tick-by-tick data files in HDF5 format (`.h5`):
* `AMAZON.h5`, `APPLE.h5`, `GOOGLE.h5` (US Nasdaq stocks)
* `LVMH.h5`, `TOTAL.h5`, `SANOFI.h5`, `BOUYGUES.h5` (Euronext stocks)
* `SONY.h5`, `PANASONIC.h5`, `CANON.h5` (TSE stocks)

This real data contains timestamps, execution prices, volumes and the state of the best book limits.

---

## 3. Mapping matrix: El Karoui theory $\longleftrightarrow$ FPGA implementation

| Theoretical concept (El Karoui - Rosenbaum) | Equation / mathematical model | FPGA hardware component (RTL / HLS) | Target silicon resource |
| :--- | :--- | :--- | :--- |
| **Best Bid & Offer (BBO)** | $P_{\text{bid}} = \max_i P_i, \quad P_{\text{ask}} = \min_j P_j$ | Combinational hardware priority / shadow registers | Flip-flops (FF) & LUTs ($1\text{ cycle}$ latency) |
| **Order Book Imbalance (OBI)** | $OBI = \frac{V_{\text{bid}} - V_{\text{ask}}}{V_{\text{bid}} + V_{\text{ask}}}$ | Fixed-point subtractor/adder + pipelined divider | DSP48E2 slices |
| **Queue position (queue depletion)** | $q(t) = q(0) - \sum \text{Exec} - \sum \text{Cancels}$ | Hardware decrementer synchronized on ITCH `'E'` and `'X'` messages | Synchronous counters in BRAM |
| **Order trigger signal** | $S_t > \theta \implies \text{Send Order}$ | Cut-through combinational comparator (`itch_order_trigger`) | Combinational LUT6 ($< 3.1\text{ ns}$) |
| **Order generation (egress)** | OUCH binary encapsulation | Parallel-to-serial shift register, AXI-Stream to PHY MAC | GTY/GTM 10GbE/25GbE SerDes |
