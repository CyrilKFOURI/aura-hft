# Claims register (CLAIMS)

> Every public AURA-HFT number must appear here with its evidence. Initial audit: 2026-10-20.
>
> **Statuses:**
> **Proven**: reproducible artifact in the repo ·
> **Simulated**: observed in simulation, but without a strict assertion or a reproducible environment ·
> **Unproven**: no evidence in the repo; removed or reworded ·
> **Experimental**: module tested on its own, not integrated into the reference pipeline

## Reference architecture

Reference pipeline: `rtl/top/aura_hft_top.sv`, **single clock at 156.25 MHz (6.4 ns period)**.
The dual-clock variant 156.25 ↔ 312.5 MHz (`rtl/experimental/aura_hft_dual_clock_top.sv`) is Experimental until a Vivado report shows that it closes timing.

## Cross-cutting findings (blocking for any "Proven")

- ~~The RTL benches do not run on a fresh environment.~~ Fixed: `Dockerfile` + `Makefile` + GitHub Actions CI. The benches require cocotb 2.x and Verilator ≥ 5.036.
- No Vivado report (timing, resources, power) and no bitstream in the repo.
- ~~No real market data.~~ The golden model is validated on 20 M real NASDAQ messages against MeatPy. The **RTL** replayed on that real data first diverged (insufficient book capacity), see C1.

→ After the initial audit, **no RTL number was Proven**. They became Proven through CI and real-data co-simulation; Vivado results are still pending.

## Register

