# Design decisions — AURA-HFT

Each decision states the problem, the options considered, the choice, and the evidence. Numbers come from `reports/` and [CLAIMS.md](CLAIMS.md).

## 1. Single 156.25 MHz reference clock

- **Problem:** the original README advertised a 312.5 MHz core with a 156.25 MHz network domain, with no timing report behind either.
- **Choice:** one 156.25 MHz domain (the 10GbE MAC clock, 6.4 ns) for the reference top. The dual-clock top is kept in `rtl/experimental/`.
- **Why:** removes a CDC (FIFO latency + verification risk) until Vivado proves the core can close at 312.5 MHz. Latency claims are expressed in cycles, so they convert directly if the clock changes.

## 2. Order table: two-choice hashing + stash, sized on real data

- **Problem:** real AAPL holds up to **39,964 live orders** (01/30/2019, 09:36). The original table held 2,048 and hashed on the *low* product bits, which spread real (sequential) order references badly.
- **Options measured on the real stream** (max stash entries needed):
  - 1 hash, 16,384 × 8 (131k slots), low bits: 190 · high bits: 6
  - 2-choice, 2 × 8,192 × 4 (65,536 slots), high bits: **6**
  - 2-choice, 2 × 8,192 × 8: 0
- **Choice:** 2-choice, 2 banks × 8,192 sets × 4 ways + 16-entry stash. Half the memory of the 8-way option for a stash that is still 2.5× oversized. Overflow is counted (`table_full`), never silent.
- **Reset:** an 8-bit epoch per entry makes the whole table empty in one cycle instead of a 65,536-cycle scrub.
- **Memory:** each bank is a set-indexed word of 4 ways (552 bits) with registered reads, so it maps to block RAM / UltraRAM.

## 3. Full-depth book: price-indexed array + 3-level bitmap

- **Problem:** real books reach **2,754 levels per side**; the original 16-entry sorted ladder silently dropped deep levels, which later surfaced as wrong best prices (first divergence after 1,244–9,408 messages).
- **Options:** larger sorted ladder (still wrong when a deep level surfaces); price-indexed array (exact, needs fast "next non-empty level").
- **Choice:** 65,536 penny ticks per side ($0–$655.35 above a configurable base). A 65,536 / 2,048 / 64-bit occupancy hierarchy finds the next non-empty level in a bounded number of steps; the top 5 are recomputed after every update (1 cycle per level).
- **Out-of-window orders** (stub quotes at $0.0001 or $199,999.99, sub-penny prices) are tracked in the order table but excluded from the price book. Measured: the real top 5 of AAPL/MSFT/TSLA always stayed within $1.01–$369.00.
- **No divider:** tick = `(off × ⌈2³⁹/100⌉) >> 39` with an exact remainder check, valid for every 32-bit offset.
- **Cost:** tick-to-trade went from 49 to 57 cycles for exactness; later recovered (decision 4).

## 4. Division-free OBI decision

- **Problem:** a 32-stage divider computed OBI = (Vb−Va)/(Vb+Va) only to compare it with two thresholds; it was 65 % of the pipeline latency.
- **Choice:** OBI ≥ T ⇔ (Vb−Va)·2³¹ ≥ T·(Vb+Va) (denominator > 0): one signed multiply per threshold, 2 cycles. The exact value is still produced off the critical path for telemetry.
- **Result:** 57 → 27 cycles end to end; the comparison is exact (the old truncated quotient could differ by one LSB at the threshold).

## 5. Two-stage pre-trade risk, formally proved

- **Problem:** a combinational 64-bit notional product + compares + cumulative add in one cycle is unlikely to close timing.
- **Choice:** stage A registers the DSP product alone, stage B compares and updates the cumulative notional; both the accumulator and its check live in stage B, so back-to-back orders still see every earlier approval. The kill switch is checked at both stages.
- **Verification:** 6 safety properties proved unbounded by k-induction (yosys `sat -tempinduct`, k = 3) with the multiplier as a cut point; 8 mutants refuted. The proof found a real bug: the cumulative sum could wrap at 2⁶⁴ and approve an order — now a 65-bit compare with saturation.

## 6. Back-pressure instead of silent drops

- **Problem:** the multi-cycle book can absorb fewer messages per cycle than the parser produces inside one packet; a 1,800-message burst lost 741 requests.
- **Choice:** the 64-entry request FIFO raises `req_almost_full` at 56, which stalls the ingress all the way back to `s_axis_tready`. Measured sustained rate: 0.117 msg/cycle ≈ 18.3 M msg/s at 156.25 MHz; NASDAQ's measured peak in the data is 470,553 msg/s.

## 7. Verification strategy: three independent references

1. **MeatPy** (independent academic library) validates the Python golden model on real data.
2. The **golden model** validates the RTL message by message on real data, plus synthetic and fault benches.
3. A **C++20 software path** re-implements the same logic and matches the golden model bit for bit, giving a CPU latency baseline.

Each comparison is itself tested (a deliberately injected bug must be detected).

## 8. Honesty rules

- No number in the README without a file in `reports/` or a test.
- Simulated ≠ measured: cycle counts are simulated; CPU latencies are measured on a laptop; nothing is measured on silicon.
- Negative results are published (the OBI strategy loses money after costs).
