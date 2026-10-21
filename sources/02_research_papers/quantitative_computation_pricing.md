# Academic Literature: Quantitative Computation & Pricing on FPGA

This document reviews the main research papers on accelerating complex financial algorithms: highly parallel Monte Carlo simulation, stochastic volatility models (Heston) and partial differential equation (PDE) solving.

---

## 1. "FPGA Acceleration of Monte Carlo Simulation" & "Massively Parallel Monte Carlo"
* **Authors:** David B. Thomas, Wayne Luk
* **Affiliation:** Imperial College London (Custom Computing Group)
* **Journal:** *IEEE Transactions on Computers / IEEE FCCM*

### Architectural contributions & technical details:
1. **High-performance random number generators (RNG):**
   * Analysis of the impact of Gaussian noise generation algorithms on FPGA. Compares the Box-Muller transform (which needs trigonometric $\sin/\cos$ and $\ln$ functions) with the Wallace generator and piecewise polynomial inversion.
   * Shows that a dedicated hardware pipeline can generate **one Gaussian random number per clock cycle** on each DSP/LUT slice.
2. **Dedicated arithmetic pipelines:**
   * Unlike CPUs, which accumulate sequentially, an FPGA can build deep adder trees that compute the mean and variance of samples in fixed point with no memory overhead.

---

## 2. "An Energy-Efficient FPGA-Based Accelerator for Option Pricing in the Heston Model" & "HyPER Framework"
* **Authors:** Christian de Schryver, Norbert Wehn, Ivan Shcherbakov, Ralf Korn
* **Affiliation:** Microelectronic Systems Design Research Group, RPTU Kaiserslautern
* **Journal / conferences:** *ACM Transactions on Reconfigurable Technology and Systems (TRETS) / IEEE ReConFig / Springer (2015)*

### Architectural contributions & technical details:
1. **Hardware discretization of the Heston model:**
   * The Heston model couples two stochastic differential equations (SDEs) with Brownian correlation $\rho$:
     $$\mathrm{d}S_t = \mu S_t \mathrm{d}t + \sqrt{v_t} S_t \mathrm{d}W_t^S$$
     $$\mathrm{d}v_t = \kappa(\theta - v_t)\mathrm{d}t + \xi \sqrt{v_t} \mathrm{d}W_t^v$$
   * The main challenge is keeping the variance $v_t$ non-negative. The authors implement the **full truncation** method on the Euler-Maruyama scheme in hardware, which eliminates square roots of negative numbers without slowing the pipeline.
2. **Energy efficiency and precision trade-offs:**
   * Analysis of the impact of custom arithmetic (24-bit fixed point vs 32-bit vs IEEE-754 floating point).
   * The FPGA accelerator outperforms an equivalent high-end GPU on **simulated paths per watt (performance/watt)** by a factor of at least 4 to 10.

---

## 3. "Accelerating the Heston Model on FPGAs using High-Level Synthesis"
* **Authors:** Stephen Weston, Oliver Pell, Tobias Becker
* **Conference:** *IEEE Workshop on High Performance Computational Finance (WHPCF)*

### Architectural contributions & technical details:
1. **From RTL to HLS (high-level synthesis):**
   * Demonstrates that complex financial algorithms can be developed in C/C++ HLS without significant efficiency loss compared with hand-written VHDL/Verilog.
2. **Loop optimization & unrolling:**
   * Uses pipelining directives to reach an initiation interval ($II = 1$), ensuring a new price path simulation starts every clock cycle.
