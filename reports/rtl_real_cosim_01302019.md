# RTL co-simulation on real NASDAQ ITCH 5.0 — `itch_lob_pipeline_top`

- Data: NASDAQ public sample 01/30/2019, first 20M messages (03:04 → 09:36 ET), SHA-256 `e24c84422e4b891bab714e89f935a82078f2bdf9e4f59cc023097bbcedee7ddb`
- Stimulus: every real message touching the symbol (adds, executions, cancels, deletes, replaces), each in its own Ethernet/IPv4/UDP/MoldUDP64 frame; Verilator 5.040 + cocotb 2.0.1
- Expected state: golden model, itself validated with 0 divergence against MeatPy on the same data ([report](golden_vs_meatpy_01302019_first20M.md))
- RTL configuration: `NUM_SETS=512`, `NUM_WAYS=4` (2,048 orders), `BOOK_DEPTH=16` price levels per side
- Compared after each message: best bid / best ask (price, shares) and top-5 depth

## Result before P4: the RTL order book was **not correct on real data**

| Symbol | Messages | First BBO divergence (msg #) | BBO divergences | Top-5 divergences | Real max levels bid / ask | Real max live orders | RTL live orders at end |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| AAPL | 125,232 | 2,930 | 122,051 (97.5 %) | 122,721 | 2,754 / 2,681 | 39,964 | 1,995 |
| MSFT | 58,888 | 9,408 | 49,160 (83.5 %) | 49,527 | 1,601 / 1,247 | 20,324 | 1,919 |
| TSLA | 31,554 | 1,244 | 30,311 (96.1 %) | 30,311 | 1,363 / 1,567 | 16,036 | 1,914 |

## Root cause

1. **Price-ladder capacity (primary).** Real books exceed 16 levels per side within the first ~100 messages (AAPL: msg 135, MSFT: 66, TSLA: 88) and reach 1,200–2,750 levels. Orders added at levels the 16-entry ladder cannot hold are lost. The book looks right while the lost levels stay deep, then the BBO goes wrong as soon as one of them becomes the best price (AAPL: msg 2,930; MSFT: 9,408; TSLA: 1,244) and never recovers.
   *Worked example (AAPL):* msg 283 adds 9 shares at $163.80 while 34 ask levels exist → not stored; at msg 1,143 that level reaches the top 5 and the RTL shows 823 shares instead of 832.
2. **Order-table capacity (secondary).** Real AAPL holds up to 39,964 live orders; the RTL table holds 2,048 and is saturated by the end of the run (1,995 entries), so later executions and cancels miss.

Neither issue appears in the synthetic benches (≤ 15 orders, ≤ 5 levels), which is why all 18 RTL benches pass.

## Consequences

- The 49-cycle / 313.6 ns tick-to-trade figure was measured on a pipeline whose book is wrong on real markets. It remains a *latency* figure for a synthetic scenario only (CLAIMS C1).
- The fix belongs to step P4 (architecture): a ladder that keeps the **best N levels exactly** with the rest of the depth in BRAM/URAM (price-indexed array around the mid, or a two-tier book), and an order table sized for ~64k live orders per symbol (URAM) with a defined, tested overflow policy.

## Reproduce

```bash
python data/fetch.py
python -m sim.validation.extract_symbol_stream data/cache/01302019.NASDAQ_ITCH50.first20000000.itch --symbol AAPL
REAL_STREAM=$PWD/data/cache/01302019.NASDAQ_ITCH50.first20000000.itch.AAPL.stream.json pytest sim/tests/test_real_data_rtl.py
```

Raw results: `reports/rtl_real_cosim_<SYMBOL>.json`.


---

## After step P4 (full-depth book) — 2026-10-20

New book architecture (`rtl/book/order_store.sv`, `rtl/book/depth_book.sv`):
- **Order table**: two-choice hashing (high multiplicative-hash bits), 2 banks × 8,192 sets × 4 ways = 65,536 orders + 16-entry stash, O(1) reset by epoch. The old table also hashed on the *low* product bits, which spread real order references badly.
- **Depth**: price-indexed shares array, 65,536 ticks of $0.01 per side ($0–$655.35), three-level occupancy bitmap, **exact top-5 recomputed after every update**. Off-window / sub-penny orders (stub quotes) are tracked but excluded from the price book.

Same data, same bench, same comparison:

| Symbol | Messages | BBO divergences | Top-5 divergences | Real max levels bid / ask | Real max live orders | RTL live orders at end |
| :-- | --: | --: | --: | --: | --: | --: |
| AAPL | 125,232 | **0** | **0** | 2,754 / 2,681 | 39,964 | 39,960 |
| MSFT | 58,888 | **0** | **0** | 1,601 / 1,247 | 20,324 | 19,143 |
| TSLA | 31,554 | **0** | **0** | 1,363 / 1,567 | 16,036 | 15,950 |

**Result: 0 divergence on 215,674 real messages across 3 symbols.**

Cost: tick-to-trade in the synthetic end-to-end scenario goes from 49 to **57 cycles** (364.8 ns at 156.25 MHz); the book stage now takes 1–2 cycles per price update plus 1 cycle per extracted level. Timing closure and memory mapping (≈ 13 Mb, URAM-sized) are not yet verified: step P5.