| # | Claim (before audit) | Where | Status | Evidence / finding | Action |
| :-- | :-- | :-- | :-- | :-- | :-- |
| C1 | Tick-to-trade **49 cycles = 313.6 ns** → 57 (new order book) → **27 cycles = 172.8 ns** (division-free OBI + 2-stage risk) → **29 cycles = 185.6 ns** (registered memories) | README, dashboard, video | Simulated latency; order book Proven on real data | `tb_tick_to_trade_top.py` measures `last_tick_to_trade_cycles` but only asserts `< 60`; a single synthetic scenario. **On real NASDAQ data, the original RTL order book was wrong** (BBO diverged from message 1,244 to 9,408 onward, then 83 to 97% of messages) because of the 16-level / 2,048-order capacity: [report](../reports/rtl_real_cosim_01302019.md) | New full-depth order book gives **0 divergence** over 215,674 real messages (AAPL, MSFT, TSLA). Latency measured on the synthetic scenario: 57 cycles. Then OBI decision by cross-multiplication (2 cycles) instead of the 32-cycle divider, and a 2-stage pipelined risk check: **27 cycles** measured end to end (synthetic scenario). Then order-book memories with registered reads (BRAM/URAM): **29 cycles** (synthetic scenario), still 0 divergence on AAPL/MSFT/TSLA. The v1 promo video still shows 49 cycles |
| C2 | **< 280 ns** (speculative parser + 312.5 MHz core) | README | Unproven | Combination never simulated end to end; speculative parser and dual-clock not integrated into the reference top | Removed |
| C3 | Clocks 156.25 ↔ 312.5 MHz, **WNS ≥ +0.12 ns** | README (summary, badge) | Unproven | No timing report | Removed; dual-clock marked Experimental |
| C4 | Resource table (14,820 LUT, 18,340 FF, 32 BRAM, 16 DSP, **WNS +0.142 ns, TIMING MET**) | README | Unproven | No matching Vivado report in the repo | Replaced by "to be produced with Vivado". Yosys estimate (not Vivado, no timing) of the order book alone: 47,760 LUT + 16,384 LUTRAM, 20,788 FF, 376 RAMB36 (> 144 available, so URAM required), 35 DSP: [report](../reports/yosys_estimate_lob_engine.md) |
| C5 | Pre-trade risk **1 cycle (6.4 ns)** → **2 stages** | README | Simulated | Register structure observed; combinational 64-bit notional not validated for timing | Worded as "1 cycle in simulation, timing to be validated" |
| C6 | PnL circuit breaker **1 cycle**, "strict compliance with SEC 15c3-5 / MiFID II RTS 6" | README | Simulated / Unproven | Cycle count: simulated. Compliance: no regulatory review possible | "Controls inspired by 15c3-5 / RTS 6" |
| C7 | "In-silicon wire-to-wire latency tracking" | README | Unproven | No board; `latency_metrology.sv` tested in simulation only | "Simulated PTP metrology; silicon measurement still to do" |
| C8 | Cross-exchange arbitrage triggered in **3.2 ns** | README | Experimental | Module not instantiated in the reference top; 3.2 ns assumes an unproven 312.5 MHz clock | "1 cycle in simulation, experimental module" |
| C9 | UIO driver **< 50 ns** register access on Cortex-A53 | README | Unproven | No board | Removed (to be measured on hardware) |
| C10 | **37 suites, 100% passed, 0 divergence** | README, badge | Proven (2026-10-20) | Not reproducible at audit time (see findings). Actual count: 35 Python test/bench files in `sim/tests`, ~140 sim + server test functions; only 11 (golden model) verified passing on 2026-10-20. **After the Docker/CI work:** `make test` in Docker (Verilator 5.040, cocotb 2.0.1) runs 18 RTL benches + 11 golden + 7 API + 1 Python driver + the C++ driver suite, all green; 2 benches had to be fixed (packed-array access, cocotb 2 API). Synthetic stimuli only | CI badge after the first GitHub run |
| C11 | Golden model validated "on an extract of a real NASDAQ ITCH 5.0 day" | former roadmap | Proven on an extract (2026-10-20) | Before: synthetic messages only. **After:** 20 M real NASDAQ messages from 2019-01-30 (03:04 → 09:36, open included), 6 symbols, 786,626 BBO + depth checks, **0 divergence** vs MeatPy: [report](../reports/golden_vs_meatpy_01302019_first20M.md). A `U` bug (ghost order) was found and fixed | Full day still to do |
| C12 | Parser **≤ 6 cycles** | README | Simulated | Bench `tb_itch_parser.py`, environment not reproducible at audit time | Kept as "simulated" |
| C13 | Avellaneda-Stoikov "exact 3-cycle" | README | Experimental | Not instantiated in the reference top | Marked experimental |
| C14 | Speculative parser, 1 cycle | README | Experimental | Not instantiated in the reference top | Marked experimental |
| C15 | Iceberg / TWAP, MoldUDP64 resilience | README | Experimental | Not instantiated in the reference top | Marked experimental |
| C16 | FCS CRC-32 "0 cycle" cut-through | README | Simulated | 64-bit combinational logic: timing not validated | "Simulated" |
| C18 | "Robust" pipeline: gaps, duplicates, corrupted frames | none | Partially proven (2026-10-21) | `test_fault_injection.py`: 10 scenarios vs golden model, 10/10 after **4 RTL bugs fixed** (duplicates re-applied, parser stall on a truncated frame / zero-length block, 741 of 1,800 requests lost in a burst without back-pressure, non-UDP frames parsed). 5,000 real IEX HIST frames repackaging 23,123 real NASDAQ messages: 0 divergence. **FCS not checked** in `aura_hft_top` (strict xfail). Coverage: line 61% / branch 66% / toggle 32%: [report](../reports/robustness.md) | FCS + coverage ≥ 90% still to do |
| C19 | Risk: no out-of-limit order, no order under kill switch | none | Proven (2026-10-21), with abstraction | Properties P1 to P6 proved by k-induction (yosys `sat -tempinduct`, k = 3, **not** SymbiYosys) with the multiplier abstracted; 8 mutants refuted; a 64-bit overflow bug in the cumulative notional was found and fixed. Same assertions under Verilator `--assert` in 2 benches | Add to CI |
| C17 | Hard-coded defaults `313.6` / `49 cyc` in the dashboard | `client/src/components/AnalyticsView.tsx`, `Launcher.tsx` | Fixed (2026-10-21) | No default values anymore: "—" when there is no data. FPGA latency read from `GET /api/latency` (29 cycles, labeled "simulated"), CPU latencies measured from `reports/software_latency/`, provenance displayed. The demo runner no longer invents jitter (random 49 ± 1 cycles) and the AXI-Lite state no longer invents telemetry (`total_orders_approved: 128` → 0, field `telemetry_source`) | none |
| C20 | Profitability of the OBI strategy | new | Measured (2026-10-21) | Backtest on real ITCH data of 2019-01-30 (04:00 to 10:11), the RTL's Q1.31 rule, fills by FIFO priority, Nasdaq/SEC/FINRA fees: net PnL negative in all 36 threshold × horizon × latency configurations; threshold 0.4 / 10 s / 1 µs in regular session: 544 trades, −0.038 $/share, 95% CI [−2,442; −1,565] $: [report](../research/obi_backtest.md) | Claim no edge; half a day only |
| C21 | C++ reference software path: same logic as the RTL, CPU latency | new | Measured (2026-10-21) | `software/ref_pipeline` bit-exact vs the golden model on 426,961 real events (AAPL/MSFT/TSLA/QQQ, 20 M messages of 2019-01-30, 0 divergence). **Measured on the laptop** (Core Ultra 7 155H, Docker/WSL2, 1 pinned thread, message already in memory, no network): p50 126 to 189 ns, p99 0.5 to 1.6 µs, p99.9 1.6 to 8.8 µs; throughput 183 to 242 M msg/s (one tracked symbol): [report](../reports/software_vs_fpga.md) | Do not compare to 185.6 ns without stating that the FPGA figure is simulated and that the CPU figure excludes the network stack |

## Modules: integration into the reference pipeline

| Module | In `aura_hft_top.sv` | Status |
| :-- | :-- | :-- |
| FCS checker, latency metrology, ingress, LOB, quant (OBI/micro-price), AXI-Lite, PnL breaker, risk + OUCH | yes | Simulated |
| `speculative_itch_parser` | yes (via `ingress_pipeline_top`) | Simulated |
| `avellaneda_stoikov_engine` | no | Experimental |
| `cross_exchange_*` | no | Experimental |
| `iceberg_twap_engine` | no | Experimental |
| `moldudp64_resilience_engine` | no | Experimental |
| `multi_symbol_router` / `multi_ticker_pipeline_top` | separate top | Experimental |
| `aura_hft_dual_clock_top` (156.25 ↔ 312.5 MHz) | separate top | Experimental |

All Experimental modules now live in `rtl/experimental/`; `aura_hft_top` is the only reference top, and the Vivado scripts synthesize it (the bitstream script used to synthesize the experimental dual-clock top).
