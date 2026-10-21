# Courses & Resources: Imperial College London (Custom Computing Group)

## 1. Institutional context
* **University:** Imperial College London (Department of Computing)
* **Lab:** Custom Computing Research Group
* **Lead researchers:** Prof. Wayne Luk, Dr. David B. Thomas
* **Website:** https://www.imperial.ac.uk/custom-computing/
* **Paper and course archive:** https://www.doc.ic.ac.uk/~wl/papers/

## 2. Teaching themes & practical work
The research group of Wayne Luk and David Thomas is widely recognized as a pioneer in applying reconfigurable architectures (FPGA) to quantitative finance and high-frequency trading.

### Teaching areas and research material:
1. **Financial computing & reconfigurable acceleration:**
   * Design principles to minimize the area cost of transcendental math operations ($\exp, \ln, \sqrt{\cdot}, \text{erf}$).
   * Use of Chebyshev polynomial approximation and LUT-based look-up tables to evaluate cumulative normal distribution functions in 1 clock cycle.
2. **Mixed-precision arithmetic methodologies:**
   * Reducing the number of bits used in Monte Carlo simulations to double or quadruple the number of compute cores that fit on one FPGA, combined with control variate sampling techniques to correct discretization bias.
3. **Dataflow computing:**
   * Modeling synchronous dataflow (SDF) streams applied to direct processing of market ticks.
