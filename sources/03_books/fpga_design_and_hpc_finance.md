# Reference Books: High-Performance FPGA Design & Numerical Finance

This selection covers advanced hardware design, timing closure, silicon resource optimization (LUT, BRAM, DSP) and financial computing architectures on FPGA.

---

## 1. FPGA Based Accelerators for Financial Applications
* **Main authors:** Christian de Schryver, Norbert Wehn et al.
* **Publisher:** Springer (2015)
* **ISBN:** 978-3319154077
* **Keywords:** High-Performance Financial Computing, Option Pricing, Monte Carlo, Finite Differences, Heston Model.

### Key concepts and chapters:
* **Part I: Financial Models and Numerical Methods:**
  * Mathematical foundations of stochastic volatility models and the Black-Scholes equations.
* **Part II: Reconfigurable Architectures & Implementation:**
  * Translating differential equations into clock-synchronized compute schemes.
  * Compute architectures for binomial/trinomial trees and finite difference solvers (Crank-Nicolson) for American options.
  * Fixed-point vs floating-point trade-offs: how to size the mantissa and exponent to preserve financial accuracy without blowing up DSP usage.
* **Part III: HyPER Framework & CPU/FPGA Co-Design:**
  * Methodology for very high-bandwidth PCIe interconnection between host servers and accelerator cards.

---

## 2. Advanced FPGA Design: Architecture, Implementation, and Optimization
* **Author:** Steve Kilts
* **Publisher:** Wiley-IEEE Press (2007)
* **ISBN:** 978-0470054369
* **Keywords:** High-Speed Design, Pipelining, Clock Domain Crossing (CDC), Timing Closure.

### Key concepts and chapters:
* **Chapter 2: High-Speed Architecture:**
  * Advanced pipelining techniques: splitting deep combinational arithmetic into several register stages.
  * Interleaving computations to exploit memory latency without stalling throughput.
* **Chapter 3: Area Optimization:**
  * Sharing arithmetic resources (DSP slices) to minimize die area.
* **Chapter 6: Clock Domains (CDC):**
  * Multi-stage synchronizers and Gray-code asynchronous FIFOs for safely passing signals between the network clock (e.g. 156.25 MHz) and the system clock (e.g. 250 MHz / 322 MHz) without metastability.
* **Chapter 8: Synthesizing for Maximum Frequency:**
  * Golden rules for timing closure: XDC constraints, propagation delay balancing, constrained placement (floorplanning).

---

## 3. High-Performance Computing Using FPGAs
* **Editors:** Wim Vanderbauwhede, Khaled Benkrid
* **Publisher:** Springer (2013)
* **ISBN:** 978-1461447900
* **Keywords:** Reconfigurable HPC, High-Level Synthesis, Parallel Architectures.

### Key concepts and chapters:
* **Finance & stochastic computing section:**
  * Modeling and hardware implementation of multidimensional quasi-random number generators.
  * Managing external memory bandwidth (DDR4 / HBM2): burst transfer techniques to saturate AXI4 memory controllers.
