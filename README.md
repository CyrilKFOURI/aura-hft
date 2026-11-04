# AURA-HFT — FPGA tick-to-trade pipeline, verified on real NASDAQ data

> A SystemVerilog tick-to-trade pipeline for the **AMD Kria KR260**: NASDAQ ITCH 5.0 over MoldUDP64 → full-depth hardware order book (exact top 5) → division-free order-book-imbalance signal → formally verified pre-trade risk → NASDAQ OUCH 5.0 orders.
>
> **Status (2026-10-21): cycle-accurate simulation.** No board yet and no Vivado timing report. Every number below links to its evidence; the full registry is [docs/CLAIMS.md](docs/CLAIMS.md).

[![Language: SystemVerilog](https://img.shields.io/badge/Language-SystemVerilog%20IEEE%201800--2017-blue.svg)](#)
[![Target: AMD Kria KR260](https://img.shields.io/badge/Target-AMD%20Kria%20KR260%20(xck26)-purple.svg)](#)
[![Clock: 156.25 MHz](https://img.shields.io/badge/Clock-156.25%20MHz%20(reference)-emerald.svg)](#)
[![Verification: Verilator 5.040 + cocotb 2.0.1](https://img.shields.io/badge/Verification-Verilator%205.040%20%7C%20cocotb%202.0.1-orange.svg)](#)
[![Status: simulation only](https://img.shields.io/badge/Status-simulation%20only-lightgrey.svg)](docs/CLAIMS.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What is proven, and how

| Claim | Evidence | Status |
| :-- | :-- | :-- |
| **The RTL order book is exact on real markets**: 0 divergence in best bid/ask and top-5 depth on **215,674 real NASDAQ messages** (AAPL, MSFT, TSLA, 01/30/2019, 04:00–09:36 ET including the opening cross) | [reports/rtl_real_cosim_01302019.md](reports/rtl_real_cosim_01302019.md) | ✅ simulated, real data |
| **The reference model is right**: golden model vs the independent MeatPy library, 20 M real messages, 6 symbols, 786,626 checks, 0 divergence; the comparison itself is mutation-tested | [reports/golden_vs_meatpy_01302019_first20M.md](reports/golden_vs_meatpy_01302019_first20M.md) | ✅ |
| **Real network framing**: 5,000 real IEX HIST Ethernet/IPv4/UDP frames re-wrapping 23,123 real NASDAQ messages, 0 divergence | [reports/robustness_p3b.md](reports/robustness_p3b.md) | ✅ simulated |
| **Fault tolerance**: 10 fault scenarios vs golden model (gaps, duplicates, truncated frames, unknown refs, non-UDP frames, 1,800-message bursts), all pass after 4 RTL bugs were found and fixed | [reports/robustness_p3b.md](reports/robustness_p3b.md) | ✅ (FCS check still missing, see limits) |
| **Risk can never let a forbidden order out**: 6 properties (kill switch, max shares, price collar, max notional, saturating cumulative notional, exclusive strobes) **proved unbounded** by k-induction; 8 mutants refuted; found a 64-bit wrap bug | [docs/CLAIMS.md C19](docs/CLAIMS.md), `rtl/assertions/`, `formal/` | ✅ proved, multiplier abstracted |
| **Tick-to-trade: 29 cycles = 185.6 ns at 156.25 MHz** (end-to-end, synthetic scenario) | `sim/tests/tb_tick_to_trade_top.py` | 🟡 simulated, timing closure unproven |
| **Software reference path** (C++20) bit-exact with the golden model on 426,961 real events; CPU p50 126–189 ns, p99.9 1.6–8.8 µs on a laptop core (no network stack) | [reports/software_vs_fpga.md](reports/software_vs_fpga.md) | ✅ measured |
| **The OBI strategy has no edge after costs**: negative net PnL in all 36 configurations on real data, with confidence intervals | [research/obi_backtest.md](research/obi_backtest.md) | ✅ measured (negative result) |
| Resources (Yosys estimate of the book only, not Vivado): 47.8 k LUT, 20.8 k FF, 35 DSP, **376 BRAM36 > 144 available** → UltraRAM mapping required | [reports/yosys_estimate_lob_engine.md](reports/yosys_estimate_lob_engine.md) | ⏳ Vivado (P5b) |

**Not claimed:** silicon measurements, timing closure, Fmax, a profitable strategy, regulatory compliance. Controls are *inspired by* SEC 15c3-5 / MiFID II RTS 6.

---

## Architecture (reference top: `rtl/top/aura_hft_top.sv`, single 156.25 MHz clock)

```
 10GbE frame ─► MoldUDP64 depacketizer ─► speculative ITCH 5.0 parser ─► 64-entry request FIFO (back-pressure)
   (FCS checker,   (gap / duplicate /       (all order types, frame-          │
    PTP timestamp)  non-UDP drop)           boundary safe)                    ▼
                                                              order_store: 2-choice hash, 2×8192×4 + stash,
                                                              O(1) epoch reset, registered BRAM reads
                                                                              │
                                                                              ▼
                                                              depth_book: 65,536 penny ticks/side, 3-level
                                                              occupancy bitmap, exact top-5 after every update
                                                                              │
                                     top-of-book ◄────────────────────────────┘
                                          │
                     obi_signal: OBI ≥ T ⇔ (Vb−Va)·2³¹ ≥ T·(Vb+Va)   (2 cycles, no divider)
                                          │
                     pre_trade_risk: 2 stages (DSP product, then limits) — formally proved
                                          │
                     OUCH 5.0 Enter Order ─► AXI4-Stream egress, latency metrology
```

Design rationale for every block: [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md).

Experimental modules (tested standalone, **not** in the reference top) live in `rtl/experimental/`: dual-clock 156.25/312.5 MHz top, Avellaneda-Stoikov, cross-exchange arbitrage, Iceberg/TWAP, MoldUDP64 recovery, multi-ticker top, and the legacy 16-level ladder.

---

## Reproduce

```bash
# 1. Full verification in Docker (Ubuntu 24.04 + Verilator 5.040 + cocotb 2.0.1; ~15 min first build)
docker build -t aura-hft-ci .
docker run --rm -v "$PWD":/work aura-hft-ci make lint typecheck test

# 2. Real NASDAQ data (streams ~250 MB from NASDAQ's public sample server; data is never committed)
make fetch-data validate-real          # golden model vs MeatPy
python -m sim.validation.extract_symbol_stream data/cache/01302019.NASDAQ_ITCH50.first20000000.itch --symbol AAPL
REAL_STREAM=$PWD/data/cache/01302019.NASDAQ_ITCH50.first20000000.itch.AAPL.stream.json \
  pytest sim/tests/test_real_data_rtl.py   # RTL vs golden, message by message

# 3. Formal proof of the risk properties
make docker-formal

# 4. Software path, backtest, dashboard
make -C software/ref_pipeline test
python -m research.obi_backtest
python -m uvicorn server.main:app & npm run dev --prefix client
```

CI (`.github/workflows/ci.yml`) runs lint, typecheck, all simulations and the dashboard build on every push.

---

## What went wrong, and what it taught

This repository started with impressive but unproven numbers. Replaying real NASDAQ data exposed the gap:

1. **The original order book was wrong on real markets** (83–97 % of messages diverged): 16 price levels and 2,048 orders against up to 2,754 levels and 39,964 live orders for AAPL. It was redesigned around measured sizing (P4).
2. **The original hash spread real order references badly** (it used the low bits of a multiplicative hash).
3. **Five robustness bugs** (duplicate frames re-applied, parser hang on truncated frames, silent FIFO loss in bursts, non-UDP frames parsed, 64-bit notional wrap) were found by fault injection and formal proof (P3b).
4. **The trading signal loses money after costs** (P8). The hardware is a correct, fast execution engine; it is not an alpha.

The step-by-step remediation is in [docs/PRO_REMEDIATION_PLAN.md](docs/PRO_REMEDIATION_PLAN.md) and [PLAN.md](PLAN.md).

---

## Known limits and next steps

- **P5b — Vivado (needs the tool):** map `order_store` / `depth_book` to UltraRAM, close timing at 156.25 MHz, commit timing/utilization reports, add the AMD 10G MAC and a store-and-forward FCS drop (today a corrupted frame reaches the book: `test_fcs_top.py` is a strict xfail).
- **P7 — KR260 board:** hardware-in-the-loop replay of the same pcaps, silicon latency with PTP timestamps.
- Coverage of the fault bench: 61 % lines / 66 % branches (target 90 %).
- The strategy has no position or exit logic and sends one order per book update while the signal holds (see P8).
- One trading day of data (pre-market + first ~40 minutes of the session).

---

## Repository layout

```
rtl/            reference pipeline (ingress, parser, book, quant, risk, egress, control, metrology, top)
rtl/experimental/  standalone experimental modules
rtl/assertions/ SVA properties + bind files          formal/  k-induction proof flow
sim/            golden model, validation scripts, cocotb benches (synthetic, fault, real-data)
software/       C++20 reference pipeline + latency benchmark
research/       OBI backtest on real data
server/ client/ FastAPI backend (replay, live public crypto feed, paper only) + React dashboard
driver/         C++20 Linux UIO driver (host-tested; no board yet)
data/           fetch scripts (NASDAQ ITCH, IEX HIST); downloaded data is gitignored
reports/        every measured result referenced above
docs/           CLAIMS registry, design decisions, interview notes, per-feature specs
video/          Blender scripts for the 3D explainer video
```
