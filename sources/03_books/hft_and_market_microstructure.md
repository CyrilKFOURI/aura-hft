# Reference Books: HFT & Market Microstructure

This selection gathers the foundational books for understanding the mechanics of electronic exchanges, order book structure and ultra-low-latency systems engineering.

---

## 1. Trades, Quotes and Prices: Financial Markets Under the Microscope
* **Authors:** Jean-Philippe Bouchaud, Julius Bonart, Jonathan Donier, Martin Gould
* **Publisher:** Cambridge University Press (2018)
* **ISBN:** 978-1107164994
* **Keywords:** Limit Order Book (LOB), Market Microstructure, Order Flow, Price Formation.

### Key chapters and concepts for the hardware project:
* **Chapter 1: The Mechanics of Trading:**
  * Rigorous description of order types (limit orders, market orders, cancellations) and the time-priority mechanism (FIFO, price/time priority).
  * Essential for coding the order book transition state machine in RTL.
* **Chapter 2: The Order Book:**
  * Mathematical definition of best bid, best offer, spread, and the liquidity density function in depth.
  * Formulas for the order book imbalance ($OBI$), the basic directional predictor in hardware:
    $$OBI = \frac{V_{bid} - V_{ask}}{V_{bid} + V_{ask}}$$
* **Chapter 4: Market Impact and the Dynamics of Liquidity:**
  * Understanding how a massive stream of cancels/deletes consumes the FPGA's compute bandwidth.

---

## 2. Algorithmic and High-Frequency Trading
* **Authors:** Álvaro Cartea, Sebastian Jaimungal, José Penalva
* **Publisher:** Cambridge University Press (2015)
* **ISBN:** 978-1107091146
* **Keywords:** Stochastic Control, Market Making, Limit Order Execution, Optimal Liquidation.

### Key chapters and concepts for the hardware project:
* **Chapter 2: Market Microstructure and Mechanics:**
  * Architecture of electronic exchanges, market fragmentation and smart order routing.
* **Chapters 6 to 8: Optimal Liquidation & Market Making:**
  * Avellaneda-Stoikov model for automated market making.
  * Derivation of analytical formulas for the optimal quoting spreads $(\delta^a, \delta^b)$ as a function of risk aversion $\gamma$ and inventory $q$:
    $$s(q) = r(q) + \frac{1}{\gamma} \ln\left(1 + \frac{\gamma}{\kappa}\right)$$
  * These simplified equations can be synthesized directly on FPGA in fixed-point arithmetic to make sub-microsecond order decisions.

---

## 3. Building Low Latency Applications with C++
* **Author:** Sourav Ghosh
* **Publisher:** Packt Publishing (2023)
* **ISBN:** 978-1837639359
* **Keywords:** Kernel Bypass, Memory Hierarchy, Lock-free, Cache-Friendly Data Structures.

### Key chapters and concepts for hardware/software integration:
* **Chapter 4: High-Performance Network Communication:**
  * Use of Solarflare Onload, DPDK and zero-copy mechanisms.
  * Understanding the shared ring buffer message-passing architecture (SPSC, single producer single consumer), the same structure as the one implemented between the FPGA DMA driver and the host application.
* **Chapter 8: Building an Exchange-Facing Matching Engine & Order Book:**
  * Reference software implementation of an L3 order book. This code serves as the golden model to check the behavior of the RTL testbench in simulation.
