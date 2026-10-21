# Vitis Quantitative Finance Library (AMD / Xilinx)

## 1. General information
* **Repository:** `Xilinx/Vitis_Libraries` (subfolder `quantitative_finance`)
* **GitHub URL:** https://github.com/Xilinx/Vitis_Libraries/tree/master/quantitative_finance
* **Official documentation:** https://xilinx.github.io/Vitis_Libraries/quantitative_finance/
* **Author / organization:** AMD AECG (Xilinx)
* **License:** Apache 2.0
* **Languages:** C++ HLS (high-level synthesis for Vivado/Vitis HLS), OpenCL / XRT (Xilinx Runtime)
* **Target architectures:** AMD Alveo U50, U200, U250, U280

## 2. Library organization in three levels (L1, L2, L3)

### Layer L1: Hardware arithmetic & statistical primitives
* **Random number generators (RNG):**
  * Mersenne Twister (MT19937) pseudo-random generator optimized for FPGA.
  * Sobol quasi-random (low-discrepancy) sequence generator.
  * Box-Muller transform and inverse cumulative normal approximation to generate Gaussian $\mathcal{N}(0, 1)$ samples at very high throughput (1 sample per cycle).
* **Numerical solvers:**
  * Pipelined tridiagonal and pentadiagonal matrix solvers (used by the Crank-Nicolson and Douglas-Rachford schemes).
  * Fixed-point (`ap_fixed`) and floating-point (`float`, `double`) arithmetic optimized for DSP slice usage.

### Layer L2: Compute engines & financial models
* **Monte Carlo pricing engines:**
  * Classic Black-Scholes-Merton model.
  * **Heston** stochastic volatility model (joint simulation of the asset price $S_t$ and its instantaneous variance $v_t$).
  * Hull-White and BGM (Brace-Gatarek-Musiela) models for interest rates.
* **Partial differential equation (PDE) solvers:**
  * 1D and 2D finite difference solvers for pricing American and barrier options.
* **Binomial & trinomial trees:**
  * Cox-Ross-Rubinstein (CRR) model, fully parallelized on FPGA.

### Layer L3: Software APIs & application deployment
* C++ and Python wrappers that let a quantitative analyst call the hardware accelerators like ordinary software functions (`priceOption()`), automatically handling OpenCL compilation, PCIe buffer allocation and data synchronization.

## 3. Relevance for quantitative computing
* This is the reference repository for any **option pricing**, **Greeks** (Delta, Gamma, Vega) or **VaR (Value at Risk)** implementation on FPGA.
* The C++ HLS source shows exactly how to structure hardware loops with the `#pragma HLS PIPELINE II=1` and `#pragma HLS UNROLL` pragmas to reach maximum throughput.

## 4. Cloning
```bash
git clone --depth 1 https://github.com/Xilinx/Vitis_Libraries.git
cd Vitis_Libraries/quantitative_finance
```
