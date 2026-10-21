# Reference software path vs FPGA

> **Read this before any figure.** The CPU latencies are **measured** on the development laptop (Intel Core Ultra 7 155H, HP Spectre x360 16", Docker on WSL2, 1 pinned thread). The FPGA latency is a **count of simulated cycles** (Verilator) at 156.25 MHz, not a measurement on a board. The two scopes are not identical (see "What the comparison does not say").

Date: 2026-10-21 · Data: NASDAQ TotalView-ITCH 5.0, public sample of 2019-01-30, first 20,000,000 messages (04:00 -> ~10:11).

## 1. What was built

`software/ref_pipeline/`: a C++20 program (g++ 13, `-O3 -march=native`), dependency-free, that replays a raw ITCH file (2-byte length prefix) with the same logic as the RTL reference path:

| Stage | RTL | C++ |
| :-- | :-- | :-- |
| ITCH 5.0 A/F/E/C/X/D/U parse + `R` directory | `itch_parser_fsm.sv` | `Pipeline::on_message` (filter on *stock locate*) |
| Full-depth book, exact top 5 | `depth_book.sv` | `std::map` per side + `unordered_map` of orders |
| Division-free OBI signal, Q1.31 | `obi_signal.sv`: (Vb-Va)·2³¹ ≥ T·(Vb+Va) | `obi_signal()` in 128-bit integers (exact) |
| Order intent | `risk_ouch_top.sv`: buy takes priority, at the bid; sell at the ask; 100 shares | identical |
| Pre-trade risk | `pre_trade_risk.sv`: kill switch, circuit breaker, size, collar, notional, **65-bit saturating** cumulative | `PreTradeRisk` (same priority order, same saturation) |

Accepted difference: the RTL holds back an intent while the OUCH transmitter is busy (`tx_busy`, ~12 cycles); the software path has no serializer and evaluates every book update.

## 2. Bit-exact validation against the golden model

`software/ref_pipeline/validate.py` compares, event by event, the C++ trace with an independent Python pipeline (`sim/golden_model` book, rule and risk from `research/obi_backtest/model.py`): timestamp, type, 5 levels × 2 sides (price, quantity), signal bits, decision, rejection reason, cumulative notional.

Configuration: thresholds ±0.40 (Q1.31 = ±858,993,459), 100 shares, max 1,000 shares, collar $0.50, max notional $50,000, **max cumulative $2M** (reached on real data, so exercised).

| Symbol | Book events | Intents | Approved | Cumulative rejects | Divergences |
| :-- | --: | --: | --: | --: | --: |
| AAPL | 125,232 | 72,134 | 123 | 72,011 | **0** |
| MSFT | 58,888 | 25,445 | 189 | 25,256 | **0** |
| TSLA | 31,554 | 16,832 | 67 | 16,765 | **0** |
| QQQ | 210,287 | 92,649 | 123 | 92,526 | **0** |

Total: **426,961 events, 0 divergence**. The corner cases the data does not reach (collar, 64-bit overflow of the cumulative, exact thresholds, extreme 32-bit values) are covered by `tests/test_ref_pipeline.cpp`.

## 3. Measured CPU latency

Method: file loaded in memory, one warm-up pass, then `std::chrono::steady_clock::now()` around each message that modifies the tracked symbol's book (parse + book + OBI + risk). Pinned thread (`sched_setaffinity`, CPU 2). Cost of two consecutive clock calls: 19-20 ns (included in the figures, not subtracted). Log-linear HDR histogram (16 sub-bins per power of 2, relative error < 6.25 %); exact percentiles computed on the sorted sample.

| Symbol | Events | p50 | p99 | p99.9 | mean | max |
| :-- | --: | --: | --: | --: | --: | --: |
| AAPL | 125,232 | 180 ns | 1,056 ns | 3,502 ns | 234 ns | 1.09 ms |
| MSFT | 58,888 | 176 ns | 1,308 ns | 3,244 ns | 225 ns | 149 µs |
| TSLA | 31,554 | 189 ns | 1,609 ns | 8,784 ns | 278 ns | 130 µs |
| QQQ | 210,287 | 126 ns | 524 ns | 1,631 ns | 164 ns | 185 µs |

Distribution (grouped HDR histogram):

| Symbol | < 100 ns | 100-200 ns | 200-500 ns | 0.5-1 µs | 1-5 µs | > 5 µs |
| :-- | --: | --: | --: | --: | --: | --: |
| AAPL | 14.6 % | 49.5 % | 32.0 % | 3.0 % | 1.0 % | 0.07 % |
| MSFT | 25.2 % | 40.0 % | 28.6 % | 4.4 % | 1.8 % | 0.04 % |
| TSLA | 16.5 % | 41.3 % | 35.0 % | 4.8 % | 2.3 % | 0.16 % |
| QQQ | 24.0 % | 52.6 % | 22.3 % | 0.9 % | 0.2 % | 0.02 % |

Throughput (no per-message timer, best of 2 warm passes): **183 to 242 M messages/s** over the whole stream, with a single tracked symbol (messages for other symbols are discarded after reading the *stock locate*, which dominates this figure).

Raw data: `reports/software_latency/<SYMBOL>.json` (served by `GET /api/latency`).

## 4. Against the FPGA (simulated)

| | FPGA (`aura_hft_top`) | CPU (this laptop) |
| :-- | :-- | :-- |
| Nature of the figure | **simulated** (Verilator, synthetic scenario) | **measured** (real NASDAQ data) |
| Latency | 29 cycles = **185.6 ns**, deterministic | p50 126-189 ns, p99 0.5-1.6 µs, p99.9 1.6-8.8 µs |
| Jitter | 0 cycles in simulation (no silicon measurement) | long tail: max 130 µs - 1.1 ms (preemption, WSL2) |
| Scope | input AXI-Stream -> output OUCH frame | message already in memory -> risk decision |

Honest reading: at the median, the software core is of the same order as the simulated FPGA, **because the measured software path excludes the whole network**. The advantage the FPGA can claim here is the **tail** (p99.9 and max) and determinism, not the median.

## 5. What the comparison does not say

- CPU side: no network card, no kernel/UDP stack, no copy to user space, no OUCH serialization, no send. A real CPU system typically adds several µs (or ~1-2 µs with kernel bypass); **not measured here**.
- FPGA side: 10GbE MAC/PCS and SFP+ are out of scope, and there is no on-board figure. The 29 cycles come from a synthetic scenario.
- A single laptop, under Docker/WSL2, with no core isolation or governor tuning: the CPU tail is pessimistic compared with a dedicated server.
- The C++ book (`std::map`) is not optimized (no per-price array, no dedicated allocator).

## 6. Live crypto feed (Python software path)

`server/live/` subscribes to a public L2 feed without authentication (Coinbase Exchange `level2_batch` BTC-USD by default, or Binance `btcusdt@depth20@100ms`), normalizes it into an internal book, applies the same Q1.31 OBI rule (sizes converted to integer units of 10⁻⁸) and pushes the result to the dashboard through `/ws/live`. **Paper only: no order is sent.** The WebSocket client is written on the standard library (asyncio + ssl); no dependency was added.

Trial of 2026-10-21, 30 s per feed, from this laptop (Python 3.12 on Windows, normalization + book + OBI time, `time.perf_counter_ns`):

| Feed | Updates | p50 | p99 | p99.9 |
| :-- | --: | --: | --: | --: |
| Coinbase BTC-USD level2_batch | 461 | 116 µs | 1.1 ms | 63 ms (initial snapshot) |
| Binance BTCUSDT depth20@100ms | 287 | 128 µs | 283 µs | 298 µs |

This Python path is ~1,000× slower than the C++ one: it serves the live demo, not the latency comparison. The "24 h without a crash" stability target **has not been tested**.

## Reproduce

```sh
# image aura-hft-ci, from the repo root, ITCH file in data/cache/
sh software/ref_pipeline/run_bench.sh data/cache/01302019.NASDAQ_ITCH50.first20000000.itch 20000000 AAPL MSFT TSLA QQQ
```
